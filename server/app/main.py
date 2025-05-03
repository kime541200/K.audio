import logging
from contextlib import asynccontextmanager
import asyncio # 仍然需要導入 asyncio，但可能不再需要 loop
import uvicorn
from fastapi import FastAPI, Request # 為了 health check 導入 Request
from fastapi.responses import JSONResponse # 為了 health check
from fastapi.openapi.docs import (
    get_redoc_html,
    get_swagger_ui_html,
    get_swagger_ui_oauth2_redirect_html,
)

# 導入設定
from .core.config import settings

# 導入服務層的加載/卸載函數
from .services.stt_service import load_stt_model, unload_stt_model, stt_model # 導入 stt_model 以便檢查

# 導入 API 路由
from .api.v1 import audio as api_v1_audio
from .api.v1 import summarize as api_v1_summarize
from .api.v1 import tts as api_v1_tts
from .api.v1 import chat as api_v1_chat 

# 配置日誌
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- lifespan 管理器 ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- Application Startup ---
    logger.info("Application startup...")
    logger.info("Loading STT model synchronously...")
    app.state.stt_model_loaded = False # 初始化狀態

    try:
        # *** 修改點：接收返回值並檢查 ***
        returned_model_object = load_stt_model() # 接收返回值

        if returned_model_object is None:
             logger.error("STT Model failed to load during startup! (Checked via return value)")
             # app.state.stt_model_loaded 保持 False
        else:
             logger.info("STT Model loaded successfully during startup. (Checked via return value)")
             app.state.stt_model_loaded = True # 設置狀態標誌為 True
             # 注意：我們仍然依賴 stt_service.py 中的全局變數 stt_model 被正確設置，
             # 因為 transcribe_audio 函數會用到它。

    except Exception as e:
        logger.error(f"Critical error during STT model loading: {e}", exc_info=True)
        app.state.stt_model_loaded = False

    yield # <--- Startup 完成

    # --- Application Shutdown ---
    logger.info("Application shutdown...")

    # *** 修改點：直接同步調用模型卸載 ***
    logger.info("Unloading STT model synchronously...")
    try:
        unload_stt_model() # <--- 直接調用
    except Exception as e:
        logger.error(f"Error during STT model unloading: {e}", exc_info=True)

    logger.info("Application shutdown complete.")

# --- FastAPI 應用實例 ---
app = FastAPI(
    title="K.audio API Server",
    description="Offline TTS/STT service with OpenAI compatible API.",
    version="0.1.0",
    lifespan=lifespan
)

# --- 包含 API 路由 ---
app.include_router(api_v1_audio.router)
app.include_router(api_v1_summarize.router)
app.include_router(api_v1_tts.router)
app.include_router(api_v1_chat.router)


####################
# Swagger UI
####################

@app.get("/docs", include_in_schema=False)
async def custom_swagger_ui_html():
    return get_swagger_ui_html(
        openapi_url=app.openapi_url,
        title=app.title + " - Swagger UI",
        oauth2_redirect_url=app.swagger_ui_oauth2_redirect_url,
        swagger_js_url=f"/static/swagger-ui-bundle.js",
        swagger_css_url=f"/static/swagger-ui.css",
    )


@app.get(app.swagger_ui_oauth2_redirect_url, include_in_schema=False)
async def swagger_ui_redirect():
    return get_swagger_ui_oauth2_redirect_html()


@app.get("/redoc", include_in_schema=False)
async def redoc_html():
    return get_redoc_html(
        openapi_url=app.openapi_url,
        title=app.title + " - ReDoc",
        redoc_js_url="/static/redoc.standalone.js",
    )


# --- 根路徑 ---
@app.get("/")
async def read_root():
    return {"message": "Welcome to K.audio API Server!"}

# --- 健康檢查路由 ---
@app.get("/health", tags=["System"])
async def health_check(request: Request): # 注入 Request 以訪問 app.state
    """
    執行健康檢查，包括模型加載狀態。
    """
    model_loaded = getattr(request.app.state, 'stt_model_loaded', False) # 從 app.state 讀取狀態
    if model_loaded:
        return {"status": "ok", "stt_model_loaded": True}
    else:
        # 如果模型加載是關鍵，返回 503
        return JSONResponse(
            status_code=503,
            content={"status": "error", "stt_model_loaded": False, "detail": "STT model failed to load or is not available."}
        )


# (用於本地測試的 uvicorn 啟動部分保持不變)
if __name__ == "__main__":
    # 注意：直接運行此文件時，lifespan 可能不會完全按預期工作於某些終端信號
    # 推薦使用 uvicorn 命令或 docker-compose 啟動
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True) # reload 方便本地開發