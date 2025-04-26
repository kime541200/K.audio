# Real-Time Audio Transcription and Translation Service

This project provides a real-time audio transcription and translation service. It leverages a locally hosted Large Language Model (LLM) for translating transcribed text between different languages, allowing users to transcribe and understand audio content in real-time, regardless of the original language.

## Features

-   **Real-Time Transcription:** Transcribes audio input into text as it is being spoken.
-   **Real-Time Translation:** Translates the transcribed text into a different language in real-time using a local LLM.
-   **Multi-Language Support:** Supports transcription and translation across various languages.
-   **Streaming Architecture:** Uses a streaming approach for efficient real-time processing.
-   **Client-Server Model:** Designed with a clear separation between client-side audio capture and server-side processing.

## Project Structure

The project is divided into two main parts:

-   **Server:** Handles audio stream reception, transcription, translation, and result broadcasting.
    -   **Location:** `server/`
    -   **Description:** The server-side components are built to manage the core logic of the service, including the streaming pipeline and integration with the local LLM.
-   **Client:** Captures audio and sends it to the server for processing.
    -   **Location:** `client/python/`
    -   **Description:** The client-side code, written in Python, is responsible for capturing audio input and streaming it to the server for real-time processing.

## Getting Started

### Prerequisites

-   Python 3.9+
-   Docker and Docker Compose (for running the server)
-   A locally hosted LLM (refer to the server setup for specific requirements)

### Installation

1.  **Clone the repository:**
```
bash
    git clone <repository_url>
    cd <repository_directory>
    
```
2.  **Server Setup (server/)**

    -   Navigate to the `server/` directory.
    -  Make sure you install the dependencies using:
```
bash
    pip install -r requirements.txt
    
```
-   You can build the docker image using the following command:
```
bash
    docker compose build
    
```
-   Start the server using Docker Compose.
```
bash
    docker compose up -d
    
```
3.  **Client Setup (client/python/)**

    -   Navigate to the `client/python/` directory.
    -   Install the client-side dependencies:
```
bash
    pip install -r requirements.txt
    
```
4. **Download whisper model**

- Run `download_whisper.py` on the root path. It will download `medium` model by default.

### Running the Service

1.  **Start the Server:** Ensure the server is running using the instructions above.
2.  **Run the Client:**
    -   Navigate to the `client/python/` directory.
    -   Run the client script:
```
bash
    python stt_stream_client.py
    
```
## Usage

1.  Start the server.
2.  Run the client script.
3.  Speak into your microphone.
4.  View the transcribed and translated text output in the server console.

## Testing

### File Transcription test (chinese)
- run the `tests/file_transcription_chinese_curl.md` test using curl.

### STT streaming test
- run `tests/client_stt_streaming.md` using curl.

## Contributing

Contributions to this project are welcome! Please feel free to fork the repository, make your changes, and submit a pull request.

## License

This project is licensed under the [License Name] License - see the `LICENSE.md` file for details.