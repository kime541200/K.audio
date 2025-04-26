import asyncio
import websockets
import sounddevice as sd
import numpy as np
import argparse
import json # 用於解析伺服器訊息
import logging

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
    """接收並打印伺服器發來的 JSON 訊息"""
    logger.info("Receiver task started.")
    try:
        async for message in websocket:
            try:
                data = json.loads(message)
                logger.info(f"Received from server: {data}")
                # 在這裡可以根據 data['type'] 做更詳細的處理
                # if data.get("type") == "final":
                #     print(f"Final Transcription: {data.get('text')}")
                # elif data.get("type") == "info":
                #     print(f"Info: {data.get('message')}")
                # elif data.get("type") == "error":
                #     print(f"Error: {data.get('message')}")

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


# --- 主函數 ---
async def main(args):
    """主執行函數"""

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


    # 3. 建立 WebSocket 連接並運行任務
    try:
        async with websockets.connect(connect_url) as websocket:
            logger.info("WebSocket connection established.")

            # 啟動 sounddevice 輸入流
            stream = sd.InputStream(
                samplerate=SAMPLE_RATE,
                blocksize=BLOCK_SIZE,
                device=device_index,
                channels=CHANNELS,
                dtype=DTYPE,
                callback=audio_callback
            )
            stream.start()
            logger.info("Audio input stream started.")

            # 運行 sender 和 receiver 任務
            sender_task = asyncio.create_task(sender(websocket))
            receiver_task = asyncio.create_task(receiver(websocket))

            # 等待任務完成 (或被中斷)
            # 我們需要一種方式來停止，例如監聽 Ctrl+C
            # asyncio.get_running_loop().add_signal_handler(signal.SIGINT, stop_event.set) # Linux/macOS
            
            # 簡單的等待停止事件被設置
            await stop_event.wait()
            logger.info("Stop event received.")


    except websockets.exceptions.InvalidURI:
        logger.error(f"Invalid WebSocket URI: {connect_url}")
    except websockets.exceptions.WebSocketException as e:
        logger.error(f"WebSocket connection failed: {e}")
    except sd.PortAudioError as e:
         logger.error(f"PortAudio error starting stream: {e}")
    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}", exc_info=True)
    finally:
        # 無論如何都要嘗試停止流和任務
        if 'stream' in locals() and stream.active:
            stream.stop()
            stream.close()
            logger.info("Audio input stream stopped.")
        
        stop_event.set() # 確保事件被設置以停止 sender
        
        # 等待 sender 完成 (給它一點時間發送 STREAM_END)
        if 'sender_task' in locals() and not sender_task.done():
            try:
                await asyncio.wait_for(sender_task, timeout=2.0)
            except asyncio.TimeoutError:
                logger.warning("Sender task did not finish gracefully.")
            except Exception as e:
                logger.error(f"Error waiting for sender task: {e}")

        # 取消 receiver (如果它還在運行)
        if 'receiver_task' in locals() and not receiver_task.done():
             receiver_task.cancel()
             try:
                 await receiver_task
             except asyncio.CancelledError:
                 logger.info("Receiver task cancelled successfully.")
             except Exception as e:
                logger.error(f"Error waiting for receiver task cancellation: {e}")

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
    args = parser.parse_args()

    if args.server_url is None and args.device != 'list':
         parser.error("the following arguments are required: server_url (unless using --device list)")

    # 處理 Ctrl+C
    loop = asyncio.get_event_loop()
    try:
        # 註冊信號處理器來設置停止事件
        # loop.add_signal_handler(signal.SIGINT, stop_event.set)
        # loop.add_signal_handler(signal.SIGTERM, stop_event.set)
        # Windows 上 add_signal_handler 可能不完全支援，使用 asyncio.run 的 shutdown_default_executor
        # 更簡單的方式是讓用戶手動按 Ctrl+C，asyncio 會引發 KeyboardInterrupt
        
        # 啟動主異步函數
        loop.run_until_complete(main(args))

    except KeyboardInterrupt:
        logger.info("Ctrl+C detected. Stopping client...")
        stop_event.set()
        # 在這裡再次調用 run_until_complete 可能會導致問題
        # main 函數的 finally 塊應該處理清理
        # 給 finally 塊一點時間執行
        # loop.run_until_complete(asyncio.sleep(1)) # 可能不需要
    finally:
        # loop.close() # 在 run_until_complete 後通常不需要手動關閉
        logger.info("Event loop finished.")