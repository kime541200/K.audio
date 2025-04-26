```bash
curl -X POST http://localhost:8000/v1/audio/transcriptions \
     -H "accept: application/json" \
     -H "Content-Type: multipart/form-data" \
     -F "file=@/home/kim/workspace/myproject/dev/K.audio/assets/test_audio_chinese.wav" \
     -F "language=zh" \
     -F "response_format=verbose_json"
```