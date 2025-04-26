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


# --- 翻譯函數 ---
async def get_translation_from_llm(text: str, source_lang: str, target_lang: str) -> str | None:
    """
    調用本地 LLM API 獲取文本翻譯。

    Args:
        text: 需要翻譯的文本。
        source_lang: 源語言代碼 (例如 'zh', 'en')。
        target_lang: 目標語言代碼 (例如 'en', 'ja')。

    Returns:
        翻譯後的文本，如果出錯則返回 None。
    """
    if client is None:
        logger.error("OpenAI client is not initialized. Cannot get translation.")
        return None
    if not text:
        logger.warning("Received empty text for translation.")
        return ""

    # --- 構建翻譯提示 ---
    # TODO: 調整prompt & 加入structure output 提取翻譯結果
    system_prompt = "你是一個專業的翻譯引擎。"
    user_prompt = f"請將以下 '{source_lang}' 文本翻譯成 '{target_lang}'：\n\n---\n{text}\n---"

    logger.info(f"Requesting translation from '{source_lang}' to '{target_lang}'. Text length: {len(text)}")

    try:
        response = await client.chat.completions.create(
            model=settings.local_llm_model_name, # 可以考慮為翻譯使用不同的模型配置
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.2, # 翻譯通常需要較低的溫度以確保準確性
            # max_tokens=int(len(text) * 1.5), # 可以根據原文長度估算最大 token
        )

        if response.choices and response.choices[0].message and response.choices[0].message.content:
            translation = response.choices[0].message.content.strip()
            logger.info(f"Translation received from LLM. Length: {len(translation)}")
            return translation
        else:
            logger.warning("LLM response did not contain valid translation content.")
            return None

    except Exception as e:
        logger.error(f"Error calling LLM API for translation: {e}", exc_info=True)
        return None