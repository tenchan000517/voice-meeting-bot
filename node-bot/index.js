import { Client, GatewayIntentBits } from 'discord.js';
import dotenv from 'dotenv';
import winston from 'winston';
import fs from 'fs/promises';
import path from 'path';
import { fileURLToPath } from 'url';

// Import our modules
import { VoiceRecorder } from './src/recorder.js';
import { CommandHandler } from './src/commands.js';
import { VoiceManager } from './src/voice-manager.js';

// Load environment variables
dotenv.config();

// Get current directory for ES modules
const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// Ensure log directory exists
await fs.mkdir(path.join(__dirname, 'logs'), { recursive: true });

// Configure logger
const logger = winston.createLogger({
  level: process.env.LOG_LEVEL || 'info',
  format: winston.format.combine(
    winston.format.timestamp(),
    winston.format.errors({ stack: true }),
    winston.format.json()
  ),
  defaultMeta: { service: 'voice-meeting-bot' },
  transports: [
    new winston.transports.File({ filename: path.join(__dirname, 'logs', 'error.log'), level: 'error' }),
    new winston.transports.File({ filename: path.join(__dirname, 'logs', 'combined.log') }),
    new winston.transports.Console({
      format: winston.format.simple()
    })
  ]
});

// Create Discord client with required intents
const client = new Client({
  intents: [
    GatewayIntentBits.Guilds,
    GatewayIntentBits.GuildMessages,
    GatewayIntentBits.MessageContent,
    GatewayIntentBits.GuildVoiceStates,
    GatewayIntentBits.GuildMembers
  ]
});

// Initialize recorder, voice manager, and command handler
const recorder = new VoiceRecorder(client, logger);
const voiceManager = new VoiceManager(client, logger);
const commandHandler = new CommandHandler(client, recorder, logger, voiceManager);

// Bot ready event
client.once('ready', async () => {
  logger.info(`Logged in as ${client.user.tag}!`);
  logger.info('Voice Meeting Recorder Bot is ready!');
  
  // Register slash commands (development - register to specific guild for faster updates)
  const devGuildId = process.env.DEV_GUILD_ID;
  if (devGuildId) {
    await commandHandler.registerCommands(devGuildId);
  } else {
    await commandHandler.registerCommands(); // Global registration
  }
});

// Handle slash commands
client.on('interactionCreate', async (interaction) => {
  if (!interaction.isCommand()) return;

  try {
    switch (interaction.commandName) {
      case 'record':
        await commandHandler.handleRecordCommand(interaction);
        break;
      case 'voice':
        await commandHandler.handleVoiceCommand(interaction);
        break;
      default:
        await interaction.reply({
          content: '❌ 不明なコマンドです。',
          ephemeral: true
        });
    }
  } catch (error) {
    logger.error('Interaction handling error:', error);
    
    if (!interaction.replied && !interaction.deferred) {
      await interaction.reply({
        content: '❌ コマンドの実行中にエラーが発生しました。',
        ephemeral: true
      });
    }
  }
});

// Basic ping command for testing (legacy)
client.on('messageCreate', async (message) => {
  if (message.author.bot) return;
  
  if (message.content === '!ping') {
    const embed = {
      color: 0x00ff00,
      title: '🎙️ Voice Meeting Recorder Bot',
      description: 'Bot is online and ready!',
      fields: [
        {
          name: 'Available Commands',
          value: `
            \`/record start\` - Start recording voice channel
            \`/record stop\` - Stop recording and generate transcript
            \`/record status\` - Check current recording status
            \`/record settings\` - Configure recording settings
          `,
          inline: false
        },
        {
          name: 'System Status',
          value: `
            🔹 Active recordings: ${recorder.getActiveRecordings().length}
            🔹 Uptime: ${Math.floor(client.uptime / 1000 / 60)} minutes
          `,
          inline: false
        }
      ],
      timestamp: new Date(),
      footer: {
        text: 'Voice Meeting Recorder v1.0'
      }
    };
    
    await message.reply({ embeds: [embed] });
  }
});

// Voice state updates (for participant tracking)
client.on('voiceStateUpdate', (oldState, newState) => {
  // Log voice channel joins/leaves for active recordings
  const recordings = recorder.getActiveRecordings();
  
  recordings.forEach(recording => {
    if (recording.channelId === newState.channelId || recording.channelId === oldState.channelId) {
      const action = newState.channelId ? 'joined' : 'left';
      logger.info(`User ${newState.member.user.tag} ${action} recorded voice channel`);
    }
  });
});

// Error handling
client.on('error', (error) => {
  logger.error('Discord client error:', error);
});

client.on('warn', (warning) => {
  logger.warn('Discord client warning:', warning);
});

// Graceful shutdown
process.on('SIGINT', async () => {
  logger.info('Received SIGINT, shutting down gracefully...');
  
  try {
    await recorder.cleanup();
    await voiceManager.cleanup();
    client.destroy();
    process.exit(0);
  } catch (error) {
    logger.error('Error during shutdown:', error);
    process.exit(1);
  }
});

process.on('SIGTERM', async () => {
  logger.info('Received SIGTERM, shutting down gracefully...');
  
  try {
    await recorder.cleanup();
    await voiceManager.cleanup();
    client.destroy();
    process.exit(0);
  } catch (error) {
    logger.error('Error during shutdown:', error);
    process.exit(1);
  }
});

process.on('unhandledRejection', (reason, promise) => {
  logger.error('Unhandled Rejection at:', promise, 'reason:', reason);
});

process.on('uncaughtException', (error) => {
  logger.error('Uncaught Exception:', error);
  process.exit(1);
});

// Login to Discord
client.login(process.env.DISCORD_BOT_TOKEN)
  .then(() => {
    logger.info('Successfully logged in to Discord');
  })
  .catch((error) => {
    logger.error('Failed to login to Discord:', error);
    process.exit(1);
  });