import whisper
import os
import tempfile
import aiofiles
from datetime import datetime, timedelta
from typing import Optional
import logging
import asyncio
from pydub import AudioSegment
import hashlib

logger = logging.getLogger(__name__)

class TranscriptionService:
    """Service for audio transcription using OpenAI Whisper"""
    
    def __init__(self):
        self.model = None
        self.model_name = os.getenv('WHISPER_MODEL', 'base')
        self.language = os.getenv('WHISPER_LANGUAGE', 'ja')
        self.device = os.getenv('WHISPER_DEVICE', 'cpu')
        self.temp_dir = os.getenv('TEMP_DIR', './temp')
        self._ensure_temp_dir()
    
    def _ensure_temp_dir(self):
        """Ensure temp directory exists"""
        os.makedirs(self.temp_dir, exist_ok=True)
    
    async def initialize(self):
        """Initialize Whisper model"""
        try:
            logger.info(f"Loading Whisper model: {self.model_name}")
            # Load model in a thread to avoid blocking
            loop = asyncio.get_event_loop()
            self.model = await loop.run_in_executor(
                None, 
                whisper.load_model, 
                self.model_name, 
                self.device
            )
            logger.info("Whisper model loaded successfully")
        except Exception as e:
            logger.error(f"Failed to load Whisper model: {e}")
            raise
    
    def is_ready(self) -> bool:
        """Check if transcription service is ready"""
        return self.model is not None
    
    async def save_temp_file(self, upload_file) -> str:
        """Save uploaded file to temp directory"""
        try:
            # Generate unique filename
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            original_name = upload_file.filename or "audio"
            filename = f"{timestamp}_{original_name}"
            file_path = os.path.join(self.temp_dir, filename)
            
            # Save file
            async with aiofiles.open(file_path, 'wb') as f:
                content = await upload_file.read()
                await f.write(content)
            
            logger.info(f"Saved temp file: {file_path}")
            return file_path
            
        except Exception as e:
            logger.error(f"Failed to save temp file: {e}")
            raise
    
    async def optimize_audio(self, input_path: str) -> str:
        """Optimize audio for Whisper processing"""
        try:
            base_name = os.path.splitext(os.path.basename(input_path))[0]
            optimized_path = os.path.join(self.temp_dir, f"{base_name}_optimized.wav")
            
            # Check if input is a raw PCM file (from Discord)
            if input_path.lower().endswith('.pcm'):
                logger.info(f"Processing raw PCM file: {input_path}")
                
                # Load raw PCM data (Discord format: 48kHz, 16-bit, mono)
                audio = AudioSegment.from_raw(
                    input_path,
                    sample_width=2,  # 16-bit = 2 bytes
                    frame_rate=48000,  # Discord voice rate
                    channels=1  # mono
                )
                
                logger.info(f"Loaded PCM: {len(audio)}ms, {audio.frame_rate}Hz, {audio.channels}ch")
                
            else:
                # Load regular audio file
                audio = AudioSegment.from_file(input_path)
                logger.info(f"Loaded audio: {len(audio)}ms, {audio.frame_rate}Hz, {audio.channels}ch")
            
            # Convert to optimal format for Whisper (16kHz, mono)
            audio = audio.set_channels(1)
            audio = audio.set_frame_rate(16000)
            
            # Export optimized audio as WAV
            audio.export(optimized_path, format="wav")
            
            logger.info(f"Audio optimized: {optimized_path} ({len(audio)}ms, 16kHz)")
            return optimized_path
            
        except Exception as e:
            logger.error(f"Audio optimization failed: {e}")
            logger.error(f"Input file: {input_path}, size: {os.path.getsize(input_path) if os.path.exists(input_path) else 'not found'} bytes")
            # Return original path if optimization fails
            return input_path
    
    async def transcribe_file(
        self, 
        file_path: str, 
        meeting_id: Optional[str] = None,
        speaker_id: Optional[str] = None,
        timestamp: Optional[str] = None
    ) -> dict:
        """Transcribe audio file to text"""
        try:
            if not self.is_ready():
                raise RuntimeError("Transcription service not initialized")
            
            # Optimize audio for better transcription
            optimized_path = await self.optimize_audio(file_path)
            
            # Perform transcription in executor to avoid blocking
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(
                None,
                self._transcribe_sync,
                optimized_path
            )
            
            # Parse result
            transcript_data = {
                "meeting_id": meeting_id,
                "speaker_id": speaker_id,
                "timestamp": timestamp or datetime.now().isoformat(),
                "text": result["text"].strip(),
                "language": result.get("language", self.language),
                "confidence": self._calculate_average_confidence(result),
                "segments": result.get("segments", []),
                "duration": result.get("duration", 0),
                "processing_time": datetime.now().isoformat()
            }
            
            # Clean up temporary files
            await self._cleanup_files([file_path, optimized_path])
            
            logger.info(f"Transcription completed for {meeting_id}")
            return transcript_data
            
        except Exception as e:
            logger.error(f"Transcription failed: {e}")
            await self._cleanup_files([file_path])
            raise
    
    def _transcribe_sync(self, file_path: str) -> dict:
        """Synchronous transcription for executor"""
        return self.model.transcribe(
            file_path,
            language=self.language,
            task="transcribe",
            word_timestamps=True,
            verbose=False
        )
    
    def _calculate_average_confidence(self, result: dict) -> float:
        """Calculate average confidence from segments"""
        try:
            segments = result.get("segments", [])
            if not segments:
                return 0.0
            
            total_confidence = 0.0
            word_count = 0
            
            for segment in segments:
                words = segment.get("words", [])
                for word in words:
                    if "probability" in word:
                        total_confidence += word["probability"]
                        word_count += 1
            
            return total_confidence / word_count if word_count > 0 else 0.0
            
        except Exception:
            return 0.0
    
    async def transcribe_realtime_chunk(
        self,
        audio_chunk: bytes,
        meeting_id: str,
        speaker_id: str,
        chunk_index: int
    ) -> dict:
        """Transcribe real-time audio chunk"""
        try:
            # Save chunk to temporary file
            chunk_filename = f"{meeting_id}_{speaker_id}_{chunk_index}.wav"
            chunk_path = os.path.join(self.temp_dir, chunk_filename)
            
            async with aiofiles.open(chunk_path, 'wb') as f:
                await f.write(audio_chunk)
            
            # Transcribe chunk
            result = await self.transcribe_file(
                chunk_path,
                meeting_id,
                speaker_id,
                datetime.now().isoformat()
            )
            
            # Add chunk-specific metadata
            result.update({
                "chunk_index": chunk_index,
                "is_realtime": True
            })
            
            return result
            
        except Exception as e:
            logger.error(f"Real-time transcription failed: {e}")
            raise
    
    async def _cleanup_files(self, file_paths: list):
        """Clean up temporary files"""
        for file_path in file_paths:
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
                    logger.debug(f"Cleaned up: {file_path}")
            except Exception as e:
                logger.warning(f"Failed to cleanup {file_path}: {e}")
    
    async def cleanup_old_files(self, hours: int = 24):
        """Clean up old temporary files"""
        try:
            current_time = datetime.now()
            cutoff_time = current_time - timedelta(hours=hours)
            
            for filename in os.listdir(self.temp_dir):
                file_path = os.path.join(self.temp_dir, filename)
                if os.path.isfile(file_path):
                    file_time = datetime.fromtimestamp(os.path.getctime(file_path))
                    if file_time < cutoff_time:
                        os.remove(file_path)
                        logger.info(f"Cleaned up old file: {filename}")
                        
        except Exception as e:
            logger.error(f"Cleanup failed: {e}")
    
    def get_supported_formats(self) -> list:
        """Get list of supported audio formats"""
        return [
            "mp3", "wav", "m4a", "flac", "ogg", 
            "aac", "wma", "aiff", "au", "webm"
        ]