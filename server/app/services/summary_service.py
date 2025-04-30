import logging
from openai import AsyncOpenAI # 使用異步客戶端
import asyncio
import re

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
    調用本地 LLM API 獲取文本翻譯, 並移除 <think> 標籤及其內容。

    Args:
        text: 需要翻譯的文本。
        source_lang: 源語言代碼 (例如 'zh', 'en')。
        target_lang: 目標語言代碼 (例如 'en', 'ja')。

    Returns:
        翻譯後的文本（已移除 <think> 內容），如果出錯則返回 None。
    """
    if client is None:
        logger.error("OpenAI client is not initialized. Cannot get translation.")
        return None
    if not text:
        logger.warning("Received empty text for translation.")
        return ""

    # --- 構建翻譯提示 (使用您提供的 prompt) ---
    system_prompt = """
You are a real-time translation agent. Your task is to instantly translate each sentence you receive from users into the specified target language.
You will only output the translated content, without providing any additional explanations or comments.

Please keep the following in mind:

- You will receive conversations sentence by sentence.
- You must translate each sentence immediately upon receiving it.
- Your output should contain only the translated text, with no prefixes, suffixes, or explanatory text.
- Ensure the accuracy and fluency of the translation.

Target Language: [Specify the target language here, e.g., English, Japanese, French, etc.]

**Example Usage (assuming the target language is English):**

**User Input:** 你好嗎？
**Agent Output:** How are you?

**User Input:** 今天天氣真好。
**Agent Output:** The weather is really nice today.

**User Input:** 很高興認識你。
**Agent Output:** Nice to meet you.
""".strip()
    # TODO: Consider dynamically replacing "[Specify the target language here...]" in system_prompt with target_lang
    # system_prompt = system_prompt.replace("[Specify the target language here...]", target_lang) # Uncomment and adapt if needed

    user_prompt = f"Please translate the following \"{source_lang}\" sentence into \"{target_lang}\":\n\n{text}"
    user_prompt += "/no_think" # add `/no_think` tag for Qwen3-30B-A3B model

    logger.info(f"Requesting translation from '{source_lang}' to '{target_lang}'. Text length: {len(text)}")

    try:
        response = await client.chat.completions.create(
            model=settings.local_llm_model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.2,
        )

        if response.choices and response.choices[0].message and response.choices[0].message.content:
            raw_translation = response.choices[0].message.content.strip()
            logger.debug(f"Raw LLM translation output: {raw_translation}") # 記錄原始輸出以供調試

            # --- 使用正則表達式移除 <think>...</think> 及其內容 ---
            # 正則表達式解釋:
            # <think> : 匹配開頭標籤
            # .*?     : 匹配任何字符 (.) 零次或多次 (*) ，使用非貪婪模式 (?)，
            #           這樣如果有多個 <think> 塊，它只匹配到最近的 </think>
            # </think>: 匹配結尾標籤
            # flags=re.DOTALL: 讓 '.' 可以匹配換行符，以防 <think> 內容跨越多行
            pattern = r"<think>.*?</think>"
            cleaned_translation = re.sub(pattern, "", raw_translation, flags=re.DOTALL).strip()

            # 檢查清理後是否還有內容
            if not cleaned_translation:
                logger.warning("LLM response became empty after removing <think> tags.")
                # 可以選擇返回 None 或空字符串，這裡返回 None 表示處理後無有效內容
                return None

            logger.info(f"Cleaned translation. Length: {len(cleaned_translation)}")
            return cleaned_translation
        else:
            logger.warning("LLM response did not contain valid content.")
            return None

    except Exception as e:
        logger.error(f"Error calling LLM API for translation: {e}", exc_info=True)
        return None