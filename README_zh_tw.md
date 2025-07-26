# K.audio - 即時語音轉文字/翻譯 Python 客戶端與伺服器

這個專案提供了一個以 Python 實現的即時語音轉文字（STT）和翻譯客戶端，以及使用 Docker 設定伺服器所需的組件。它利用 Whisper 進行語音轉文字，CTtranslate2 進行翻譯，以及 FastAPI 建立伺服器 API。

## 概述

K.audio 允許使用者從麥克風串流音訊到伺服器，接收即時轉錄，並可選擇翻譯轉錄內容。它還包含文字轉語音（TTS）和與 LLM 進行對話模式的功能。伺服器設計為在 Docker 容器中運行，使部署和管理更加容易。

## 功能

### 客戶端（Python）

- 從麥克風即時串流音訊到伺服器。
- 接收並顯示最終轉錄結果。
- 可選擇即時翻譯轉錄片段。
- 自動偵測可用的輸入音訊裝置。
- 關閉時將完整轉錄和可選摘要儲存到本地檔案。
- 允許指定來源/目標語言和初始語音轉文字提示。
- 可設定結果輸出目錄。
- 使用 CustomTkinter 建立的 GUI 介面。
- 文字轉語音（TTS）功能。
- 與 LLM 整合進行回應的對話模式。

### 伺服器（Docker）

- 使用 Docker 容器運行 K.audio 伺服器。
- 支援 GPU 加速以提高處理速度。
- 可設定環境變數以設定語音轉文字模型和設定。
- 用於語音轉文字、翻譯、摘要和 TTS 的 API 端點。

## 開始使用

### 先決條件

- Python 3.9 或更高版本。
- pip（Python 的套件安裝程式）。
- Docker 和 Docker Compose。
- PortAudio（適用於 Linux 使用者）。

### 安裝

1. **克隆儲存庫：**

```bash
git clone <repository_url>
```

2. **導航到客戶端目錄：**

```bash
cd K.audio/client/python
```

3. **建立並啟用虛擬環境：**

- **Linux/macOS：**

```bash
python3 -m venv venv
source venv/bin/activate
```

- **Windows：**

```bash
python -m venv venv
venv\Scripts\activate
```

4. **安裝依賴：**

```bash
pip install -r requirements.txt
```

- **Linux（Debian/Ubuntu 範例）：** 你可能需要先安裝 PortAudio：

```bash
sudo apt update
sudo apt install portaudio19-dev python3-dev
```

### 使用方式

#### 客戶端

```bash
python k_audio_gui_client.py
```

或使用命令行客戶端

```bash
python stt_stream_client.py <server_websocket_url> [選項]
```

- `<server_websocket_url>`：K.audio 伺服器的完整 WebSocket URL（例如，`ws://192.168.1.103:8000/v1/audio/transcriptions/ws`）。
- 選項：
- `-d <index_or_list>`, `--device <index_or_list>`：指定輸入音訊裝置索引。使用 `-d list` 查看可用裝置。
- `-o <path>`, `--output-dir <path>`：儲存轉錄和摘要檔案的目錄。
- `-l <lang_code>`, `--language <lang_code>`：指定語音轉文字的來源語言（例如，`zh`、`en`）。
- `-p <prompt_text>`, `--prompt <prompt_text>`：設定語音轉文字模型的初始提示。
- `--translate`：啟用即時翻譯。
- `--target-lang <lang_code>`：翻譯的目標語言。
- `--source-lang <lang_code>`：翻譯的來源語言（可選）。

#### 伺服器

1. 導航到伺服器目錄：

```bash
cd K.audio/server
```

2. 使用 Docker Compose 啟動伺服器：

```bash
docker-compose up --build
```

### Docker Compose

`docker-compose.yml` 檔案使用 Docker 設定 K.audio 伺服器。它包括：

- 從 `./server` 目錄構建伺服器映像檔。
- 映射連接埠 8000 作為伺服器 API。
- 將本地 `models` 目錄掛載到容器中的 `/app/models`。
- 使用 NVIDIA Container Toolkit 啟用 GPU 使用。
- 設定用於語音轉文字裝置、計算類型和模型路徑的環境變數。

### 其他腳本

- `download_whisper.py`：用於下載和整理 Whisper 語音轉文字模型的腳本。
- 用於檔案轉錄的 Curl 指令：可在 `file_transcription_chinese_curl.md` 中找到。

## 注意事項

- 確保伺服器可以從客戶端機器存取（檢查 IP 位址和防火牆）。
- 請參閱特定語言的 README（`README_zh_TW.md`）以獲取繁體中文的說明。
- 如需疑難排解，請檢查伺服器日誌和客戶端控制台輸出。
- 如果沒有 GPU，請考慮在 `docker-compose.yml` 環境變數中設定 `STT_DEVICE=cpu`。

## 貢獻

歡迎對專案做出貢獻。請 fork 儲存庫並提交 pull request 進行變更。

## 授權

[在此處新增授權資訊]
