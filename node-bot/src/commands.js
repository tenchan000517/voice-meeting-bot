import { SlashCommandBuilder, PermissionFlagsBits, EmbedBuilder } from 'discord.js';

export const commands = [
  new SlashCommandBuilder()
    .setName('record')
    .setDescription('Voice meeting recording commands')
    .addSubcommand(subcommand =>
      subcommand
        .setName('start')
        .setDescription('Start recording the voice channel')
        .addStringOption(option =>
          option
            .setName('title')
            .setDescription('Meeting title (optional)')
            .setRequired(false)
        )
    )
    .addSubcommand(subcommand =>
      subcommand
        .setName('stop')
        .setDescription('Stop recording and generate transcript')
    )
    .addSubcommand(subcommand =>
      subcommand
        .setName('status')
        .setDescription('Check current recording status')
    )
    .addSubcommand(subcommand =>
      subcommand
        .setName('settings')
        .setDescription('Configure recording settings')
        .addStringOption(option =>
          option
            .setName('quality')
            .setDescription('Audio quality setting')
            .setRequired(false)
            .addChoices(
              { name: 'High (48kHz)', value: 'high' },
              { name: 'Medium (24kHz)', value: 'medium' },
              { name: 'Low (16kHz)', value: 'low' }
            )
        )
        .addIntegerOption(option =>
          option
            .setName('maxduration')
            .setDescription('Maximum recording duration in hours (1-6)')
            .setRequired(false)
            .setMinValue(1)
            .setMaxValue(6)
        )
    )
    .setDefaultMemberPermissions(PermissionFlagsBits.Administrator),
  
  new SlashCommandBuilder()
    .setName('voice')
    .setDescription('Voice channel monitoring commands')
    .addSubcommand(subcommand =>
      subcommand
        .setName('join')
        .setDescription('Join voice channel in mute mode')
    )
    .addSubcommand(subcommand =>
      subcommand
        .setName('leave')
        .setDescription('Leave voice channel')
    )
    .addSubcommand(subcommand =>
      subcommand
        .setName('status')
        .setDescription('Check voice channel status')
    )
    .addSubcommand(subcommand =>
      subcommand
        .setName('autoleave')
        .setDescription('Toggle auto-leave when no humans present')
        .addBooleanOption(option =>
          option
            .setName('enabled')
            .setDescription('Enable or disable auto-leave')
            .setRequired(true)
        )
    )
    .setDefaultMemberPermissions(PermissionFlagsBits.Administrator)
];

export class CommandHandler {
  constructor(client, recorder, logger, voiceManager = null) {
    this.client = client;
    this.recorder = recorder;
    this.voiceManager = voiceManager;
    this.logger = logger;
    this.adminUsers = process.env.ADMIN_USER_IDS?.split(',') || [];
  }

  async handleRecordCommand(interaction) {
    try {
      const subcommand = interaction.options.getSubcommand();

      // Check permissions
      if (!this._hasPermission(interaction)) {
        return await interaction.reply({
          content: '❌ この機能を使用する権限がありません。',
          ephemeral: true
        });
      }

      switch (subcommand) {
        case 'start':
          return await this._handleStartRecording(interaction);
        case 'stop':
          return await this._handleStopRecording(interaction);
        case 'status':
          return await this._handleStatus(interaction);
        case 'settings':
          return await this._handleSettings(interaction);
        default:
          return await interaction.reply({
            content: '❌ 不明なコマンドです。',
            ephemeral: true
          });
      }

    } catch (error) {
      this.logger.error('Command handling error:', error);
      
      if (!interaction.replied && !interaction.deferred) {
        await interaction.reply({
          content: '❌ コマンドの実行中にエラーが発生しました。',
          ephemeral: true
        });
      }
    }
  }

