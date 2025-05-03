from faster_whisper import WhisperModel
# from pydub import AudioSegment # 非流式時使用 pydub，流式時處理原始 bytes 更高效
import numpy as np # faster-whisper 可以接受 numpy array
import webrtcvad
import os
import tempfile
import io
import logging
import asyncio
from typing import BinaryIO, Tuple, Dict, Any, AsyncGenerator, List
from collections import deque # 用於緩衝音訊幀

from ..core.config import settings

# 設定日誌記錄器
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- 全局變數存儲加載的模型 ---
# 我們將在 FastAPI 的 lifespan 事件中加載模型，避免每次請求都加載
stt_model: WhisperModel | None = None


# --- 可以在類別或函數開頭定義這些常數，方便調整 ---
DEFAULT_TEMPERATURE = 0.0
# DEFAULT_NO_SPEECH_THRESHOLD = 0.7 # 無法傳遞給 numpy 輸入的 transcribe
# DEFAULT_LOG_PROB_THRESHOLD = -0.8 # 無法傳遞給 numpy 輸入的 transcribe

# *** 主要修改這裡：調整後處理閾值 ***
FILTER_NO_SPEECH_PROB_THRESHOLD = 0.85 # 大幅提高此值 (例如設為 0.8 / 0.85 / 0.9)
FILTER_AVG_LOGPROB_THRESHOLD = -1.2    # 可以稍微降低此值 (更寬鬆)，避免誤殺
# 常見幻覺詞列表 (可自行擴充)
COMMON_HALLUCINATIONS = [
    "Thank you for watching",
    "Thanks for watching",
    "Transcribed by",
    "Please subscribe",
    "...", # 避免單純的點點點
]

def load_stt_model():
    global stt_model # 聲明修改全局變數
    if stt_model is None:
        logger.info(f"Loading STT model '{settings.stt_model_path}' on device '{settings.stt_device}' with compute type '{settings.stt_compute_type}'...")
        try:
            if not os.path.exists(settings.stt_model_path):
                 logger.error(f"STT model path not found: {settings.stt_model_path}")
                 stt_model = None # 確保路徑不存在時為 None
                 return stt_model # <--- 如果路徑錯誤，返回 None

            # --- 賦值 ---
            stt_model = WhisperModel(
                settings.stt_model_path,
                device=settings.stt_device,
                compute_type=settings.stt_compute_type
            )
            logger.info("STT model loaded successfully.") # <--- 成功日志
        except Exception as e:
            logger.error(f"Error loading STT model: {e}", exc_info=True)
            stt_model = None # 確保異常時為 None

    return stt_model # <--- **新增**: 返回最終的 stt_model (可能是對象或 None)

def unload_stt_model():
    """卸載模型並清理資源 (如果需要)"""
    global stt_model
    if stt_model is not None:
        logger.info("Unloading STT model...")
        # faster-whisper 模型加載後可能不需要顯式卸載來釋放主要記憶體，
        # Python 的垃圾回收應該會處理。CTranslate2 可能有更複雜的資源管理，
        # 但通常刪除對象引用就足夠了。
        # 如果未來遇到資源洩漏，可能需要研究 CTranslate2 的底層 API。
        del stt_model
        stt_model = None
        # 如果使用 GPU，可以嘗試清理 CUDA 緩存 (如果庫支援)
        # import torch
        # if settings.stt_device == "cuda":
        #     torch.cuda.empty_cache()
        logger.info("STT model unloaded.")


# --- 非流式轉錄函數 (保持不變，以防未來仍需使用) ---
def transcribe_audio_file(file: BinaryIO, language: str | None = None, initial_prompt: str | None = None) -> Tuple[str, list, Dict[str, Any]]:
    """
    轉錄完整的音訊檔案 (非流式)。
    注意: 此函數使用了 pydub 和臨時文件，與流式處理不同。
    """
    if stt_model is None:
        logger.error("STT model is not loaded. Cannot transcribe.")
        raise ValueError("STT model is not available.")
    try:
        from pydub import AudioSegment # 局部導入
        logger.info("Reading audio file (non-streaming)...")
        file.seek(0)
        audio_data = io.BytesIO(file.read())
        audio = AudioSegment.from_file(audio_data)
        logger.info("Converting audio format (non-streaming)...")
        audio = audio.set_frame_rate(16000).set_channels(1).set_sample_width(2)
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=True) as tmp_audio_file:
            audio.export(tmp_audio_file.name, format="wav")
            logger.info(f"Temporary WAV file created: {tmp_audio_file.name}")
            transcribe_options = {
                "language": language, "initial_prompt": initial_prompt,
                "word_timestamps": False, "vad_filter": True,
                "vad_parameters": {"min_silence_duration_ms": 500}
            }
            transcribe_options = {k: v for k, v in transcribe_options.items() if v is not None}
            logger.info(f"Starting transcription (non-streaming) with options: {transcribe_options}")
            segments_generator, info = stt_model.transcribe(tmp_audio_file.name, **transcribe_options)
            segments_list = []
            full_text_list = []
            for segment in segments_generator:
                segments_list.append({"start": segment.start, "end": segment.end, "text": segment.text.strip()})
                full_text_list.append(segment.text.strip())
            full_text = " ".join(full_text_list)
            info_dict = {"language": info.language, "language_probability": info.language_probability, "duration": info.duration}
            logger.info(f"Transcription finished (non-streaming). Detected language: {info.language}")
            return full_text, segments_list, info_dict
    except Exception as e:
        logger.error(f"Error during non-streaming transcription: {e}", exc_info=True)
        raise

