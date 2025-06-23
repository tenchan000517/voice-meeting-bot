from fastapi import FastAPI, File, UploadFile, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn
import os
import logging
from datetime import datetime, timedelta
from typing import Optional, List
import asyncio
from dotenv import load_dotenv

from src.models import init_db
from src.transcription import TranscriptionService
from src.summarization import SummarizationService
from src.meeting_manager import MeetingManager

# Load environment variables
load_dotenv()

# Configure logging with file rotation
import logging.handlers
import os
from pathlib import Path

# Create logs directory
log_dir = Path(__file__).parent / "logs"
log_dir.mkdir(exist_ok=True)

# Configure rotating file handler
error_handler = logging.handlers.RotatingFileHandler(
    log_dir / "api-error.log",
    maxBytes=5*1024*1024,  # 5MB
    backupCount=3
)
error_handler.setLevel(logging.ERROR)

access_handler = logging.handlers.RotatingFileHandler(
    log_dir / "api-access.log", 
    maxBytes=5*1024*1024,  # 5MB
    backupCount=3
)
access_handler.setLevel(logging.INFO)

# Configure console handler
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)

# Set formatter
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
error_handler.setFormatter(formatter)
access_handler.setFormatter(formatter)
console_handler.setFormatter(formatter)

# Configure root logger
logging.basicConfig(
    level=getattr(logging, os.getenv('LOG_LEVEL', 'INFO')),
    handlers=[console_handler, access_handler, error_handler]
)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="Voice Meeting Recorder API",
    description="API for transcribing and summarizing Discord voice meetings",
    version="1.0.0"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify exact origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize services
transcription_service = TranscriptionService()
summarization_service = SummarizationService()
meeting_manager = MeetingManager()

# Pydantic models
class TranscriptionRequest(BaseModel):
    meeting_id: str
    speaker_id: str
    timestamp: datetime

class SummarizationRequest(BaseModel):
    meeting_id: str
    transcript_text: str
    participants: List[str]
    duration_minutes: int

class MeetingStatus(BaseModel):
    meeting_id: str
    status: str
    participants: List[str]
    start_time: datetime
    duration_minutes: Optional[int] = None
    transcript_progress: Optional[float] = None

@app.on_event("startup")
async def startup_event():
    """Initialize database and services on startup"""
    try:
        init_db()
        logger.info("Database initialized successfully")
        
        # Initialize Whisper model
        await transcription_service.initialize()
        logger.info("Transcription service initialized")
        
        # Check Ollama connection
        await summarization_service.initialize()
        logger.info("Summarization service initialized")
        
    except Exception as e:
        logger.error(f"Failed to initialize services: {e}")
        raise

@app.get("/")
async def root():
    """Health check endpoint"""
    return {
        "message": "Voice Meeting Recorder API",
        "status": "online",
        "timestamp": datetime.now(),
        "services": {
            "transcription": transcription_service.is_ready(),
            "summarization": summarization_service.is_ready()
        }
    }

@app.post("/transcribe")
async def transcribe_audio(
    background_tasks: BackgroundTasks,
    audio_file: UploadFile = File(...),
    meeting_id: str = None,
    speaker_id: str = None,
    timestamp: str = None
):
    """Transcribe audio file to text"""
    try:
        # Validate file type
        if not audio_file.content_type.startswith('audio/'):
            raise HTTPException(status_code=400, detail="File must be an audio file")
        
        # Check file size
        max_size = int(os.getenv('MAX_FILE_SIZE_MB', 100)) * 1024 * 1024
        file_size = len(await audio_file.read())
        await audio_file.seek(0)  # Reset file pointer
        
        if file_size > max_size:
            raise HTTPException(status_code=413, detail="File too large")
        
        # Save uploaded file temporarily
        temp_path = await transcription_service.save_temp_file(audio_file)
        
        # Start transcription in background
        background_tasks.add_task(
            transcription_service.transcribe_file,
            temp_path,
            meeting_id,
            speaker_id,
            timestamp
        )
        
        return {
            "message": "Transcription started",
            "meeting_id": meeting_id,
            "status": "processing"
        }
        
    except Exception as e:
        logger.error(f"Transcription error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/summarize")
