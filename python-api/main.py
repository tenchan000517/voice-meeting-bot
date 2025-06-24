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

async def send_chunk_summary_to_discord(meeting_id: str, chunk_data: dict):
    """Send lightweight chunk summary notification to Discord via webhook"""
    try:
        # 軽量化：重いコンテンツをwebhookに含めず、ダウンロードリンクのみ送信
        webhook_data = {
            "meeting_id": meeting_id,
            "event": "chunk_summary",
            "chunk_index": chunk_data["chunk_index"],
            "time_range": chunk_data["time_range"],
            "timestamp": datetime.now().isoformat(),
            "download_links": {
                "chunk_summary": f"/download/meeting/{meeting_id}/chunk/{chunk_data['chunk_index']}/summary",
                "chunk_transcript": f"/download/meeting/{meeting_id}/chunk/{chunk_data['chunk_index']}/transcript"
            }
        }
        
        await send_webhook_notification(meeting_id, webhook_data)
        
        # Mark as sent in database
        await meeting_manager.mark_chunk_summary_sent(meeting_id, chunk_data["chunk_index"])
        
        logger.info(f"Sent lightweight chunk summary notification to Discord for chunk {chunk_data['chunk_index']}")
        
    except Exception as e:
        logger.error(f"Failed to send chunk summary notification to Discord: {e}")

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
            
            # NEW: Try to determine chunk index and generate real-time chunk summary
            try:
                if chunk_index is not None:
                    # Extract numeric chunk index
                    numeric_chunk_index = int(chunk_index) if isinstance(chunk_index, str) and chunk_index.isdigit() else 0
                    
                    # Get chunk transcript data
                    chunk_data = await meeting_manager.get_chunk_transcript_for_summary(
                        meeting_id, numeric_chunk_index
                    )
                    
                    if chunk_data and chunk_data.get('transcript_text'):
                        logger.info(f"Generating real-time summary for chunk {numeric_chunk_index}")
                        
                        # Generate chunk summary
                        chunk_summary_data = await summarization_service.create_realtime_chunk_summary(
                            meeting_id=meeting_id,
                            chunk_index=numeric_chunk_index,
                            transcript_text=chunk_data['transcript_text'],
                            participants=chunk_data.get('participants', []),
                            chunk_start_time=chunk_data['chunk_start_time'],
                            chunk_end_time=chunk_data['chunk_end_time']
                        )
                        
                        # Save chunk summary to database
                        await meeting_manager.save_chunk_summary(
                            meeting_id=meeting_id,
                            chunk_index=numeric_chunk_index,
                            chunk_start_time=chunk_data['chunk_start_time'],
                            chunk_end_time=chunk_data['chunk_end_time'],
                            transcript_text=chunk_data['transcript_text'],
                            summary_text=chunk_summary_data['summary_text'],
                            key_points=chunk_summary_data['key_points'],
                            participants=chunk_data.get('participants', [])
                        )
                        
                        # Send chunk summary to Discord immediately
                        await send_chunk_summary_to_discord(meeting_id, chunk_summary_data)
                        
                        logger.info(f"Real-time chunk summary completed for chunk {numeric_chunk_index}")
                        
            except Exception as chunk_error:
                logger.error(f"Failed to generate chunk summary: {chunk_error}")
                # Continue with normal processing even if chunk summary fails
            
            # Check if all chunks are completed for final summary
            if await meeting_manager.check_all_chunks_completed(meeting_id):
                logger.info(f"All chunks completed for meeting {meeting_id}, generating final integrated summary")
                
                # Generate final integrated summary from all chunk summaries
                await generate_final_integrated_summary(meeting_id)
                
                # Send webhook notification after final summarization is complete
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