class AudioTranscriptionStreamer:
    """處理單個 WebSocket 連接的音訊流"""

    # VAD 接受 10, 20, 30 ms 的幀
    # Whisper 使用 16kHz 採樣率, 16-bit PCM
    # 30 ms = 0.03 s
    # 樣本數 = 16000 Hz * 0.03 s = 480 樣本
    # 字節數 = 480 樣本 * 2 bytes/樣本 = 960 字節
    MS_PER_FRAME = 30  # VAD 幀長度 (毫秒)
    SAMPLES_PER_FRAME = int(16000 * MS_PER_FRAME / 1000)
    BYTES_PER_FRAME = SAMPLES_PER_FRAME * 2 # (16-bit = 2 bytes)

    # 我們累積多少秒的靜音後才最終確定一個語句結束
    # 這有助於處理語句中的短暫停頓
    SILENCE_THRESHOLD_SEC = 0.5 # 半秒靜音觸發轉錄

    def __init__(self, language: str | None = None, initial_prompt: str | None = None):
        if stt_model is None:
            raise ValueError("STT model is not loaded.")
        self.stt_model = stt_model # 使用加載好的全局模型
        self.language = language
        self.initial_prompt = initial_prompt

        # 初始化 VAD
        self.vad = webrtcvad.Vad()
        # 設置 VAD 敏感度 (0-3, 3 最敏感)
        self.vad.set_mode(1) # 模式 1 或 2 通常比較平衡

        # 音訊緩衝區
        self._buffer = deque()
        self._frames_processed = 0 # 已處理的幀數 (用於計算時間戳)
        self._speech_frames = deque() # 累積檢測到的語音幀
        self._current_speech_start_time = 0.0 # 當前語音片段開始時間
        self._silence_frames_after_speech = 0 # 檢測到語音後的連續靜音幀數
        self._is_speaking = False # 當前是否處於語音活動狀態

        # 計算觸發轉錄所需的靜音幀數
        self._silence_frames_needed = int(self.SILENCE_THRESHOLD_SEC * 1000 / self.MS_PER_FRAME)

        logger.info(f"AudioTranscriptionStreamer initialized. Silence threshold: {self.SILENCE_THRESHOLD_SEC}s ({self._silence_frames_needed} frames)")

    async def _transcribe_segment(self, audio_data: bytes) -> AsyncGenerator[Dict[str, Any], None]:
        """
        在背景執行單個語音片段的轉錄，並應用過濾減少幻覺。
        """
        if not audio_data:
            logger.info("Skipping transcription for empty audio data.")
            return

        start_time = self._current_speech_start_time # 假設 self._current_speech_start_time 在 process_audio_chunk 中被設置
        logger.info(f"Transcribing segment starting at {start_time:.2f}s...")

        try:
            # 將 bytes 轉換為 float32 numpy array (Whisper 需要這個格式)
            audio_np = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32) / 32768.0

            # --- 設定轉錄選項 ---
            # *** 修改點：移除所有不被接受的參數 ***
            transcribe_options = {
                # "language": self.language, # 語言提示通常是支持的
                # "initial_prompt": self.initial_prompt, # 已移除
                # "temperature": DEFAULT_TEMPERATURE, # <--- 移除
                # "no_speech_threshold": DEFAULT_NO_SPEECH_THRESHOLD, # <--- 移除
                # "log_prob_threshold": DEFAULT_LOG_PROB_THRESHOLD, # <--- 移除
                # "word_timestamps": False, # 已移除
                # "vad_filter": False,      # 已移除
            }
            # 移除字典中值為 None 的項目 (現在主要影響 language)
            transcribe_options = {k: v for k, v in transcribe_options.items() if v is not None}

            logger.info(f"Starting transcription for segment at {start_time:.2f}s with options: {transcribe_options}")

            # 使用 run_in_executor 在背景線程執行轉錄
            loop = asyncio.get_running_loop()
            # 確保 self.stt_model 存在且已加載
            if self.stt_model is None:
                 logger.error("STT model is not loaded inside streamer.")
                 raise ValueError("STT model not loaded")

            segments_generator, info = await loop.run_in_executor(
                None, # 使用默認線程池
                self.stt_model.transcribe, # 調用模型的 transcribe
                audio_np,                 # 傳遞 numpy array
                **transcribe_options
            )

            # --- 處理並過濾轉錄結果 ---
            segment_text_parts: List[str] = []
            last_end_time = start_time # 初始化為片段開始時間
            low_confidence_segments_skipped = 0
            no_speech_segments_skipped = 0
            hallucination_warnings = 0
            total_segments_processed = 0

            for segment in segments_generator:
                total_segments_processed += 1
                absolute_start = start_time + segment.start
                absolute_end = start_time + segment.end
                text = segment.text.strip() if segment.text else ""

                # 1. 過濾高 "無語音" 概率的片段
                if segment.no_speech_prob > FILTER_NO_SPEECH_PROB_THRESHOLD:
                    logger.info(f"Segment [{absolute_start:.2f}s -> {absolute_end:.2f}s] skipped (no_speech_prob: {segment.no_speech_prob:.2f} > {FILTER_NO_SPEECH_PROB_THRESHOLD}) Text: '{text}'")
                    no_speech_segments_skipped += 1
                    continue

                # 2. 過濾低平均對數概率的片段 (可能為幻覺或低質量識別)
                if segment.avg_logprob < FILTER_AVG_LOGPROB_THRESHOLD:
                    logger.info(f"Segment [{absolute_start:.2f}s -> {absolute_end:.2f}s] skipped (avg_logprob: {segment.avg_logprob:.2f} < {FILTER_AVG_LOGPROB_THRESHOLD}) Text: '{text}'")
                    low_confidence_segments_skipped += 1
                    continue

                # 3. 檢查是否包含常見幻覺詞 (僅發出警告，除非您想完全跳過)
                contains_hallucination = False
                for hallucination in COMMON_HALLUCINATIONS:
                    # 進行不區分大小寫的檢查，並確保不是被包含在正常詞語中 (例如 "thanks" vs "Thanks for watching")
                    # 這裡用簡單的 in 檢查，更複雜的匹配可能需要正則表達式
                    if hallucination.lower() in text.lower():
                        logger.warning(f"Segment [{absolute_start:.2f}s -> {absolute_end:.2f}s] potentially contains hallucination phrase '{hallucination}'. Text: '{text}'")
                        hallucination_warnings += 1
                        contains_hallucination = True
                        # break # 如果找到一個就足夠發警告
                # 如果決定要因為幻覺詞而跳過，可以在這裡加 continue
                # if contains_hallucination:
                #    continue

                # --- 如果片段通過所有過濾 ---
                if text: # 確保文本不為空
                    segment_text_parts.append(text)
                    last_end_time = absolute_end # 更新最後有效文本的結束時間
                # logger.debug(f"Valid segment accepted: [{absolute_start:.2f}s -> {absolute_end:.2f}s] {text}")

            # --- 組合最終文本並產生結果 ---
            full_text = " ".join(segment_text_parts)

            # 僅在實際有文本輸出時才產生結果
            if full_text:
                confidence_score = None # faster-whisper 的 info 可能不直接提供整體置信度, 但可以基於過濾情況判斷
                logger.info(f"Segment transcription complete: [{start_time:.2f}s -> {last_end_time:.2f}s] Text: '{full_text}' "
                            f"(Processed: {total_segments_processed}, Skipped_NoSpeech: {no_speech_segments_skipped}, Skipped_LowConf: {low_confidence_segments_skipped}, HallucinationWarn: {hallucination_warnings})")
                yield {
                    "type": "final",
                    "start": start_time,
                    "end": last_end_time, # 使用最後有效片段的結束時間
                    "text": full_text,
                    "language": info.language,
                    "language_probability": info.language_probability,
                    # 提供一些過濾的統計信息，供上層參考
                    "confidence_info": {
                         "total_segments_processed": total_segments_processed,
                         "no_speech_segments_skipped": no_speech_segments_skipped,
                         "low_confidence_segments_skipped": low_confidence_segments_skipped,
                         "hallucination_warnings": hallucination_warnings,
                         "avg_logprob_threshold": FILTER_AVG_LOGPROB_THRESHOLD,
                         "no_speech_prob_threshold": FILTER_NO_SPEECH_PROB_THRESHOLD
                    }
                }
            else:
                logger.info(f"Segment transcription complete but no text output after filtering: [{start_time:.2f}s -> {last_end_time:.2f}s] "
                            f"(Processed: {total_segments_processed}, Skipped_NoSpeech: {no_speech_segments_skipped}, Skipped_LowConf: {low_confidence_segments_skipped}, HallucinationWarn: {hallucination_warnings})")
                # 可以選擇性地發送一個空的 final 消息或 info 消息
                # yield {"type": "info", "message": "No speech detected or filtered out in segment"}

        except Exception as e:
            logger.error(f"Error during segment transcription starting at {start_time:.2f}s: {e}", exc_info=True)
            yield {"type": "error", "message": f"Transcription error: {e}"}

    async def process_audio_chunk(self, chunk: bytes) -> AsyncGenerator[Dict[str, Any], None]:
        """處理從 WebSocket 傳來的一個音訊塊"""
        self._buffer.append(chunk)
        accumulated_bytes = b"".join(self._buffer)

        # 檢查是否有足夠的數據組成一個 VAD 幀
        while len(accumulated_bytes) >= self.BYTES_PER_FRAME:
            frame = accumulated_bytes[:self.BYTES_PER_FRAME]
            accumulated_bytes = accumulated_bytes[self.BYTES_PER_FRAME:]

            self._frames_processed += 1
            frame_start_time = (self._frames_processed - 1) * self.MS_PER_FRAME / 1000.0

            try:
                is_speech = self.vad.is_speech(frame, 16000)
            except Exception as e:
                # VAD 可能對異常幀拋出錯誤
                logger.warning(f"VAD error on frame: {e}")
                is_speech = False # 當作靜音處理

            if is_speech:
                #logger.debug(f"Frame {self._frames_processed}: Speech detected")
                if not self._is_speaking:
                    # 從靜音變為語音 -> 語音片段開始
                    self._is_speaking = True
                    self._current_speech_start_time = frame_start_time
                    logger.info(f"Speech segment started at {self._current_speech_start_time:.2f}s")
                    # 清空之前的語音幀並添加當前幀
                    self._speech_frames.clear()
                    self._speech_frames.append(frame)
                    self._silence_frames_after_speech = 0 # 重置靜音計數
                    yield {"type": "info", "message": "Speech detected"}
                else:
                    # 持續語音 -> 添加幀到緩衝
                    self._speech_frames.append(frame)
                    self._silence_frames_after_speech = 0 # 重置靜音計數

            else: # is not speech
                #logger.debug(f"Frame {self._frames_processed}: Silence detected")
                if self._is_speaking:
                    # 從語音變為靜音
                    self._silence_frames_after_speech += 1
                    # 添加靜音幀到緩衝，以便 Whisper 能處理結尾的靜音
                    self._speech_frames.append(frame)

                    if self._silence_frames_after_speech >= self._silence_frames_needed:
                        # 連續靜音達到閾值 -> 語音片段結束，觸發轉錄
                        logger.info(f"Silence threshold reached after speech at frame {self._frames_processed}. Triggering transcription.")
                        segment_data = b"".join(self._speech_frames)
                        self._speech_frames.clear()
                        self._is_speaking = False
                        self._silence_frames_after_speech = 0

                        # 異步執行轉錄並產生結果
                        async for result in self._transcribe_segment(segment_data):
                             yield result

                        yield {"type": "info", "message": "Silence detected"}
                else:
                    # 持續靜音 -> 不處理，等待語音
                    pass

        # 將剩餘不足一幀的數據放回緩衝區
        self._buffer.clear()
        if accumulated_bytes:
            self._buffer.append(accumulated_bytes)

    async def stream_complete(self) -> AsyncGenerator[Dict[str, Any], None]:
        """處理音訊流結束時可能剩餘的語音數據"""
        logger.info("Audio stream complete. Processing remaining speech data...")
        if self._is_speaking and self._speech_frames:
             logger.info("Transcribing final segment...")
             segment_data = b"".join(self._speech_frames)
             self._speech_frames.clear()
             self._is_speaking = False
             async for result in self._transcribe_segment(segment_data):
                 yield result
        logger.info("Streamer cleanup complete.")