from fastapi import APIRouter, HTTPException, status, Body, Response
from pydantic import BaseModel, Field
import logging
from typing import List, Optional, Dict, Any # 導入所需類型
import httpx # 導入 httpx

# 導入代理服務
from ...services import summary_service # 現在包含聊天代理函數

# --- 定義兼容 OpenAI 的 Pydantic 模型 (簡化版) ---
class ChatMessage(BaseModel):
    role: str
    content: str

class ChatCompletionRequest(BaseModel):
    model: str = Field(description="要使用的模型 ID。")
    messages: List[ChatMessage] = Field(description="描述對話的消息列表。")
    temperature: Optional[float] = Field(default=0.7, ge=0.0, le=2.0, description="控制隨機性。")
    max_tokens: Optional[int] = Field(None, description="限制生成的最大 token 數。")
    # 可以添加 stream 等其他參數，但代理模式下先不處理 stream

# 這裡我們先不定義嚴格的 Response 模型，直接返回 JSON
# class ChatCompletionChoice(BaseModel): ...
# class ChatCompletionResponse(BaseModel): ...


# --- API 路由 ---
router = APIRouter(
    prefix="/v1", # 與 OpenAI 保持一致
    tags=["Chat"], # API 文件中的標籤
)
logger = logging.getLogger(__name__)


@router.post(
    "/chat/completions",
    # response_model=ChatCompletionResponse, # 暫不使用嚴格模型，直接返回 JSON
    summary="Create Chat Completion (Proxied)",
    description="接收聊天消息，代理請求到本地 LLM 服務，並返回其響應。"
)
async def create_chat_completion(
    request: ChatCompletionRequest = Body(...)
):
    """
    代理聊天補全請求到本地 LLM。
    """
    logger.info(f"Received chat completion request for model '{request.model}'. Messages count: {len(request.messages)}")

    # 構建轉發給後端的 payload (排除未設置的字段以保持靈活性)
    backend_payload = request.model_dump(exclude_unset=True)

    # 調用代理服務
    backend_response = await summary_service.proxy_chat_request(backend_payload)

    if backend_response is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The LLM service is currently unavailable (proxy failed)."
        )

    # 中繼後端服務的響應 (直接返回 JSON)
    # 需要設置 media_type，否則 FastAPI 可能會嘗試再次序列化
    media_type = backend_response.headers.get("content-type", "application/json")
    logger.info(f"Relaying LLM response with status {backend_response.status_code} and content-type {media_type}")

    return Response(
        content=backend_response.content,
        status_code=backend_response.status_code,
        media_type=media_type
    )