async def generate_final_integrated_summary(meeting_id: str):
    """Generate final integrated summary from all chunk summaries"""
    try:
        logger.info(f"Generating final integrated summary for meeting {meeting_id}")
        
        # Get meeting info
        meeting_status = await meeting_manager.get_meeting_status(meeting_id)
        if not meeting_status:
            logger.error(f"Meeting not found: {meeting_id}")
            return
        
        # Get all chunk summaries
        chunk_summaries = await meeting_manager.get_all_chunk_summaries(meeting_id)
        
        if not chunk_summaries:
            logger.warning(f"No chunk summaries found for meeting: {meeting_id}")
            # Fallback to old hierarchical summarization
            await meeting_manager.trigger_hierarchical_summarization(meeting_id)
            return
        
        # Generate final integrated summary
        participants = meeting_status.get('participants', [])
        total_duration = meeting_status.get('duration_minutes', 0)
        
        integrated_summary_data = await summarization_service.create_final_integrated_summary(
            meeting_id=meeting_id,
            chunk_summaries=chunk_summaries,
            total_duration=total_duration,
            all_participants=participants
        )
        
        # Save integrated summary to file
        file_path = await summarization_service.save_summary(meeting_id, integrated_summary_data)
        
        # Save to database
        await meeting_manager.save_summary(
            meeting_id=meeting_id,
            summary_content=integrated_summary_data['full_summary'],
            summary_type='integrated_final',
            file_path=file_path,
            generated_by='ollama_integrated'
        )
        
        # Update meeting status
        await meeting_manager.update_meeting_status(meeting_id, 'completed')
        await meeting_manager.update_processing_status(meeting_id, summarization_status='completed')
        
        # Send lightweight final summary notification to Discord
        final_summary_webhook = {
            "meeting_id": meeting_id,
            "event": "final_summary",
            "timestamp": datetime.now().isoformat(),
            "download_links": {
                "final_summary": f"/download/meeting/{meeting_id}/final-summary",
                "summary": f"/download/meeting/{meeting_id}/summary",
                "transcript": f"/download/meeting/{meeting_id}/transcript",
                "chunks": f"/download/meeting/{meeting_id}/chunks"
            }
        }
        await send_webhook_notification(meeting_id, final_summary_webhook)
        
        logger.info(f"Final integrated summary completed for meeting: {meeting_id}")
        
    except Exception as e:
        logger.error(f"Failed to generate final integrated summary: {e}")
        await meeting_manager.update_processing_status(
            meeting_id, 
            summarization_status='failed',
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
                    "download_url": f"http://52.91.224.198:3003/audio/{filename}"
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

@app.get("/meeting/{meeting_id}/chunk-summaries")
async def get_chunk_summaries(meeting_id: str):
    """Get all chunk summaries for a meeting"""
    try:
        chunk_summaries = await meeting_manager.get_all_chunk_summaries(meeting_id)
        if not chunk_summaries:
            raise HTTPException(status_code=404, detail="No chunk summaries found")
        
        return {
            "meeting_id": meeting_id,
            "chunk_summaries": chunk_summaries,
            "total_chunks": len(chunk_summaries),
            "timestamp": datetime.now()
        }
        
    except Exception as e:
        logger.error(f"Get chunk summaries error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/meeting/{meeting_id}/unsent-chunk-summaries")
async def get_unsent_chunk_summaries(meeting_id: str):
    """Get chunk summaries that haven't been sent to UI yet"""
    try:
        unsent_summaries = await meeting_manager.get_unsent_chunk_summaries(meeting_id)
        
        return {
            "meeting_id": meeting_id,
            "unsent_chunk_summaries": unsent_summaries,
            "count": len(unsent_summaries),
            "timestamp": datetime.now()
        }
        
    except Exception as e:
        logger.error(f"Get unsent chunk summaries error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/meeting/{meeting_id}/send-pending-summaries")
async def send_pending_chunk_summaries(meeting_id: str):
    """Send any pending chunk summaries to Discord"""
    try:
        unsent_summaries = await meeting_manager.get_unsent_chunk_summaries(meeting_id)
        
        sent_count = 0
        for chunk_data in unsent_summaries:
            try:
                await send_chunk_summary_to_discord(meeting_id, chunk_data)
                sent_count += 1
            except Exception as e:
                logger.error(f"Failed to send chunk {chunk_data['chunk_index']}: {e}")
        
        return {
            "meeting_id": meeting_id,
            "sent_count": sent_count,
            "total_pending": len(unsent_summaries),
            "timestamp": datetime.now()
        }
        
    except Exception as e:
        logger.error(f"Send pending summaries error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/meeting/{meeting_id}/generate-chunk-summary/{chunk_index}")
async def generate_chunk_summary_manually(meeting_id: str, chunk_index: int):
    """Manually generate chunk summary for a specific chunk"""
    try:
        # Get chunk transcript data
        chunk_data = await meeting_manager.get_chunk_transcript_for_summary(
            meeting_id, chunk_index
        )
        
        if not chunk_data or not chunk_data.get('transcript_text'):
            raise HTTPException(status_code=404, detail="No transcript data found for this chunk")
        
        # Generate chunk summary
        chunk_summary_data = await summarization_service.create_realtime_chunk_summary(
            meeting_id=meeting_id,
            chunk_index=chunk_index,
            transcript_text=chunk_data['transcript_text'],
            participants=chunk_data.get('participants', []),
            chunk_start_time=chunk_data['chunk_start_time'],
            chunk_end_time=chunk_data['chunk_end_time']
        )
        
        # Save chunk summary to database
        await meeting_manager.save_chunk_summary(
            meeting_id=meeting_id,
            chunk_index=chunk_index,
            chunk_start_time=chunk_data['chunk_start_time'],
            chunk_end_time=chunk_data['chunk_end_time'],
            transcript_text=chunk_data['transcript_text'],
            summary_text=chunk_summary_data['summary_text'],
            key_points=chunk_summary_data['key_points'],
            participants=chunk_data.get('participants', [])
        )
        
        # Send to Discord
        await send_chunk_summary_to_discord(meeting_id, chunk_summary_data)
        
        return {
            "meeting_id": meeting_id,
            "chunk_index": chunk_index,
            "summary_data": chunk_summary_data,
            "status": "completed"
        }
        
    except Exception as e:
        logger.error(f"Manual chunk summary generation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/download/meeting/{meeting_id}/chunk/{chunk_index}/summary")
async def download_chunk_summary(meeting_id: str, chunk_index: int):
    """Download formatted chunk summary as Markdown"""
    try:
        # Get chunk summary from database
        chunk_summaries = await meeting_manager.get_all_chunk_summaries(meeting_id)
        chunk_summary = None
        
        for chunk in chunk_summaries:
            if chunk['chunk_index'] == chunk_index:
                chunk_summary = chunk
                break
        
        if not chunk_summary:
            raise HTTPException(status_code=404, detail="Chunk summary not found")
        
        # Format chunk summary for download
        formatted_summary = summarization_service.format_chunk_summary_for_discord(chunk_summary)
        
        return PlainTextResponse(
            content=formatted_summary,
            headers={
                "Content-Disposition": f"attachment; filename=chunk_summary_{meeting_id}_{chunk_index}.md",
                "Content-Type": "text/markdown"
            }
        )
        
    except Exception as e:
        logger.error(f"Download chunk summary error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/download/meeting/{meeting_id}/chunk/{chunk_index}/transcript")
async def download_chunk_transcript(meeting_id: str, chunk_index: int):
    """Download chunk transcript as plain text"""
    try:
        # Get chunk summary from database (contains transcript)
        chunk_summaries = await meeting_manager.get_all_chunk_summaries(meeting_id)
        chunk_summary = None
        
        for chunk in chunk_summaries:
            if chunk['chunk_index'] == chunk_index:
                chunk_summary = chunk
                break
        
        if not chunk_summary:
            raise HTTPException(status_code=404, detail="Chunk transcript not found")
        
        # Format transcript for download
        transcript_content = f"""# チャンク文字起こし

**会議ID**: {meeting_id}
**チャンク**: {chunk_index} ({chunk_summary['time_range']})
**生成日時**: {chunk_summary['generated_at']}
**参加者**: {', '.join(chunk_summary.get('participants', []))}

## 文字起こし内容

{chunk_summary['transcript_text']}
"""
        
        return PlainTextResponse(
            content=transcript_content,
            headers={
                "Content-Disposition": f"attachment; filename=chunk_transcript_{meeting_id}_{chunk_index}.txt",
                "Content-Type": "text/plain"
            }
        )
        
    except Exception as e:
        logger.error(f"Download chunk transcript error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/download/meeting/{meeting_id}/final-summary")
async def download_final_summary(meeting_id: str):
    """Download final integrated summary as Markdown"""
    try:
        # Check for integrated final summary first
        summary_data = await meeting_manager.get_meeting_status(meeting_id)
        if not summary_data:
            raise HTTPException(status_code=404, detail="Meeting not found")
        
        # Try to find the latest summary file
        output_dir = Path(__file__).parent / "output"
        summary_files = list(output_dir.glob(f"meeting_{meeting_id}_*.md"))
        
        if not summary_files:
            # Fallback: Generate summary from chunk summaries if available
            chunk_summaries = await meeting_manager.get_all_chunk_summaries(meeting_id)
            if chunk_summaries:
                # Generate integrated summary from chunks
                participants = summary_data.get('participants', [])
                total_duration = summary_data.get('duration_minutes', 0)
                
                integrated_summary_data = await summarization_service.create_final_integrated_summary(
                    meeting_id=meeting_id,
                    chunk_summaries=chunk_summaries,
                    total_duration=total_duration,
                    all_participants=participants
                )
                
                summary_content = integrated_summary_data['full_summary']
            else:
                raise HTTPException(status_code=404, detail="No summary available for this meeting")
        else:
            # Read the latest summary file
            latest_file = max(summary_files, key=lambda p: p.stat().st_mtime)
            async with aiofiles.open(latest_file, 'r', encoding='utf-8') as f:
                summary_content = await f.read()
        
        return PlainTextResponse(
            content=summary_content,
            headers={
                "Content-Disposition": f"attachment; filename=final_summary_{meeting_id}.md",
                "Content-Type": "text/markdown"
            }
        )
        
    except Exception as e:
        logger.error(f"Download final summary error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/download/meeting/{meeting_id}/all-chunks")
async def download_all_chunk_summaries(meeting_id: str):
    """Download all chunk summaries as a combined Markdown file"""
    try:
        chunk_summaries = await meeting_manager.get_all_chunk_summaries(meeting_id)
        if not chunk_summaries:
            raise HTTPException(status_code=404, detail="No chunk summaries found")
        
        # Combine all chunk summaries
        combined_content = f"# 全チャンク要約一覧\n\n**会議ID**: {meeting_id}\n**生成日時**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        
        for chunk in chunk_summaries:
            formatted_chunk = summarization_service.format_chunk_summary_for_discord(chunk)
            combined_content += f"{formatted_chunk}\n\n---\n\n"
        
        return PlainTextResponse(
            content=combined_content,
            headers={
                "Content-Disposition": f"attachment; filename=all_chunks_{meeting_id}.md",
                "Content-Type": "text/markdown"
            }
        )
        
    except Exception as e:
        logger.error(f"Download all chunks error: {e}")
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