# K.audio - 即時 STT/翻譯 Python 客戶端

這個 Python 客戶端透過 WebSocket 連接到 K.audio 伺服器，以執行即時語音轉文字 (STT)，可選擇接著進行即時翻譯並觸發會話結束摘要。

## 功能

* 從麥克風到伺服器的即時音訊串流。
* 接收並顯示最終轉錄結果。
* 選擇性地即時翻譯轉錄的語句。
* 自動偵測可用的輸入音訊裝置。
* 關閉時將完整的轉錄和選擇性摘要儲存到本地檔案。
* 允許指定來源/目標語言和初始 STT 提示。
* 可配置結果的輸出目錄。

## 先決條件

1.  **Python：** 建議使用 3.9 或更高版本（使用 3.12 開發）。您可以從 [python.org](https://www.python.org/) 下載 Python。
2.  **pip：** Python 的套件安裝程式，通常隨 Python 安裝一起提供。
3.  **PortAudio (僅限 Linux)：** `sounddevice` 函式庫依賴於 PortAudio 函式庫。
    * **Windows 和 macOS：** PortAudio 通常**包含**在 pip 下載的 `sounddevice` 套件中，因此通常不需要單獨安裝。
    * **Linux：** 您很可能**需要先安裝 PortAudio 開發函式庫** *然後*再安裝 Python 需求。請參閱下面的安裝步驟。
4.  **K.audio 伺服器：** 您需要 K.audio 伺服器的執行實例及其 WebSocket URL (例如，`ws://<server_ip>:8000/v1/audio/transcriptions/ws`)。確保客戶端機器可以存取伺服器（檢查 IP 位址和防火牆）。

## 安裝

強烈建議使用 Python 虛擬環境，以避免與系統範圍的套件發生衝突。

1.  **取得程式碼：**
    * 複製儲存庫：`git clone <repository_url>`
    * 或下載 `client/python` 目錄。

2.  **切換到客戶端目錄：**

    ```bash
    cd path/to/K.audio/client/python
    ```

3.  **建立並啟用虛擬環境：**
    * **Linux/macOS：**

        ```bash
        python3 -m venv venv
        source venv/bin/activate
        ```

    * **Windows (命令提示字元/PowerShell)：**

        ```bash
        python -m venv venv
        venv\Scripts\activate
        ```

    您應該會在命令提示字元的開頭看到 `(venv)`。

4.  **安裝依賴項 (特定作業系統)：**

    * **Linux (Debian/Ubuntu 範例)：**
        * **先安裝 PortAudio：**

            ```bash
            sudo apt update
            sudo apt install portaudio19-dev python3-dev
            ```

            *(注意：`python3-dev` 提供編譯某些 Python 套件所需的標頭檔)。*
        * *(對於 Fedora/CentOS/RHEL 使用：`sudo dnf install portaudio-devel python3-devel`)*
        * **安裝 Python 需求：**

            ```bash
            pip install -r requirements.txt
            ```

    * **Windows：**
        * PortAudio 通常已捆綁。直接安裝 Python 需求：

            ```bash
            pip install -r requirements.txt
            ```

    * **macOS：**
        * PortAudio 通常已捆綁。直接安裝 Python 需求：

            ```bash
            pip install -r requirements.txt
            ```

        * *(如果 `pip install` 因 PortAudio 錯誤而失敗，您可能需要透過 Homebrew 安裝：`brew install portaudio`，然後再嘗試 pip 安裝。)*

## 用法

請確保您的虛擬環境已啟用後再執行客戶端。

```bash
python stt_stream_client.py <server_websocket_url> [options]
```

**必要參數：**

* `<server_websocket_url>`：您的 K.audio 伺服器的完整 WebSocket URL (例如，`ws://192.168.1.103:8000/v1/audio/transcriptions/ws`)。

**選項：**

* `-h, --help`：顯示說明訊息並退出。
* `-d <index_or_list>, --device <index_or_list>`：指定輸入音訊裝置索引。使用 `-d list` 查看可用的裝置及其索引。預設為系統的預設輸入裝置。
* `-o <path>, --output-dir <path>`：儲存轉錄和摘要檔案的目錄。預設為 `./k.audio_output`。
* `-l <lang_code>, --language <lang_code>`：指定 STT 的來源語言 (例如，`zh`，`en`)。如果未提供，Whisper 將嘗試自動偵測每個語句的語言。
* `-p <prompt_text>, --prompt <prompt_text>`：為 STT 模型設定初始提示。（注意：由於函式庫限制，在串流模式下目前被忽略）。
* `--translate`：啟用即時翻譯。
* `--target-lang <lang_code>`：翻譯的目標語言 (例如，`en`，`ja`，`zh-Hant`)。如果啟用 `--translate`，則為**必需**。
* `--source-lang <lang_code>`：翻譯的來源語言。如果提供，將覆寫 Whisper 的語言偵測用於翻譯目的。

**範例：**

1.  **列出可用的輸入裝置：**

    ```bash
    python stt_stream_client.py --device list
    ```

2.  **基本即時 STT (使用預設麥克風)：**

    ```bash
    python stt_stream_client.py ws://<server_ip>:8000/v1/audio/transcriptions/ws
    ```

3.  **使用裝置索引 2 進行即時 STT：**

    ```bash
    python stt_stream_client.py ws://<server_ip>:8000/v1/audio/transcriptions/ws -d 2
    ```

4.  **即時 STT 並進行中文 -> 英文翻譯：**

    ```bash
    python stt_stream_client.py ws://<server_ip>:8000/v1/audio/transcriptions/ws --translate --target-lang en --source-lang zh
    ```

5.  **即時 STT 並翻譯成日文（自動偵測來源）：**

    ```bash
    python stt_stream_client.py ws://<server_ip>:8000/v1/audio/transcriptions/ws --translate --target-lang ja
    ```

6.  **將輸出儲存到特定目錄：**

    ```bash
    python stt_stream_client.py ws://<server_ip>:8000/v1/audio/transcriptions/ws --output-dir ./my_meeting_notes
    ```

**停止客戶端：**

* 在執行客戶端的終端機中按 `Ctrl + C`。
* 客戶端將嘗試正常停止音訊串流，向伺服器發送結束信號，儲存轉錄，並可能會詢問您是否要產生摘要。

**輸出檔案：**

* 停止後，客戶端會在指定的輸出目錄（預設：`./k.audio_output`）中建立一個子目錄。子目錄以會話開始時間戳命名（例如，`20250427_130800`）。
* 在此子目錄中：
    * `transcript.txt`：包含完整的轉錄文本，語句之間有換行符。
    * `summary.txt`：包含 LLM 生成的摘要（如果請求並成功產生摘要）。

## 故障排除

* **連線被拒絕：** 確保 K.audio 伺服器正在執行且可透過指定的 URL 存取。檢查客戶端和伺服器機器的防火牆。驗證 IP 位址和連接埠。
* **PortAudio 錯誤 (Linux)：** 確保您在執行 `pip install -r requirements.txt` *之前*安裝了 `portaudio19-dev`（或等效的套件）。
* **找不到音訊裝置 / 無效的裝置索引：** 使用 `--device list` 執行以查看可用的裝置及其正確的索引。確保麥克風已正確連接並被作業系統識別。
* **權限被拒絕 (音訊)：** 在某些 Linux 系統上，您的使用者可能需要屬於 `audio` 群組才能存取音訊裝置。
* **翻譯/摘要錯誤：** 檢查 K.audio 伺服器日誌中與 LLM API 呼叫相關的錯誤（連線問題、無效的 API 金鑰、LLM 服務錯誤）。