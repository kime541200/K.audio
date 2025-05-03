import tkinter
from tkinter import filedialog, messagebox
from tkinter import ttk # <--- 導入 ttk 用於 PanedWindow
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
import numpy as np
import wave
import io

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
        self.geometry("900x750")

        # --- 字體定義 ---
        system_name = platform.system()
        if system_name == "Windows":
            default_font_family = "Segoe UI"
            cjk_font_family = "Microsoft JhengHei UI"
        elif system_name == "Darwin":
            default_font_family = "Helvetica Neue"
            cjk_font_family = "PingFang TC"
        else: # Linux or other
            default_font_family = "Ubuntu"
            cjk_font_family = "Noto Sans CJK TC"

        self.label_font = ctk.CTkFont(family=default_font_family, size=13)
        self.button_font = ctk.CTkFont(family=default_font_family, size=13, weight="bold")
        self.entry_font = ctk.CTkFont(family=cjk_font_family, size=13)
        self.textbox_font = ctk.CTkFont(family=cjk_font_family, size=14)

        # --- 狀態變數 ---
        self.is_recording = False
        self.async_thread = None
        self.websocket_client = None
        self.audio_stream = None
        self.stop_event = None
        self.audio_queue = None
        self.gui_queue = queue.Queue()
        self.transcript_parts = []
        self.session_timestamp = None
        self.session_dir = None
        self.output_dir_var = ctk.StringVar(value="./k.audio_output")
        self.available_voices_list = []
        self.tts_voice_var = ctk.StringVar(value="Loading...")
        self.voice_checkbox_vars = {}
        self.conversation_mode_var = ctk.BooleanVar() # <--- 初始化對話模式變量
        self.right_pane_label_var = ctk.StringVar(value="Translation") # <--- 初始化右側窗格標籤變量

        # --- UI 佈局 ---
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1) # PanedWindow 在第 3 行

        # --- 頂部菜單欄 ---
        self.menu_frame = ctk.CTkFrame(self, height=30)
        self.menu_frame.grid(row=0, column=0, padx=10, pady=(10,0), sticky="ew")
        self.theme_label = ctk.CTkLabel(self.menu_frame, text="Appearance:", font=self.label_font)
        self.theme_label.pack(side="left", padx=(10, 5))
        self.theme_menu = ctk.CTkOptionMenu(
            self.menu_frame, values=["System", "Light", "Dark"],
            command=self.change_appearance_mode, font=self.label_font
        )
        self.theme_menu.pack(side="left", padx=5)

        # --- 設定框架 ---
        self.settings_frame = ctk.CTkFrame(self)
        self.settings_frame.grid(row=1, column=0, padx=10, pady=10, sticky="ew")
        self.settings_frame.grid_columnconfigure(1, weight=1)
        self.settings_frame.grid_columnconfigure(3, weight=1)

        # Row 0: URL
        self.url_label = ctk.CTkLabel(self.settings_frame, text="Server URL:", font=self.label_font)
        self.url_label.grid(row=0, column=0, padx=5, pady=5, sticky="w")
        self.url_entry = ctk.CTkEntry(self.settings_frame, placeholder_text="ws://<server_ip>:8000/v1/audio/transcriptions/ws", font=self.entry_font)
        self.url_entry.grid(row=0, column=1, columnspan=4, padx=5, pady=5, sticky="ew")
        self.url_entry.insert(0, "ws://localhost:8000/v1/audio/transcriptions/ws") # 使用 localhost 作為更通用的默認值

        # Row 1: Device & Output Directory
        self.device_label = ctk.CTkLabel(self.settings_frame, text="Input Device:", font=self.label_font)
        self.device_label.grid(row=1, column=0, padx=5, pady=5, sticky="w")
        self.device_options = self.get_input_devices()
        self.device_var = ctk.StringVar(value=self.get_default_input_device_name())
        self.device_menu = ctk.CTkOptionMenu(self.settings_frame, variable=self.device_var, values=list(self.device_options.keys()), font=self.label_font)
        self.device_menu.grid(row=1, column=1, padx=5, pady=5, sticky="ew")
        self.output_dir_label = ctk.CTkLabel(self.settings_frame, text="Output Dir:", font=self.label_font)
        self.output_dir_label.grid(row=1, column=2, padx=(10,5), pady=5, sticky="w")
        self.output_dir_entry = ctk.CTkEntry(self.settings_frame, textvariable=self.output_dir_var, font=self.entry_font)
        self.output_dir_entry.grid(row=1, column=3, padx=5, pady=5, sticky="ew")
        self.browse_button = ctk.CTkButton(self.settings_frame, text="Browse...", command=self.browse_output_directory, width=80, font=self.button_font)
        self.browse_button.grid(row=1, column=4, padx=5, pady=5)

        # Row 2: Translation Options
        self.translate_var = ctk.BooleanVar()
        self.translate_checkbox = ctk.CTkCheckBox(self.settings_frame, text="Translate", variable=self.translate_var, command=self.toggle_translation_options, font=self.label_font)
        self.translate_checkbox.grid(row=2, column=0, padx=5, pady=5, sticky="w")
        self.target_lang_label = ctk.CTkLabel(self.settings_frame, text="Target:", font=self.label_font)
        self.target_lang_label.grid(row=2, column=1, padx=(5, 5), pady=5, sticky="e")
        self.target_lang_entry = ctk.CTkEntry(self.settings_frame, placeholder_text="en", width=60, font=self.entry_font)
        self.target_lang_entry.grid(row=2, column=2, padx=5, pady=5, sticky="w")
        self.source_lang_label = ctk.CTkLabel(self.settings_frame, text="Source (Opt):", font=self.label_font)
        self.source_lang_label.grid(row=2, column=3, padx=(5, 5), pady=5, sticky="e")
        self.source_lang_entry = ctk.CTkEntry(self.settings_frame, placeholder_text="zh", width=60, font=self.entry_font)
        self.source_lang_entry.grid(row=2, column=4, padx=5, pady=5, sticky="w")

        # Row 3: Conversation Mode
        self.conversation_checkbox = ctk.CTkCheckBox(
            self.settings_frame, text="Conversation Mode", variable=self.conversation_mode_var,
            font=self.label_font, command=self.toggle_conversation_mode
        )
        self.conversation_checkbox.grid(row=3, column=0, columnspan=2, padx=5, pady=5, sticky="w")

        # Control Buttons (Column 5)
        self.start_button = ctk.CTkButton(self.settings_frame, text="Start Recording", command=self.start_recording, font=self.button_font)
        self.start_button.grid(row=0, column=5, padx=10, pady=5, sticky="ew")
        self.stop_button = ctk.CTkButton(self.settings_frame, text="Stop Recording", command=self.stop_recording, state="disabled", font=self.button_font)
        self.stop_button.grid(row=1, column=5, padx=10, pady=5, sticky="ew")
        self.summarize_button = ctk.CTkButton(self.settings_frame, text="Summarize", command=self.summarize_transcript, state="disabled", font=self.button_font)
        self.summarize_button.grid(row=2, column=5, padx=10, pady=5, sticky="ew")
        self.transcribe_file_button = ctk.CTkButton(self.settings_frame, text="Transcribe File...", command=self.transcribe_file_button_clicked, font=self.button_font)
        self.transcribe_file_button.grid(row=0, column=6, padx=(5, 10), pady=5, sticky="ew")
        # --- TTS 控制框架 ---
        self.tts_frame = ctk.CTkFrame(self)
        self.tts_frame.grid(row=2, column=0, padx=10, pady=(0, 10), sticky="ew")
        self.tts_frame.grid_columnconfigure(1, weight=1)
        self.tts_label = ctk.CTkLabel(self.tts_frame, text="Text to Speech:", font=self.label_font)
        self.tts_label.grid(row=0, column=0, padx=5, pady=(10, 0), sticky="nw")
        self.tts_input_textbox = ctk.CTkTextbox(self.tts_frame, height=80, wrap="word", font=self.textbox_font)
        self.tts_input_textbox.grid(row=0, column=1, padx=5, pady=(10, 5), sticky="ew")
        self.tts_input_textbox.insert("1.0", "Hello world! This is a test.")
        self.tts_input_textbox.configure(state="disabled")
        self.tts_options_frame = ctk.CTkFrame(self.tts_frame)
        self.tts_options_frame.grid(row=1, column=1, padx=5, pady=(0, 10), sticky="ew")
        self.tts_voice_label = ctk.CTkLabel(self.tts_options_frame, text="Voice(s):", font=self.label_font)
        self.tts_voice_label.pack(side="left", padx=(0, 5))
        self.selected_voice_display = ctk.CTkLabel( # *** 修正：移除重複的定義 ***
            self.tts_options_frame, textvariable=self.tts_voice_var, font=self.label_font, anchor="w"
        )
        self.selected_voice_display.pack(side="left", padx=5, fill="x", expand=True)
        self.select_voice_button = ctk.CTkButton(
            self.tts_options_frame, text="Select Voice(s)...", command=self.open_voice_selection_popup,
            font=self.button_font, width=120
        )
        self.select_voice_button.pack(side="left", padx=5)
        self.select_voice_button.configure(state="disabled")
        self.retry_load_voices_button = ctk.CTkButton(self.tts_options_frame, text="Retry Load", command=self.init_load_voices, font=self.button_font, width=80)
        self.retry_load_voices_button.pack(side="left", padx=(5,0))
        self.retry_load_voices_button.pack_forget()
        self.speak_button = ctk.CTkButton(self.tts_options_frame, text="Speak", command=self.synthesize_and_play, font=self.button_font)
        self.speak_button.pack(side="left", padx=10)
        self.speak_button.configure(state="disabled")

        # --- 使用 PanedWindow 替代 display_frame ---
        self.paned_window = ttk.PanedWindow(self, orient=tkinter.HORIZONTAL)
        self.paned_window.grid(row=3, column=0, padx=10, pady=(0, 10), sticky="nsew")
        self.transcript_pane_frame = ctk.CTkFrame(self.paned_window, corner_radius=0)
        self.translation_pane_frame = ctk.CTkFrame(self.paned_window, corner_radius=0)
        self.paned_window.add(self.transcript_pane_frame, weight=1)
        self.paned_window.add(self.translation_pane_frame, weight=1)

        # --- 在左右框架內添加標籤和文本框 ---
        self.transcript_pane_frame.grid_rowconfigure(1, weight=1)
        self.transcript_pane_frame.grid_columnconfigure(0, weight=1)
        self.transcript_label = ctk.CTkLabel(self.transcript_pane_frame, text="Transcript", font=self.label_font)
        self.transcript_label.grid(row=0, column=0, padx=5, pady=(5,0), sticky="w")
        self.transcript_textbox = ctk.CTkTextbox(self.transcript_pane_frame, wrap="word", state="disabled", font=self.textbox_font)
        self.transcript_textbox.grid(row=1, column=0, padx=5, pady=(0,5), sticky="nsew")

        # --- 翻譯窗格的佈局和標籤 ---
        self.translation_pane_frame.grid_rowconfigure(1, weight=1)
        self.translation_pane_frame.grid_columnconfigure(0, weight=1)
        # self.translation_label = ctk.CTkLabel(self.translation_pane_frame, text="Translation", font=self.label_font) # 舊標籤
        # 使用 StringVar 控制標籤文本
        self.right_pane_label = ctk.CTkLabel(self.translation_pane_frame, textvariable=self.right_pane_label_var, font=self.label_font)
        self.right_pane_label.grid(row=0, column=0, padx=5, pady=(5,0), sticky="w")
        self.translation_textbox = ctk.CTkTextbox(self.translation_pane_frame, wrap="word", state="disabled", font=self.textbox_font)
        self.translation_textbox.grid(row=1, column=0, padx=5, pady=(0,5), sticky="nsew")

        # --- 狀態欄 ---
        self.status_label = ctk.CTkLabel(self, text="Status: Idle", anchor="w", height=20, font=self.label_font)
        self.status_label.grid(row=4, column=0, padx=10, pady=5, sticky="ew")

        # --- Tag 配置 ---
        self.transcript_textbox.tag_config("error", foreground="red")
        self.translation_textbox.tag_config("error", foreground="red")

        # Initial state based on checkboxes
        self.toggle_translation_options()
        self.toggle_conversation_mode()

        # --- 啟動 GUI 隊列處理 & 加載聲音 ---
        self.process_gui_queue()
        self.after(100, self.init_load_voices)

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

    def browse_output_directory(self):
        dir_path = filedialog.askdirectory(initialdir=self.output_dir_var.get() or Path(".").resolve())
        if dir_path:
            self.output_dir_var.set(dir_path) # <--- 更新 StringVar
            logger.info(f"Output directory set to: {dir_path}")

    # --- 實現 change_appearance_mode 方法 ---
    def change_appearance_mode(self, new_mode: str):
        """更改 CustomTkinter 的外觀模式"""
        new_mode_lower = new_mode.lower() # 確保是小寫
        ctk.set_appearance_mode(new_mode_lower)
        logger.info(f"Appearance mode changed to: {new_mode_lower}")

    def toggle_translation_options(self):
        # *** 修改：檢查對話模式狀態 ***
        # 只有在非對話模式下，翻譯選項才可能啟用
        can_enable_translate = not self.conversation_mode_var.get()
        translate_checked = self.translate_var.get()

        if translate_checked and can_enable_translate:
            self.target_lang_entry.configure(state="normal")
            self.source_lang_entry.configure(state="normal")
            if not self.target_lang_entry.get():
                self.target_lang_entry.insert(0, "en")
        else:
            # 如果對話模式啟用或翻譯未勾選，都禁用
            self.target_lang_entry.configure(state="disabled")
            self.source_lang_entry.configure(state="disabled")
    
    # --- 切換對話模式的 UI 邏輯 ---
    def toggle_conversation_mode(self):
        if self.conversation_mode_var.get():
            # 進入對話模式
            self.right_pane_label_var.set("LLM Response") # 更新標籤
            # 禁用翻譯相關（如果之前未禁用）
            self.translate_checkbox.configure(state="disabled")
            self.translate_var.set(False) # 取消勾選
            self.toggle_translation_options() # 確保語言輸入框被禁用
            # 禁用其他按鈕
            self.summarize_button.configure(state="disabled")
            self.transcribe_file_button.configure(state="disabled")
        else:
            # 退出對話模式
            self.right_pane_label_var.set("Translation") # 恢復標籤
            # 啟用翻譯相關
            self.translate_checkbox.configure(state="normal")
            self.toggle_translation_options() # 根據翻譯勾選框恢復
            # 恢復其他按鈕狀態
            self.transcribe_file_button.configure(state="normal")
            if self.transcript_parts and not self.is_recording: # 只有在有記錄且未錄音時才啟用總結
                self.summarize_button.configure(state="normal")
            else:
                self.summarize_button.configure(state="disabled")

    def update_status(self, message):
        self.status_label.configure(text=f"Status: {message}")

    # --- 加載聲音列表的方法 ---
    def load_voices_from_server(self):
        """從 K.audio 伺服器獲取聲音列表並更新變數和 UI"""
        logger.info("Attempting to load voices from server...")
        self.tts_voice_var.set("Loading...")
        if hasattr(self, 'select_voice_button'): self.select_voice_button.configure(state="disabled")
        if hasattr(self, 'speak_button'): self.speak_button.configure(state="disabled")
        if hasattr(self, 'tts_input_textbox'): self.tts_input_textbox.configure(state="disabled")
        if hasattr(self, 'retry_load_voices_button'): self.retry_load_voices_button.pack_forget()

        ws_url = self.url_entry.get().strip()
        if not ws_url.startswith("ws://"):
            logger.error("Cannot load voices: Invalid WebSocket URL.")
            self.update_status("Error: Cannot load voices - Invalid URL")
            self.tts_voice_var.set("Error loading")
            if hasattr(self, 'retry_load_voices_button'): self.retry_load_voices_button.pack(side="left", padx=(5,0))
            if hasattr(self, 'select_voice_button'): self.select_voice_button.configure(state="disabled")
            return

        base_url = ws_url.split('/v1/audio/transcriptions/ws')[0]
        server_http_url = base_url.replace("ws://", "http://", 1)
        voices_url = f"{server_http_url}/v1/audio/voices"

        try:
            with httpx.Client() as client:
                response = client.get(voices_url, timeout=10.0)
                response.raise_for_status()
                data = response.json()

            if "voices" in data and isinstance(data["voices"], list) and data["voices"]:
                self.available_voices_list = sorted(data["voices"])
                logger.info(f"Successfully loaded {len(self.available_voices_list)} voices.")
                default_voice = self.available_voices_list[0]
                self.tts_voice_var.set(default_voice)
                if hasattr(self, 'select_voice_button'): self.select_voice_button.configure(state="normal")
                if hasattr(self, 'speak_button'): self.speak_button.configure(state="normal")
                if hasattr(self, 'tts_input_textbox'): self.tts_input_textbox.configure(state="normal")
                if hasattr(self, 'retry_load_voices_button'): self.retry_load_voices_button.pack_forget()
                self.update_status("Voices loaded.")
            else:
                logger.error(f"Failed to load voices: Invalid format received - {data}")
                self.available_voices_list = []
                self.tts_voice_var.set("Load failed")
                if hasattr(self, 'retry_load_voices_button'): self.retry_load_voices_button.pack(side="left", padx=(5,0))
                self.update_status("Error: Failed to load voices - Invalid format")

        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error loading voices: {e.response.status_code} - {e.response.text[:100]}")
            self.available_voices_list = []
            self.tts_voice_var.set("Load failed")
            if hasattr(self, 'retry_load_voices_button'): self.retry_load_voices_button.pack(side="left", padx=(5,0))
            self.update_status(f"Error: Failed to load voices - Server error {e.response.status_code}")
        except Exception as e:
            logger.error(f"Error loading voices: {e}", exc_info=True)
            self.available_voices_list = []
            self.tts_voice_var.set("Load failed")
            if hasattr(self, 'retry_load_voices_button'): self.retry_load_voices_button.pack(side="left", padx=(5,0))
            self.update_status(f"Error: Failed to load voices - {e}")

    def init_load_voices(self):
        # *** 修改點：在開始加載前禁用重試按鈕 ***
        # 需要檢查按鈕是否存在，因為 after 可能在按鈕創建前被調用
        if hasattr(self, 'retry_load_voices_button'):
            self.retry_load_voices_button.pack_forget()
        threading.Thread(target=self.load_voices_from_server, daemon=True).start()

    def open_voice_selection_popup(self):
        if not self.available_voices_list:
            logger.warning("Voice list not loaded yet or empty.")
            messagebox.showwarning("No Voices", "Voice list is not available.")
            return

        popup = ctk.CTkToplevel(self)
        popup.title("Select Voice(s)")
        popup.geometry("350x450")
        popup.transient(self)
        # popup.grab_set() # 先註釋掉 grab_set 看看是否影響滾輪
        
        scrollable_frame = ctk.CTkScrollableFrame(popup, label_text="Available Voices", label_font=self.label_font)
        scrollable_frame.pack(padx=10, pady=10, expand=True, fill="both")

        # --- 添加滾輪綁定 ---
        def _on_mousewheel(event):
            # 根據事件 delta 或 num 計算滾動量
            # CustomTkinter 的滾動框架內部應該處理了這個，但我們再綁定一次以確保
            # 注意：這個 delta 值在不同平台可能不同或符號相反
            # 這裡用 CustomTkinter 的內部方法嘗試滾動 (可能需要根據版本調整)
            # 或者直接操作 canvas yview_scroll
            if platform.system() == "Linux":
                scroll_amount = -1 if event.num == 4 else 1
            elif platform.system() == "Darwin": # macOS
                scroll_amount = -1 * event.delta
            else: # Windows
                scroll_amount = -1 * int(event.delta / 120)

            # 嘗試調用內部滾動方法 (如果存在)
            if hasattr(scrollable_frame, "_parent_canvas"): # 檢查內部 canvas 是否存在
                scrollable_frame._parent_canvas.yview_scroll(scroll_amount, "units")
            else: # 備用方法 (可能不適用於 CTkScrollableFrame 的內部結構)
                pass # logger.warning("Could not find internal canvas for scrolling")

        # 綁定到 scrollable_frame 和可能需要獲取焦點的子組件
        # 綁定到框架本身
        scrollable_frame.bind("<MouseWheel>", _on_mousewheel)
        # 當鼠標進入時嘗試獲取焦點 (有助於滾輪事件)
        scrollable_frame.bind("<Enter>", lambda e: scrollable_frame.focus_set())

        # --- 修改點：創建 CheckBox ---
        for voice_name in self.available_voices_list:
            var = ctk.BooleanVar()            
            if voice_name.split('(')[0].strip() in set(s.split('(')[0].strip() for s in self.tts_voice_var.get().split('+')):
                var.set(True)
            self.voice_checkbox_vars[voice_name] = var

            cb = ctk.CTkCheckBox(
                scrollable_frame, text=voice_name, variable=var, font=self.label_font
            )
            cb.pack(anchor="w", padx=10, pady=2)
            # *** 新增：也為 CheckBox 綁定滾輪事件 ***
            # 這確保了當鼠標懸停在選項上時也能滾動
            cb.bind("<MouseWheel>", _on_mousewheel)

        # --- 修改點：OK 按鈕的命令 ---
        ok_button = ctk.CTkButton(
            popup,
            text="OK",
            # 使用 lambda 傳遞 popup 對象給回調函數
            command=lambda p=popup: self.apply_voice_selection_and_close(p),
            font=self.button_font
        )
        ok_button.pack(pady=10)

        # *** 修改點：延遲執行 grab_set ***
        # popup.grab_set() # 直接調用可能太快
        popup.after(100, popup.grab_set) # 延遲 100ms 執行 grab_set

    # --- 應用聲音選擇並關閉彈窗的方法 ---
    def apply_voice_selection_and_close(self, popup_window):
        """收集選中的聲音，更新變量，並關閉彈窗"""
        selected_voices = []
        for voice_name, var in self.voice_checkbox_vars.items():
            if var.get(): # 如果被選中
                selected_voices.append(voice_name)

        if not selected_voices:
            # 如果一個都沒選，可以彈出提示或設置一個默認值
            # messagebox.showwarning("No Selection", "Please select at least one voice.", parent=popup_window)
            # return
            # 或者設置為第一個可用的聲音
            if self.available_voices_list:
                 selected_voices.append(self.available_voices_list[0])
                 logger.warning("No voice selected, defaulting to the first available voice.")
            else: # 理論上不可能發生，因為按鈕是禁用的
                 logger.error("No voices available to select.")
                 popup_window.destroy()
                 return


        # 使用 '+' 連接選中的聲音名稱
        combined_voice_string = "+".join(selected_voices)
        self.tts_voice_var.set(combined_voice_string) # 更新主界面的 StringVar
        logger.info(f"Voice selection updated: {combined_voice_string}")
        popup_window.destroy() # 關閉彈窗

    # --- GUI 消息處理 ---
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

                # --- 處理文件轉錄結果 ---
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
                
                # --- 處理 TTS 狀態 ---
                elif msg_type == "tts_status_update":
                    self.update_status(message.get("message", "TTS Status"))
                    is_done = message.get("done", False)
                    if is_done:
                        self.speak_button.configure(state="normal")
                        # *** 如果不是因為錯誤結束，則嘗試重啟麥克風 ***
                        if "Error" not in message.get("message", ""):
                             self.maybe_restart_mic()
                
                # --- 處理 LLM 回應 ---
                elif msg_type == "llm_response":
                    llm_text = message.get("text", "")
                    if llm_text:
                        self.update_status("LLM response received. Preparing TTS...")
                        # 在右側文本框顯示 LLM 回應
                        self.translation_textbox.configure(state="normal")
                        self.translation_textbox.insert("end", f"[LLM] {llm_text}\n")
                        self.translation_textbox.configure(state="disabled")
                        self.translation_textbox.see("end")

                        # *** 自動觸發 TTS 播放 ***
                        # 我們需要一個獨立的方法來觸發 TTS，避免與按鈕回調混淆
                        # *** 在觸發 TTS 前停止麥克風 ***
                        self.stop_mic_if_recording() # <--- 新增調用
                        self.trigger_tts_playback(llm_text)
                    else:
                        self.update_status("LLM returned empty response.")
                        self.maybe_restart_mic() # LLM 回應為空也要重啟麥克風
                
                # *** 新增：處理 TTS 播放完成的消息 ***
                elif msg_type == "tts_playback_finished":
                    logger.info("TTS playback finished message received.")
                    self.maybe_restart_mic() # <--- 嘗試重啟麥克風
                else:
                    self.process_standard_message(message)

        except queue.Empty:
            pass
        finally:
            self.after(100, self.process_gui_queue)

    def process_standard_message(self, message):
        msg_type = message.get("type")
        text = None
        if msg_type == "final":
            text = message.get("text", "")
            lang = message.get("language", "unk")
            self.transcript_textbox.configure(state="normal")
            self.transcript_textbox.insert("end", f"[{lang}] {text}\n")
            self.transcript_textbox.configure(state="disabled")
            self.transcript_textbox.see("end")
            self.transcript_parts.append(text) # 累積文字用於保存和總結
    
        # *** 新增：檢查是否在對話模式，如果是則觸發聊天請求 ***
        if self.conversation_mode_var.get() and text:
            logger.info("Conversation mode: Triggering LLM chat request.")
            self.update_status("Sending to LLM...")
            # 在背景線程執行聊天請求
            threading.Thread(target=self.run_chat_request_sync, args=(text,), daemon=True).start()
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

    # --- 顯示文件轉錄結果的彈窗 ---
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

    # --- 停止和啟動麥克風的方法 ---
    def stop_mic_if_recording(self):
        """如果正在錄音，則停止麥克風輸入流"""
        if self.is_recording and self.audio_stream and self.audio_stream.active:
            try:
                logger.info("Temporarily stopping microphone stream for TTS playback.")
                self.audio_stream.stop()
                # 不需要 close，只是 stop
            except Exception as e:
                 logger.error(f"Error stopping microphone stream: {e}", exc_info=True)

    def maybe_restart_mic(self):
        """如果處於錄音狀態且流已停止，則重新啟動"""
        # 只有在用戶沒有手動點擊 Stop 的情況下才重啟
        if self.is_recording:
            if self.audio_stream and not self.audio_stream.active:
                try:
                    logger.info("Restarting microphone stream after TTS playback.")
                    self.audio_stream.start()
                    self.update_status("Microphone restarted. Listening...")
                except Exception as e:
                    logger.error(f"Error restarting microphone stream: {e}", exc_info=True)
                    self.update_status("Error restarting mic. Please stop/start.")
            elif not self.audio_stream:
                logger.warning("Cannot restart mic: audio_stream is None.")
            else: # stream is active
                logger.debug("Mic stream already active, no need to restart.")
        else:
            logger.info("Not restarting mic as recording is stopped.")

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
        # *** 修改點：禁用對話模式勾選框 ***
        self.conversation_checkbox.configure(state="disabled")
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
        # *** 修改點：確保 is_recording 在停止時設置為 False ***
        self.is_recording = False # <--- 立即設置為 False
        if self.stop_event: # 檢查是否存在
            self.stop_event.set()
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
        # *** 修改點：確保 is_recording 在這裡也設置為 False ***
        self.is_recording = False
        self.url_entry.configure(state="normal")
        self.device_menu.configure(state="normal")
        self.translate_checkbox.configure(state="normal")
        self.toggle_translation_options() # 根據 checkbox 狀態設置語言框
        self.start_button.configure(state="normal")
        self.stop_button.configure(state="disabled")
        # *** 修改點：確保啟用 Conversation Mode checkbox ***
        self.conversation_checkbox.configure(state="normal")
        self.toggle_conversation_mode() # 確保根據其狀態恢復其他 UI

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

    # --- 文件轉錄按鈕的回調 ---
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

    # --- 在新線程中執行文件轉錄請求的函數 ---
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

    # --- TTS 和 Chat 相關方法 ---
    def synthesize_and_play(self):
        logger.info("Speak button clicked.")
        text_to_speak = self.tts_input_textbox.get("1.0", "end-1c").strip() # 獲取文本框內容

        if text_to_speak:
            # *** 新增：觸發 TTS 前停止麥克風 ***
            self.stop_mic_if_recording()
            
            self.speak_button.configure(state="disabled") # 禁用按鈕防止重複點擊
            self.trigger_tts_playback(text_to_speak)
        else:
            logger.warning("No text entered in TTS input box.")
            self.update_status("Error: Please enter text to synthesize.")

        selected_voice = self.tts_voice_var.get()
        if not selected_voice:
            logger.warning("No voice selected for TTS.")
            self.update_status("Error: Please select a voice.")
            return

        self.update_status("Synthesizing audio...")
        self.speak_button.configure(state="disabled") # 禁用按鈕

        # 獲取伺服器 HTTP URL
        ws_url = self.url_entry.get().strip()
        if not ws_url.startswith("ws://"):
            logger.error("Invalid WebSocket URL for TTS.")
            self.update_status("Error: Invalid server URL.")
            self.speak_button.configure(state="normal") # 恢復按鈕
            return
        base_url = ws_url.split('/v1/audio/transcriptions/ws')[0]
        server_http_url = base_url.replace("ws://", "http://", 1)

        # 在背景線程執行 TTS 請求和播放
        threading.Thread(
            target=self.run_tts_request_sync,
            args=(server_http_url, text_to_speak, selected_voice),
            daemon=True
        ).start()

    # --- 新增/重構：觸發 TTS 的方法 ---
    def trigger_tts_playback(self, text_to_speak: str):
        """觸發 TTS 合成和播放"""
        selected_voice = self.tts_voice_var.get()
        if not text_to_speak or not selected_voice or selected_voice in ["Loading...", "Load failed"]:
            logger.warning(f"Invalid TTS input: Voice='{selected_voice}'")
            self.update_status("Error: Cannot synthesize - Invalid text or voice.")
            # 即使 TTS 輸入無效，如果之前停止了 mic，也應該嘗試恢復
            self.gui_queue.put_nowait({"type": "tts_playback_finished"}) # 發送完成信號以嘗試重啟 mic
            return

        logger.info("Triggering TTS playback...")
        self.update_status("Synthesizing audio...")
        # 這裡可以先禁用按鈕，以防用戶在請求發出前再次點擊
        # speak_button 的最終狀態由 run_tts_request_sync 通過隊列更新
        self.speak_button.configure(state="disabled")

        ws_url = self.url_entry.get().strip()

        # --- 錯誤處理：檢查 URL 有效性 ---
        if not ws_url or not ws_url.startswith("ws://"):
            error_msg = "Invalid Server WebSocket URL for TTS."
            logger.error(error_msg)
            self.update_status(f"Error: {error_msg}")
            # 發送完成信號，以便 GUI 隊列處理程序可以恢復 Speak 按鈕狀態
            self.gui_queue.put_nowait({"type": "tts_status_update", "message": f"Error: {error_msg}", "done": True})
            # 同時也發送播放完成信號，以防萬一需要重啟麥克風
            self.gui_queue.put_nowait({"type": "tts_playback_finished"})
            return # 停止執行

        # --- 從 WebSocket URL 推斷 HTTP URL ---
        try:
            # 使用更安全的方式分割，避免路徑不匹配時出錯
            base_url_parts = ws_url.split("/v1/audio/transcriptions/ws")
            if len(base_url_parts) < 1:
                 raise ValueError("Cannot parse base URL from WebSocket URL.")
            base_url = base_url_parts[0]
            server_http_url = base_url.replace("ws://", "http://", 1) # 只替換第一個 ws://
        except Exception as e:
            error_msg = f"Cannot derive HTTP URL from WebSocket URL: {e}"
            logger.error(error_msg)
            self.update_status(f"Error: {error_msg}")
            self.gui_queue.put_nowait({"type": "tts_status_update", "message": f"Error: {error_msg}", "done": True})
            self.gui_queue.put_nowait({"type": "tts_playback_finished"})
            return # 停止執行

        # 在背景線程執行 TTS 請求和播放
        threading.Thread(
            target=self.run_tts_request_sync,
            args=(server_http_url, text_to_speak, selected_voice),
            daemon=True
        ).start()

    # --- 執行 TTS 請求和播放的函數 ---
    def run_tts_request_sync(self, server_http_url: str, text: str, voice: str):
        """在新線程中執行同步的 TTS 請求和流式播放 (假設接收 PCM)"""
        tts_url = f"{server_http_url}/v1/audio/speech"
        logger.info(f"Requesting TTS stream from: {tts_url} for voice: {voice}")
        KOKORO_SAMPLE_RATE = 24000 # Keep assumption for playback for now
        KOKORO_CHANNELS = 1        # Keep assumption for playback for now
        stream = None
        playback_started = False

        try:
            payload = {
                "input": text,
                "voice": voice,
                # *** FIX 1: Revert response_format to 'wav' ***
                "response_format": "wav",
                "model": "kokoro", # Or another model ID accepted by K.audio/Kokoro
                "speed": 1.0
            }
            # Accept header should match requested format
            headers = {"accept": "audio/wav"}

            with httpx.Client() as client:
                with client.stream("POST", tts_url, json=payload, headers=headers, timeout=60.0) as response:
                    # *** FIX 2: Read error response body before accessing text ***
                    try:
                        response.raise_for_status() # Check initial status
                    except httpx.HTTPStatusError as status_error:
                         # Read the error response body before re-raising or handling
                         try:
                             error_body_text = status_error.response.read().decode('utf-8', errors='ignore')
                         except httpx.ResponseNotRead: # Should not happen after read()
                             error_body_text = "(Could not read error body)"
                         except Exception as read_err:
                             error_body_text = f"(Error reading error body: {read_err})"
                         # Add detail to the original exception or log it
                         logger.error(f"HTTP Status Error {status_error.response.status_code} Body: {error_body_text[:500]}")
                         # Re-raise the original exception to be caught by the outer handler
                         raise status_error

                    # --- If status is OK (2xx), proceed with streaming ---
                    content_type = response.headers.get("content-type", "").lower()
                    if "audio/wav" not in content_type: # Check if we actually got WAV
                         # Handle unexpected content type if necessary, but proceed assuming it might be playable
                         logger.warning(f"Received Content-Type '{content_type}', attempting to process as WAV stream.")
                         # raise ValueError(f"Expected audio/wav, but received {content_type}")

                    logger.info("Receiving streaming audio data...")
                    self.gui_queue.put_nowait({"type": "tts_status_update", "message": "Receiving audio stream..."})

                    byte_iterator = response.iter_bytes(chunk_size=1024 * 2) # Read 2KB chunks

                    # *** Revert: Assume WAV stream, parse header again ***
                    header_bytes_needed = 44
                    wav_header = b''
                    header_parsed = False
                    sample_rate = KOKORO_SAMPLE_RATE # Default if header parsing fails
                    n_channels = KOKORO_CHANNELS    # Default if header parsing fails

                    while len(wav_header) < header_bytes_needed:
                        try:
                            chunk = next(byte_iterator)
                            wav_header += chunk
                        except StopIteration:
                            raise ValueError("Incomplete WAV header received (stream ended unexpectedly).")

                    header_data = wav_header[:header_bytes_needed]
                    remainder = wav_header[header_bytes_needed:]

                    try:
                        with io.BytesIO(header_data) as header_f:
                            with wave.open(header_f, 'rb') as wf:
                                sample_rate = wf.getframerate()
                                n_channels = wf.getnchannels()
                                sampwidth = wf.getsampwidth()
                                logger.info(f"WAV properties from stream header: Rate={sample_rate}, Channels={n_channels}, Width={sampwidth}")
                                if sampwidth != 2:
                                    raise ValueError(f"Unsupported sample width: {sampwidth}")
                                # Update channels based on header
                                KOKORO_CHANNELS = n_channels
                        header_parsed = True
                    except wave.Error as e:
                        logger.warning(f"Could not parse WAV header from stream ({e}), falling back to default parameters ({KOKORO_SAMPLE_RATE} Hz, {KOKORO_CHANNELS} Ch). Data might be raw PCM.")
                        # If header parsing fails, treat *all* received data (including header bytes) as audio
                        remainder = wav_header # Treat the whole header buffer as audio start

                    # Create and start output stream
                    stream = sd.OutputStream(
                        samplerate=sample_rate, # Use parsed or default rate
                        channels=n_channels,    # Use parsed or default channels
                        dtype=DTYPE,
                        blocksize=1024
                    )
                    stream.start()
                    playback_started = True
                    logger.info(f"Audio output stream started at {sample_rate} Hz.")
                    self.gui_queue.put_nowait({"type": "tts_status_update", "message": "Playing audio stream..."})

                    # Write remainder
                    if remainder:
                         audio_chunk_np = np.frombuffer(remainder, dtype=DTYPE)
                         stream.write(audio_chunk_np)

                    # Iterate and play rest
                    for chunk in byte_iterator:
                        if chunk:
                            audio_chunk_np = np.frombuffer(chunk, dtype=DTYPE)
                            stream.write(audio_chunk_np)

                    logger.info("Finished writing audio stream to sounddevice.")
                    self.gui_queue.put_nowait({"type": "tts_status_update", "message": "TTS stream finished.", "done": True})

        # --- Error Handling ---
        except httpx.HTTPStatusError as e:
             # Error body was read above (or attempted)
             error_detail = error_body_text if 'error_body_text' in locals() else f"(Status: {e.response.status_code})"
             logger.error(f"HTTP error during TTS stream request: {e.response.status_code} - {error_detail}")
             self.gui_queue.put_nowait({"type": "tts_status_update", "message": f"TTS Server Error: {e.response.status_code}", "done": True})
        except httpx.RequestError as e: ... # Keep as is
        except (wave.Error, ValueError) as e: # Keep as is
             logger.error(f"Error processing WAV stream data: {e}")
             self.gui_queue.put_nowait({"type": "tts_status_update", "message": f"Error: Invalid audio data - {e}", "done": True})
        except sd.PortAudioError as e: ... # Keep as is
        except Exception as e: ... # Keep as is
        finally:
            # ... (Close stream, send tts_playback_finished) ...
            if stream: ...
            self.gui_queue.put_nowait({"type": "tts_playback_finished"})

    # --- 執行聊天請求的函數 (在線程中運行) ---
    def run_chat_request_sync(self, transcript_text: str):
        """在新線程中執行同步的 LLM 聊天請求"""
        # *** 修改點：從 UI 或默認值獲取模型名稱 ***
        # 這裡我們暫時硬編碼一個值，理想情況下應來自配置或 UI
        llm_model_name = "Qwen3-30B-A3B-UD-IQ1_S" # 或者 self.llm_model_entry.get() (如果添加了輸入框)
        # 獲取伺服器 HTTP URL
        ws_url = self.url_entry.get().strip()
        if not ws_url.startswith("ws://"):
            logger.error("Invalid WebSocket URL for chat request.")
            self.gui_queue.put_nowait({"type":"tts_status_update", "message":"Error: Invalid server URL"})
            return
        base_url = ws_url.split('/v1/audio/transcriptions/ws')[0]
        server_http_url = base_url.replace("ws://", "http://", 1)
        chat_url = f"{server_http_url}/v1/chat/completions"

        logger.info(f"Requesting LLM Chat completion from: {chat_url}")

        try:
            system_prompt = """
You are an AI voice chat assistant. Your primary function is to interact with the user in a natural, conversational manner suitable for a real-time voice exchange.

**Core Directives:**

1.  **Conversational Tone:** Respond as if you are speaking directly to the user in a friendly, natural chat. Use simple, clear language.
2.  **Conciseness:** Keep your answers brief and to the point. Voice interactions require clarity and brevity. Avoid lengthy explanations or unnecessary filler words.
3.  **Accuracy:** Ensure the information you provide is correct and directly addresses the user's query.
4.  **Direct Answers:** Provide the requested information or response directly. **Crucially, do NOT output your reasoning, thought process, search steps, or any meta-commentary about how you arrived at the answer.** Your response should solely consist of the concise, accurate, and conversational answer itself.

**Example Interaction:**

* **User:** "What's the weather like in Taipei today?"
* **Your Ideal Response (Concise, Direct, Conversational):** "It's currently sunny and warm in Taipei, around 28 degrees Celsius."
* **Avoid Responses Like:** "Okay, let me check the weather for Taipei. According to my sources, the weather in Taipei today is sunny with a high of 28 degrees Celsius. I found this information by accessing a weather API..."

Maintain this style consistently across all interactions. Act as a helpful, efficient, and conversational voice assistant.
""".strip()
            # 構建請求體
            payload = {
                "model": llm_model_name, # 使用變量
                "messages": [
                    {
                        "role": "system", 
                        "content": system_prompt
                        },
                    {"role": "user", "content": transcript_text + "/no_think"}
                ],
                "temperature": 0.7, # 可以調整
                "max_tokens": 150, # 可以限制回復長度
            }
            with httpx.Client() as client:
                response = client.post(chat_url, json=payload, timeout=120.0)
                response.raise_for_status()
                result = response.json()

            # 提取 LLM 回應
            if result.get("choices") and result["choices"][0].get("message") and result["choices"][0]["message"].get("content"):
                 llm_response_text = result["choices"][0]["message"]["content"].strip()
                 logger.info(f"LLM response received: {llm_response_text[:100]}...")
                 # 將結果放入 GUI 隊列
                 self.gui_queue.put_nowait({"type": "llm_response", "text": llm_response_text})
            else:
                 logger.error(f"Invalid LLM response format: {result}")
                 self.gui_queue.put_nowait({"type": "tts_status_update", "message": "Error: Invalid LLM response"})

        except httpx.HTTPStatusError as e:
             error_detail = e.response.text[:200]
             logger.error(f"HTTP error during chat request: {e.response.status_code} - {error_detail}")
             self.gui_queue.put_nowait({"type": "tts_status_update", "message": f"LLM Server Error: {e.response.status_code}"})
        except httpx.RequestError as e:
             logger.error(f"Request error during chat request: {e}")
             self.gui_queue.put_nowait({"type": "tts_status_update", "message": f"LLM Connection Error: {e}"})
        except Exception as e:
             logger.error(f"Unexpected error during chat request: {e}", exc_info=True)
             self.gui_queue.put_nowait({"type": "tts_status_update", "message": f"Chat Request Error: {e}"})

    # --- 同步的 HTTP 請求 ---
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