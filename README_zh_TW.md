# 語音轉文字與摘要服務

## 簡介

這個專案是一個語音轉文字（Speech-to-Text, STT）的轉錄服務，並具備摘要功能。它採用客戶端-伺服器架構，能夠將語音內容轉換成文字，並自動產生內容摘要。專案中包含模型目錄、音訊資產資料夾，並且提供了 Docker 部署方案。

## 主要功能

-   **語音轉文字 (STT)**：將音訊內容轉換成文字。
-   **自動摘要**：自動生成音訊內容的摘要。
-   **客戶端-伺服器架構**：採用分離的客戶端和伺服器架構，便於系統擴展和維護。
-   **模型目錄**：專案包含一個 `models` 目錄，用於存放機器學習模型，提供語音辨識和摘要功能。
-   **音訊資產**：`assets` 資料夾中包含測試用的音訊檔案。
-   **Docker 支援**：提供 `Dockerfile` 和 `docker-compose.yml`，方便快速部署和執行。

## 專案架構

-   **`client/`**：客戶端程式碼，包含 Python 程式碼。
    -   `python/`：包含 Python 客戶端相關的程式碼與說明。
-   **`server/`**：伺服器端程式碼，包含：
    -   `app/`：主要應用程式碼。
    -   `Dockerfile`：用於構建伺服器端的 Docker 映像。
    -   `requirements.txt`：伺服器端 Python 依賴的套件清單。
-   **`models/`**：存放機器學習模型的目錄，例如 Faster-Whisper 模型。
-   **`assets/`**：存放音訊檔案的目錄，例如測試用的音訊檔。
-   **`docker-compose.yml`**：使用 Docker Compose 部署專案的設定檔。
-   **`download_whisper.py`**：用來下載whisper模型程式。
-    **`.idx/`**：開發環境的檔案，例如dev.nix。
-   **`.vscode/`**：vscode環境的檔案，例如setting.json。
-   **`tests/`**：包含測試檔案，例如curl指令、streaming測試。
-   **`k.audio_output`**: 測試資料的輸出目錄。

## 快速開始

1.  **環境準備**

    -   安裝 Docker 和 Docker Compose。

2.  **部署服務**
```
bash
    docker-compose up -d --build
    
```
3.  **測試**

    -   可以透過客戶端程式連接伺服器進行語音轉文字與摘要測試。
    -   使用curl指令，請參考`tests`資料夾。

## 客戶端使用說明

1.  **安裝依賴套件**
```
bash
    cd client/python
    pip install -r requirements.txt
    
```
2.  **執行客戶端程式**
```
bash
    python stt_stream_client.py
    
```
或者
```
bash
    python k_audio_gui_client.py
    
```
## 貢獻

歡迎任何形式的貢獻，包括但不限於：

-   提交 Pull Requests。
-   報告 Issue。
-   提供建議和改進方案。

## 授權

本專案使用 MIT 授權。