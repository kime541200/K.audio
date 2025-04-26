import asyncio
from fastapi import (
    APIRouter, UploadFile, File, Form, HTTPException,
    Depends, Request, WebSocket, WebSocketDisconnect
) # 添加 WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse, PlainTextResponse
import srt
import logging
from typing import Literal, Dict, Any
from datetime import timedelta
import numpy as np # 確保導入 numpy

# 導入流式處理類和非流式函數
from ...services.stt_service import (
    transcribe_audio_file,
    AudioTranscriptionStreamer, # 導入流式處理類
    stt_model # 雖然 streamer 內部使用，但這裡可能不需要直接導入了
)
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
):
    await websocket.accept()
    logger.info(f"WebSocket connection accepted from {websocket.client.host}:{websocket.client.port}")

    # 檢查模型是否已加載
    # 注意：WebSocket 沒有 request.app，需要找到 app 實例
    # 一個方法是通過依賴注入，或者如果 app 在全局可訪問
    # 暫時依賴 lifespan 中設置的狀態 (假設 app.state 可用)
    # 更健壯的方式是使用 Depends()
    model_loaded = getattr(websocket.app.state, 'stt_model_loaded', False)
    if not model_loaded:
        logger.error("WebSocket connection attempt but STT model not loaded.")
        await websocket.close(code=1011, reason="STT service is not available") # 1011 = Internal Error
        return

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
                    #logger.debug(f"Received {len(chunk)} bytes of audio data.")
                    # 將音訊塊交給 streamer 處理，並將結果發回客戶端
                    async for result in streamer.process_audio_chunk(chunk):
                        await websocket.send_json(result)

                elif "text" in data:
                    message = data["text"]
                    logger.info(f"Received text message: {message}")
                    if message == "STREAM_END": # 約定一個結束信號
                        logger.info("Received stream end signal.")
                        break # 退出接收循環
                    else:
                         # 可以處理其他控制訊息
                         await websocket.send_json({"type": "info", "message": f"Received unknown text message: {message}"})

            except WebSocketDisconnect:
                logger.info(f"WebSocket disconnected by client {websocket.client.host}:{websocket.client.port}")
                break # 退出接收循環
            except Exception as e:
                 logger.error(f"Error during WebSocket communication: {e}", exc_info=True)
                 # 嘗試發送錯誤訊息給客戶端
                 await websocket.send_json({"type": "error", "message": f"Server error: {e}"})
                 break # 發生錯誤，退出循環

        # WebSocket 接收循環結束 (客戶端斷開或收到結束信號)
        logger.info("Processing any remaining audio in buffer...")
        async for result in streamer.stream_complete():
            await websocket.send_json(result)

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