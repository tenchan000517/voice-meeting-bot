import { joinVoiceChannel, EndBehaviorType, VoiceConnectionStatus } from '@discordjs/voice';
import { createWriteStream, promises as fs } from 'fs';
import path from 'path';
import { pipeline } from 'stream/promises';
import opusPkg from '@discordjs/opus';
const { OpusEncoder } = opusPkg;
import prismPkg from 'prism-media';
const prism = prismPkg;
import axios from 'axios';
import winston from 'winston';

export class VoiceRecorder {
  constructor(client, logger) {
    this.client = client;
    this.logger = logger;
    this.activeRecordings = new Map();
    this.completedRecordings = new Map(); // For 24-hour retention
    this.tempDir = process.env.TEMP_DIR || './temp';
    this.chunkDuration = parseInt(process.env.CHUNK_DURATION) || 1800000; // 30 minutes
    this.maxDuration = parseInt(process.env.MAX_RECORDING_DURATION) || 10800000; // 3 hours
    this.apiUrl = process.env.PYTHON_API_URL || 'http://localhost:8000';
    
    this._ensureTempDir();
    this._startCleanupTimer();
  }

  async _ensureTempDir() {
    try {
      await fs.mkdir(this.tempDir, { recursive: true });
    } catch (error) {
      this.logger.error('Failed to create temp directory:', error);
    }
  }

  async startRecording(voiceChannel, meetingId, meetingTitle = null) {
    try {
      // Check if already recording in this channel
      if (this.activeRecordings.has(voiceChannel.id)) {
        throw new Error('Already recording in this voice channel');
      }

      this.logger.info(`Starting recording in channel: ${voiceChannel.name} (${voiceChannel.id})`);

      // Join voice channel
      const connection = joinVoiceChannel({
        channelId: voiceChannel.id,
        guildId: voiceChannel.guild.id,
        adapterCreator: voiceChannel.guild.voiceAdapterCreator,
        selfDeaf: false,
        selfMute: true,
      });

      // Wait for connection to be ready
      await this._waitForConnection(connection);

      // Create audio receiver (newer Discord.js API)
      const receiver = connection.receiver;

      // Setup recording session
      const recording = {
        meetingId,
        meetingTitle,
        channelId: voiceChannel.id,
        guildId: voiceChannel.guild.id,
        connection,
        receiver,
        startTime: new Date(),
        participants: new Map(),
        audioFiles: [],
        chunkCount: 0,
        status: 'recording'
      };

      this.activeRecordings.set(voiceChannel.id, recording);

      // Start listening for users
      this._setupUserListeners(recording);

      // Setup automatic chunk recording
      this._startChunkRecording(recording);

      // Setup automatic stop after max duration
      setTimeout(() => {
        if (this.activeRecordings.has(voiceChannel.id)) {
          this.stopRecording(voiceChannel.id, 'Maximum duration reached');
        }
      }, this.maxDuration);

      // Notify API about new meeting
      await this._notifyMeetingStart(recording);

      this.logger.info(`Recording started successfully: ${meetingId}`);
      
      return {
        meetingId,
        status: 'recording',
        startTime: recording.startTime,
        channelName: voiceChannel.name
      };

    } catch (error) {
      this.logger.error('Failed to start recording:', error);
      throw error;
    }
  }

  async stopRecording(channelId, reason = 'Manual stop') {
    try {
      const recording = this.activeRecordings.get(channelId);
      if (!recording) {
        throw new Error('No active recording in this channel');
      }

      this.logger.info(`Stopping recording: ${recording.meetingId}, reason: ${reason}`);

      recording.status = 'stopping';
      recording.endTime = new Date();

      // Stop all user recordings
      for (const [userId, userRecording] of recording.participants) {
        await this._stopUserRecording(userRecording);
      }

      // Disconnect from voice channel
      if (recording.connection) {
        recording.connection.destroy();
      }

      // Calculate duration
      const duration = Math.floor((recording.endTime - recording.startTime) / 1000 / 60);

      // Trigger transcription processing
      await this._triggerTranscription(recording);

      // Move to completed recordings for 24-hour retention
      recording.status = 'completed';
      this.completedRecordings.set(recording.meetingId, {
        ...recording,
        completedAt: new Date()
      });
      
      // Remove from active recordings
      this.activeRecordings.delete(channelId);

      this.logger.info(`Recording stopped: ${recording.meetingId}, duration: ${duration} minutes`);

      return {
        meetingId: recording.meetingId,
        status: 'processing',
        duration,
        audioFiles: recording.audioFiles.length,
        participants: recording.participants.size
      };

    } catch (error) {
      this.logger.error('Failed to stop recording:', error);
      throw error;
    }
  }

