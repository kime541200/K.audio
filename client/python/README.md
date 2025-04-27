# K.audio - Real-time STT/Translation Python Client

This Python client connects to the K.audio server via WebSocket to perform real-time speech-to-text (STT), optionally followed by real-time translation and end-of-session summarization triggering.

## Features

* Real-time audio streaming from microphone to server.
* Receives and displays final transcription results.
* Optional real-time translation of transcribed segments.
* Automatically detects available input audio devices.
* Saves full transcript and optional summary to local files upon closing.
* Allows specifying source/target languages and initial STT prompt.
* Configurable output directory for results.

## Prerequisites

1.  **Python:** Version 3.9 or higher recommended (developed with 3.12). You can download Python from [python.org](https://www.python.org/).
2.  **pip:** Python's package installer, usually included with Python installations.
3.  **PortAudio (Linux Only):** The `sounddevice` library relies on the PortAudio library.
    * **Windows & macOS:** PortAudio is typically **included** within the `sounddevice` package downloaded by pip, so no separate installation is usually needed.
    * **Linux:** You most likely **need to install PortAudio development libraries** *before* installing the Python requirements. See installation steps below.
4.  **K.audio Server:** You need a running instance of the K.audio server and its WebSocket URL (e.g., `ws://<server_ip>:8000/v1/audio/transcriptions/ws`). Ensure the server is accessible from the client machine (check IP addresses and firewalls).

## Installation

It is strongly recommended to use a Python virtual environment to avoid conflicts with system-wide packages.

1.  **Get the Code:**
    * Clone the repository: `git clone <repository_url>`
    * Or download the `client/python` directory.

2.  **Navigate to Client Directory:**
    ```bash
    cd path/to/K.audio/client/python
    ```

3.  **Create and Activate Virtual Environment:**
    * **Linux/macOS:**
        ```bash
        python3 -m venv venv
        source venv/bin/activate
        ```
    * **Windows (Command Prompt/PowerShell):**
        ```bash
        python -m venv venv
        venv\Scripts\activate
        ```
    You should see `(venv)` appear at the beginning of your command prompt.

4.  **Install Dependencies (OS Specific):**

    * **Linux (Debian/Ubuntu Example):**
        * **Install PortAudio first:**
            ```bash
            sudo apt update
            sudo apt install portaudio19-dev python3-dev
            ```
            *(Note: `python3-dev` provides headers needed for compiling some Python packages).*
        * *(For Fedora/CentOS/RHEL use: `sudo dnf install portaudio-devel python3-devel`)*
        * **Install Python requirements:**
            ```bash
            pip install -r requirements.txt
            ```

    * **Windows:**
        * PortAudio is usually bundled. Directly install Python requirements:
            ```bash
            pip install -r requirements.txt
            ```

    * **macOS:**
        * PortAudio is usually bundled. Directly install Python requirements:
            ```bash
            pip install -r requirements.txt
            ```
        * *(If `pip install` fails with PortAudio errors, you might need to install it via Homebrew: `brew install portaudio`, then try pip install again.)*

## Usage

Make sure your virtual environment is activated before running the client.

```bash
python stt_stream_client.py <server_websocket_url> [options]
```

**Required Argument:**

* `<server_websocket_url>`: The full WebSocket URL of your K.audio server (e.g., `ws://192.168.1.103:8000/v1/audio/transcriptions/ws`).

**Options:**

* `-h, --help`: Show help message and exit.
* `-d <index_or_list>, --device <index_or_list>`: Specify the input audio device index. Use `-d list` to see available devices and their indices. Defaults to the system's default input device.
* `-o <path>, --output-dir <path>`: Directory to save transcript and summary files. Defaults to `./k.audio_output`.
* `-l <lang_code>, --language <lang_code>`: Specify the source language for STT (e.g., `zh`, `en`). If not provided, Whisper will attempt auto-detection for each segment.
* `-p <prompt_text>, --prompt <prompt_text>`: Set an initial prompt for the STT model. (Note: Currently ignored in streaming mode due to library limitations).
* `--translate`: Enable real-time translation.
* `--target-lang <lang_code>`: Target language for translation (e.g., `en`, `ja`, `zh-Hant`). **Required** if `--translate` is enabled.
* `--source-lang <lang_code>`: Source language for translation. If provided, overrides Whisper's language detection for translation purposes.

**Examples:**

1.  **List available input devices:**
    ```bash
    python stt_stream_client.py --device list
    ```

2.  **Basic real-time STT (using default mic):**
    ```bash
    python stt_stream_client.py ws://<server_ip>:8000/v1/audio/transcriptions/ws
    ```

3.  **Real-time STT using device index 2:**
    ```bash
    python stt_stream_client.py ws://<server_ip>:8000/v1/audio/transcriptions/ws -d 2
    ```

4.  **Real-time STT with Chinese -> English translation:**
    ```bash
    python stt_stream_client.py ws://<server_ip>:8000/v1/audio/transcriptions/ws --translate --target-lang en --source-lang zh
    ```

5.  **Real-time STT with translation to Japanese (auto-detect source):**
    ```bash
    python stt_stream_client.py ws://<server_ip>:8000/v1/audio/transcriptions/ws --translate --target-lang ja
    ```

6.  **Save outputs to a specific directory:**
    ```bash
    python stt_stream_client.py ws://<server_ip>:8000/v1/audio/transcriptions/ws --output-dir ./my_meeting_notes
    ```

**Stopping the Client:**

* Press `Ctrl + C` in the terminal where the client is running.
* The client will attempt to gracefully stop the audio stream, send an end signal to the server, save the transcript, and potentially ask if you want to generate a summary.

**Output Files:**

* Upon stopping, the client creates a subdirectory within the specified output directory (default: `./k.audio_output`). The subdirectory is named with the session's start timestamp (e.g., `20250427_130800`).
* Inside this subdirectory:
    * `transcript.txt`: Contains the full transcribed text, with line breaks between segments.
    * `summary.txt`: Contains the LLM-generated summary (if summarization was requested and successful).

## Troubleshooting

* **Connection Refused:** Ensure the K.audio server is running and accessible at the specified URL. Check firewalls on both client and server machines. Verify the IP address and port.
* **PortAudio Errors (Linux):** Make sure you installed `portaudio19-dev` (or equivalent) *before* running `pip install -r requirements.txt`.
* **Cannot Find Audio Device / Invalid Device Index:** Run with `--device list` to see available devices and their correct indices. Ensure the microphone is properly connected and recognized by the OS.
* **Permission Denied (Audio):** On some Linux systems, your user might need to be part of the `audio` group to access audio devices.
* **Translation/Summarization Errors:** Check the K.audio server logs for errors related to the LLM API call (connection issues, invalid API key, LLM service errors).