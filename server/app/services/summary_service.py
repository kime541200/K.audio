import logging
from openai import AsyncOpenAI # 使用異步客戶端
import asyncio

from ..core.config import settings

logger = logging.getLogger(__name__)

# --- 初始化 OpenAI 客戶端 ---
# 確保設置 base_url 指向本地 LLM
# 如果本地 LLM 不需要 API Key，api_key 可以設為一個非 None 的假值或根據庫的要求調整
try:
    client = AsyncOpenAI(
        base_url=settings.local_llm_api_base,
        api_key=settings.local_llm_api_key or "DUMMY_KEY" # 提供默認假值
    )
    logger.info(f"OpenAI client initialized for base_url: {settings.local_llm_api_base}")
except Exception as e:
    logger.error(f"Failed to initialize OpenAI client: {e}", exc_info=True)
    client = None # 初始化失敗

async def get_summary_from_llm(text: str) -> str | None:
    """
    調用本地 LLM API 獲取文本摘要。

    Args:
        text: 需要總結的文本。

    Returns:
        摘要文本，如果出錯則返回 None。
    """
    if client is None:
        logger.error("OpenAI client is not initialized. Cannot get summary.")
        return None
    if not text:
        logger.warning("Received empty text for summarization.")
        return ""

    # --- 構建提示 ---
    # 您可以根據需要調整這個系統提示和用戶提示
    system_prompt = "你是一個擅長總結會議記錄的助理。"
    user_prompt = f"請根據以下會議記錄生成一份簡潔明瞭、包含重點結論和待辦事項的摘要：\n\n---\n{text}\n---"

    logger.info(f"Requesting summary from LLM. Text length: {len(text)}")

    try:
        response = await client.chat.completions.create(
            model=settings.local_llm_model_name, # 使用配置的模型名稱
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.7, # 可以調整溫度或其他參數
            # max_tokens=500, # 可以限制最大 token 數
        )

        # 檢查是否有有效的回應
        if response.choices and response.choices[0].message and response.choices[0].message.content:
            summary = response.choices[0].message.content.strip()
            logger.info(f"Summary received from LLM. Length: {len(summary)}")
            return summary
        else:
            logger.warning("LLM response did not contain valid content.")
            return None

    except Exception as e:
        logger.error(f"Error calling LLM API: {e}", exc_info=True)
        return None