  async _waitForConnection(connection) {
    return new Promise((resolve, reject) => {
      const timeout = setTimeout(() => {
        reject(new Error('Connection timeout'));
      }, 10000);

      connection.on(VoiceConnectionStatus.Ready, () => {
        clearTimeout(timeout);
        resolve();
      });

      connection.on(VoiceConnectionStatus.Disconnected, () => {
        clearTimeout(timeout);
        reject(new Error('Connection failed'));
      });
    });
  }

  _setupUserListeners(recording) {
    const { receiver } = recording;

    // Listen for users speaking
    receiver.speaking.on('start', (userId) => {
      this._startUserRecording(recording, userId);
    });

    receiver.speaking.on('end', (userId) => {
      this._pauseUserRecording(recording, userId);
    });
  }

  async _startUserRecording(recording, userId) {
    try {
      if (recording.participants.has(userId)) {
        // Resume existing recording
        const userRecording = recording.participants.get(userId);
        userRecording.isPaused = false;
        return;
      }

      // Get user info
      const user = await this.client.users.fetch(userId);
      
      // Debug logging
      this.logger.info(`Recording guild ID: ${recording.guildId}`);
      this.logger.info(`Available guilds: ${Array.from(this.client.guilds.cache.keys()).join(', ')}`);
      
      const guild = this.client.guilds.cache.get(recording.guildId);
      
      if (!guild) {
        this.logger.error(`Guild not found: ${recording.guildId}, available: ${Array.from(this.client.guilds.cache.keys())}`);
        throw new Error(`Guild not found: ${recording.guildId}`);
      }
      
      const member = await guild.members.fetch(userId);

      this.logger.info(`Starting recording for user: ${user.tag} (${userId})`);

      // Create audio stream
      const audioStream = recording.receiver.subscribe(userId, {
        end: {
          behavior: EndBehaviorType.Manual,
        },
      });

      // Create file path
      const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
      const filename = `${recording.meetingId}_${userId}_${timestamp}.pcm`;
      const filePath = path.join(this.tempDir, filename);

      // Create write stream
      const writeStream = createWriteStream(filePath);

      // Setup opus decoder
      const opusDecoder = new prism.opus.Decoder({
        frameSize: 960,
        channels: 1,
        rate: 48000,
      });

      // Pipe audio through decoder to file
      pipeline(audioStream, opusDecoder, writeStream).catch(error => {
        this.logger.error(`Audio pipeline error for user ${userId}:`, error);
      });

      const userRecording = {
        userId,
        username: user.tag,
        displayName: member.displayName,
        audioStream,
        writeStream,
        filePath,
        startTime: new Date(),
        isPaused: false,
        duration: 0
      };

      recording.participants.set(userId, userRecording);

    } catch (error) {
      this.logger.error(`Failed to start user recording for ${userId}:`, error);
    }
  }

  async _pauseUserRecording(recording, userId) {
    const userRecording = recording.participants.get(userId);
    if (userRecording && !userRecording.isPaused) {
      userRecording.isPaused = true;
      userRecording.pauseTime = new Date();
    }
  }

  async _stopUserRecording(userRecording) {
    try {
      if (userRecording.writeStream && !userRecording.writeStream.destroyed) {
        userRecording.writeStream.end();
      }

      if (userRecording.audioStream && !userRecording.audioStream.destroyed) {
        userRecording.audioStream.destroy();
      }

      userRecording.endTime = new Date();
      userRecording.duration = Math.floor((userRecording.endTime - userRecording.startTime) / 1000);

      this.logger.info(`Stopped recording for user: ${userRecording.username}, duration: ${userRecording.duration}s`);

    } catch (error) {
      this.logger.error(`Error stopping user recording for ${userRecording.userId}:`, error);
    }
  }

