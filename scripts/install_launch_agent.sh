#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PLIST_SRC="$PROJECT_DIR/scripts/com.xhs-agent.plist.template"
PLIST_DST="$HOME/Library/LaunchAgents/com.xhs-agent.plist"

mkdir -p "$HOME/Library/LaunchAgents"
sed "s#__PROJECT_DIR__#$PROJECT_DIR#g" "$PLIST_SRC" > "$PLIST_DST"
launchctl unload "$PLIST_DST" >/dev/null 2>&1 || true
launchctl load "$PLIST_DST"
echo "小红书运营分析 Agent 已加入 macOS 后台任务。"
echo "日志：$PROJECT_DIR/data/xhs-agent.log"
