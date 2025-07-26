# K.audio - Real-time STT/Translation Python Client and Server

This project provides a real-time Speech-to-Text (STT) and translation client implemented in Python, along with the necessary components for setting up a server using Docker. It leverages technologies like Whisper for STT, CTtranslate2 for translation, and FastAPI for the server API.

## Overview

K.audio allows users to stream audio from their microphone to a server, receive real-time transcriptions, and optionally translate the transcriptions. It also includes features for text-to-speech (TTS) and conversation mode with an LLM. The server is designed to be run in a Docker container, making deployment and management easier.

## Features

### Client (Python)

-   Real-time audio streaming from microphone to server.
-   Receives and displays final transcription results.
-   Optional real-time translation of transcribed segments.
-   Automatically detects available input audio devices.
-   Saves full transcript and optional summary to local files upon closing.
-   Allows specifying source/target languages and initial STT prompt.
-   Configurable output directory for results.
-   GUI interface built with CustomTkinter.
-   Text-to-Speech (TTS) functionality.
-   Conversation mode with integration of an LLM for responses.

### Server (Docker)

-   Runs the K.audio server using Docker containers.
-   Supports GPU acceleration for faster processing.
-   Configurable environment variables for STT model and settings.
-   API endpoints for STT, translation, summarization, and TTS.

## Getting Started

### Prerequisites

-   Python 3.9 or higher.
-   pip (Python's package installer).
-   Docker and Docker Compose.
-   PortAudio (for Linux users).

### Installation

1.  **Clone the repository:**

    ```bash
    git clone <repository_url>
    ```

2.  **Navigate to the client directory:**

    ```bash
    cd K.audio/client/python
    ```

3.  **Create and activate a virtual environment:**

    -   **Linux/macOS:**

        ```bash
        python3 -m venv venv
        source venv/bin/activate
        ```

    -   **Windows:**

        ```bash
        python -m venv venv
        venv\Scripts\activate
        ```

4.  **Install dependencies:**

    ```bash
    pip install -r requirements.txt
    ```

    -   **Linux (Debian/Ubuntu Example):** You might need to install PortAudio first:

        ```bash
        sudo apt update
        sudo apt install portaudio19-dev python3-dev
        ```

### Usage

#### Client

```bash
python k_audio_gui_client.py
```

or for command-line client

```bash
python stt_stream_client.py <server_websocket_url> [options]
```

-   `<server_websocket_url>`: The full WebSocket URL of your K.audio server (e.g., `ws://192.168.1.103:8000/v1/audio/transcriptions/ws`).
-   Options:
    -   `-d <index_or_list>`, `--device <index_or_list>`: Specify the input audio device index. Use `-d list` to see available devices.
    -   `-o <path>`, `--output-dir <path>`: Directory to save transcript and summary files.
    -   `-l <lang_code>`, `--language <lang_code>`: Specify the source language for STT (e.g., `zh`, `en`).
    -   `-p <prompt_text>`, `--prompt <prompt_text>`: Set an initial prompt for the STT model.
    -   `--translate`: Enable real-time translation.
    -   `--target-lang <lang_code>`: Target language for translation.
    -   `--source-lang <lang_code>`: Source language for translation (optional).

#### Server

1.  Navigate to the server directory:

    ```bash
    cd K.audio/server
    ```

2.  Start the server using Docker Compose:

    ```bash
    docker-compose up --build
    ```

### Docker Compose

The `docker-compose.yml` file sets up the K.audio server using Docker. It includes:

-   Building the server image from the `./server` directory.
-   Mapping port 8000 for the server API.
-   Mounting local `models` directory to `/app/models` in the container.
-   Enabling GPU usage with the NVIDIA Container Toolkit.
-   Setting environment variables for STT device, compute type, and model path.

### Additional Scripts

-   `download_whisper.py`: Script to download and organize Whisper STT models.
-   Curl commands for file transcriptions: Found in `file_transcription_chinese_curl.md`.

## Notes

-   Ensure your server is accessible from the client machine (check IP addresses and firewalls).
-   Refer to the language-specific README (`README_zh_TW.md`) for instructions in Traditional Chinese.
-   For troubleshooting, check the server logs and the client console output.
-   Consider setting `STT_DEVICE=cpu` in the `docker-compose.yml` environment variables if you don't have a GPU.

## Contributing

Contributions to the project are welcome. Please fork the repository and submit pull requests with your changes.

## License

[Add license information here]