  _startChunkRecording(recording) {
    const chunkInterval = setInterval(() => {
      if (!this.activeRecordings.has(recording.channelId)) {
        clearInterval(chunkInterval);
        return;
      }

      this._processChunk(recording);
      recording.chunkCount++;

    }, this.chunkDuration);

    recording.chunkInterval = chunkInterval;
  }

  async _processChunk(recording) {
    try {
      this.logger.info(`Processing chunk ${recording.chunkCount} for meeting: ${recording.meetingId}`);

      // Create chunk summary
      const chunkData = {
        meetingId: recording.meetingId,
        chunkIndex: recording.chunkCount,
        participants: Array.from(recording.participants.keys()),
        timestamp: new Date(),
        audioFiles: []
      };

      // Collect audio files for this chunk
      for (const [userId, userRecording] of recording.participants) {
        if (userRecording.filePath && await this._fileExists(userRecording.filePath)) {
          chunkData.audioFiles.push({
            userId,
            username: userRecording.username,
            filePath: userRecording.filePath,
            duration: userRecording.duration
          });
        }
      }

      recording.audioFiles.push(chunkData);

      // Send to API for processing
      await this._sendChunkToAPI(chunkData);

    } catch (error) {
      this.logger.error(`Chunk processing error for meeting ${recording.meetingId}:`, error);
    }
  }

  async _fileExists(filePath) {
    try {
      await fs.access(filePath);
      return true;
    } catch {
      return false;
    }
  }

  async _notifyMeetingStart(recording) {
    try {
      const meetingData = {
        meeting_id: recording.meetingId,
        discord_guild_id: recording.guildId,
        discord_channel_id: recording.channelId,
        meeting_title: recording.meetingTitle,
        start_time: recording.startTime.toISOString(),
        status: 'recording'
      };

      await axios.post(`${this.apiUrl}/meeting/start`, meetingData, {
        timeout: 5000
      });

      this.logger.info(`Meeting start notification sent: ${recording.meetingId}`);

    } catch (error) {
      this.logger.error('Failed to notify meeting start:', error);
      // Don't throw - recording should continue even if API is down
    }
  }

  async _sendChunkToAPI(chunkData) {
    try {
      this.logger.info(`Sending ${chunkData.audioFiles.length} audio files for chunk ${chunkData.chunkIndex}`);
      
      for (const audioFile of chunkData.audioFiles) {
        if (await this._fileExists(audioFile.filePath)) {
          this.logger.info(`Processing audio file: ${audioFile.filePath} (size: ${(await fs.stat(audioFile.filePath)).size} bytes)`);
          
          const formData = new FormData();
          const fileBuffer = await fs.readFile(audioFile.filePath);
          const blob = new Blob([fileBuffer], { type: 'audio/pcm' });
          
          formData.append('audio_file', blob, `chunk_${chunkData.chunkIndex}_${audioFile.userId}.pcm`);
          formData.append('meeting_id', chunkData.meetingId);
          formData.append('speaker_id', audioFile.userId);
          formData.append('timestamp', chunkData.timestamp.toISOString());

          this.logger.info(`Sending transcription request to ${this.apiUrl}/transcribe`);

          const response = await axios.post(`${this.apiUrl}/transcribe`, formData, {
            headers: {
              'Content-Type': 'multipart/form-data',
            },
            timeout: 30000
          });

          this.logger.info(`Successfully sent audio chunk to API: ${audioFile.filePath}, response: ${response.status}`);
        } else {
          this.logger.warning(`Audio file not found: ${audioFile.filePath}`);
        }
      }

    } catch (error) {
      this.logger.error('Failed to send chunk to API:', error);
      this.logger.error('API Error details:', error.response?.data || error.message);
      this.logger.error('API URL:', this.apiUrl);
    }
  }

