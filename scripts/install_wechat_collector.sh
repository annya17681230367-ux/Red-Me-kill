#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PLIST_SRC="$PROJECT_DIR/scripts/com.xhs-agent.wechat-collector.plist.template"
PLIST_DST="$HOME/Library/LaunchAgents/com.xhs-agent.wechat-collector.plist"

mkdir -p "$HOME/Library/LaunchAgents"
chmod +x "$PROJECT_DIR/scripts/start-wechat-collector.sh"
sed "s#__PROJECT_DIR__#$PROJECT_DIR#g" "$PLIST_SRC" > "$PLIST_DST"
launchctl unload "$PLIST_DST" >/dev/null 2>&1 || true
launchctl load "$PLIST_DST"
echo "微信链接收集入口已部署为后台任务。"
echo "日志：$PROJECT_DIR/data/wechat-collector.log"