  async _handleStartRecording(interaction) {
    try {
      // Check if user is in a voice channel
      const voiceChannel = interaction.member.voice.channel;
      if (!voiceChannel) {
        return await interaction.reply({
          content: '❌ ボイスチャンネルに参加してからコマンドを実行してください。',
          ephemeral: true
        });
      }

      // Check bot permissions
      const permissions = voiceChannel.permissionsFor(interaction.client.user);
      if (!permissions.has(['Connect', 'Speak'])) {
        return await interaction.reply({
          content: '❌ ボットにボイスチャンネルへの接続権限がありません。',
          ephemeral: true
        });
      }

      const title = interaction.options.getString('title');
      const meetingId = this._generateMeetingId();

      await interaction.deferReply();

      // Start recording
      const result = await this.recorder.startRecording(voiceChannel, meetingId, title);

      const embed = new EmbedBuilder()
        .setColor(0x00ff00)
        .setTitle('🎙️ 録音開始')
        .setDescription(`ボイスチャンネル「${voiceChannel.name}」の録音を開始しました`)
        .addFields(
          { name: '会議ID', value: result.meetingId, inline: true },
          { name: '開始時刻', value: result.startTime.toLocaleString('ja-JP'), inline: true },
          { name: 'タイトル', value: title || '未設定', inline: true },
          { name: '📋 注意事項', value: '• 最大3時間まで録音可能\n• 30分ごとに自動処理\n• 録音停止で議事録生成開始', inline: false }
        )
        .setTimestamp()
        .setFooter({ text: 'Voice Meeting Recorder' });

      await interaction.editReply({ embeds: [embed] });

      // Send notification to channel
      const notificationEmbed = new EmbedBuilder()
        .setColor(0xff9900)
        .setTitle('🔴 録音中')
        .setDescription('このボイスチャンネルは現在録音されています')
        .addFields(
          { name: '開始者', value: interaction.user.toString(), inline: true },
          { name: '会議ID', value: result.meetingId, inline: true }
        )
        .setTimestamp();

      await interaction.followUp({ 
        embeds: [notificationEmbed],
        ephemeral: false 
      });

    } catch (error) {
      this.logger.error('Start recording error:', error);
      
      const errorEmbed = new EmbedBuilder()
        .setColor(0xff0000)
        .setTitle('❌ 録音開始エラー')
        .setDescription(error.message || '録音の開始に失敗しました')
        .setTimestamp();

      if (interaction.deferred) {
        await interaction.editReply({ embeds: [errorEmbed] });
      } else {
        await interaction.reply({ embeds: [errorEmbed], ephemeral: true });
      }
    }
  }

  async _handleStopRecording(interaction) {
    try {
      const voiceChannel = interaction.member.voice.channel;
      if (!voiceChannel) {
        return await interaction.reply({
          content: '❌ ボイスチャンネルに参加してからコマンドを実行してください。',
          ephemeral: true
        });
      }

      await interaction.deferReply();

      // Stop recording
      const result = await this.recorder.stopRecording(voiceChannel.id);

      const embed = new EmbedBuilder()
        .setColor(0xff0000)
        .setTitle('⏹️ 録音停止')
        .setDescription('録音を停止し、議事録の生成を開始しました')
        .addFields(
          { name: '会議ID', value: result.meetingId, inline: true },
          { name: '録音時間', value: `${result.duration}分`, inline: true },
          { name: '参加者数', value: `${result.participants}人`, inline: true },
          { name: '音声ファイル数', value: `${result.audioFiles}件`, inline: true },
          { name: '📝 処理状況', value: '文字起こしと要約を生成中...\n完了時に通知します', inline: false }
        )
        .setTimestamp()
        .setFooter({ text: 'Voice Meeting Recorder' });

      await interaction.editReply({ embeds: [embed] });

    } catch (error) {
      this.logger.error('Stop recording error:', error);
      
      const errorEmbed = new EmbedBuilder()
        .setColor(0xff0000)
        .setTitle('❌ 録音停止エラー')
        .setDescription(error.message || '録音の停止に失敗しました')
        .setTimestamp();

      if (interaction.deferred) {
        await interaction.editReply({ embeds: [errorEmbed] });
      } else {
        await interaction.reply({ embeds: [errorEmbed], ephemeral: true });
      }
    }
  }

  async _handleStatus(interaction) {
    try {
      const recordings = this.recorder.getActiveRecordings();

      if (recordings.length === 0) {
        const embed = new EmbedBuilder()
          .setColor(0x666666)
          .setTitle('📊 録音状況')
          .setDescription('現在、アクティブな録音はありません')
          .setTimestamp();

        return await interaction.reply({ embeds: [embed] });
      }

      const embed = new EmbedBuilder()
        .setColor(0x0099ff)
        .setTitle('📊 録音状況')
        .setDescription(`${recordings.length}件の録音がアクティブです`)
        .setTimestamp();

      recordings.forEach((recording, index) => {
        const channel = interaction.client.channels.cache.get(recording.channelId);
        const channelName = channel ? channel.name : '不明なチャンネル';
        
        embed.addFields({
          name: `🎙️ 録音 ${index + 1}`,
          value: `**チャンネル:** ${channelName}\n**会議ID:** ${recording.meetingId}\n**開始時刻:** ${recording.startTime.toLocaleString('ja-JP')}\n**録音時間:** ${recording.duration}分\n**参加者:** ${recording.participants}人`,
          inline: false
        });
      });

      await interaction.reply({ embeds: [embed] });

    } catch (error) {
      this.logger.error('Status check error:', error);
      await interaction.reply({
        content: '❌ 状況確認中にエラーが発生しました。',
        ephemeral: true
      });
    }
  }

