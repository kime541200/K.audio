import asyncio
import websockets
import sounddevice as sd
import numpy as np
import argparse
import json # 用於解析伺服器訊息
import logging
import httpx # <--- 新增導入 httpx
from pathlib import Path # <--- 用於處理路徑
from datetime import datetime # <--- 用於生成時間戳

# --- 基本設定 ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)

# --- 音訊參數 (必須與伺服器 stt_service.py 中的設置匹配) ---
SAMPLE_RATE = 16000
CHANNELS = 1
DTYPE = 'int16' # 16-bit PCM
# VAD 幀長度 (毫秒) - 決定我們發送的塊大小
MS_PER_FRAME = 30
SAMPLES_PER_FRAME = int(SAMPLE_RATE * MS_PER_FRAME / 1000)
# 注意：sounddevice 的 blocksize 是樣本數
BLOCK_SIZE = SAMPLES_PER_FRAME

# --- 全局變數 ---
# 使用 asyncio Queue 在同步回調和異步任務間傳遞數據
audio_queue = asyncio.Queue()
# 用於通知發送任務停止的事件
stop_event = asyncio.Event()
# 用於累積文字稿的列表
transcript_parts = []
# 保存文字稿的文件路徑
# transcript_file_path: Path | None = None

# --- sounddevice 回調函數 ---
def audio_callback(indata, frames, time, status):
    """
    此函數由 sounddevice 在單獨的線程中調用。
    indata: numpy array (frames, channels)
    frames: 實際讀取的幀數 (樣本數)
    time: 時間信息
    status: 狀態標誌
    """
    if status:
        logger.warning(f"Sounddevice status: {status}")
    
    # 將 numpy array 轉換為 bytes 並放入隊列
    # 確保 indata 是 int16 類型
    if indata.dtype != np.int16:
        # 如果不是 int16 (例如 float32)，需要轉換並縮放
        # 假設 indata 範圍在 -1.0 到 1.0 之間
        # indata_int16 = (indata * 32767).astype(np.int16)
        # logger.warning(f"Input data type is {indata.dtype}, converting to int16.")
        # 但我們在 InputStream 指定了 dtype='int16'，所以理論上不需要轉換
        # 如果遇到問題，取消上面這段註解
        pass # 假設 indata 已經是 int16

    # 將數據放入異步隊列 (需要 non-blocking put)
    try:
        audio_queue.put_nowait(indata.tobytes())
    except asyncio.QueueFull:
        logger.warning("Audio queue is full, dropping frame.")


# --- 異步任務：發送音訊數據 ---
async def sender(websocket):
    """從隊列中獲取音訊數據並通過 WebSocket 發送"""
    logger.info("Sender task started.")
    try:
        while not stop_event.is_set():
            try:
                # 從隊列中等待數據
                chunk = await asyncio.wait_for(audio_queue.get(), timeout=0.1)
                await websocket.send(chunk)
                #logger.debug(f"Sent {len(chunk)} bytes of audio data.")
                audio_queue.task_done()
            except asyncio.TimeoutError:
                # 隊列為空，繼續等待或檢查停止信號
                continue
            except asyncio.CancelledError:
                logger.info("Sender task cancelled.")
                break
            except Exception as e:
                logger.error(f"Error in sender task: {e}", exc_info=True)
                break

        # 發送結束信號
        logger.info("Sending STREAM_END signal...")
        await websocket.send("STREAM_END")

    except websockets.exceptions.ConnectionClosedOK:
         logger.info("WebSocket connection closed normally by server (sender).")
    except websockets.exceptions.ConnectionClosedError as e:
         logger.error(f"WebSocket connection closed with error (sender): {e}")
    except Exception as e:
        logger.error(f"Unexpected error in sender task: {e}", exc_info=True)
    finally:
         logger.info("Sender task finished.")


# --- 異步任務：接收伺服器訊息 ---
async def receiver(websocket):
    """接收伺服器訊息，打印並累積最終文字稿"""
    logger.info("Receiver task started.")
    global transcript_parts # 聲明我們要修改全局列表
    transcript_parts.clear() # 確保每次運行前清空

    try:
        async for message in websocket:
            try:
                data = json.loads(message)
                logger.info(f"Received from server: {data}")

                # *** 累積 'final' 類型的文本 ***
                if data.get("type") == "final" and "text" in data:
                    transcript_parts.append(data["text"]) # 將最終文本添加到列表中

            except json.JSONDecodeError:
                logger.warning(f"Received non-JSON message: {message}")
            except asyncio.CancelledError:
                logger.info("Receiver task cancelled.")
                break
            except Exception as e:
                logger.error(f"Error processing received message: {e}", exc_info=True)

    except websockets.exceptions.ConnectionClosedOK:
         logger.info("WebSocket connection closed normally by server (receiver).")
    except websockets.exceptions.ConnectionClosedError as e:
         logger.error(f"WebSocket connection closed with error (receiver): {e}")
    except Exception as e:
        logger.error(f"Unexpected error in receiver task: {e}", exc_info=True)
    finally:
         logger.info("Receiver task finished.")


