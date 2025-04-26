# PortAudio

必需要在**運行客戶端的這台機器**上，**安裝 PortAudio 的開發函式庫**。安裝方法取決於所使用的作業系統。

**請根據客戶端機器的作業系統，執行對應的安裝指令：**

* **Debian / Ubuntu / 或基於 Debian 的 Linux 發行版:**
    ```bash
    sudo apt-get update
    sudo apt-get install portaudio19-dev python3.12-dev # 同時確保 Python dev headers 也安裝了
    ```

* **Fedora / CentOS / RHEL:**
    ```bash
    sudo dnf update # 或者 sudo yum update
    sudo dnf install portaudio-devel python3.12-devel # 或者 sudo yum install ...
    ```

* **macOS (使用 Homebrew):**
    ```bash
    brew install portaudio pkg-config # pkg-config 有時也需要
    ```

* **Windows:**
    * 要從 [PortAudio 官方網站](http://www.portaudio.com/download.html) 下載預編譯的 PortAudio DLL 檔案（通常是 .dll）。
    * 將下載的 DLL 檔案（例如 `portaudio_x64.dll` 或類似名稱）放到 Python 可以找到的地方，例如：
        * 放到所使用的 Python 環境的 `Scripts` 或 `Library/bin` 目錄下。
        * 或者放到系統的 PATH 環境變數所包含的某個目錄下。
    * 確保安裝了與所使用的 Python 版本（64位元）匹配的 PortAudio 版本。