#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_DIR"
echo "微信小红书链接收集入口已启动。"
echo "使用方式：在微信里复制包含小红书链接的群消息，系统会自动写入 data/manual_links.csv。"
echo "停止方式：按 Ctrl+C。"
exec "$PROJECT_DIR/scripts/xhs-agent.sh" wechat-watch-clipboard --interval 1.5
