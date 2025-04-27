# Speech to Text Transcription and Summarization Project

This project provides a robust speech-to-text transcription service with added summarization features. It utilizes a client-server architecture for scalability and flexibility.

## Project Structure

The project is organized into the following key directories:

-   **assets/**: Contains audio files used for testing and demonstration.
-   **client/**: Holds the client-side code, enabling users to interact with the transcription and summarization service.
-   **models/**: Stores the pre-trained models used for speech recognition and summarization.
-   **server/**: Contains the backend server application, responsible for handling requests and processing audio data.
-   **k.audio_output**: This is where the generated transcriptions and summaries are outputted to.
- **docker-compose.yml**: This file contains configurations for launching the server in a docker container.

## Features

-   **Speech to Text Transcription**: Converts spoken language into text.
-   **Summarization**: Generates concise summaries of transcribed audio.
-   **Client-Server Architecture**: Allows for easy scaling and multiple client connections.
-   **Pre-trained Models**: Leverages existing models for accurate transcription and summarization.
- **Docker support**: The server can be launched in a docker container.

## Client

The `client/python` directory contains the python client. The client can be launched as a GUI.

## Server

The `server` directory contains the server files.

## Getting Started

1.  Clone the repository.
2.  Ensure you have Docker installed if you intend to use the docker-compose.yml file.
3.  Download the models to the `models` folder.
4. Follow the instructions in the client/server README.md files to start the client and server.

## Usage

-   The client sends an audio file to the server.
-   The server processes the audio.
-   The server returns a transcription and/or summary.
- output files are created in the k.audio_output folder

## Dependencies

-   Refer to `client/python/requirements.txt` for client dependencies.
-   Refer to `server/requirements.txt` for server dependencies.

## License

This project is licensed under the [License Name] - see the [LICENSE.md](LICENSE.md) file for details.