async def summarize_meeting(request: SummarizationRequest):
    """Generate meeting summary from transcript"""
    try:
        # Generate summary using Ollama
        summary = await summarization_service.create_summary(
            meeting_id=request.meeting_id,
            transcript=request.transcript_text,
            participants=request.participants,
            duration=request.duration_minutes
        )
        
        # Save summary to file
        summary_path = await summarization_service.save_summary(
            request.meeting_id,
            summary
        )
        
        return {
            "meeting_id": request.meeting_id,
            "summary": summary,
            "summary_file": summary_path,
            "status": "completed"
        }
        
    except Exception as e:
        logger.error(f"Summarization error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/meeting/{meeting_id}/status")
async def get_meeting_status(meeting_id: str) -> MeetingStatus:
    """Get current status of a meeting recording"""
    try:
        status = await meeting_manager.get_meeting_status(meeting_id)
        if not status:
            raise HTTPException(status_code=404, detail="Meeting not found")
        
        return status
        
    except Exception as e:
        logger.error(f"Status check error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/meeting/{meeting_id}/transcript")
async def get_meeting_transcript(meeting_id: str):
    """Get full transcript for a meeting"""
    try:
        transcript = await meeting_manager.get_transcript(meeting_id)
        if not transcript:
            raise HTTPException(status_code=404, detail="Transcript not found")
        
        return {
            "meeting_id": meeting_id,
            "transcript": transcript,
            "timestamp": datetime.now()
        }
        
    except Exception as e:
        logger.error(f"Transcript retrieval error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/meeting/start")
async def start_meeting(request: dict):
    """Start a new meeting"""
    try:
        meeting_id = request.get("meeting_id")
        participants = request.get("participants", [])
        
        await meeting_manager.create_meeting(
            meeting_id=meeting_id,
            discord_guild_id=request.get("discord_guild_id"),
            discord_channel_id=request.get("discord_channel_id"),
            meeting_title=request.get("meeting_title"),
            participants=participants
        )
        
        return {
            "meeting_id": meeting_id,
            "status": "started",
            "timestamp": datetime.now()
        }
        
    except Exception as e:
        logger.error(f"Start meeting error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/meeting/finalize")
async def finalize_meeting(request: dict):
    """Finalize meeting and trigger processing"""
    try:
        meeting_id = request.get("meeting_id")
        
        await meeting_manager.update_meeting_status(meeting_id, "processing")
        
        return {
            "meeting_id": meeting_id,
            "status": "processing",
            "timestamp": datetime.now()
        }
        
    except Exception as e:
        logger.error(f"Finalize meeting error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/meeting/{meeting_id}")
async def delete_meeting(meeting_id: str):
    """Delete meeting data and files"""
    try:
        await meeting_manager.delete_meeting(meeting_id)
        return {
            "meeting_id": meeting_id,
            "status": "deleted",
            "timestamp": datetime.now()
        }
        
    except Exception as e:
        logger.error(f"Deletion error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health_check():
    """Detailed health check for monitoring"""
    try:
        return {
            "status": "healthy",
            "timestamp": datetime.now(),
            "services": {
                "transcription": {
                    "status": "ready" if transcription_service.is_ready() else "not_ready",
                    "model": os.getenv('WHISPER_MODEL', 'base')
                },
                "summarization": {
                    "status": "ready" if summarization_service.is_ready() else "not_ready",
                    "model": os.getenv('OLLAMA_MODEL', 'gemma2:2b')
                },
                "database": {
                    "status": "connected"
                }
            },
            "version": "1.0.0"
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {
            "status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.now()
        }

if __name__ == "__main__":
    # Run the API server
    host = os.getenv('API_HOST', '0.0.0.0')
    port = int(os.getenv('API_PORT', 8000))
    debug = os.getenv('API_DEBUG', 'false').lower() == 'true'
    
    uvicorn.run(
        "main:app",
        host=host,
        port=port,
        reload=debug,
        log_level=os.getenv('LOG_LEVEL', 'info').lower()
    )