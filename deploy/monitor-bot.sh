#!/bin/bash

# Discord Bot 総合監視スクリプト
# EC2での永続稼働監視用

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

print_header() {
    echo -e "${BLUE}================================${NC}"
    echo -e "${BLUE} Discord Bot 監視ダッシュボード${NC}"
    echo -e "${BLUE}================================${NC}"
    echo ""
}

check_service_status() {
    echo -e "${BLUE}📊 サービス状態:${NC}"
    if sudo systemctl is-active --quiet voice-meeting-discord-bot.service; then
        echo -e "  ✅ ${GREEN}Discord Bot: Running${NC}"
    else
        echo -e "  ❌ ${RED}Discord Bot: Stopped${NC}"
    fi
    
    # プロセス詳細
    PROCESS_INFO=$(ps aux | grep "node index.js" | grep -v grep | head -1)
    if [ -n "$PROCESS_INFO" ]; then
        PID=$(echo $PROCESS_INFO | awk '{print $2}')
        CPU=$(echo $PROCESS_INFO | awk '{print $3}')
        MEM=$(echo $PROCESS_INFO | awk '{print $4}')
        echo -e "  📈 PID: $PID, CPU: ${CPU}%, Memory: ${MEM}%"
    fi
    echo ""
}

check_network_status() {
    echo -e "${BLUE}🌐 ネットワーク状態:${NC}"
    
    # ポート3003チェック
    if ss -tln | grep -q ":3003"; then
        echo -e "  ✅ ${GREEN}Port 3003: Listening${NC}"
    else
        echo -e "  ❌ ${RED}Port 3003: Not listening${NC}"
    fi
    
    # Webhook テスト
    if curl -s -f "http://localhost:3003/webhook/meeting-completed" -X POST -H "Content-Type: application/json" -d '{"test":"monitor"}' > /dev/null 2>&1; then
        echo -e "  ✅ ${GREEN}Webhook: Responding${NC}"
    else
        echo -e "  ❌ ${RED}Webhook: Not responding${NC}"
    fi
    
    # Python API接続テスト
    API_URL=$(grep PYTHON_API_URL /home/ec2-user/voice-meeting-bot/node-bot/.env | cut -d'=' -f2)
    if [ -n "$API_URL" ]; then
        if curl -s -f "$API_URL/health" > /dev/null 2>&1; then
            echo -e "  ✅ ${GREEN}Python API: Reachable${NC}"
        else
            echo -e "  ⚠️  ${YELLOW}Python API: Unreachable (Local server expected)${NC}"
        fi
    fi
    echo ""
}

check_disk_usage() {
    echo -e "${BLUE}💾 ディスク使用量:${NC}"
    
    # 音声ファイル一時保存ディレクトリ
    TEMP_DIR="/tmp/voice-meeting-bot/temp"
    if [ -d "$TEMP_DIR" ]; then
        TEMP_SIZE=$(du -sh "$TEMP_DIR" 2>/dev/null | cut -f1)
        FILE_COUNT=$(find "$TEMP_DIR" -name "*.pcm" | wc -l)
        echo -e "  📁 音声ファイル: ${TEMP_SIZE} (${FILE_COUNT} files)"
    fi
    
    # ログファイルサイズ
    LOG_SIZE=$(sudo journalctl -u voice-meeting-discord-bot.service --disk-usage 2>/dev/null | grep -o '[0-9.]*[A-Z]*' | head -1)
    echo -e "  📄 システムログ: ${LOG_SIZE:-N/A}"
    
    # ルートディスク使用量
    ROOT_USAGE=$(df / | tail -1 | awk '{print $5}' | sed 's/%//')
    if [ "$ROOT_USAGE" -gt 80 ]; then
        echo -e "  ⚠️  ${YELLOW}Root disk: ${ROOT_USAGE}% (High usage)${NC}"
    else
        echo -e "  ✅ Root disk: ${ROOT_USAGE}%"
    fi
    echo ""
}

check_recent_activity() {
    echo -e "${BLUE}📈 最近のアクティビティ:${NC}"
    
    # 最近の音声ファイル
    RECENT_FILES=$(find /tmp/voice-meeting-bot/temp -name "*.pcm" -mtime -1 2>/dev/null | wc -l)
    echo -e "  🎵 過去24時間の録音: ${RECENT_FILES} files"
    
    # 最新ログ（エラーのみ）
    RECENT_ERRORS=$(sudo journalctl -u voice-meeting-discord-bot.service --since "1 hour ago" | grep -i error | wc -l)
    if [ "$RECENT_ERRORS" -gt 0 ]; then
        echo -e "  ⚠️  ${YELLOW}過去1時間のエラー: ${RECENT_ERRORS}${NC}"
    else
        echo -e "  ✅ 過去1時間のエラー: 0"
    fi
    
    # 最後の更新確認
    if [ -f "/var/log/voice-meeting-bot-update.log" ]; then
        LAST_UPDATE=$(tail -n 1 /var/log/voice-meeting-bot-update.log 2>/dev/null | grep -o '^[0-9-]* [0-9:]*')
        if [ -n "$LAST_UPDATE" ]; then
            echo -e "  🔄 最終更新チェック: ${LAST_UPDATE}"
        fi
    fi
    echo ""
}

print_quick_commands() {
    echo -e "${BLUE}🛠️  クイックコマンド:${NC}"
    echo "  bot-restart  - サービス再起動"
    echo "  bot-logs     - リアルタイムログ表示"
    echo "  bot-update   - 手動更新実行"
    echo "  bot-status   - 詳細ステータス表示"
    echo ""
}

# メイン実行
print_header
check_service_status
check_network_status
check_disk_usage
check_recent_activity
print_quick_commands

# 引数に応じた追加処理
case "${1:-}" in
    "logs")
        echo -e "${BLUE}📋 リアルタイムログ表示中...${NC}"
        sudo journalctl -u voice-meeting-discord-bot.service -f
        ;;
    "errors")
        echo -e "${BLUE}❌ 最近のエラーログ:${NC}"
        sudo journalctl -u voice-meeting-discord-bot.service --since "24 hours ago" | grep -i error | tail -10
        ;;
    "clean")
        echo -e "${BLUE}🧹 古い音声ファイルをクリーンアップ中...${NC}"
        find /tmp/voice-meeting-bot/temp -name "*.pcm" -mtime +1 -delete 2>/dev/null
        echo "✅ クリーンアップ完了"
        ;;
esac