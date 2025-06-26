from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine, and_, or_, desc
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import logging
import json
import os
from dotenv import load_dotenv

from .models import Meeting, Transcript, Summary, ProcessingStatus, AudioFile, ChunkSummary, get_db, SessionLocal

load_dotenv()

logger = logging.getLogger(__name__)

class MeetingManager:
    """Manager for meeting data and coordination between services"""
    
    def __init__(self):
        self.db_session = SessionLocal
        
    async def create_meeting(
        self,
        meeting_id: str,
        discord_guild_id: str,
        discord_channel_id: str,
        meeting_title: Optional[str] = None,
        participants: Optional[List[str]] = None
    ) -> Meeting:
        """Create a new meeting record"""
        db = self.db_session()
        try:
            # Create meeting record
            meeting = Meeting(
                meeting_id=meeting_id,
                discord_guild_id=discord_guild_id,
                discord_channel_id=discord_channel_id,
                meeting_title=meeting_title,
                start_time=datetime.utcnow(),
                status='recording',
                participants=json.dumps(participants or [])
            )
            
            db.add(meeting)
            
            # Create processing status record
            processing_status = ProcessingStatus(
                meeting_id=meeting_id,
                transcription_status='pending',
                summarization_status='pending'
            )
            
            db.add(processing_status)
            db.commit()
            
            logger.info(f"Created meeting record: {meeting_id}")
            
            # Verify the record was actually saved
            saved_meeting = db.query(Meeting).filter(Meeting.meeting_id == meeting_id).first()
            if not saved_meeting:
                raise Exception(f"Meeting record not found after commit: {meeting_id}")
            
            logger.info(f"Verified meeting record saved successfully: {meeting_id}")
            return meeting
            
        except Exception as e:
            logger.error(f"Failed to create meeting: {e}")
            db.rollback()
            raise
        finally:
            db.close()
    
    async def update_meeting_status(self, meeting_id: str, status: str) -> bool:
        """Update meeting status"""
        db = self.db_session()
        try:
            meeting = db.query(Meeting).filter(Meeting.meeting_id == meeting_id).first()
            if meeting:
                meeting.status = status
                meeting.updated_at = datetime.utcnow()
                
                if status in ['completed', 'failed']:
                    meeting.end_time = datetime.utcnow()
                    
                    # Calculate duration
                    if meeting.end_time and meeting.start_time:
                        duration = (meeting.end_time - meeting.start_time).total_seconds() / 60
                        meeting.duration_minutes = int(duration)
                
                db.commit()
                
                # Verify the update was saved
                db.refresh(meeting)
                logger.info(f"Updated meeting {meeting_id} status to {status} (verified: {meeting.status})")
                return True
            else:
                logger.error(f"Meeting not found for status update: {meeting_id}")
                return False
                
        except Exception as e:
            logger.error(f"Failed to update meeting status: {e}")
            db.rollback()
            return False
        finally:
            db.close()
    
    async def add_transcript_segment(
        self,
        meeting_id: str,
        speaker_id: str,
        speaker_name: str,
        text: str,
        confidence: float,
        start_time: datetime,
        duration_seconds: float,
        audio_file_path: Optional[str] = None
    ) -> Transcript:
        """Add a transcript segment"""
        try:
            db = self.db_session()
            
            transcript = Transcript(
                meeting_id=meeting_id,
                speaker_id=speaker_id,
                speaker_name=speaker_name,
                text=text,
                confidence=confidence,
                start_time=start_time,
                end_time=start_time + timedelta(seconds=duration_seconds),
                duration_seconds=duration_seconds,
                audio_file_path=audio_file_path
            )
            
            db.add(transcript)
            db.commit()
            
            logger.info(f"Added transcript segment for meeting {meeting_id}, speaker {speaker_name}")
            return transcript
            
        except Exception as e:
            logger.error(f"Failed to add transcript segment: {e}")
            db.rollback()
            raise
        finally:
            db.close()
    
    async def get_meeting_transcript(self, meeting_id: str) -> Optional[str]:
        """Get full transcript for a meeting"""
        try:
            db = self.db_session()
            
            transcripts = db.query(Transcript).filter(
                Transcript.meeting_id == meeting_id
            ).order_by(Transcript.start_time).all()
            
            if not transcripts:
                return None
            
            # Build full transcript
            transcript_lines = []
            current_speaker = None
            
            for segment in transcripts:
                if segment.speaker_name != current_speaker:
                    if current_speaker is not None:
                        transcript_lines.append("")  # Add blank line between speakers
                    
                    timestamp = segment.start_time.strftime("%H:%M:%S")
                    transcript_lines.append(f"[{timestamp}] {segment.speaker_name}:")
                    current_speaker = segment.speaker_name
                
                transcript_lines.append(f"  {segment.text}")
            
            return "\n".join(transcript_lines)
            
        except Exception as e:
            logger.error(f"Failed to get transcript: {e}")
            return None
        finally:
            db.close()
    
    async def get_transcript_segments(self, meeting_id: str) -> Optional[List[Dict]]:
        """Get transcript segments as list for download endpoints"""
        try:
            db = self.db_session()
            
            transcripts = db.query(Transcript).filter(
                Transcript.meeting_id == meeting_id
            ).order_by(Transcript.start_time).all()
            
            if not transcripts:
                return None
            
            segments = []
            for transcript in transcripts:
                segments.append({
                    'speaker_id': transcript.speaker_id,
                    'speaker_name': transcript.speaker_name,
                    'text': transcript.text,
                    'start_time': transcript.start_time,
                    'duration_seconds': transcript.duration_seconds,
                    'audio_file_path': transcript.audio_file_path
                })
            
            return segments
            
        except Exception as e:
            logger.error(f"Error retrieving transcript segments for meeting {meeting_id}: {e}")
            return None
        finally:
            db.close()
    
    async def save_summary(
        self,
        meeting_id: str,
        summary_content: str,
        summary_type: str = 'full',
        file_path: Optional[str] = None,
        generated_by: str = 'ollama'
    ) -> Summary:
        """Save meeting summary"""
        try:
            db = self.db_session()
            
            summary = Summary(
                meeting_id=meeting_id,
                summary_type=summary_type,
                content=summary_content,
                generated_by=generated_by,
                file_path=file_path
            )
            
            db.add(summary)
            db.commit()
            
            logger.info(f"Saved {summary_type} summary for meeting {meeting_id}")
            return summary
            
        except Exception as e:
            logger.error(f"Failed to save summary: {e}")
            db.rollback()
            raise
        finally:
            db.close()
    
    async def update_processing_status(
        self,
        meeting_id: str,
        transcription_status: Optional[str] = None,
        transcription_progress: Optional[float] = None,
        summarization_status: Optional[str] = None,
        error_message: Optional[str] = None
    ) -> bool:
        """Update processing status"""
        try:
            db = self.db_session()
            
            status = db.query(ProcessingStatus).filter(
                ProcessingStatus.meeting_id == meeting_id
            ).first()
            
            if not status:
                # Create new status record
                status = ProcessingStatus(meeting_id=meeting_id)
                db.add(status)
            
            # Update fields
            if transcription_status is not None:
                status.transcription_status = transcription_status
                if transcription_status == 'processing' and status.processing_start is None:
                    status.processing_start = datetime.utcnow()
                elif transcription_status in ['completed', 'failed']:
                    status.processing_end = datetime.utcnow()
            
            if transcription_progress is not None:
                status.transcription_progress = transcription_progress
            
            if summarization_status is not None:
                status.summarization_status = summarization_status
            
            if error_message is not None:
                status.error_message = error_message
            
            status.updated_at = datetime.utcnow()
            db.commit()
            
            logger.info(f"Updated processing status for meeting {meeting_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to update processing status: {e}")
            db.rollback()
            return False
        finally:
            db.close()
    
    async def get_meeting_status(self, meeting_id: str) -> Optional[Dict]:
        """Get detailed meeting status"""
        try:
            db = self.db_session()
            
            # Get meeting info
            meeting = db.query(Meeting).filter(Meeting.meeting_id == meeting_id).first()
            if not meeting:
                return None
            
            # Get processing status
            processing = db.query(ProcessingStatus).filter(
                ProcessingStatus.meeting_id == meeting_id
            ).first()
            
            # Get transcript count
            transcript_count = db.query(Transcript).filter(
                Transcript.meeting_id == meeting_id
            ).count()
            
            # Get summary count
            summary_count = db.query(Summary).filter(
                Summary.meeting_id == meeting_id
            ).count()
            
            # Parse participants
            participants = []
            if meeting.participants:
                try:
                    participants = json.loads(meeting.participants)
                except:
                    participants = []
            
            # Calculate duration
            duration_minutes = meeting.duration_minutes
            if not duration_minutes and meeting.start_time:
                end_time = meeting.end_time or datetime.utcnow()
                duration_minutes = int((end_time - meeting.start_time).total_seconds() / 60)
            
            status_data = {
                'meeting_id': meeting.meeting_id,
                'status': meeting.status,
                'start_time': meeting.start_time,
                'end_time': meeting.end_time,
                'duration_minutes': duration_minutes,
                'participants': participants,
                'transcript_segments': transcript_count,
                'summaries': summary_count,
                'processing': {
                    'transcription_status': processing.transcription_status if processing else 'unknown',
                    'transcription_progress': processing.transcription_progress if processing else 0.0,
                    'summarization_status': processing.summarization_status if processing else 'unknown',
                    'error_message': processing.error_message if processing else None
                } if processing else None
            }
            
            return status_data
            
        except Exception as e:
            logger.error(f"Failed to get meeting status: {e}")
            return None
        finally:
            db.close()
    
    async def get_recent_meetings(self, guild_id: str, limit: int = 10) -> List[Dict]:
        """Get recent meetings for a guild"""
        try:
            db = self.db_session()
            
            meetings = db.query(Meeting).filter(
                Meeting.discord_guild_id == guild_id
            ).order_by(desc(Meeting.start_time)).limit(limit).all()
            
            result = []
            for meeting in meetings:
                participants = []
                if meeting.participants:
                    try:
                        participants = json.loads(meeting.participants)
                    except:
                        participants = []
                
                result.append({
                    'meeting_id': meeting.meeting_id,
                    'title': meeting.meeting_title,
                    'start_time': meeting.start_time,
                    'duration_minutes': meeting.duration_minutes,
                    'status': meeting.status,
                    'participants': len(participants)
                })
            
            return result
            
        except Exception as e:
            logger.error(f"Failed to get recent meetings: {e}")
            return []
        finally:
            db.close()
    
    async def delete_meeting(self, meeting_id: str) -> bool:
        """Delete meeting and all related data"""
        try:
            db = self.db_session()
            
            # Delete in order: summaries, transcripts, audio files, processing status, meeting
            db.query(Summary).filter(Summary.meeting_id == meeting_id).delete()
            db.query(Transcript).filter(Transcript.meeting_id == meeting_id).delete()
            db.query(AudioFile).filter(AudioFile.meeting_id == meeting_id).delete()
            db.query(ProcessingStatus).filter(ProcessingStatus.meeting_id == meeting_id).delete()
            db.query(Meeting).filter(Meeting.meeting_id == meeting_id).delete()
            
            db.commit()
            
            logger.info(f"Deleted meeting {meeting_id} and all related data")
            return True
            
        except Exception as e:
            logger.error(f"Failed to delete meeting: {e}")
            db.rollback()
            return False
        finally:
            db.close()
    
    async def get_meeting_transcript_chunks(self, meeting_id: str, chunk_duration_minutes: int = 30) -> List[Dict]:
        """Get meeting transcript in chunks for hierarchical summarization"""
        try:
            db = self.db_session()
            
            # Get all transcripts for the meeting
            transcripts = db.query(Transcript).filter(
                Transcript.meeting_id == meeting_id
            ).order_by(Transcript.start_time).all()
            
            if not transcripts:
                return []
            
            # Group transcripts into chunks based on time
            chunks = []
            current_chunk = {
                'start_time': transcripts[0].start_time,
                'texts': [],
                'speakers': set()
            }
            
            chunk_start = transcripts[0].start_time
            
            for transcript in transcripts:
                # Check if this transcript belongs to current chunk
                time_diff = (transcript.start_time - chunk_start).total_seconds() / 60
                
                if time_diff >= chunk_duration_minutes:
                    # Save current chunk
                    chunks.append({
                        'text': '\n'.join(current_chunk['texts']),
                        'speakers': list(current_chunk['speakers']),
                        'start_time': current_chunk['start_time'],
                        'duration_minutes': chunk_duration_minutes
                    })
                    
                    # Start new chunk
                    chunk_start = transcript.start_time
                    current_chunk = {
                        'start_time': transcript.start_time,
                        'texts': [],
                        'speakers': set()
                    }
                
                # Add to current chunk
                current_chunk['texts'].append(f"[{transcript.speaker_name}]: {transcript.text}")
                current_chunk['speakers'].add(transcript.speaker_name)
            
            # Add final chunk
            if current_chunk['texts']:
                chunks.append({
                    'text': '\n'.join(current_chunk['texts']),
                    'speakers': list(current_chunk['speakers']),
                    'start_time': current_chunk['start_time'],
                    'duration_minutes': chunk_duration_minutes
                })
            
            logger.info(f"Split meeting {meeting_id} into {len(chunks)} chunks")
            return chunks
            
        except Exception as e:
            logger.error(f"Failed to get transcript chunks: {e}")
            return []
        finally:
            db.close()
    
    async def increment_completed_chunks(self, meeting_id: str):
        """Increment the count of completed transcription chunks"""
        try:
            db = self.db_session()
            status = db.query(ProcessingStatus).filter(
                ProcessingStatus.meeting_id == meeting_id
            ).first()
            
            if status:
                status.completed_chunks += 1
                status.updated_at = datetime.utcnow()
                
                # Update progress
                if status.total_chunks > 0:
                    status.transcription_progress = status.completed_chunks / status.total_chunks
                
                db.commit()
                logger.info(f"Updated chunk progress for {meeting_id}: {status.completed_chunks}/{status.total_chunks}")
            
        except Exception as e:
            logger.error(f"Failed to increment completed chunks: {e}")
            db.rollback()
        finally:
            db.close()
    
    async def set_total_chunks(self, meeting_id: str, total_chunks: int):
        """Set the total number of chunks for a meeting"""
        try:
            db = self.db_session()
            status = db.query(ProcessingStatus).filter(
                ProcessingStatus.meeting_id == meeting_id
            ).first()
            
            if not status:
                status = ProcessingStatus(meeting_id=meeting_id)
                db.add(status)
            
            status.total_chunks = total_chunks
            status.updated_at = datetime.utcnow()
            db.commit()
            
            logger.info(f"Set total chunks for {meeting_id}: {total_chunks}")
            
        except Exception as e:
            logger.error(f"Failed to set total chunks: {e}")
            db.rollback()
        finally:
            db.close()
    
    async def check_all_chunks_completed(self, meeting_id: str) -> bool:
        """Check if all transcription chunks are completed"""
        try:
            db = self.db_session()
            status = db.query(ProcessingStatus).filter(
                ProcessingStatus.meeting_id == meeting_id
            ).first()
            
            if not status:
                return False
            
            # Check if all chunks are completed
            is_complete = (status.total_chunks > 0 and 
                          status.completed_chunks >= status.total_chunks and
                          status.transcription_status != 'failed')
            
            if is_complete:
                status.transcription_status = 'completed'
                status.processing_end = datetime.utcnow()
                db.commit()
            
            return is_complete
            
        except Exception as e:
            logger.error(f"Failed to check chunk completion: {e}")
            return False
        finally:
            db.close()
    
    async def trigger_hierarchical_summarization(self, meeting_id: str) -> bool:
        """Trigger hierarchical summarization for a completed meeting"""
        try:
            # Get meeting info
            db = self.db_session()
            meeting = db.query(Meeting).filter(Meeting.meeting_id == meeting_id).first()
            
            if not meeting:
                logger.error(f"Meeting not found: {meeting_id}")
                return False
            
            # Parse participants
            participants = json.loads(meeting.participants) if meeting.participants else []
            
            # Get transcript chunks
            chunks = await self.get_meeting_transcript_chunks(meeting_id)
            
            if not chunks:
                logger.warning(f"No transcript chunks found for meeting: {meeting_id}")
                # Update status to indicate no transcripts
                await self.update_processing_status(
                    meeting_id,
                    summarization_status="no_transcripts"
                )
                return False
            
            # Import summarization service
            from .summarization import SummarizationService
            summarization_service = SummarizationService()
            
            # Create hierarchical summary
            summary_data = await summarization_service.create_hierarchical_summary(
                meeting_id=meeting_id,
                chunk_transcripts=chunks,
                participants=participants,
                total_duration=meeting.duration_minutes or 0
            )
            
            # Save summary to file
            file_path = await summarization_service.save_summary(meeting_id, summary_data)
            
            # Save to database
            await self.save_summary(
                meeting_id=meeting_id,
                summary_content=summary_data['full_summary'],
                summary_type='hierarchical',
                file_path=file_path,
                generated_by='ollama_hierarchical'
            )
            
            # Update meeting status
            await self.update_meeting_status(meeting_id, 'completed')
            await self.update_processing_status(meeting_id, summarization_status='completed')
            
            logger.info(f"Hierarchical summarization completed for meeting: {meeting_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to trigger hierarchical summarization: {e}")
            await self.update_processing_status(
                meeting_id, 
                summarization_status='failed',
                error_message=str(e)
            )
            return False
        finally:
            db.close()
    
    async def cleanup_old_meetings(self, days: int = 30) -> int:
        """Clean up old meetings and their data"""
        try:
            db = self.db_session()
            
            cutoff_date = datetime.utcnow() - timedelta(days=days)
            
            # Find old meetings
            old_meetings = db.query(Meeting).filter(
                Meeting.start_time < cutoff_date
            ).all()
            
            deleted_count = 0
            for meeting in old_meetings:
                await self.delete_meeting(meeting.meeting_id)
                deleted_count += 1
            
            logger.info(f"Cleaned up {deleted_count} old meetings")
            return deleted_count
            
        except Exception as e:
            logger.error(f"Failed to cleanup old meetings: {e}")
            return 0
        finally:
            db.close()
    
    async def get_meeting_statistics(self, guild_id: Optional[str] = None) -> Dict:
        """Get meeting statistics"""
        try:
            db = self.db_session()
            
            query = db.query(Meeting)
            if guild_id:
                query = query.filter(Meeting.discord_guild_id == guild_id)
            
            total_meetings = query.count()
            
            # Meetings by status
            status_counts = {}
            for status in ['recording', 'processing', 'completed', 'failed']:
                count = query.filter(Meeting.status == status).count()
                status_counts[status] = count
            
            # Recent activity (last 7 days)
            recent_date = datetime.utcnow() - timedelta(days=7)
            recent_meetings = query.filter(Meeting.start_time >= recent_date).count()
            
            # Average duration
            completed_meetings = query.filter(
                and_(Meeting.status == 'completed', Meeting.duration_minutes.isnot(None))
            ).all()
            
            avg_duration = 0
            if completed_meetings:
                total_duration = sum(m.duration_minutes for m in completed_meetings)
                avg_duration = total_duration / len(completed_meetings)
            
            return {
                'total_meetings': total_meetings,
                'status_breakdown': status_counts,
                'recent_meetings_7_days': recent_meetings,
                'average_duration_minutes': round(avg_duration, 1),
                'guild_id': guild_id
            }
            
        except Exception as e:
            logger.error(f"Failed to get statistics: {e}")
            return {}
        finally:
            db.close()
    
    async def save_chunk_summary(
        self,
        meeting_id: str,
        chunk_index: int,
        chunk_start_time: datetime,
        chunk_end_time: datetime,
        transcript_text: str,
        summary_text: str,
        key_points: str,
        participants: List[str]
    ) -> ChunkSummary:
        """Save chunk summary to database"""
        try:
            db = self.db_session()
            
            # Check if chunk summary already exists
            existing = db.query(ChunkSummary).filter(
                and_(
                    ChunkSummary.meeting_id == meeting_id,
                    ChunkSummary.chunk_index == chunk_index
                )
            ).first()
            
            if existing:
                # Update existing chunk summary
                existing.chunk_end_time = chunk_end_time
                existing.transcript_text = transcript_text
                existing.summary_text = summary_text
                existing.key_points = key_points
                existing.participants = json.dumps(participants)
                existing.generated_at = datetime.utcnow()
                existing.sent_to_ui = False  # Reset sent flag
                chunk_summary = existing
            else:
                # Create new chunk summary
                chunk_summary = ChunkSummary(
                    meeting_id=meeting_id,
                    chunk_index=chunk_index,
                    chunk_start_time=chunk_start_time,
                    chunk_end_time=chunk_end_time,
                    transcript_text=transcript_text,
                    summary_text=summary_text,
                    key_points=key_points,
                    participants=json.dumps(participants),
                    status='completed'
                )
                db.add(chunk_summary)
            
            db.commit()
            
            logger.info(f"Saved chunk summary for meeting {meeting_id}, chunk {chunk_index}")
            return chunk_summary
            
        except Exception as e:
            logger.error(f"Failed to save chunk summary: {e}")
            db.rollback()
            raise
        finally:
            db.close()
    
    async def mark_chunk_summary_sent(self, meeting_id: str, chunk_index: int) -> bool:
        """Mark chunk summary as sent to UI"""
        try:
            db = self.db_session()
            
            chunk_summary = db.query(ChunkSummary).filter(
                and_(
                    ChunkSummary.meeting_id == meeting_id,
                    ChunkSummary.chunk_index == chunk_index
                )
            ).first()
            
            if chunk_summary:
                chunk_summary.sent_to_ui = True
                db.commit()
                logger.info(f"Marked chunk {chunk_index} as sent for meeting {meeting_id}")
                return True
            else:
                logger.warning(f"Chunk summary not found: {meeting_id}, chunk {chunk_index}")
                return False
                
        except Exception as e:
            logger.error(f"Failed to mark chunk as sent: {e}")
            db.rollback()
            return False
        finally:
            db.close()
    
    async def get_unsent_chunk_summaries(self, meeting_id: str) -> List[Dict]:
        """Get chunk summaries that haven't been sent to UI yet"""
        try:
            db = self.db_session()
            
            unsent_chunks = db.query(ChunkSummary).filter(
                and_(
                    ChunkSummary.meeting_id == meeting_id,
                    ChunkSummary.sent_to_ui == False
                )
            ).order_by(ChunkSummary.chunk_index).all()
            
            result = []
            for chunk in unsent_chunks:
                participants = []
                if chunk.participants:
                    try:
                        participants = json.loads(chunk.participants)
                    except:
                        participants = []
                
                result.append({
                    'meeting_id': chunk.meeting_id,
                    'chunk_index': chunk.chunk_index,
                    'time_range': f"{chunk.chunk_index * 30}分〜{(chunk.chunk_index + 1) * 30}分",
                    'chunk_start_time': chunk.chunk_start_time.isoformat(),
                    'chunk_end_time': chunk.chunk_end_time.isoformat() if chunk.chunk_end_time else None,
                    'transcript_text': chunk.transcript_text,
                    'summary_text': chunk.summary_text,
                    'key_points': chunk.key_points,
                    'participants': participants,
                    'generated_at': chunk.generated_at.isoformat()
                })
            
            return result
            
        except Exception as e:
            logger.error(f"Failed to get unsent chunk summaries: {e}")
            return []
        finally:
            db.close()
    
    async def get_all_chunk_summaries(self, meeting_id: str) -> List[Dict]:
        """Get all chunk summaries for a meeting"""
        try:
            db = self.db_session()
            
            chunks = db.query(ChunkSummary).filter(
                ChunkSummary.meeting_id == meeting_id
            ).order_by(ChunkSummary.chunk_index).all()
            
            result = []
            for chunk in chunks:
                participants = []
                if chunk.participants:
                    try:
                        participants = json.loads(chunk.participants)
                    except:
                        participants = []
                
                result.append({
                    'meeting_id': chunk.meeting_id,
                    'chunk_index': chunk.chunk_index,
                    'time_range': f"{chunk.chunk_index * 30}分〜{(chunk.chunk_index + 1) * 30}分",
                    'chunk_start_time': chunk.chunk_start_time.isoformat(),
                    'chunk_end_time': chunk.chunk_end_time.isoformat() if chunk.chunk_end_time else None,
                    'transcript_text': chunk.transcript_text,
                    'summary_text': chunk.summary_text,
                    'key_points': chunk.key_points,
                    'participants': participants,
                    'generated_at': chunk.generated_at.isoformat(),
                    'sent_to_ui': chunk.sent_to_ui
                })
            
            return result
            
        except Exception as e:
            logger.error(f"Failed to get chunk summaries: {e}")
            return []
        finally:
            db.close()
    
    async def get_chunk_transcript_for_summary(self, meeting_id: str, chunk_index: int, chunk_duration_minutes: int = 30) -> Dict:
        """Get transcript text for a specific chunk"""
        try:
            db = self.db_session()
            
            # Get meeting start time
            meeting = db.query(Meeting).filter(Meeting.meeting_id == meeting_id).first()
            if not meeting:
                return {}
            
            # Calculate chunk time boundaries
            chunk_start_offset = chunk_index * chunk_duration_minutes * 60  # seconds
            chunk_end_offset = (chunk_index + 1) * chunk_duration_minutes * 60  # seconds
            
            chunk_start_time = meeting.start_time + timedelta(seconds=chunk_start_offset)
            chunk_end_time = meeting.start_time + timedelta(seconds=chunk_end_offset)
            
            # Get transcripts within this chunk
            transcripts = db.query(Transcript).filter(
                and_(
                    Transcript.meeting_id == meeting_id,
                    Transcript.start_time >= chunk_start_time,
                    Transcript.start_time < chunk_end_time
                )
            ).order_by(Transcript.start_time).all()
            
            if not transcripts:
                return {}
            
            # Combine transcript texts
            transcript_lines = []
            speakers = set()
            
            for transcript in transcripts:
                transcript_lines.append(f"[{transcript.speaker_name}]: {transcript.text}")
                speakers.add(transcript.speaker_name)
            
            # Get actual end time (either last transcript or chunk boundary)
            actual_end_time = min(transcripts[-1].end_time or chunk_end_time, chunk_end_time)
            
            return {
                'meeting_id': meeting_id,
                'chunk_index': chunk_index,
                'chunk_start_time': chunk_start_time,
                'chunk_end_time': actual_end_time,
                'transcript_text': '\n'.join(transcript_lines),
                'participants': list(speakers)
            }
            
        except Exception as e:
            logger.error(f"Failed to get chunk transcript: {e}")
            return {}
        finally:
            db.close()