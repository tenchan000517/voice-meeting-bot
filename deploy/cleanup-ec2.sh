#!/bin/bash

# Voice Meeting Bot EC2クリーンアップスクリプト
# 実行前にzeroone_supportサービスの安全確認を行う

echo "🧹 EC2クリーンアップ開始..."

# zeroone_supportサービス確認
echo "📋 現在のサービス状況確認:"
tmux list-sessions 2>/dev/null || echo "tmuxセッションなし"

# 古い音声ファイルの確認
echo ""
echo "📊 削除対象ファイルサイズ確認:"
echo "PCMファイル:"
find /home/ec2-user -name "*.pcm" -type f -exec ls -lh {} \; 2>/dev/null | head -10

echo ""
echo "WAVファイル:"
find /home/ec2-user -name "*_optimized.wav" -type f -exec ls -lh {} \; 2>/dev/null | head -10

echo ""
echo "合計削除対象サイズ:"
find /home/ec2-user -name "*.pcm" -o -name "*_optimized.wav" -type f -exec du -ch {} + 2>/dev/null | tail -1

# 削除確認
echo ""
read -p "🔥 上記ファイルを削除しますか？ (y/N): " confirm

if [[ $confirm =~ ^[Yy]$ ]]; then
    echo "🗑️  古い音声ファイル削除中..."
    
    # PCMファイル削除
    deleted_pcm=$(find /home/ec2-user -name "*.pcm" -type f -delete -print 2>/dev/null | wc -l)
    echo "PCMファイル削除: ${deleted_pcm}個"
    
    # WAVファイル削除
    deleted_wav=$(find /home/ec2-user -name "*_optimized.wav" -type f -delete -print 2>/dev/null | wc -l)
    echo "WAVファイル削除: ${deleted_wav}個"
    
    echo "✅ クリーンアップ完了"
else
    echo "❌ クリーンアップをキャンセルしました"
fi

# 重いPython処理の確認
echo ""
echo "🔍 重いPython処理確認:"
ps aux | grep -E "(whisper|ollama|python.*voice)" | grep -v grep || echo "重いPython処理は見つかりませんでした"

# Pythonパッケージ確認
echo ""
echo "📦 インストール済みの重いPythonパッケージ:"
pip list 2>/dev/null | grep -E "(whisper|torch|ollama)" || echo "重いパッケージは見つかりませんでした"

echo ""
echo "🏁 クリーンアップスクリプト完了"
echo "次のステップ: Discord Bot軽量版のデプロイ"