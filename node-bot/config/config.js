const path = require('path');

module.exports = {
    // API接続設定
    pythonApi: {
        host: process.env.PYTHON_API_HOST || 'localhost',
        port: process.env.PYTHON_API_PORT || 8000,
        baseUrl: process.env.PYTHON_API_URL || 'http://localhost:8000'
    },
    
    // Discord設定
    discord: {
        token: process.env.DISCORD_TOKEN,
        guildId: process.env.DISCORD_GUILD_ID,
        clientId: process.env.DISCORD_CLIENT_ID
    },
    
    // ログ設定
    logging: {
        level: process.env.LOG_LEVEL || 'info',
        directory: path.join(__dirname, '..', 'logs')
    }
};