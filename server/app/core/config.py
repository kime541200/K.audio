import os
from pydantic_settings import BaseSettings
from pydantic import Field # Use Field for alias

class Settings(BaseSettings):
    # STT Settings
    # 從環境變數讀取，如果沒有則使用預設值
    stt_model_path: str = Field(default="/app/models/faster-whisper-medium", validation_alias="STT_MODEL_PATH") # 使用容器內的絕對路徑
    stt_device: str = Field(default="cuda", validation_alias="STT_DEVICE") # "cuda" or "cpu"
    stt_compute_type: str = Field(default="float16", validation_alias="STT_COMPUTE_TYPE") # e.g., "float16", "int8_float16", "int8" (GPU); "int8", "float32" (CPU)

    # --- LLM Settings ---
    # 確保這個 URL 指向您本地 LLM 的 OpenAI 相容端點
    local_llm_api_base: str = Field(default="http://localhost:8001/v1", validation_alias="LOCAL_LLM_API_BASE")
    # 如果您的本地 LLM 不需要 API Key，可以設為 None 或一個假值
    # openai 庫可能需要一個非 None 的值，即使服務器忽略它
    local_llm_api_key: str = Field(default="DUMMY_KEY", validation_alias="LOCAL_LLM_API_KEY") # 使用假值或 None
    # 可以添加 LLM 模型名稱的配置，如果需要的話
    local_llm_model_name: str = Field(default="local-llm", validation_alias="LOCAL_LLM_MODEL_NAME") # 本地 LLM 使用的模型名稱 (或留空讓端點決定)


    class Config:
        # If you want to load variables from a .env file:
        # env_file = ".env"
        # env_file_encoding = 'utf-8'
        extra = 'ignore' # Ignore extra fields from environment variables

# 建立設定實例供其他模組導入
settings = Settings()

# 打印加載的設置 (用於調試)
print("--- Application Settings ---")
print(f"STT Model Path: {settings.stt_model_path}")
print(f"STT Device: {settings.stt_device}")
print(f"STT Compute Type: {settings.stt_compute_type}")
print(f"LLM API Base: {settings.local_llm_api_base}")
print(f"LLM Model Name: {settings.local_llm_model_name}")
print("--------------------------")