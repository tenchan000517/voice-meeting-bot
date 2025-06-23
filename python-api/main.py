from fastapi import FastAPI, File, UploadFile, HTTPException, BackgroundTasks, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel
import uvicorn
import os
import logging
from datetime import datetime, timedelta
from typing import Optional, List
import asyncio
from dotenv import load_dotenv
from pathlib import Path
import json
import httpx

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

async def send_webhook_notification(meeting_id: str, webhook_data: dict):
    """Send webhook notification to Discord bot"""
    try:
        webhook_url = os.getenv('DISCORD_WEBHOOK_URL', 'http://localhost:3002/webhook/meeting-completed')
        
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(webhook_url, json=webhook_data)
            response.raise_for_status()
            logger.info(f"Webhook sent successfully for meeting {meeting_id}")
    except httpx.TimeoutException:
        logger.warning(f"Webhook timeout for meeting {meeting_id} - falling back to polling")
    except Exception as e:
        logger.error(f"Webhook failed for meeting {meeting_id}: {e} - falling back to polling")

async def process_transcription(
    file_path: str,
    meeting_id: str,
    speaker_id: str,
    timestamp: str,
    chunk_index: str = None
):
    """Process transcription and save to database"""
    try:
        # Handle None values with defaults
        if not meeting_id:
            meeting_id = "unknown_meeting"
            logger.warning("Meeting ID is None, using default")
        
        if not speaker_id:
            speaker_id = "unknown_speaker"
            logger.warning("Speaker ID is None, using default")
        
        logger.info(f"Processing transcription for meeting: {meeting_id}, speaker: {speaker_id}, chunk: {chunk_index}")
        
        # Perform transcription
        result = await transcription_service.transcribe_file(
            file_path,
            meeting_id,
            speaker_id,
            timestamp
        )
        
        # Save to database
        if result and result.get("text"):
            await meeting_manager.add_transcript_segment(
                meeting_id=meeting_id,
                speaker_id=speaker_id,
                speaker_name=f"User_{speaker_id}",
                text=result["text"],
                confidence=result.get("confidence", 0.0),
                start_time=datetime.fromisoformat(result["timestamp"]) if result.get("timestamp") else datetime.utcnow(),
                duration_seconds=result.get("duration", 0.0),
                audio_file_path=file_path
            )
            
            logger.info(f"Transcription saved to database for meeting {meeting_id}")
            
            # Update completed chunks count
            await meeting_manager.increment_completed_chunks(meeting_id)
            
            # Check if all chunks are completed
            if await meeting_manager.check_all_chunks_completed(meeting_id):
                logger.info(f"All chunks completed for meeting {meeting_id}, triggering summarization")
                await meeting_manager.trigger_hierarchical_summarization(meeting_id)
                
                # Send webhook notification after summarization is complete
                webhook_data = {
                    "meeting_id": meeting_id,
                    "event": "meeting_completed",
                    "timestamp": datetime.now().isoformat(),
                    "download_links": {
                        "summary": f"/download/meeting/{meeting_id}/summary",
                        "transcript": f"/download/meeting/{meeting_id}/transcript",
                        "chunks": f"/download/meeting/{meeting_id}/chunks"
                    }
                }
                await send_webhook_notification(meeting_id, webhook_data)
        else:
            logger.warning(f"No transcription text to save for meeting {meeting_id}")
            
    except Exception as e:
        logger.error(f"Failed to process transcription: {e}")
        if meeting_id and meeting_id != "unknown_meeting":
            await meeting_manager.update_processing_status(
                meeting_id,
                transcription_status="failed",
                error_message=str(e)
            )

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
    meeting_id: str = Form(None),
    speaker_id: str = Form(None),
    timestamp: str = Form(None)
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
            process_transcription,
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
        transcript = await meeting_manager.get_meeting_transcript(meeting_id)
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
        audio_files_count = request.get("audio_files_count", 1)
        
        await meeting_manager.update_meeting_status(meeting_id, "processing")
        
        # Set the total number of chunks to expect
        await meeting_manager.set_total_chunks(meeting_id, audio_files_count)
        
        logger.info(f"Meeting finalized: {meeting_id}, expecting {audio_files_count} audio chunks")
        
        return {
            "meeting_id": meeting_id,
            "status": "processing",
            "timestamp": datetime.now(),
            "expected_chunks": audio_files_count
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

@app.get("/download/meeting/{meeting_id}/summary")
async def download_meeting_summary(meeting_id: str):
    """Download meeting summary as Markdown file"""
    try:
        output_dir = Path(__file__).parent / "output"
        
        # Find the summary file for the meeting
        summary_files = list(output_dir.glob(f"meeting_{meeting_id}_*.md"))
        if not summary_files:
            raise HTTPException(status_code=404, detail="Summary not found")
        
        summary_file = summary_files[0]  # Get the latest file
        
        if not summary_file.exists():
            raise HTTPException(status_code=404, detail="Summary file not found")
        
        return FileResponse(
            path=str(summary_file),
            filename=f"meeting_summary_{meeting_id}.md",
            media_type="text/markdown"
        )
        
    except Exception as e:
        logger.error(f"Download summary error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/download/meeting/{meeting_id}/transcript")
async def download_meeting_transcript(meeting_id: str):
    """Download meeting transcript as plain text"""
    try:
        transcript_segments = await meeting_manager.get_transcript_segments(meeting_id)
        if not transcript_segments:
            raise HTTPException(status_code=404, detail="Transcript not found")
        
        # Format transcript as plain text
        transcript_text = f"Meeting Transcript: {meeting_id}\n"
        transcript_text += f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        transcript_text += "=" * 50 + "\n\n"
        
        for segment in transcript_segments:
            timestamp = segment.get('start_time', 'Unknown')
            speaker = segment.get('speaker_name', 'Unknown Speaker')
            text = segment.get('text', '')
            transcript_text += f"[{timestamp}] {speaker}: {text}\n\n"
        
        return PlainTextResponse(
            content=transcript_text,
            headers={
                "Content-Disposition": f"attachment; filename=meeting_transcript_{meeting_id}.txt"
            }
        )
        
    except Exception as e:
        logger.error(f"Download transcript error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/download/meeting/{meeting_id}/chunks")
async def download_meeting_chunks_info(meeting_id: str):
    """Download meeting audio chunks information as JSON"""
    try:
        # Get meeting info from database
        meeting_info = await meeting_manager.get_meeting_status(meeting_id)
        if not meeting_info:
            raise HTTPException(status_code=404, detail="Meeting not found")
        
        # Get transcript segments to identify audio files
        transcript_segments = await meeting_manager.get_transcript_segments(meeting_id)
        if not transcript_segments:
            raise HTTPException(status_code=404, detail="No audio chunks found")
        
        chunks_info = []
        for idx, segment in enumerate(transcript_segments):
            audio_file_path = segment.get('audio_file_path', '')
            if audio_file_path:
                filename = Path(audio_file_path).name
                chunks_info.append({
                    "chunk_index": idx,
                    "filename": filename,
                    "speaker_id": segment.get('speaker_id', ''),
                    "speaker_name": segment.get('speaker_name', ''),
                    "duration": segment.get('duration_seconds', 0),
                    "start_time": str(segment.get('start_time', '')),
                    "download_url": f"/download/meeting/{meeting_id}/chunk/{filename}"
                })
        
        chunks_data = {
            "meeting_id": meeting_id,
            "total_chunks": len(chunks_info),
            "chunks": chunks_info,
            "generated_at": datetime.now().isoformat()
        }
        
        return PlainTextResponse(
            content=json.dumps(chunks_data, indent=2),
            headers={
                "Content-Disposition": f"attachment; filename=meeting_chunks_{meeting_id}.json",
                "Content-Type": "application/json"
            }
        )
        
    except Exception as e:
        logger.error(f"Download chunks info error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/download/meeting/{meeting_id}/chunk/{filename}")
async def download_audio_chunk(meeting_id: str, filename: str):
    """Download individual audio chunk file"""
    try:
        # Security check: ensure filename doesn't contain path traversal
        if ".." in filename or "/" in filename or "\\" in filename:
            raise HTTPException(status_code=400, detail="Invalid filename")
        
        # Look for the file in temp directory first (for recent recordings)
        temp_dir = Path(__file__).parent.parent / "node-bot" / "temp"
        chunk_file = temp_dir / filename
        
        if not chunk_file.exists():
            # Look in output directory as backup
            output_dir = Path(__file__).parent / "temp"
            chunk_file = output_dir / filename
        
        if not chunk_file.exists():
            raise HTTPException(status_code=404, detail="Audio chunk not found")
        
        return FileResponse(
            path=str(chunk_file),
            filename=filename,
            media_type="audio/wav"
        )
        
    except Exception as e:
        logger.error(f"Download audio chunk error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

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