import asyncio
from fastapi import (
    APIRouter, UploadFile, File, Form, HTTPException,
    Depends, Request, WebSocket, WebSocketDisconnect, Query
)
from fastapi.responses import JSONResponse, PlainTextResponse
import srt
import logging
from typing import Literal, Dict, Any
from datetime import timedelta
import numpy as np

# 導入流式處理類和非流式函數
from ...services.stt_service import (
    transcribe_audio_file,
    AudioTranscriptionStreamer,
)
# --- 導入翻譯服務 ---
from ...services import summary_service # 現在包含翻譯函數
from ...core.config import settings

router = APIRouter(
    prefix="/v1/audio", # 路由前綴
    tags=["Audio"],     # API 文件中的標籤
)

logger = logging.getLogger(__name__)

def format_timestamp(seconds: float) -> str:
    """將秒數格式化為 VTT/SRT 時間戳 (HH:MM:SS.mmm)"""
    delta = timedelta(seconds=seconds)
    hours, remainder = divmod(delta.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    milliseconds = delta.microseconds // 1000
    return f"{hours:02}:{minutes:02}:{seconds:02}.{milliseconds:03d}"

def create_srt(segments: list) -> str:
    """根據 segments 生成 SRT 格式內容"""
    subs = []
    for i, segment in enumerate(segments):
        start_time = timedelta(seconds=segment['start'])
        end_time = timedelta(seconds=segment['end'])
        # srt 庫需要 timedelta 對象
        sub = srt.Subtitle(index=i + 1, start=start_time, end=end_time, content=segment['text'])
        subs.append(sub)
    return srt.compose(subs)

def create_vtt(segments: list) -> str:
    """根據 segments 生成 VTT 格式內容"""
    lines = ["WEBVTT", ""]
    for segment in segments:
        start = format_timestamp(segment['start'])
        end = format_timestamp(segment['end'])
        lines.append(f"{start} --> {end}")
        lines.append(segment['text'])
        lines.append("")
    return "\n".join(lines)


@router.post("/transcriptions", name="create_transcription")
async def create_transcription_endpoint(
    request: Request,
    file: UploadFile = File(...),
    model: str = Form("whisper-1"), # 忽略
    language: str | None = Form(None),
    prompt: str | None = Form(None),
    response_format: Literal["json", "text", "srt", "vtt", "verbose_json"] = Form("json"),
    temperature: float = Form(0.0) # 忽略
):
    model_loaded = getattr(request.app.state, 'stt_model_loaded', False)
    if not model_loaded:
        logger.error("Transcription endpoint called but STT model is not loaded (checked via app.state).")
        raise HTTPException(status_code=503, detail="STT service is not available. Model not loaded.")

    logger.info(f"Received non-streaming request: filename='{file.filename}'...")

    try:
        # *** 修改點: 調用非流式函數 ***
        loop = asyncio.get_running_loop()
        full_text, segments, info = await loop.run_in_executor(
            None,
            transcribe_audio_file, # <--- 調用這個函數
            file.file,
            language,
            prompt
        )
    except ValueError as e:
         # Handle cases like model not loaded error from service layer
         logger.error(f"Value error during transcription: {e}")
         raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.error(f"Transcription failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error during transcription: {e}")
    finally:
        # 確保文件被關閉 (FastAPI 通常會處理，但明確關閉更好)
         await file.close()
         logger.info(f"Closed uploaded file: {file.filename}")


    # 根據 response_format 格式化輸出
    if response_format == "json":
        return {"text": full_text}
    elif response_format == "verbose_json":
        return {
            "task": "transcribe", # OpenAI 格式
            "language": info["language"],
            "duration": info["duration"],
            "text": full_text,
            "segments": segments,
        }
    elif response_format == "text":
        return PlainTextResponse(full_text)
    elif response_format == "srt":
        # 需要 srt 庫: pip install srt
        # 確保 transcribe_audio 返回的 segments 包含 start, end, text
        srt_content = create_srt(segments)
        return PlainTextResponse(srt_content, media_type="text/plain") # 或者 application/x-subrip
    elif response_format == "vtt":
        vtt_content = create_vtt(segments)
        return PlainTextResponse(vtt_content, media_type="text/vtt")
    else:
        # 理論上不會到這裡，因為有 Literal 約束
        raise HTTPException(status_code=400, detail="Invalid response format")

# --- 新增: WebSocket 流式端點 ---
@router.websocket("/transcriptions/ws")
async def websocket_transcription_endpoint(
    websocket: WebSocket,
    language: str | None = None, # 可以通過查詢參數傳遞配置
    prompt: str | None = None,
    # --- 新增：翻譯相關參數 ---
    translate: bool = Query(False, description="是否啟用即時翻譯功能。"),
    target_lang: str | None = Query(None, description="目標翻譯語言代碼 (例如 'en', 'ja')。啟用翻譯時必需。"),
    source_lang: str | None = Query(None, description="源語言代碼 (可選，若不指定則使用 Whisper 檢測結果)。")
):
    await websocket.accept()
    logger.info(f"WebSocket connection accepted from {websocket.client.host}:{websocket.client.port}")
    logger.info(f"Connection options: language='{language}', prompt='{prompt}', translate={translate}, target_lang='{target_lang}', source_lang='{source_lang}'")

    # 檢查模型是否加載
    model_loaded = getattr(websocket.app.state, 'stt_model_loaded', False)
    if not model_loaded:
        # ... (處理模型未加載錯誤) ...
        logger.error("WebSocket connection attempt but STT model not loaded.")
        await websocket.close(code=1011, reason="STT service is not available")
        return

    # 檢查翻譯參數
    if translate and not target_lang:
        logger.error("Translation enabled but target_lang not specified.")
        await websocket.close(code=1008, reason="target_lang is required when translate=true") # 1008 = Policy Violation
        return
    

    # --- 新增：異步輔助函數，用於執行翻譯並發送結果 ---
    async def translate_and_send(text: str, detected_source_lang: str):
        lang_to_use = source_lang or detected_source_lang # 優先使用客戶端指定的源語言
        if not lang_to_use:
            logger.warning("Cannot perform translation: source language not specified and not detected.")
            return # 無法確定源語言

        logger.info(f"Requesting translation for segment: '{text[:30]}...' from {lang_to_use} to {target_lang}")
        translation = await summary_service.get_translation_from_llm(text, lang_to_use, target_lang)

        if translation:
            try:
                await websocket.send_json({
                    "type": "translation",
                    "original_text": text,
                    "translated_text": translation,
                    "source_lang": lang_to_use,
                    "target_lang": target_lang
                })
                logger.info("Translation sent to client.")
            except websockets.exceptions.ConnectionClosed:
                logger.warning("Could not send translation, connection closed.")
            except Exception as e:
                logger.error(f"Error sending translation to client: {e}", exc_info=True)
        else:
             logger.warning("Translation failed or returned empty.")
             # 可以選擇是否發送錯誤訊息給客戶端
             # await websocket.send_json({"type": "error", "message": "Translation failed"})

    try:
        # 創建流式處理器實例
        streamer = AudioTranscriptionStreamer(language=language, initial_prompt=prompt)
        logger.info("AudioTranscriptionStreamer created for WebSocket connection.")

        # 循環接收音訊數據
        while True:
            try:
                # data 可能包含 bytes (音訊) 或 str (控制訊息)
                data = await websocket.receive()

                if "bytes" in data:
                    chunk = data["bytes"]
                    # 處理音訊塊並獲取結果
                    async for result in streamer.process_audio_chunk(chunk):
                        # **首先發送原始結果 (final/info/error)**
                        await websocket.send_json(result)

                        # **如果結果是 final 且啟用了翻譯，則觸發翻譯任務**
                        if result.get("type") == "final" and translate:
                            original_text = result.get("text")
                            detected_lang = result.get("language") # Whisper 檢測到的語言
                            if original_text and target_lang: # 確保有文本和目標語言
                                # *** 創建一個異步任務來處理翻譯，不阻塞主循環 ***
                                asyncio.create_task(translate_and_send(original_text, detected_lang))
                            elif not target_lang:
                                # 這不應該發生，因為前面檢查過了
                                logger.warning("Translation enabled but target_lang is missing.")


                elif "text" in data:
                    # ... (處理 STREAM_END 等文本消息 - 保持不變) ...
                    message = data["text"]
                    logger.info(f"Received text message: {message}")
                    if message == "STREAM_END":
                        logger.info("Received stream end signal.")
                        break
                    else:
                         await websocket.send_json({"type": "info", "message": f"Received unknown text message: {message}"})

            except WebSocketDisconnect:
                logger.info(f"WebSocket disconnected by client {websocket.client.host}:{websocket.client.port}")
                break
            except Exception as e:
                 logger.error(f"Error during WebSocket communication loop: {e}", exc_info=True)
                 try: # 嘗試發送錯誤
                     await websocket.send_json({"type": "error", "message": f"Server processing error: {e}"})
                 except: pass
                 break

        # WebSocket 接收循環結束 (客戶端斷開或收到結束信號)
        logger.info("Processing any remaining audio in buffer...")
        async for result in streamer.stream_complete():
            await websocket.send_json(result)
            # 如果最後一段也需要翻譯
            if result.get("type") == "final" and translate:
                original_text = result.get("text")
                detected_lang = result.get("language")
                if original_text and target_lang:
                    asyncio.create_task(translate_and_send(original_text, detected_lang))


        logger.info("Closing WebSocket connection.")
        await websocket.close()

    except ValueError as e:
        # Handle cases like model not loaded during streamer initialization
        logger.error(f"Error initializing streamer: {e}")
        await websocket.close(code=1011, reason=str(e))
    except Exception as e:
        # Catch potential errors during initial connection or setup
        logger.error(f"Unexpected error in WebSocket endpoint: {e}", exc_info=True)
        # Try to close gracefully
        try:
            await websocket.close(code=1011, reason="Unexpected server error")
        except:
            pass # Ignore errors during close if connection already broke