# --- 調用總結 API 的函數 ---
async def request_summarization(server_http_url: str, text: str) -> str | None:
    """向 K.audio 伺服器請求文本摘要"""
    summarization_url = f"{server_http_url}/v1/summarizations" # 構造 URL
    logger.info(f"Requesting summarization from: {summarization_url}")

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                summarization_url,
                json={"text": text},
                headers={"Content-Type": "application/json", "accept": "application/json"},
                timeout=120.0 # 給 LLM 調用留足夠的時間 (例如 120 秒)
            )

            response.raise_for_status() # 如果狀態碼不是 2xx，則拋出異常

            result = response.json()
            if "summary" in result:
                logger.info("Summarization successful.")
                return result["summary"]
            else:
                logger.error(f"Summarization response missing 'summary' key: {result}")
                return None

    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error during summarization request: {e.response.status_code} - {e.response.text}")
        return None
    except httpx.RequestError as e:
        logger.error(f"Request error during summarization request: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error during summarization request: {e}", exc_info=True)
        return None

# --- 主函數 ---
async def main(args):
    """主執行函數"""
    global transcript_file_path # 允許修改全局變數

    # 1. 選擇音訊設備
    try:
        devices = sd.query_devices()
        input_devices = [(i, d['name']) for i, d in enumerate(devices) if d['max_input_channels'] > 0]

        if not input_devices:
            logger.error("No input audio devices found!")
            return

        if args.device is None:
            device_index = sd.default.device['input']
            device_name = sd.query_devices(device_index, 'input')['name']
            logger.info(f"Using default input device: {device_index} - {device_name}")
        elif args.device == 'list':
            print("Available input devices:")
            for index, name in input_devices:
                default_marker = "(default)" if index == sd.default.device['input'] else ""
                print(f"  {index}: {name} {default_marker}")
            return
        else:
            try:
                device_index = int(args.device)
                if device_index not in [d[0] for d in input_devices]:
                    raise ValueError("Invalid device index.")
                device_name = sd.query_devices(device_index, 'input')['name']
                logger.info(f"Using selected input device: {device_index} - {device_name}")
            except (ValueError, sd.PortAudioError) as e:
                logger.error(f"Invalid device selected: {args.device}. Error: {e}")
                logger.info("Available input devices:")
                for index, name in input_devices:
                     default_marker = "(default)" if index == sd.default.device['input'] else ""
                     logger.info(f"  {index}: {name} {default_marker}")
                return

    except Exception as e:
        logger.error(f"Error querying audio devices: {e}", exc_info=True)
        return

    # 2. 構建 WebSocket URL (包含查詢參數)
    # ws://<host>:<port>/v1/audio/transcriptions/ws?language=zh&prompt=...
    connect_url = args.server_url
    query_params = []
    if args.language:
        query_params.append(f"language={args.language}")
    if args.prompt:
        query_params.append(f"prompt={args.prompt}")
    if query_params:
        connect_url += "?" + "&".join(query_params)
    logger.info(f"Connecting to WebSocket: {connect_url}")

    # --- 使用命令行參數指定的輸出目錄 ---
    output_dir = Path(args.output_dir) # <--- 使用 args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True) # parents=True 允許創建多級目錄

    websocket_connection = None
    stream = None
    sender_task = None
    receiver_task = None
    session_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S") # <--- 生成會話時間戳
    session_dir: Path | None = None # <--- 用於存放本次會話文件的目錄

    try:
        async with websockets.connect(connect_url) as websocket:
            websocket_connection = websocket # 保存引用
            logger.info("WebSocket connection established.")

            stream = sd.InputStream(
                samplerate=SAMPLE_RATE, blocksize=BLOCK_SIZE,
                device=device_index, channels=CHANNELS,
                dtype=DTYPE, callback=audio_callback
            )
            stream.start()
            logger.info("Audio input stream started.")

            sender_task = asyncio.create_task(sender(websocket))
            receiver_task = asyncio.create_task(receiver(websocket))

            # 等待停止事件 (例如 Ctrl+C)
            await stop_event.wait()
            logger.info("Stop event received.")

    except websockets.exceptions.InvalidURI:
        logger.error(f"Invalid WebSocket URI: {connect_url}")
    except websockets.exceptions.WebSocketException as e:
        logger.error(f"WebSocket connection failed: {e}")
    except sd.PortAudioError as e:
         logger.error(f"PortAudio error starting stream: {e}")
    except Exception as e:
        logger.error(f"An unexpected error occurred during main execution: {e}", exc_info=True)
    finally:
        # --- 清理與結束流程 ---
        logger.info("Starting cleanup...")
        if stream and stream.active:
            stream.stop()
            stream.close()
            logger.info("Audio input stream stopped.")

        stop_event.set() # 確保事件被設置

        if sender_task and not sender_task.done():
            try:
                logger.info("Waiting for sender task to finish...")
                await asyncio.wait_for(sender_task, timeout=2.0)
            except asyncio.TimeoutError:
                logger.warning("Sender task did not finish sending STREAM_END gracefully.")
            except Exception as e:
                 logger.error(f"Error waiting for sender task completion: {e}")

        # WebSocket 關閉應該由 websockets.connect() 的上下文管理器處理，
        # 但如果提前退出或出錯，最好還是嘗試關閉
        # if websocket_connection and not websocket_connection.closed:
        #     try:
        #         await websocket_connection.close()
        #         logger.info("WebSocket connection closed.")
        #     except Exception as e:
        #         logger.warning(f"Error closing WebSocket connection during cleanup: {e}")


        if receiver_task and not receiver_task.done():
             logger.info("Cancelling receiver task...")
             receiver_task.cancel()
             try:
                 await receiver_task
             except asyncio.CancelledError:
                 logger.info("Receiver task cancelled successfully.")
             except Exception as e:
                 logger.error(f"Error waiting for receiver task cancellation: {e}")

        # --- 文字稿處理和摘要請求 ---
        if transcript_parts:
            # *** 修改點：使用換行符連接 ***
            full_transcript = "\n".join(transcript_parts)
            
            # *** 修改點：創建會話子目錄 ***
            session_dir = output_dir / session_timestamp
            session_dir.mkdir(exist_ok=True)
            
            # *** 修改點：在會話子目錄中保存文件 ***
            transcript_file_path = session_dir / "transcript.txt" # 固定文件名

            try:
                with open(transcript_file_path, "w", encoding="utf-8") as f:
                    f.write(full_transcript)
                logger.info(f"Transcript saved to: {transcript_file_path}")

                # 詢問用戶是否總結
                summarize_choice = input("Summarize this transcript? (y/n): ").lower()

                if summarize_choice == 'y':
                    server_http_url = args.server_url.replace("ws://", "http://").split('/v1/audio/transcriptions/ws')[0]
                    summary_text = await request_summarization(server_http_url, full_transcript)

                    if summary_text:
                        print("\n--- Summary ---")
                        print(summary_text)
                        print("---------------")
                        
                        # *** 修改點：在會話子目錄中保存摘要 ***
                        summary_file_path = session_dir / "summary.txt" # 固定文件名
                        try:
                            with open(summary_file_path, "w", encoding="utf-8") as f:
                                f.write(summary_text)
                            logger.info(f"Summary saved to: {summary_file_path}")
                        except IOError as e:
                            logger.error(f"Failed to save summary file: {e}")
                    else:
                        print("Failed to retrieve summary.")
            except IOError as e:
                logger.error(f"Failed to save transcript file: {e}")
            except Exception as e: # 捕獲 input() 可能的異常
                 logger.error(f"Error during summarization prompt/request: {e}", exc_info=True)

        else:
            logger.info("No transcript parts were recorded.")

        logger.info("Client shutdown complete.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Real-time Speech-to-Text WebSocket Client")
    parser.add_argument(
        "server_url",
        # default="ws://localhost:8000/v1/audio/transcriptions/ws", # 本地測試用
        nargs='?', # 使其成為可選參數，方便使用 --device list
        help="WebSocket server URL (e.g., ws://<your_server_ip>:8000/v1/audio/transcriptions/ws)"
    )
    parser.add_argument(
        "-d", "--device",
        default=None, # 預設使用系統預設輸入設備
        help="Input device index or 'list' to show available devices."
    )
    parser.add_argument(
        "-l", "--language",
        type=str,
        default=None, # 讓伺服器自動檢測
        help="Language code (e.g., 'zh', 'en'). Default: auto-detect."
    )
    parser.add_argument(
        "-p", "--prompt",
        type=str,
        default=None,
        help="Optional initial prompt for the model."
    )
    parser.add_argument(
        "-o", "--output-dir",
        type=str,
        default="./k.audio_output", # 設置默認值
        help="Directory to save transcript and summary files."
    )
    args = parser.parse_args()

    if args.server_url is None and args.device != 'list':
         parser.error("the following arguments are required: server_url (unless using --device list)")

    # --- 修改: 使用 asyncio.run() 來運行 ---
    # asyncio.run() 會自動處理事件循環的創建和關閉
    # 並能更好地處理 KeyboardInterrupt
    try:
        asyncio.run(main(args))
    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt received. Exiting...")
        # asyncio.run() 會處理清理工作，但確保 stop_event 被設置很重要
        stop_event.set()
    except Exception as e:
         logger.critical(f"Unhandled exception in main execution: {e}", exc_info=True)

    # 在 asyncio.run() 之後，事件循環已關閉
    logger.info("Application finished.")