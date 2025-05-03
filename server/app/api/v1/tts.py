import json
from fastapi import APIRouter, HTTPException, status, Body, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
import logging
from typing import Literal, List, AsyncGenerator
import httpx

from ...services import tts_proxy_service # 導入代理服務

router = APIRouter(
    prefix="/v1/audio", # 保持和 OpenAI 一致的前綴
    tags=["Audio"],     # 可以和 STT 共用 Audio 標籤
)

logger = logging.getLogger(__name__)

# --- 定義 TTS 請求體模型 (參考 OpenAI) ---
class TTSRequest(BaseModel):
    model: str = Field(description="模型 ID (例如 'kokoro' 或 'vits')，代理模式下可能被忽略或用於路由。")
    input: str = Field(..., min_length=1, description="要轉換為音頻的文本。")
    voice: str = Field(..., description="要使用的聲音標識符 (例如 'default', 'speaker_1')。")
    response_format: Literal["wav", "mp3", "opus", "aac", "flac"] = Field(
        default="wav", description="返回的音頻格式 (代理模式下可能只支持後端服務提供的格式)。"
    )
    speed: float = Field(default=1.0, ge=0.25, le=4.0, description="語音速度。")

# --- 新增：獲取聲音列表的響應模型 ---
class VoicesResponse(BaseModel):
    voices: List[str] = Field(description="可用的聲音名稱列表。")

@router.post(
    "/speech",
    summary="Generates audio from the input text (Proxied)",
    description="Receives text and proxies the request to the backend TTS service. Supports streaming output if backend provides it.",
    # **修改點：不再指定 response_model，因為可能是流式或非流式**
)
async def create_speech(
    request: TTSRequest = Body(...)
):
    """
    代理 TTS 請求到後端服務。
    """
    logger.info(f"Received TTS request for voice '{request.voice}', speed {request.speed}. Input length: {len(request.input)}")

    backend_payload = {
        "input": request.input,
        "voice": request.voice,
        "response_format": request.response_format,
        "speed": request.speed,
        "model": request.model
    }

    backend_response = await tts_proxy_service.proxy_tts_request(backend_payload)

    if backend_response is None:
        # 代理服務層發生連接錯誤或未知錯誤
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The text-to-speech service is currently unavailable."
        )
    
    status_code = backend_response.status_code
    headers = backend_response.headers
    media_type = headers.get("content-type", f"audio/{request.response_format}")

    # **修改點：先處理錯誤，確保關閉流**
    if not (200 <= status_code < 300):
        try:
            error_detail = (await backend_response.aread()).decode('utf-8', errors='ignore')[:500]
        except Exception as e_read:
            error_detail = f"(Failed to read error body: {e_read})"
        finally:
            await backend_response.aclose() # <--- 確保關閉錯誤響應流
        logger.error(f"Backend TTS service returned error {status_code}: {error_detail}")
        raise HTTPException(status_code=status_code, detail=f"Backend TTS service error: {error_detail}")

    # 判斷是否流式
    is_streaming = "chunked" in headers.get("transfer-encoding", "").lower()

    if is_streaming:
        logger.info(f"Relaying streaming TTS response with content-type {media_type}")
        # **修改點：簡化生成器，並在 finally 中關閉 response**
        async def stream_generator() -> AsyncGenerator[bytes, None]:
            # 將 backend_response 傳遞到生成器作用域
            response_to_close = backend_response
            try:
                async for chunk in response_to_close.aiter_bytes():
                    yield chunk
                logger.info("Backend TTS stream finished.")
            except Exception as e_stream:
                logger.error(f"Error iterating backend TTS stream: {e_stream}", exc_info=True)
                # 可以選擇在此處 yield 一個錯誤標誌，或讓 FastAPI/Starlette 處理異常
                # 例如: yield b'{"error": "Stream iteration failed"}'
            finally:
                # **非常重要：確保在生成器結束時關閉 httpx 響應流**
                logger.info("Closing backend TTS response stream in generator finally block.")
                await response_to_close.aclose()

        headers_to_relay = {"content-type": media_type}
        return StreamingResponse(
            stream_generator(),
            status_code=status_code,
            media_type=media_type,
            headers=headers_to_relay
        )
    else: # 非流式
        logger.info(f"Relaying non-streaming TTS response with content-type {media_type}")
        try:
            # **修改點：在這裡讀取內容**
            audio_bytes = await backend_response.aread()
        except Exception as e_read:
             logger.error(f"Error reading non-streaming backend response: {e_read}", exc_info=True)
             await backend_response.aclose() # 讀取失敗也要關閉
             raise HTTPException(status_code=500, detail="Failed to read backend TTS response")
        finally:
            # **確保關閉非流式響應的連接**
            await backend_response.aclose()

        if audio_bytes:
             return Response(content=audio_bytes, status_code=status_code, media_type=media_type)
        else:
             logger.warning("Non-streaming TTS response has empty content despite success status.")
             return Response(content=b'', status_code=status.HTTP_204_NO_CONTENT)
    
# --- 新增：GET /voices 端點 ---
@router.get(
    "/voices",
    response_model=VoicesResponse, # 指定響應模型
    summary="List Available Voices (Proxied)",
    description="從後端 TTS 服務獲取可用的聲音列表。"
)
async def list_voices():
    """
    代理獲取聲音列表的請求。
    """
    logger.info("Received request to list voices.")
    backend_response = await tts_proxy_service.proxy_get_request("/v1/audio/voices") # <--- 調用 GET 代理

    if backend_response is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The text-to-speech service is currently unavailable (failed to connect)."
        )

    # 檢查後端響應狀態碼
    if 200 <= backend_response.status_code < 300:
        try:
            # 直接返回後端的 JSON 內容 (FastAPI 會自動處理 Pydantic 模型的驗證和轉換)
            json_response = backend_response.json()
            logger.info(f"Relaying voices list: {json_response}")
            # 確保返回的結構與 VoicesResponse 匹配
            if "voices" in json_response and isinstance(json_response["voices"], list):
                 return json_response
            else:
                 logger.error(f"Backend voices response format unexpected: {json_response}")
                 raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Backend returned unexpected voice list format.")

        except json.JSONDecodeError:
            logger.error("Failed to decode JSON response from backend voices endpoint.")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Backend returned non-JSON voice list.")
        except Exception as e:
             logger.error(f"Error processing backend voices response: {e}", exc_info=True)
             raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error processing backend response: {e}")
    else:
        # 後端服務返回錯誤
        error_detail = backend_response.text[:500]
        logger.error(f"Backend TTS service returned error for voices list {backend_response.status_code}: {error_detail}")
        raise HTTPException(
            status_code=backend_response.status_code,
            detail=f"Backend TTS service error: {error_detail}"
        )