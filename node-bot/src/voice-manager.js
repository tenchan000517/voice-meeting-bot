import { joinVoiceChannel, VoiceConnectionStatus } from '@discordjs/voice';

export class VoiceManager {
  constructor(client, logger) {
    this.client = client;
    this.logger = logger;
    this.activeConnections = new Map(); // channelId -> connection info
    this.autoLeaveEnabled = true;
    this.checkInterval = 5000; // Check every 5 seconds
  }

  // Join voice channel in mute mode
  async joinChannel(voiceChannel) {
    try {
      if (this.activeConnections.has(voiceChannel.id)) {
        throw new Error('Already connected to this voice channel');
      }

      this.logger.info(`Joining voice channel: ${voiceChannel.name} (${voiceChannel.id})`);

      const connection = joinVoiceChannel({
        channelId: voiceChannel.id,
        guildId: voiceChannel.guild.id,
        adapterCreator: voiceChannel.guild.voiceAdapterCreator,
        selfDeaf: false,
        selfMute: true, // Join muted
      });

      // Wait for connection to be ready
      await this._waitForConnection(connection);

      const connectionInfo = {
        channelId: voiceChannel.id,
        guildId: voiceChannel.guild.id,
        channelName: voiceChannel.name,
        connection,
        joinTime: new Date(),
        autoLeaveTimer: null
      };

      this.activeConnections.set(voiceChannel.id, connectionInfo);

      // Start monitoring for auto-leave
      if (this.autoLeaveEnabled) {
        this._startAutoLeaveMonitoring(connectionInfo);
      }

      this.logger.info(`Successfully joined voice channel: ${voiceChannel.name}`);

      return {
        channelId: voiceChannel.id,
        channelName: voiceChannel.name,
        status: 'connected',
        joinTime: connectionInfo.joinTime
      };

    } catch (error) {
      this.logger.error('Failed to join voice channel:', error);
      throw error;
    }
  }

  // Leave voice channel
  async leaveChannel(channelId, reason = 'Manual leave') {
    try {
      const connectionInfo = this.activeConnections.get(channelId);
      if (!connectionInfo) {
        throw new Error('Not connected to this voice channel');
      }

      this.logger.info(`Leaving voice channel: ${connectionInfo.channelName}, reason: ${reason}`);

      // Clear auto-leave timer
      if (connectionInfo.autoLeaveTimer) {
        clearInterval(connectionInfo.autoLeaveTimer);
      }

      // Disconnect
      if (connectionInfo.connection) {
        connectionInfo.connection.destroy();
      }

      // Calculate duration
      const duration = Math.floor((new Date() - connectionInfo.joinTime) / 1000 / 60);

      // Clean up
      this.activeConnections.delete(channelId);

      this.logger.info(`Left voice channel: ${connectionInfo.channelName}, duration: ${duration} minutes`);

      return {
        channelId,
        channelName: connectionInfo.channelName,
        status: 'disconnected',
        duration
      };

    } catch (error) {
      this.logger.error('Failed to leave voice channel:', error);
      throw error;
    }
  }

  // Check if there are non-bot members in the voice channel
  async _checkChannelMembers(connectionInfo) {
    try {
      const channel = await this.client.channels.fetch(connectionInfo.channelId);
      if (!channel || !channel.isVoiceBased()) {
        return false;
      }

      // Get current members in the voice channel (excluding bots)
      const humanMembers = channel.members.filter(member => !member.user.bot);
      
      this.logger.debug(`Voice channel ${connectionInfo.channelName} has ${humanMembers.size} human members`);

      return humanMembers.size > 0;
    } catch (error) {
      this.logger.error('Error checking channel members:', error);
      return false;
    }
  }

  // Start monitoring for auto-leave
  _startAutoLeaveMonitoring(connectionInfo) {
    connectionInfo.autoLeaveTimer = setInterval(async () => {
      const hasHumanMembers = await this._checkChannelMembers(connectionInfo);
      
      if (!hasHumanMembers) {
        this.logger.info(`No human members in ${connectionInfo.channelName}, auto-leaving`);
        await this.leaveChannel(connectionInfo.channelId, 'Auto-leave: No human participants');
      }
    }, this.checkInterval);
  }

  // Wait for voice connection to be ready
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

  // Get active connections
  getActiveConnections() {
    const connections = [];
    for (const [channelId, connectionInfo] of this.activeConnections) {
      connections.push({
        channelId,
        channelName: connectionInfo.channelName,
        guildId: connectionInfo.guildId,
        joinTime: connectionInfo.joinTime,
        duration: Math.floor((new Date() - connectionInfo.joinTime) / 1000 / 60)
      });
    }
    return connections;
  }

  // Enable/disable auto-leave feature
  setAutoLeave(enabled) {
    this.autoLeaveEnabled = enabled;
    this.logger.info(`Auto-leave feature ${enabled ? 'enabled' : 'disabled'}`);
  }

  // Cleanup all connections
  async cleanup() {
    try {
      for (const channelId of this.activeConnections.keys()) {
        await this.leaveChannel(channelId, 'Bot shutdown');
      }
    } catch (error) {
      this.logger.error('Cleanup error:', error);
    }
  }
}