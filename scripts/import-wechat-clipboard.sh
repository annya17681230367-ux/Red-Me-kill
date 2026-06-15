#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
mkdir -p "$PROJECT_DIR/data"
pbpaste > "$PROJECT_DIR/data/wechat_messages.txt"
echo "已从剪贴板导入微信群聊天内容：$PROJECT_DIR/data/wechat_messages.txt"
