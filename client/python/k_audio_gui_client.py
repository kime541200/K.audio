import tkinter
from tkinter import filedialog, messagebox
import customtkinter as ctk
import sounddevice as sd
import asyncio
import threading
import queue
import websockets
import json
import httpx
from pathlib import Path
from datetime import datetime
import logging
import platform
import ctypes

# --- 基本設定 ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

# --- DPI Awareness (Windows) ---
try:
    if platform.system() == "Windows":
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
        logger.info("Set DPI awareness for Windows.")
except Exception as e:
    logger.warning(f"Could not set DPI awareness: {e}")

# --- 音訊參數 ---
SAMPLE_RATE = 16000
CHANNELS = 1
DTYPE = 'int16'
MS_PER_FRAME = 30
SAMPLES_PER_FRAME = int(SAMPLE_RATE * MS_PER_FRAME / 1000)
BLOCK_SIZE = SAMPLES_PER_FRAME

# --- 主應用程式類 ---
class KAudioClientApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("K.audio Client")
        self.geometry("900x700") # 稍微再增大

        # --- 字體定義 ---
        # *** 修改點：定義字體 ***
        # 可以根據操作系統選擇不同字體
        system_name = platform.system()
        if system_name == "Windows":
            default_font_family = "Segoe UI"
            cjk_font_family = "Microsoft JhengHei UI" # 或 Microsoft YaHei UI
        elif system_name == "Darwin": # macOS
            default_font_family = "Helvetica Neue"
            cjk_font_family = "PingFang TC" # 或 PingFang SC
        else: # Linux or other
            default_font_family = "Ubuntu" # 或 Noto Sans, sans-serif
            cjk_font_family = "Noto Sans CJK TC" # 需要用戶安裝
        
        # 創建字體對象 (可選，也可以直接用元組)
        self.label_font = ctk.CTkFont(family=default_font_family, size=13)
        self.button_font = ctk.CTkFont(family=default_font_family, size=13, weight="bold")
        self.entry_font = ctk.CTkFont(family=cjk_font_family, size=13) # CJK 字體用於可能輸入中文的地方
        self.textbox_font = ctk.CTkFont(family=cjk_font_family, size=14) # 文本框用稍大字體



        # --- 狀態變數 ---
        self.is_recording = False
        self.async_thread = None
        self.websocket_client = None
        self.audio_stream = None
        # *** 修改點：移除在這裡創建 asyncio 對象 ***
        # self.stop_event = asyncio.Event()
        # self.audio_queue = asyncio.Queue()
        self.stop_event = None # 初始化為 None
        self.audio_queue = None # 初始化為 None
        self.gui_queue = queue.Queue() # GUI 隊列保持不變
        self.transcript_parts = []
        self.session_timestamp = None
        self.session_dir = None
        self.output_dir_var = ctk.StringVar(value="./k.audio_output")

        # --- UI 佈局 ---
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        # --- 頂部菜單欄 ---
        self.menu_frame = ctk.CTkFrame(self, height=30)
        self.menu_frame.grid(row=0, column=0, padx=10, pady=(10,0), sticky="ew")

        self.theme_label = ctk.CTkLabel(self.menu_frame, text="Appearance:", font=self.label_font) # <--- 應用字體
        self.theme_label.pack(side="left", padx=(10, 5))
        self.theme_menu = ctk.CTkOptionMenu(
            self.menu_frame,
            values=["System", "Light", "Dark"],
            command=self.change_appearance_mode,
            font=self.label_font # <--- 應用字體
        )
        self.theme_menu.pack(side="left", padx=5)

        # --- 設定框架 ---
        self.settings_frame = ctk.CTkFrame(self)
        self.settings_frame.grid(row=1, column=0, padx=10, pady=10, sticky="ew")
        self.settings_frame.grid_columnconfigure(1, weight=1)
        self.settings_frame.grid_columnconfigure(3, weight=1)
        # 列 0, 2, 4, 5 保持 weight=0

        # Row 0: URL
        self.url_label = ctk.CTkLabel(self.settings_frame, text="Server URL:")
        self.url_label.grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.url_entry = ctk.CTkEntry(self.settings_frame, placeholder_text="ws://<server_ip>:8000/v1/audio/transcriptions/ws")
        self.url_entry.grid(row=0, column=1, columnspan=4, padx=5, pady=5, sticky="ew") # 橫跨到第4列
        # *** 請修改為您的伺服器默認地址 ***
        self.url_entry.insert(0, "ws://localhost:8000/v1/audio/transcriptions/ws")

        # Row 1: Device & Output Directory
        self.device_label = ctk.CTkLabel(self.settings_frame, text="Input Device:")
        self.device_label.grid(row=1, column=0, padx=5, pady=5, sticky="w")
        self.device_options = self.get_input_devices()
        self.device_var = ctk.StringVar(value=self.get_default_input_device_name())
        self.device_menu = ctk.CTkOptionMenu(self.settings_frame, variable=self.device_var, values=list(self.device_options.keys()))
        self.device_menu.grid(row=1, column=1, padx=5, pady=5, sticky="ew")

        self.output_dir_label = ctk.CTkLabel(self.settings_frame, text="Output Dir:")
        self.output_dir_label.grid(row=1, column=2, padx=(10,5), pady=5, sticky="w")
        # 使用 textvariable 綁定 StringVar
        self.output_dir_entry = ctk.CTkEntry(self.settings_frame, textvariable=self.output_dir_var)
        self.output_dir_entry.grid(row=1, column=3, padx=5, pady=5, sticky="ew")
        self.browse_button = ctk.CTkButton(self.settings_frame, text="Browse...", command=self.browse_output_directory, width=80)
        self.browse_button.grid(row=1, column=4, padx=5, pady=5)

        # Row 2: Translation Options
        self.translate_var = ctk.BooleanVar()
        self.translate_checkbox = ctk.CTkCheckBox(self.settings_frame, text="Translate", variable=self.translate_var, command=self.toggle_translation_options)
        self.translate_checkbox.grid(row=2, column=0, padx=5, pady=5, sticky="w")

        self.target_lang_label = ctk.CTkLabel(self.settings_frame, text="Target:")
        self.target_lang_label.grid(row=2, column=1, padx=(5, 5), pady=5, sticky="e")
        self.target_lang_entry = ctk.CTkEntry(self.settings_frame, placeholder_text="en", width=60)
        self.target_lang_entry.grid(row=2, column=2, padx=5, pady=5, sticky="w")

        self.source_lang_label = ctk.CTkLabel(self.settings_frame, text="Source (Opt):")
        self.source_lang_label.grid(row=2, column=3, padx=(5, 5), pady=5, sticky="e")
        self.source_lang_entry = ctk.CTkEntry(self.settings_frame, placeholder_text="zh", width=60)
        self.source_lang_entry.grid(row=2, column=4, padx=5, pady=5, sticky="w")
        self.toggle_translation_options()

        # Control Buttons (Column 5)
        self.start_button = ctk.CTkButton(self.settings_frame, text="Start Recording", command=self.start_recording)
        self.start_button.grid(row=0, column=5, padx=10, pady=5, sticky="ew")
        self.stop_button = ctk.CTkButton(self.settings_frame, text="Stop Recording", command=self.stop_recording, state="disabled")
        self.stop_button.grid(row=1, column=5, padx=10, pady=5, sticky="ew")
        self.summarize_button = ctk.CTkButton(self.settings_frame, text="Summarize", command=self.summarize_transcript, state="disabled")
        self.summarize_button.grid(row=2, column=5, padx=10, pady=5, sticky="ew")

        # *** 新增：文件轉錄按鈕 ***
        self.transcribe_file_button = ctk.CTkButton(self.settings_frame, text="Transcribe File...", command=self.transcribe_file_button_clicked, font=self.button_font) # <-- Font
        self.transcribe_file_button.grid(row=0, column=6, padx=(5, 10), pady=5, sticky="ew") # 放在第 6 列


        # --- 文本顯示框架 ---
        self.display_frame = ctk.CTkFrame(self)
        self.display_frame.grid(row=2, column=0, padx=10, pady=(0, 10), sticky="nsew")
        self.display_frame.grid_columnconfigure(0, weight=1)
        self.display_frame.grid_columnconfigure(1, weight=1)
        self.display_frame.grid_rowconfigure(0, weight=1)

        # 文字稿文本框
        self.transcript_textbox = ctk.CTkTextbox(self.display_frame, wrap="word", state="disabled", font=self.textbox_font) # <-- Font
        self.transcript_textbox.grid(row=0, column=0, padx=(10, 5), pady=10, sticky="nsew")

        # 翻譯文本框
        self.translation_textbox = ctk.CTkTextbox(self.display_frame, wrap="word", state="disabled", font=self.textbox_font) # <-- Font
        self.translation_textbox.grid(row=0, column=1, padx=(5, 10), pady=10, sticky="nsew")

        # --- 狀態欄 ---
        self.status_label = ctk.CTkLabel(self, text="Status: Idle", anchor="w", height=20, font=self.label_font) # <-- Font
        self.status_label.grid(row=3, column=0, padx=10, pady=5, sticky="ew")

        # --- 配置 Textbox Tag 樣式 (保持不變) ---
        self.transcript_textbox.tag_config("error", foreground="red")
        self.translation_textbox.tag_config("error", foreground="red")

        # --- 啟動 GUI 隊列處理 ---
        self.process_gui_queue()

    # --- UI 輔助方法 ---
    def get_input_devices(self):
        devices = sd.query_devices()
        input_devices_dict = {}
        for i, d in enumerate(devices):
            if d['max_input_channels'] > 0:
                input_devices_dict[f"{i}: {d['name']}"] = i
        return input_devices_dict

    def get_default_input_device_name(self):
        try:
            default_idx = sd.default.device['input']
            if default_idx == -1: # -1 表示沒有預設輸入設備
                 raise sd.PortAudioError("No default input device found")
            default_device = sd.query_devices(default_idx, 'input')
            return f"{default_idx}: {default_device['name']}"
        except Exception as e:
            logger.error(f"Could not get default input device: {e}")
            options = list(self.get_input_devices().keys())
            return options[0] if options else ""

    def toggle_translation_options(self):
        if self.translate_var.get():
            self.target_lang_entry.configure(state="normal")
            self.source_lang_entry.configure(state="normal")
            # *** 新增：設置默認目標語言 ***
            if not self.target_lang_entry.get(): # 檢查是否為空
                self.target_lang_entry.insert(0, "en") # 插入 "en"
        else:
            self.target_lang_entry.configure(state="disabled")
            self.source_lang_entry.configure(state="disabled")

    def update_status(self, message):
        self.status_label.configure(text=f"Status: {message}")

    def browse_output_directory(self):
        dir_path = filedialog.askdirectory(initialdir=self.output_dir_var.get() or Path(".").resolve())
        if dir_path:
            self.output_dir_var.set(dir_path) # <--- 更新 StringVar
            logger.info(f"Output directory set to: {dir_path}")


    # *** 新增：實現 change_appearance_mode 方法 ***
    def change_appearance_mode(self, new_mode: str):
        """更改 CustomTkinter 的外觀模式"""
        new_mode_lower = new_mode.lower() # 確保是小寫
        ctk.set_appearance_mode(new_mode_lower)
        logger.info(f"Appearance mode changed to: {new_mode_lower}")

    # --- GUI 消息處理 (添加文件轉錄結果處理) ---
    def process_gui_queue(self):
        try:
            while True:
                message = self.gui_queue.get_nowait()
                msg_type = message.get("type")
                logger.debug(f"Processing GUI queue message: {message}")

                if msg_type == "summary_result":
                     logger.info("Processing summary_result message.") # <-- 添加日誌
                     summary = message.get("summary", "No summary content.")
                     self.show_summary_popup(summary) # <-- 調用彈窗
                     self.update_status("Summary received.")
                     # 重新啟用按鈕，確保即使彈窗有問題按鈕也能恢復
                     if not self.is_recording and self.transcript_parts:
                         self.summarize_button.configure(state="normal")

                elif msg_type == "enable_summary_button":
                     # 重新啟用按鈕的邏輯
                     if not self.is_recording and self.transcript_parts:
                         self.summarize_button.configure(state="normal")
                         logger.debug("Summarize button re-enabled via queue.")
                     else:
                          logger.debug("Conditions not met to re-enable summarize button via queue.")

                elif msg_type == "force_stop_ui":
                     if self.is_recording:
                          self.stop_recording()
                     self.update_status("Stopped due to error in background task.")

                # *** 新增：處理文件轉錄結果 ***
                elif msg_type == "file_transcription_result":
                     result_text = message.get("text", "No text found.")
                     file_path = message.get("file_path", "Unknown file")
                     self.show_file_transcription_popup(f"Result for: {Path(file_path).name}", result_text)
                     self.update_status(f"File transcription complete: {Path(file_path).name}")
                     self.transcribe_file_button.configure(state="normal") # 重新啟用按鈕
                elif msg_type == "file_transcription_error":
                     error_msg = message.get("error", "Unknown error")
                     file_path = message.get("file_path", "Unknown file")
                     messagebox.showerror("File Transcription Error", f"Failed to transcribe {Path(file_path).name}:\n{error_msg}")
                     self.update_status(f"Error transcribing file: {error_msg}")
                     self.transcribe_file_button.configure(state="normal") # 重新啟用按鈕
                else:
                     self.process_standard_message(message)

        except queue.Empty:
            pass
        finally:
            self.after(100, self.process_gui_queue)

    def process_standard_message(self, message):
         msg_type = message.get("type")
         if msg_type == "final":
             text = message.get("text", "")
             lang = message.get("language", "unk")
             self.transcript_textbox.configure(state="normal")
             self.transcript_textbox.insert("end", f"[{lang}] {text}\n")
             self.transcript_textbox.configure(state="disabled")
             self.transcript_textbox.see("end")
             self.transcript_parts.append(text) # 累積文字用於保存和總結
         elif msg_type == "translation":
             translated = message.get("translated_text", "")
             source = message.get("source_lang", "?")
             target = message.get("target_lang", "?")
             self.translation_textbox.configure(state="normal")
             self.translation_textbox.insert("end", f"[{source}->{target}] {translated}\n")
             self.translation_textbox.configure(state="disabled")
             self.translation_textbox.see("end")
         elif msg_type == "info":
              self.update_status(message.get('message', 'Info'))
         elif msg_type == "error":
              error_msg = message.get('message', 'Unknown')
              self.update_status(f"Error: {error_msg}")
              # 在兩個文本框都顯示錯誤可能有助於調試
              self.transcript_textbox.configure(state="normal")
              self.transcript_textbox.insert("end", f"[ERROR] {error_msg}\n", "error")
              self.transcript_textbox.configure(state="disabled")
              self.transcript_textbox.see("end")
              self.translation_textbox.configure(state="normal")
              self.translation_textbox.insert("end", f"[ERROR] {error_msg}\n", "error")
              self.translation_textbox.configure(state="disabled")
              self.translation_textbox.see("end")
         else:
              logger.warning(f"Received unknown message type in queue: {message}")

    def show_summary_popup(self, summary_text):
        try:
            logger.info("Attempting to show summary popup.") # <-- 添加日誌
            popup = ctk.CTkToplevel(self)
            popup.title("Summarization Result")
            popup.geometry("500x400")

            # 使其成為主窗口的瞬態窗口並獲取焦點
            popup.transient(self)
            popup.grab_set()

            textbox = ctk.CTkTextbox(popup, wrap="word", font=self.textbox_font) # 使用實例的字體
            textbox.pack(padx=10, pady=10, expand=True, fill="both")
            textbox.insert("1.0", summary_text)
            textbox.configure(state="disabled")

            close_button = ctk.CTkButton(popup, text="Close", command=popup.destroy, font=self.button_font)
            close_button.pack(pady=10)

            logger.info("Summary popup created successfully.") # <-- 添加日誌

            # 可以取消下面的註釋，讓主窗口等待彈窗關閉（會阻塞交互）
            # self.wait_window(popup)

        except Exception as e:
            logger.error(f"Error creating CTk summary popup: {e}", exc_info=True)
            # 如果 CTk 彈窗失敗，回退到標準的 messagebox
            try:
                 logger.info("Falling back to tkinter messagebox for summary.")
                 messagebox.showinfo("Summary Result", summary_text)
            except Exception as e_mb:
                 logger.error(f"Error showing summary messagebox: {e_mb}", exc_info=True)
                 # 連 messagebox 都失敗了，只能打印到控制台
                 print("\n--- Summary (Popup Failed) ---")
                 print(summary_text)
                 print("----------------------------")

    # *** 新增：顯示文件轉錄結果的彈窗 ***
    def show_file_transcription_popup(self, title, result_text):
        popup = ctk.CTkToplevel(self)
        popup.title(title)
        popup.geometry("600x400")
        popup.attributes("-topmost", True)

        textbox = ctk.CTkTextbox(popup, wrap="word", font=self.textbox_font) # 使用定義的字體
        textbox.pack(padx=10, pady=10, expand=True, fill="both")
        textbox.insert("1.0", result_text)
        textbox.configure(state="disabled")

        close_button = ctk.CTkButton(popup, text="Close", command=popup.destroy, font=self.button_font)
        close_button.pack(pady=10)

    # --- 按鈕回調 ---
    def start_recording(self):
        logger.info("Start button clicked.")

        # *** 修改點：每次開始時創建新的 asyncio 對象 ***
        self.audio_queue = asyncio.Queue()
        self.stop_event = asyncio.Event()
        # 確保 transcript_parts 被清空
        self.transcript_parts.clear()

        self.is_recording = True
        self.update_status("Connecting...")

        # *** 修改點：從 StringVar 獲取輸出目錄 ***
        output_dir_str = self.output_dir_var.get().strip()
        if not output_dir_str:
            self.update_status("Error: Output directory cannot be empty.")
            self.reset_ui_to_idle()
            return
        output_dir = Path(output_dir_str) # 在這裡轉為 Path 對象
        try:
             output_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
             logger.error(f"Error creating output directory {output_dir}: {e}")
             self.update_status(f"Error: Cannot create output directory: {e}")
             self.reset_ui_to_idle()
             return
        
        # --- 獲取配置 ---
        ws_url = self.url_entry.get().strip()
        selected_device_name = self.device_var.get()
        device_index = self.device_options.get(selected_device_name)
        translate_enabled = self.translate_var.get()
        target_lang = self.target_lang_entry.get().strip() if translate_enabled else None
        source_lang = self.source_lang_entry.get().strip() if translate_enabled and self.source_lang_entry.get().strip() else None

        # --- 參數檢查 ---
        if not ws_url or not ws_url.startswith("ws://"):
            self.update_status("Error: Invalid WebSocket URL.")
            self.reset_ui_to_idle() # 重置 UI
            return
        if device_index is None:
             self.update_status("Error: Invalid audio device selected.")
             self.reset_ui_to_idle()
             return
        if translate_enabled and not target_lang:
             self.update_status("Error: Target language required for translation.")
             self.reset_ui_to_idle()
             return

        # --- 更新 UI 狀態 ---
        self.url_entry.configure(state="disabled")
        self.device_menu.configure(state="disabled")
        self.translate_checkbox.configure(state="disabled")
        self.target_lang_entry.configure(state="disabled")
        self.source_lang_entry.configure(state="disabled")
        self.start_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        self.summarize_button.configure(state="disabled")
        self.transcript_textbox.configure(state="normal")
        self.transcript_textbox.delete("1.0", "end")
        self.transcript_textbox.configure(state="disabled")
        self.translation_textbox.configure(state="normal")
        self.translation_textbox.delete("1.0", "end")
        self.translation_textbox.configure(state="disabled")
        self.transcript_parts.clear()

        # 重置 stop_event
        self.stop_event.clear()

        # 在單獨線程中運行異步邏輯
        self.async_thread = threading.Thread(
            target=self.run_async_loop,
            args=(ws_url, device_index, translate_enabled, target_lang, source_lang),
            daemon=True
        )
        self.async_thread.start()

    def stop_recording(self):
        logger.info("Stop button clicked.")
        # *** 修改點：檢查 stop_event 是否存在 ***
        if self.is_recording and self.stop_event:
            self.stop_event.set() # 通知異步任務停止
        # else: # 如果 stop_event 還沒創建就點了 stop (不太可能，但可以加個保護)
        #     logger.warning("Stop clicked but recording not fully started or already stopped.")

        # --- 文件保存 ---
        if self.transcript_parts:
            full_transcript = "\n".join(self.transcript_parts)
            self.session_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            
            # *** 修改點：從 StringVar 獲取輸出目錄 ***
            current_output_dir = Path(self.output_dir_var.get().strip() or "./k.audio_output")
            self.session_dir = current_output_dir / self.session_timestamp
            try:
                self.session_dir.mkdir(parents=True, exist_ok=True)
                transcript_file_path = self.session_dir / "transcript.txt"
                with open(transcript_file_path, "w", encoding="utf-8") as f:
                    f.write(full_transcript)
                logger.info(f"Transcript saved to: {transcript_file_path}")
                self.update_status(f"Stopped. Transcript saved.")
                self.summarize_button.configure(state="normal")
            except Exception as e: # 更廣泛地捕獲目錄創建和文件寫入錯誤
                 logger.error(f"Failed to create directory or save transcript file: {e}")
                 self.update_status(f"Error saving transcript: {e}")
                 self.summarize_button.configure(state="disabled")
        else:
            self.update_status("Stopped. No transcript recorded.")
            self.summarize_button.configure(state="disabled")
            logger.info("No transcript recorded.")

        self.reset_ui_to_idle() # 重置 UI

    def reset_ui_to_idle(self):
        """將 UI 組件重置回未錄製狀態"""
        self.is_recording = False
        self.url_entry.configure(state="normal")
        self.device_menu.configure(state="normal")
        self.translate_checkbox.configure(state="normal")
        self.toggle_translation_options() # 根據 checkbox 狀態設置語言框
        self.start_button.configure(state="normal")
        self.stop_button.configure(state="disabled")
        # summarize_button 的狀態由 stop_recording 根據是否有內容決定

    def summarize_transcript(self):
        logger.info("Summarize button clicked.")
        if not self.transcript_parts:
            logger.warning("No transcript available to summarize.")
            self.update_status("No transcript to summarize.")
            return
        if not self.session_dir or not (self.session_dir / "transcript.txt").exists():
             # 如果 session_dir 未設置或文件不存在 (理論上不應發生)
             logger.error("Transcript file path is missing or file not found for summarization.")
             self.update_status("Error: Transcript file missing.")
             return

        self.update_status("Requesting summary...")
        self.summarize_button.configure(state="disabled") # 防止重複點擊

        # 從內存獲取文字稿
        full_transcript = "\n".join(self.transcript_parts)

        # 獲取伺服器 HTTP URL
        ws_url = self.url_entry.get().strip()
        if not ws_url.startswith("ws://"):
            logger.error("Invalid WebSocket URL for summarization.")
            self.update_status("Error: Invalid server URL.")
            self.summarize_button.configure(state="normal") # 恢復按鈕
            return
        # 更健壯的 URL 替換
        base_url = ws_url.split('/v1/audio/transcriptions/ws')[0]
        server_http_url = base_url.replace("ws://", "http://", 1)

        # 在背景線程執行同步 HTTP 請求
        threading.Thread(target=self.run_summarization_sync, args=(server_http_url, full_transcript), daemon=True).start()

    def run_summarization_sync(self, server_http_url, full_transcript):
        """在新線程中執行同步的總結請求"""
        try:
            summary_text = self.request_summarization_sync(server_http_url, full_transcript)
            if summary_text:
                 # 保存摘要文件
                 if self.session_dir:
                     summary_file_path = self.session_dir / "summary.txt"
                     try:
                         with open(summary_file_path, "w", encoding="utf-8") as f:
                             f.write(summary_text)
                         logger.info(f"Summary saved to: {summary_file_path}")
                     except IOError as e:
                         logger.error(f"Failed to save summary file: {e}")

                 # 將結果放回 GUI 隊列顯示
                 self.gui_queue.put({"type": "summary_result", "summary": summary_text})
            else:
                 self.gui_queue.put({"type": "status", "message": "Failed to retrieve summary."})
        except Exception as e:
             logger.error(f"Error running sync summarization task: {e}", exc_info=True)
             self.gui_queue.put({"type": "status", "message": f"Summarization error: {e}"})
        finally:
             # 重新啟用按鈕
             self.gui_queue.put({"type": "enable_summary_button"})


    # *** 新增：文件轉錄按鈕的回調 ***
    def transcribe_file_button_clicked(self):
        logger.info("Transcribe file button clicked.")
        # 彈出文件選擇對話框
        filepath = filedialog.askopenfilename(
            title="Select Audio File",
            filetypes=(("Audio Files", "*.wav *.mp3 *.m4a *.ogg *.flac"), ("All Files", "*.*"))
        )
        if not filepath:
            logger.info("File selection cancelled.")
            return

        logger.info(f"Selected file: {filepath}")
        self.update_status(f"Uploading and transcribing {Path(filepath).name}...")
        self.transcribe_file_button.configure(state="disabled") # 禁用按鈕防止重複點擊

        # 獲取伺服器 HTTP URL
        ws_url = self.url_entry.get().strip()
        if not ws_url.startswith("ws://"):
            logger.error("Invalid WebSocket URL.")
            messagebox.showerror("Error", "Invalid Server WebSocket URL.")
            self.update_status("Error: Invalid server URL.")
            self.transcribe_file_button.configure(state="normal")
            return
        base_url = ws_url.split('/v1/audio/transcriptions/ws')[0]
        server_http_url = base_url.replace("ws://", "http://", 1)

        # 在背景線程執行文件上傳和轉錄請求
        threading.Thread(target=self.run_file_transcription_sync, args=(server_http_url, filepath), daemon=True).start()

    # *** 新增：在新線程中執行文件轉錄請求的函數 ***
    def run_file_transcription_sync(self, server_http_url: str, filepath: str):
        """在新線程中執行同步的文件轉錄請求"""
        transcription_url = f"{server_http_url}/v1/audio/transcriptions"
        logger.info(f"Requesting file transcription from: {transcription_url}")
        files = None
        try:
            # 準備文件和可能的表單數據
            files = {'file': (Path(filepath).name, open(filepath, 'rb'))}
            # 可以添加其他參數，如語言或響應格式
            data = {'response_format': 'verbose_json'} # 獲取詳細信息

            with httpx.Client() as client:
                response = client.post(
                    transcription_url,
                    files=files,
                    data=data, # 將其他參數放在 data 中
                    timeout=300.0 # 文件轉錄可能需要更長時間
                )
                response.raise_for_status()
                result = response.json()
                # 根據 verbose_json 格式提取文本
                transcribed_text = result.get("text", "Transcription finished, but no text found.")
                # 可以獲取更多信息，例如 result.get("language"), result.get("duration")
                logger.info(f"File transcription successful for {filepath}")
                # 將結果放入 GUI 隊列
                self.gui_queue.put({"type": "file_transcription_result", "text": transcribed_text, "file_path": filepath})

        except httpx.HTTPStatusError as e:
             error_detail = e.response.text[:500] # 獲取部分錯誤細節
             logger.error(f"HTTP error during file transcription: {e.response.status_code} - {error_detail}")
             self.gui_queue.put({"type": "file_transcription_error", "error": f"Server Error {e.response.status_code}: {error_detail}", "file_path": filepath})
        except httpx.RequestError as e:
             logger.error(f"Request error during file transcription: {e}")
             self.gui_queue.put({"type": "file_transcription_error", "error": f"Connection Error: {e}", "file_path": filepath})
        except FileNotFoundError:
             logger.error(f"File not found: {filepath}")
             self.gui_queue.put({"type": "file_transcription_error", "error": "File not found.", "file_path": filepath})
        except Exception as e:
             logger.error(f"Unexpected error during file transcription: {e}", exc_info=True)
             self.gui_queue.put({"type": "file_transcription_error", "error": f"Unexpected error: {e}", "file_path": filepath})
        finally:
            # 確保文件被關閉
            if files and 'file' in files and hasattr(files['file'][1], 'close'):
                files['file'][1].close()

    # --- 同步的 HTTP 請求函數 (移入類中) ---
    def request_summarization_sync(self, server_http_url: str, text: str) -> str | None:
        """(同步) 向 K.audio 伺服器請求文本摘要"""
        summarization_url = f"{server_http_url}/v1/summarizations"
        logger.info(f"Requesting summarization sync from: {summarization_url}")
        try:
            with httpx.Client() as client:
                response = client.post(
                    summarization_url,
                    json={"text": text},
                    headers={"Content-Type": "application/json", "accept": "application/json"},
                    timeout=120.0
                )
                response.raise_for_status()
                result = response.json()
                if "summary" in result:
                    logger.info("Summarization sync successful.")
                    return result["summary"]
                else:
                    logger.error(f"Summarization response missing 'summary' key: {result}")
                    return None
        except httpx.HTTPStatusError as e:
             logger.error(f"HTTP error during summarization sync request: {e.response.status_code} - {e.response.text}")
             return None
        except httpx.RequestError as e:
             logger.error(f"Request error during summarization sync request: {e}")
             return None
        except Exception as e:
             logger.error(f"Unexpected error during summarization sync request: {e}", exc_info=True)
             return None

    # --- 異步處理的核心邏輯 ---
    def run_async_loop(self, ws_url, device_index, translate, target_lang, source_lang):
        """在單獨線程中運行 asyncio 事件循環"""
        # *** 這個函數現在只負責設置和運行 loop ***
        # *** asyncio 對象的創建移到 start_recording ***
        loop = None # 初始化
        try:
             logger.info("Starting new asyncio event loop in background thread.")
             loop = asyncio.new_event_loop()
             asyncio.set_event_loop(loop)
             # *** 注意：websocket_logic 現在需要知道使用哪個 queue 和 event ***
             # *** 我們仍然使用 self.audio_queue 和 self.stop_event ***
             # *** 因為它們在 start_recording 中被重新創建了 ***
             loop.run_until_complete(self.websocket_logic(ws_url, device_index, translate, target_lang, source_lang))
        except Exception as e:
             logger.error(f"Error in async loop thread: {e}", exc_info=True)
             # 使用 put_nowait 因為我們可能不在事件循環中
             self.gui_queue.put_nowait({"type": "status", "message": f"Runtime Error: {e}"})
             self.gui_queue.put_nowait({"type": "force_stop_ui"})
        finally:
             if loop:
                 loop.close()


    async def websocket_logic(self, ws_url, device_index, translate, target_lang, source_lang):
        """實際的 WebSocket 連接、音訊流和任務管理"""
        self.audio_stream = None
        sender_task = None
        receiver_task = None
        stop_event_task = None # <--- 確保 stop_event_task 在這裡創建

        # 構建帶參數的 URL
        query_params = []
        if translate:
            query_params.append("translate=true")
            if target_lang: query_params.append(f"target_lang={target_lang}")
            if source_lang: query_params.append(f"source_lang={source_lang}")
        if query_params:
            ws_url += "?" + "&".join(query_params)
        logger.info(f"Thread connecting to WebSocket: {ws_url}")

        try:
            async with websockets.connect(ws_url) as websocket:
                self.websocket_client = websocket
                # *** 使用 put_nowait 將狀態放入 GUI 隊列 ***
                self.gui_queue.put_nowait({"type": "status", "message": "Connected. Recording..."})
                loop = asyncio.get_running_loop() # 獲取當前 (由 run_async_loop 設置的) 循環

                def thread_safe_audio_callback(indata, frames, time, status):
                    if status: logger.warning(f"Sounddevice status: {status}")
                    try:
                        # 使用 loop.call_soon_threadsafe 將 put 操作安排到 asyncio 循環中
                        loop.call_soon_threadsafe(self.audio_queue.put_nowait, indata.tobytes())
                    except queue.Full: # 標準 queue 用 Queue.Full
                        logger.warning("Audio queue is full, dropping frame.")
                    except RuntimeError as e: # 捕獲 loop is closed 的錯誤
                         if "Event loop is closed" in str(e):
                             logger.warning("Audio callback called but event loop is closed.")
                         else:
                             logger.error(f"Error in thread_safe_audio_callback: {e}")
                    except Exception as e:
                         logger.error(f"Error in thread_safe_audio_callback: {e}")

                self.audio_stream = sd.InputStream(
                    samplerate=SAMPLE_RATE, blocksize=BLOCK_SIZE,
                    device=device_index, channels=CHANNELS,
                    dtype=DTYPE, callback=thread_safe_audio_callback
                )
                self.audio_stream.start()
                logger.info("Audio input stream started in thread.")

                # 使用當前循環創建任務，引用 self.audio_queue 和 self.stop_event
                sender_task = asyncio.create_task(self.sender(websocket))
                receiver_task = asyncio.create_task(self.gui_receiver(websocket))
                stop_event_task = asyncio.create_task(self.stop_event.wait(), name="StopEventWaitTask") # 使用 self.stop_event

                # 等待停止事件或任一任務先完成 (保持不變)
                done, pending = await asyncio.wait(
                    {sender_task, receiver_task, stop_event_task},
                    return_when=asyncio.FIRST_COMPLETED
                )

                # 檢查是哪個任務先完成
                if stop_event_task in done:
                    logger.info("Stop event triggered websocket_logic completion.")
                else:
                     # 可能是 sender 或 receiver 異常結束
                     logger.warning(f"Sender or Receiver task finished unexpectedly. Triggering stop.")
                     self.stop_event.set() # 確保停止事件被設置

                # --- 異步清理 ---
                logger.info("Starting async cleanup in websocket_logic...")

                # 1. **優先停止音訊流**
                if self.audio_stream and self.audio_stream.active:
                    logger.info("Stopping audio stream...")
                    self.audio_stream.stop()
                    self.audio_stream.close()
                    logger.info("Audio stream stopped in async cleanup.")
                    self.audio_stream = None
                else:
                     logger.info("Audio stream already inactive or not started.")

                # 2. 取消仍在運行的任務
                logger.info("Cancelling pending tasks...")
                for task in pending:
                    # if task and not task.done(): # 檢查是否是 Task 且未完成 (pending 集合理論上都是未完成的)
                    logger.debug(f"Cancelling task: {task.get_name()}")
                    task.cancel()

                # 等待所有任務（包括被取消的）完成其最終處理
                await asyncio.gather(*pending, return_exceptions=True)
                logger.info("Pending tasks gathered after cancellation.")


        except Exception as e:
             logger.error(f"WebSocket logic failed: {e}", exc_info=True)
             self.gui_queue.put({"type": "status", "message": f"Connection Error: {e}"})
        finally:
            logger.info("Exiting websocket_logic.")
            # 再次確保音訊流已停止，以防異常跳轉到 finally
            if self.audio_stream and self.audio_stream.active:
                 try:
                     logger.warning("Stopping audio stream in final finally block.")
                     self.audio_stream.stop()
                     self.audio_stream.close()
                 except Exception as e_stop:
                     logger.error(f"Error stopping stream in final finally block: {e_stop}")
                 self.audio_stream = None
            # *** 使用 put_nowait ***
            if not self.stop_event.is_set():
                 self.gui_queue.put_nowait({"type": "force_stop_ui"})


    # --- sender 和 receiver 作為類的方法 ---
    async def sender(self, websocket):
        """從隊列中獲取音訊數據並通過 WebSocket 發送"""
        logger.info("Sender task started.")
        try:
            while not self.stop_event.is_set():
                try:
                    # 從 asyncio 隊列獲取數據
                    chunk = await asyncio.wait_for(self.audio_queue.get(), timeout=0.1)
                    await websocket.send(chunk)
                    self.audio_queue.task_done()
                except asyncio.TimeoutError:
                    continue
                except asyncio.CancelledError:
                    logger.info("Sender task cancelled.")
                    break
                except Exception as e:
                    logger.error(f"Error in sender task: {e}", exc_info=True)
                    break
            # *** 修正點：檢查 websocket 是否關閉 ***
            if not websocket.closed: # <--- 使用 .closed 屬性
                 logger.info("Attempting to send STREAM_END signal...")
                 try:
                      await websocket.send("STREAM_END")
                      logger.info("STREAM_END signal sent.")
                 except Exception as e:
                      logger.warning(f"Could not send STREAM_END signal: {e}")
            else:
                logger.info("WebSocket already closed, cannot send STREAM_END.")

        except websockets.exceptions.ConnectionClosedOK:
             logger.info("WebSocket connection closed normally by server (sender).")
        except websockets.exceptions.ConnectionClosedError as e:
             logger.error(f"WebSocket connection closed with error (sender): {e}")
        except Exception as e:
            logger.error(f"Unexpected error in sender task: {e}", exc_info=True)
        finally:
            logger.info("Sender task finished.")


    async def gui_receiver(self, websocket):
        """接收 WebSocket 消息並放入 GUI 隊列"""
        logger.info("GUI Receiver task started.")
        # 不需要全局 transcript_parts，消息由 GUI 隊列處理器累積
        try:
            async for message in websocket:
                try:
                    data = json.loads(message)
                    self.gui_queue.put_nowait(data) # <--- 使用 put_nowait
                except json.JSONDecodeError:
                    logger.warning(f"Received non-JSON message: {message}")
                    self.gui_queue.put({"type": "error", "message": f"Received invalid data: {message[:100]}"})
                except asyncio.CancelledError:
                    logger.info("GUI Receiver task cancelled.")
                    break
                except Exception as e:
                    logger.error(f"Error processing received message in GUI receiver: {e}", exc_info=True)
                    self.gui_queue.put({"type": "error", "message": f"Processing error: {e}"})
        except websockets.exceptions.ConnectionClosedOK:
            logger.info("WebSocket connection closed normally (GUI receiver).")
        except websockets.exceptions.ConnectionClosedError as e:
            logger.error(f"WebSocket connection closed with error (GUI receiver): {e}")
            self.gui_queue.put({"type": "status", "message": f"Connection Closed: {e}"})
        except Exception as e:
            logger.error(f"Unexpected error in GUI receiver task: {e}", exc_info=True)
            self.gui_queue.put({"type": "status", "message": f"Receiver Error: {e}"})
        finally:
            logger.info("GUI Receiver task finished.")


# --- 主程序入口 ---
if __name__ == "__main__":
    # 設置 CustomTkinter 默認外觀
    ctk.set_appearance_mode("System") # 默認跟隨系統
    ctk.set_default_color_theme("blue")

    # 啟動應用
    app = KAudioClientApp()
    app.mainloop()

    logger.info("GUI Application finished.")