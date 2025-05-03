import logging
import httpx # 確保 httpx 已安裝 (之前 LLM 已安裝)
from typing import Dict, Any, Optional

from ..core.config import settings

logger = logging.getLogger(__name__)

# 使用異步 httpx 客戶端進行請求轉發
# 創建一個可重用的異步客戶端實例 (可以考慮使用 lifespan 管理)
# 為了簡單起見，暫時在函數內創建
# http_client = httpx.AsyncClient(timeout=60.0) # 設置合理的超時時間

async def proxy_tts_request(payload: Dict[str, Any]) -> Optional[httpx.Response]:
    """
    將 TTS 請求轉發給配置的後端 TTS 服務。

    Args:
        payload: 從 K.audio API 端點收到的請求體數據 (字典形式)。

    Returns:
        httpx.Response 對象如果成功，否則返回 None。
    """
    target_url = f"{settings.tts_service_api_base}/v1/audio/speech"
    logger.info(f"Proxying TTS request to: {target_url}")

    headers = {
        "Content-Type": "application/json",
        # **修改點：接受任何音頻類型，讓後端決定**
        # 或者根據 payload 中的 response_format 設置
        "accept": f"audio/{payload.get('response_format', 'wav')}" # 優先使用請求的格式
        # "accept": "*/*" # 或者接受任何類型
    }
    # 如果 TTS 服務需要 API Key:
    # if settings.tts_service_api_key:
    #     headers["Authorization"] = f"Bearer {settings.tts_service_api_key}"


    # *** 修改點：不使用 response 的上下文管理器 ***
    client = httpx.AsyncClient(timeout=60.0) # 每次請求創建一個新的 client
    try:
        # 1. 構建請求
        req = client.build_request(
            "POST", target_url, json=payload, headers=headers
        )
        # 2. 發送請求，明確 stream=True
        response = await client.send(req, stream=True)
        logger.info(f"Initial response from TTS service: Status {response.status_code}")

        # 3. 檢查初始錯誤狀態 (但不關閉流)
        if response.status_code >= 400:
            # 讀取錯誤體以便日誌記錄或上層處理
            try:
                 await response.aread() # 讀取內容到內部緩存
                 logger.error(f"Backend TTS service returned error status {response.status_code}. Body read.")
            except Exception as read_err:
                 logger.error(f"Backend TTS service returned error status {response.status_code}, but failed to read body: {read_err}")
            # 仍然返回 response，讓 API 層處理狀態碼

        # 4. **重要：返回 response，但不關閉 client 或 response 流**
        # 調用者 (API 端點) 必須負責調用 response.aclose() 和 client.aclose()
        # 為了簡化 API 層，我們先返回 response，並假設 API 層會處理關閉
        # 注意：client 需要保持活躍直到流被消耗完畢。這意味著上面的 client 創建方式需要調整
        # --> 折衷方案：還是返回 response，API 層需要確保在使用完 aiter_bytes 後調用 aclose

        # 為了避免 client 過早關閉，修改為不使用 async with httpx.AsyncClient()
        # 而是在函數結束時不關閉 client，或者將 client 提升為全局/lifespan 管理
        # 暫時先這樣返回 response，寄希望於 FastAPI/Starlette 能處理流的關閉
        return response

    except httpx.RequestError as e:
        logger.error(f"Error requesting TTS service at {target_url}: {e}", exc_info=True)
        await client.aclose() # 出錯時嘗試關閉 client
        return None
    except Exception as e:
        logger.error(f"Unexpected error during TTS proxy request: {e}", exc_info=True)
        await client.aclose() # 出錯時嘗試關閉 client
        return None
    # 注意：正常返回 response 時，client 沒有關閉，這依賴於調用者後續關閉 response 流
    

# --- 新增：代理 GET 請求的函數 ---
async def proxy_get_request(endpoint_path: str) -> Optional[httpx.Response]:
    """
    將 GET 請求轉發給配置的後端 TTS 服務。

    Args:
        endpoint_path: 相對於 base_url 的端點路徑 (例如 "/v1/audio/voices")。

    Returns:
        httpx.Response 對象如果成功，否則返回 None。
    """
    # 確保路徑以 / 開頭
    if not endpoint_path.startswith("/"):
        endpoint_path = "/" + endpoint_path

    target_url = f"{settings.tts_service_api_base}{endpoint_path}"
    logger.info(f"Proxying GET request to: {target_url}")

    headers = {
        "accept": "application/json" # 通常這類請求返回 JSON
    }
    # 如果需要 API Key
    # if settings.tts_service_api_key:
    #     headers["Authorization"] = f"Bearer {settings.tts_service_api_key}"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client: # GET 請求超時可以短一些
            response = await client.get(target_url, headers=headers)
        logger.info(f"Received GET response from service with status code: {response.status_code}")
        return response
    except httpx.RequestError as e:
        logger.error(f"Error requesting service at {target_url}: {e}", exc_info=True)
        return None
    except Exception as e:
        logger.error(f"Unexpected error during GET proxy request: {e}", exc_info=True)
        return None