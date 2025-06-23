import express from 'express';
import logger from './logger.js';

class WebhookServer {
    constructor(bot, voiceRecorder) {
        this.app = express();
        this.bot = bot;
        this.voiceRecorder = voiceRecorder;
        this.server = null;
        
        // Middleware
        this.app.use(express.json());
        
        // Health check endpoint
        this.app.get('/health', (req, res) => {
            res.json({ status: 'ok', timestamp: new Date().toISOString() });
        });
        
        // Webhook endpoint for meeting completion
        this.app.post('/webhook/meeting-completed', async (req, res) => {
            try {
                const { meeting_id, event, timestamp, download_links } = req.body;
                
                if (event !== 'meeting_completed') {
                    return res.status(400).json({ error: 'Invalid event type' });
                }
                
                logger.info(`Webhook received for meeting: ${meeting_id}`);
                
                // Send download links message to Discord
                await this.sendDownloadLinksMessage(meeting_id, download_links);
                
                res.json({ status: 'success', processed_at: new Date().toISOString() });
                
            } catch (error) {
                logger.error('Webhook processing error:', error);
                res.status(500).json({ error: 'Internal server error' });
            }
        });
    }
    
    async sendDownloadLinksMessage(meetingId, downloadLinks) {
        try {
            // Find the channel where the meeting was recorded
            // This would be stored in the meeting data or passed through the webhook
            const channelId = await this.getMeetingChannelId(meetingId);
            
            if (!channelId) {
                logger.warn(`No channel found for meeting ${meetingId}`);
                return;
            }
            
            const channel = this.bot.channels.cache.get(channelId);
            
            if (!channel) {
                logger.warn(`Channel ${channelId} not found in cache`);
                return;
            }
            
            logger.info(`Found channel: ${channel.name} (${channel.type}), guild: ${channel.guild?.name}`);
            
            // Check bot permissions
            const permissions = channel.permissionsFor(this.bot.user);
            logger.info(`Bot permissions in channel: SendMessages=${permissions?.has('SendMessages')}, EmbedLinks=${permissions?.has('EmbedLinks')}`);
            
            // Create download buttons and message
            const { ActionRowBuilder, ButtonBuilder, ButtonStyle, EmbedBuilder } = await import('discord.js');
            
            const embed = new EmbedBuilder()
                .setTitle('📊 議事録の準備が完了しました')
                .setDescription(`ミーティング: \`${meetingId}\`\n\n以下のボタンから各種データをダウンロードできます。`)
                .setColor('#00ff00')
                .setTimestamp()
                .addFields(
                    { name: '📄 要約・議事録', value: 'Markdown形式の議事録', inline: true },
                    { name: '📝 転写テキスト', value: '全発言の転写データ', inline: true },
                    { name: '🎵 音声チャンク', value: '録音データの情報', inline: true }
                )
                .setFooter({ text: 'データ保存期限: 7日間' });
            
            const row = new ActionRowBuilder()
                .addComponents(
                    new ButtonBuilder()
                        .setCustomId(`download_summary_${meetingId}`)
                        .setLabel('📊 要約・議事録')
                        .setStyle(ButtonStyle.Primary),
                    new ButtonBuilder()
                        .setCustomId(`download_transcript_${meetingId}`)
                        .setLabel('📄 転写テキスト')
                        .setStyle(ButtonStyle.Secondary),
                    new ButtonBuilder()
                        .setCustomId(`download_chunks_${meetingId}`)
                        .setLabel('🎵 音声チャンク')
                        .setStyle(ButtonStyle.Success)
                );
            
            const sentMessage = await channel.send({
                embeds: [embed],
                components: [row]
            });
            
            logger.info(`Download links message sent for meeting ${meetingId} to channel ${channelId}, message ID: ${sentMessage.id}`);
            
        } catch (error) {
            logger.error(`Failed to send download links message for meeting ${meetingId}:`, error);
        }
    }
    
    async getMeetingChannelId(meetingId) {
        try {
            // Use VoiceRecorder to find the recording
            const recordingInfo = this.voiceRecorder.findRecordingByMeetingId(meetingId);
            if (recordingInfo) {
                return recordingInfo.channelId;
            }
            
            // Fallback: could be retrieved from database or other storage
            logger.warn(`Could not find channel for meeting ${meetingId}`);
            return null;
            
        } catch (error) {
            logger.error(`Error getting meeting channel ID for ${meetingId}:`, error);
            return null;
        }
    }
    
    start(port = 3001) {
        return new Promise((resolve, reject) => {
            this.server = this.app.listen(port, (error) => {
                if (error) {
                    logger.error('Failed to start webhook server:', error);
                    reject(error);
                } else {
                    logger.info(`Webhook server started on port ${port}`);
                    resolve();
                }
            });
        });
    }
    
    stop() {
        return new Promise((resolve) => {
            if (this.server) {
                this.server.close(() => {
                    logger.info('Webhook server stopped');
                    resolve();
                });
            } else {
                resolve();
            }
        });
    }
}

export default WebhookServer;