  async _triggerTranscription(recording) {
    try {
      this.logger.info(`Starting transcription trigger for meeting: ${recording.meetingId}`);
      this.logger.info(`Recording participants: ${recording.participants.size}, audio files: ${recording.audioFiles.length}`);
      
      // First, send any remaining audio files to API
      const finalAudioFiles = [];
      for (const [userId, userRecording] of recording.participants) {
        if (userRecording.filePath && await this._fileExists(userRecording.filePath)) {
          finalAudioFiles.push({
            userId,
            username: userRecording.username,
            filePath: userRecording.filePath,
            duration: userRecording.duration
          });
          this.logger.info(`Found audio file for final transcription: ${userRecording.filePath}`);
        }
      }
      
      // Send final audio files to transcription API
      if (finalAudioFiles.length > 0) {
        this.logger.info(`Sending ${finalAudioFiles.length} audio files for transcription`);
        const finalChunkData = {
          meetingId: recording.meetingId,
          chunkIndex: 'final',
          participants: Array.from(recording.participants.keys()),
          timestamp: new Date(),
          audioFiles: finalAudioFiles
        };
        
        await this._sendChunkToAPI(finalChunkData);
        this.logger.info(`Sent final audio chunks for transcription`);
      } else {
        this.logger.warning(`No audio files found for transcription: ${recording.meetingId}`);
      }

      const transcriptionData = {
        meeting_id: recording.meetingId,
        participants: Array.from(recording.participants.values()).map(p => ({
          user_id: p.userId,
          username: p.username,
          display_name: p.displayName,
          duration: p.duration
        })),
        duration_minutes: Math.floor((recording.endTime - recording.startTime) / 1000 / 60),
        audio_files_count: finalAudioFiles.length
      };

      this.logger.info(`Finalizing meeting with data: ${JSON.stringify(transcriptionData)}`);

      await axios.post(`${this.apiUrl}/meeting/finalize`, transcriptionData, {
        timeout: 10000
      });

      this.logger.info(`Transcription triggered successfully for meeting: ${recording.meetingId}`);

    } catch (error) {
      this.logger.error('Failed to trigger transcription:', error);
      this.logger.error('Error details:', error.response?.data || error.message);
    }
  }

  getActiveRecordings() {
    const recordings = [];
    for (const [channelId, recording] of this.activeRecordings) {
      recordings.push({
        meetingId: recording.meetingId,
        channelId,
        status: recording.status,
        startTime: recording.startTime,
        participants: recording.participants.size,
        duration: Math.floor((new Date() - recording.startTime) / 1000 / 60)
      });
    }
    return recordings;
  }

  // Find recording by meetingId (for webhook server)
  findRecordingByMeetingId(meetingId) {
    // Check active recordings first
    for (const [channelId, recording] of this.activeRecordings) {
      if (recording.meetingId === meetingId) {
        return { channelId, ...recording };
      }
    }
    
    // Check completed recordings
    const completedRecording = this.completedRecordings.get(meetingId);
    if (completedRecording) {
      return completedRecording;
    }
    
    return null;
  }

  // Start cleanup timer for completed recordings
  _startCleanupTimer() {
    // Clean up every hour
    setInterval(() => {
      this._cleanupCompletedRecordings();
    }, 60 * 60 * 1000);
  }
  
  // Clean up completed recordings older than 24 hours
  _cleanupCompletedRecordings() {
    const now = new Date();
    const maxAge = 24 * 60 * 60 * 1000; // 24 hours
    
    for (const [meetingId, recording] of this.completedRecordings) {
      if (now - recording.completedAt > maxAge) {
        this.completedRecordings.delete(meetingId);
        this.logger.info(`Cleaned up completed recording: ${meetingId}`);
      }
    }
  }

  async cleanup() {
    try {
      // Stop all active recordings
      for (const channelId of this.activeRecordings.keys()) {
        await this.stopRecording(channelId, 'Bot shutdown');
      }

      // Clear completed recordings
      this.completedRecordings.clear();

      // Clean up old temp files
      const files = await fs.readdir(this.tempDir);
      const now = new Date();
      const maxAge = 24 * 60 * 60 * 1000; // 24 hours

      for (const file of files) {
        const filePath = path.join(this.tempDir, file);
        const stats = await fs.stat(filePath);
        
        if (now - stats.mtime > maxAge) {
          await fs.unlink(filePath);
          this.logger.info(`Cleaned up old file: ${file}`);
        }
      }

    } catch (error) {
      this.logger.error('Cleanup error:', error);
    }
  }
}