  async _handleSettings(interaction) {
    try {
      const quality = interaction.options.getString('quality');
      const maxDuration = interaction.options.getInteger('maxduration');

      if (!quality && !maxDuration) {
        // Show current settings
        const embed = new EmbedBuilder()
          .setColor(0x0099ff)
          .setTitle('⚙️ 録音設定')
          .addFields(
            { name: '音質', value: '中 (24kHz)', inline: true },
            { name: '最大録音時間', value: '3時間', inline: true },
            { name: 'チャンク間隔', value: '30分', inline: true },
            { name: '自動削除', value: '24時間後', inline: true }
          )
          .setFooter({ text: '設定を変更するには、オプションを指定してください' })
          .setTimestamp();

        return await interaction.reply({ embeds: [embed], ephemeral: true });
      }

      // Update settings (placeholder - implement actual settings storage)
      const embed = new EmbedBuilder()
        .setColor(0x00ff00)
        .setTitle('✅ 設定更新')
        .setDescription('録音設定を更新しました')
        .setTimestamp();

      if (quality) {
        embed.addFields({ name: '音質', value: quality, inline: true });
      }

      if (maxDuration) {
        embed.addFields({ name: '最大録音時間', value: `${maxDuration}時間`, inline: true });
      }

      await interaction.reply({ embeds: [embed], ephemeral: true });

    } catch (error) {
      this.logger.error('Settings error:', error);
      await interaction.reply({
        content: '❌ 設定変更中にエラーが発生しました。',
        ephemeral: true
      });
    }
  }

  _hasPermission(interaction) {
    // Check if user is admin
    if (interaction.member.permissions.has(PermissionFlagsBits.Administrator)) {
      return true;
    }

    // Check if user is in admin list
    if (this.adminUsers.includes(interaction.user.id)) {
      return true;
    }

    return false;
  }

  _generateMeetingId() {
    const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
    const random = Math.random().toString(36).substring(2, 8);
    return `meeting-${timestamp}-${random}`;
  }

  async handleVoiceCommand(interaction) {
    try {
      const subcommand = interaction.options.getSubcommand();

      // Check if voice manager is available
      if (!this.voiceManager) {
        return await interaction.reply({
          content: '❌ 音声管理機能が利用できません。',
          ephemeral: true
        });
      }

      // Check permissions
      if (!this._hasPermission(interaction)) {
        return await interaction.reply({
          content: '❌ この機能を使用する権限がありません。',
          ephemeral: true
        });
      }

      switch (subcommand) {
        case 'join':
          return await this._handleVoiceJoin(interaction);
        case 'leave':
          return await this._handleVoiceLeave(interaction);
        case 'status':
          return await this._handleVoiceStatus(interaction);
        case 'autoleave':
          return await this._handleAutoLeave(interaction);
        default:
          return await interaction.reply({
            content: '❌ 不明なコマンドです。',
            ephemeral: true
          });
      }

    } catch (error) {
      this.logger.error('Voice command handling error:', error);
      
      if (!interaction.replied && !interaction.deferred) {
        await interaction.reply({
          content: '❌ コマンドの実行中にエラーが発生しました。',
          ephemeral: true
        });
      }
    }
  }

  async _handleVoiceJoin(interaction) {
    try {
      // Check if user is in a voice channel
      const voiceChannel = interaction.member.voice.channel;
      if (!voiceChannel) {
        return await interaction.reply({
          content: '❌ ボイスチャンネルに参加してからコマンドを実行してください。',
          ephemeral: true
        });
      }

      // Check bot permissions
      const permissions = voiceChannel.permissionsFor(interaction.client.user);
      if (!permissions.has(['Connect', 'Speak'])) {
        return await interaction.reply({
          content: '❌ ボットにボイスチャンネルへの接続権限がありません。',
          ephemeral: true
        });
      }

      await interaction.deferReply();

      // Join voice channel
      const result = await this.voiceManager.joinChannel(voiceChannel);

      const embed = new EmbedBuilder()
        .setColor(0x00ff00)
        .setTitle('🔊 ボイスチャンネル参加')
        .setDescription(`ボイスチャンネル「${voiceChannel.name}」に参加しました`)
        .addFields(
          { name: 'チャンネル', value: result.channelName, inline: true },
          { name: '参加時刻', value: result.joinTime.toLocaleString('ja-JP'), inline: true },
          { name: '自動退出', value: 'ユーザーがいなくなったら自動退出します', inline: false }
        )
        .setTimestamp()
        .setFooter({ text: 'Voice Monitor Bot' });

      await interaction.editReply({ embeds: [embed] });

    } catch (error) {
      this.logger.error('Voice join error:', error);
      
      const errorEmbed = new EmbedBuilder()
        .setColor(0xff0000)
        .setTitle('❌ 参加エラー')
        .setDescription(error.message || 'ボイスチャンネルへの参加に失敗しました')
        .setTimestamp();

      if (interaction.deferred) {
        await interaction.editReply({ embeds: [errorEmbed] });
      } else {
        await interaction.reply({ embeds: [errorEmbed], ephemeral: true });
      }
    }
  }

