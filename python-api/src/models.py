from sqlalchemy import create_engine, Column, Integer, String, DateTime, Boolean, Text, Float
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
import os
from dotenv import load_dotenv

load_dotenv()

Base = declarative_base()

class Meeting(Base):
    """Voice meeting records"""
    __tablename__ = 'meetings'
    
    meeting_id = Column(String, primary_key=True)
    discord_guild_id = Column(String, nullable=False)
    discord_channel_id = Column(String, nullable=False)
    meeting_title = Column(String, nullable=True)
    start_time = Column(DateTime, default=datetime.utcnow)
    end_time = Column(DateTime, nullable=True)
    duration_minutes = Column(Integer, nullable=True)
    status = Column(String, default='recording')  # recording, processing, completed, failed
    participants = Column(Text, nullable=True)  # JSON string of participant list
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class Transcript(Base):
    """Individual transcript segments"""
    __tablename__ = 'transcripts'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    meeting_id = Column(String, nullable=False)
    speaker_id = Column(String, nullable=False)  # Discord user ID
    speaker_name = Column(String, nullable=True)  # Discord username/display name
    text = Column(Text, nullable=False)
    confidence = Column(Float, nullable=True)  # Whisper confidence score
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=True)
    duration_seconds = Column(Float, nullable=True)
    audio_file_path = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class Summary(Base):
    """Meeting summaries and analysis"""
    __tablename__ = 'summaries'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    meeting_id = Column(String, nullable=False)
    summary_type = Column(String, default='full')  # full, key_points, action_items
    content = Column(Text, nullable=False)
    generated_by = Column(String, default='ollama')  # AI model used
    generated_at = Column(DateTime, default=datetime.utcnow)
    file_path = Column(String, nullable=True)  # Path to saved summary file

class ProcessingStatus(Base):
    """Track processing status of meetings"""
    __tablename__ = 'processing_status'
    
    meeting_id = Column(String, primary_key=True)
    transcription_status = Column(String, default='pending')  # pending, processing, completed, failed
    transcription_progress = Column(Float, default=0.0)  # 0.0 to 1.0
    summarization_status = Column(String, default='pending')
    error_message = Column(Text, nullable=True)
    processing_start = Column(DateTime, nullable=True)
    processing_end = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class AudioFile(Base):
    """Track audio files and cleanup"""
    __tablename__ = 'audio_files'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    meeting_id = Column(String, nullable=False)
    file_path = Column(String, nullable=False)
    file_size_bytes = Column(Integer, nullable=True)
    duration_seconds = Column(Float, nullable=True)
    format = Column(String, nullable=True)  # mp3, wav, etc.
    created_at = Column(DateTime, default=datetime.utcnow)
    scheduled_deletion = Column(DateTime, nullable=True)
    deleted = Column(Boolean, default=False)

# Database connection setup
DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///./meetings.db')
engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    """Get database session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_db():
    """Initialize database tables"""
    Base.metadata.create_all(bind=engine)
    print("Database tables created successfully")