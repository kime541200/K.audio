# Python

> 客戶端裝置必須安裝好 PortAudio，細節請參考 [此文件](../client/python/README.md)

## list availiable audio device in Client end-point

```bash
$ python client/python/stt_stream_client.py --device list
Available input devices:
  4: HDA Intel PCH: ALC897 Analog (hw:1,0) 
  5: HDA Intel PCH: ALC897 Alt Analog (hw:1,2) 
  10: USB Device 0x46d:0x81b: Audio (hw:2,0) 
  12: pipewire 
  13: pulse 
  14: default (default)
2025-04-26 18:27:51,245 [INFO] Event loop finished.
```

## Use default microphone to connect to server

For example, server IP=`192.168.1.103`

```bash
python client/python/stt_stream_client.py ws://192.168.1.103:8000/v1/audio/transcriptions/ws
```

## Use specific microphone

For example, use audio device of index=10

```bash
python client/python/stt_stream_client.py ws://192.168.1.103:8000/v1/audio/transcriptions/ws --device 10
```

## Specific language to chinese

```bash
python client/python/stt_stream_client.py ws://192.168.1.103:8000/v1/audio/transcriptions/ws --language zh
```

## Specify output directory

```bash
python client/python/stt_stream_client.py ws://192.168.1.103:8000/v1/audio/transcriptions/ws --output-dir ./output
```

## Enable streaming translate

```bash
python client/python/stt_stream_client.py ws://192.168.1.103:8000/v1/audio/transcriptions/ws --translate --target-lang en
```

set source language and target language

```bash
python client/python/stt_stream_client.py ws://192.168.1.103:8000/v1/audio/transcriptions/ws --translate --target-lang en --source-lang zh
```