  async _handleVoiceLeave(interaction) {
    try {
      const voiceChannel = interaction.member.voice.channel;
      if (!voiceChannel) {
        return await interaction.reply({
          content: '❌ ボイスチャンネルに参加してからコマンドを実行してください。',
          ephemeral: true
        });
      }

      await interaction.deferReply();

      // Leave voice channel
      const result = await this.voiceManager.leaveChannel(voiceChannel.id);

      const embed = new EmbedBuilder()
        .setColor(0xff0000)
        .setTitle('👋 ボイスチャンネル退出')
        .setDescription(`ボイスチャンネル「${result.channelName}」から退出しました`)
        .addFields(
          { name: 'チャンネル', value: result.channelName, inline: true },
          { name: '滞在時間', value: `${result.duration}分`, inline: true }
        )
        .setTimestamp()
        .setFooter({ text: 'Voice Monitor Bot' });

      await interaction.editReply({ embeds: [embed] });

    } catch (error) {
      this.logger.error('Voice leave error:', error);
      
      const errorEmbed = new EmbedBuilder()
        .setColor(0xff0000)
        .setTitle('❌ 退出エラー')
        .setDescription(error.message || 'ボイスチャンネルからの退出に失敗しました')
        .setTimestamp();

      if (interaction.deferred) {
        await interaction.editReply({ embeds: [errorEmbed] });
      } else {
        await interaction.reply({ embeds: [errorEmbed], ephemeral: true });
      }
    }
  }

  async _handleVoiceStatus(interaction) {
    try {
      const connections = this.voiceManager.getActiveConnections();

      if (connections.length === 0) {
        const embed = new EmbedBuilder()
          .setColor(0x666666)
          .setTitle('📊 ボイス接続状況')
          .setDescription('現在、ボイスチャンネルに接続していません')
          .setTimestamp();

        return await interaction.reply({ embeds: [embed] });
      }

      const embed = new EmbedBuilder()
        .setColor(0x0099ff)
        .setTitle('📊 ボイス接続状況')
        .setDescription(`${connections.length}個のボイスチャンネルに接続中`)
        .setTimestamp();

      connections.forEach((connection, index) => {
        const channel = interaction.client.channels.cache.get(connection.channelId);
        const channelName = channel ? channel.name : '不明なチャンネル';
        
        embed.addFields({
          name: `🔊 接続 ${index + 1}`,
          value: `**チャンネル:** ${channelName}\n**参加時刻:** ${connection.joinTime.toLocaleString('ja-JP')}\n**滞在時間:** ${connection.duration}分`,
          inline: false
        });
      });

      await interaction.reply({ embeds: [embed] });

    } catch (error) {
      this.logger.error('Voice status error:', error);
      await interaction.reply({
        content: '❌ 状況確認中にエラーが発生しました。',
        ephemeral: true
      });
    }
  }

  async _handleAutoLeave(interaction) {
    try {
      const enabled = interaction.options.getBoolean('enabled');
      
      this.voiceManager.setAutoLeave(enabled);

      const embed = new EmbedBuilder()
        .setColor(enabled ? 0x00ff00 : 0xff9900)
        .setTitle('⚙️ 自動退出設定')
        .setDescription(`自動退出機能を${enabled ? '有効' : '無効'}にしました`)
        .addFields({
          name: '設定内容',
          value: enabled 
            ? 'ボイスチャンネルにユーザーがいなくなったら自動で退出します'
            : '自動退出は無効です。手動で退出してください',
          inline: false
        })
        .setTimestamp();

      await interaction.reply({ embeds: [embed] });

    } catch (error) {
      this.logger.error('Auto-leave setting error:', error);
      await interaction.reply({
        content: '❌ 設定変更中にエラーが発生しました。',
        ephemeral: true
      });
    }
  }

  async registerCommands(guildId = null) {
    try {
      if (guildId) {
        // Register to specific guild (faster for development)
        const guild = await this.client.guilds.fetch(guildId);
        await guild.commands.set(commands);
        this.logger.info(`Commands registered to guild: ${guild.name}`);
      } else {
        // Register globally (takes up to 1 hour to propagate)
        await this.client.application.commands.set(commands);
        this.logger.info('Commands registered globally');
      }
    } catch (error) {
      this.logger.error('Failed to register commands:', error);
    }
  }
}