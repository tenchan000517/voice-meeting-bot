import express from 'express';
import path from 'path';
import logger from './logger.js';

class WebhookServer {
    constructor(bot, voiceRecorder) {
        this.app = express();
        this.bot = bot;
        this.voiceRecorder = voiceRecorder;
        this.server = null;
        
        // Middleware
        this.app.use(express.json());
        
        // Static file serving for audio files
        this.app.use('/audio', express.static('/tmp/voice-meeting-bot/temp'));
        
        // Health check endpoint
        this.app.get('/health', (req, res) => {
            res.json({ status: 'ok', timestamp: new Date().toISOString() });
        });
        
        // Individual audio file download endpoint
        this.app.get('/audio/:filename', (req, res) => {
            try {
                const filepath = path.join('/tmp/voice-meeting-bot/temp', req.params.filename);
                res.download(filepath, (err) => {
                    if (err) {
                        logger.error(`Error downloading audio file ${req.params.filename}:`, err);
                        res.status(404).json({ error: 'Audio file not found' });
                    }
                });
            } catch (error) {
                logger.error(`Error serving audio file ${req.params.filename}:`, error);
                res.status(500).json({ error: 'Internal server error' });
            }
        });
        
        // Webhook endpoint for meeting events (lightweight design)
        this.app.post('/webhook/meeting-completed', async (req, res) => {
            try {
                const { meeting_id, event, timestamp, download_links, chunk_index, time_range } = req.body;
                
                logger.info(`Webhook received - Event: ${event}, Meeting: ${meeting_id}`);
                
                switch (event) {
                    case 'chunk_summary':
                        await this.sendChunkSummaryNotification(meeting_id, chunk_index, time_range, download_links);
                        break;
                    
                    case 'final_summary':
                        await this.sendFinalSummaryNotification(meeting_id, download_links);
                        break;
                    
                    case 'meeting_completed':
                        await this.sendDownloadLinksMessage(meeting_id, download_links);
                        break;
                    
                    default:
                        logger.warn(`Unknown event type: ${event}`);
                        return res.status(400).json({ error: 'Unknown event type' });
                }
                
                res.json({ status: 'success', event: event, processed_at: new Date().toISOString() });
                
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
    
    async sendChunkSummaryNotification(meetingId, chunkIndex, timeRange, downloadLinks) {
        try {
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
            
            const { EmbedBuilder, ButtonBuilder, ButtonStyle, ActionRowBuilder } = await import('discord.js');
            
            const embed = new EmbedBuilder()
                .setTitle(`📝 リアルタイム議事録 (${timeRange})`)
                .setDescription(`**会議ID**: \`${meetingId}\`\n**時間帯**: ${timeRange}\n\n💡 **軽量設計**: 重い処理はサーバー側で完結し、ダウンロードリンクのみ提供`)
                .setColor('#00bfff')
                .setTimestamp()
                .addFields(
                    { name: '📋 チャンク要約', value: 'この時間帯の要約をダウンロード', inline: true },
                    { name: '📄 文字起こし', value: 'この時間帯の転写をダウンロード', inline: true }
                )
                .setFooter({ text: `チャンク ${chunkIndex} - サーバー側処理完了` });
            
            const row = new ActionRowBuilder()
                .addComponents(
                    new ButtonBuilder()
                        .setCustomId(`download_chunk_summary_${meetingId}_${chunkIndex}`)
                        .setLabel('📋 チャンク要約')
                        .setStyle(ButtonStyle.Primary),
                    new ButtonBuilder()
                        .setCustomId(`download_chunk_transcript_${meetingId}_${chunkIndex}`)
                        .setLabel('📄 チャンク転写')
                        .setStyle(ButtonStyle.Secondary)
                );
            
            await channel.send({
                embeds: [embed],
                components: [row]
            });
            
            logger.info(`Chunk summary notification sent for meeting ${meetingId}, chunk ${chunkIndex}`);
            
        } catch (error) {
            logger.error(`Failed to send chunk summary notification for meeting ${meetingId}:`, error);
        }
    }
    
    async sendFinalSummaryNotification(meetingId, downloadLinks) {
        try {
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
            
            const { EmbedBuilder, ButtonBuilder, ButtonStyle, ActionRowBuilder } = await import('discord.js');
            
            const embed = new EmbedBuilder()
                .setTitle('🎙️ 最終議事録が完成しました')
                .setDescription(`**会議ID**: \`${meetingId}\`\n\n✅ **全チャンク処理完了** - 統合議事録をサーバー側で生成\n💡 **軽量設計**: ダウンロードリンクのみ提供`)
                .setColor('#00ff00')
                .setTimestamp()
                .addFields(
                    { name: '📊 最終統合議事録', value: '全チャンクを統合した完全版', inline: true },
                    { name: '📝 全チャンク要約', value: '時間帯別要約の一覧', inline: true },
                    { name: '📄 完全転写', value: '全発言の転写データ', inline: true }
                )
                .setFooter({ text: '会議完了 - サーバー側処理完了' });
            
            const row = new ActionRowBuilder()
                .addComponents(
                    new ButtonBuilder()
                        .setCustomId(`download_final_summary_${meetingId}`)
                        .setLabel('🎙️ 最終議事録')
                        .setStyle(ButtonStyle.Success),
                    new ButtonBuilder()
                        .setCustomId(`download_all_chunks_${meetingId}`)
                        .setLabel('📝 全チャンク要約')
                        .setStyle(ButtonStyle.Primary),
                    new ButtonBuilder()
                        .setCustomId(`download_transcript_${meetingId}`)
                        .setLabel('📄 完全転写')
                        .setStyle(ButtonStyle.Secondary)
                );
            
            await channel.send({
                embeds: [embed],
                components: [row]
            });
            
            logger.info(`Final summary notification sent for meeting ${meetingId}`);
            
        } catch (error) {
            logger.error(`Failed to send final summary notification for meeting ${meetingId}:`, error);
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