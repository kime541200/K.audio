from fastapi import APIRouter, HTTPException, status, Body
from pydantic import BaseModel, Field
import logging

# 導入總結服務
from ...services import summary_service

router = APIRouter(
    prefix="/v1", # 將前綴設為 /v1
    tags=["Summarization"], # API 文件中的標籤
)

logger = logging.getLogger(__name__)

# --- 定義請求體模型 ---
class SummarizationRequest(BaseModel):
    text: str = Field(..., description="需要進行總結的原始文本。", min_length=1)
    # 可以添加其他參數，例如要求特定的總結長度等
    # model: str | None = Field(None, description="指定用於總結的模型 (如果伺服器支持)")

# --- 定義響應體模型 (可選但推薦) ---
class SummarizationResponse(BaseModel):
    summary: str = Field(description="生成的摘要文本。")


@router.post(
    "/summarizations",
    response_model=SummarizationResponse, # 指定響應模型
    summary="Create Text Summarization", # API 文件中的摘要
    description="接收一段文本，調用本地 LLM 生成摘要。" # API 文件中的描述
)
async def create_summarization(
    request: SummarizationRequest = Body(...) # 從請求體獲取數據
):
    """
    接收文本並生成摘要。
    """
    logger.info(f"Received summarization request. Text length: {len(request.text)}")

    # 調用服務層進行總結
    summary = await summary_service.get_summary_from_llm(request.text)

    if summary is None:
        logger.error("Failed to get summary from LLM service.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Failed to generate summary due to an internal error with the LLM service."
        )

    logger.info("Summarization successful.")
    return SummarizationResponse(summary=summary)