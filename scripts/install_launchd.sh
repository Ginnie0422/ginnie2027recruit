#!/bin/zsh
set -euo pipefail

PROJECT_DIR="/Users/zilliz/Documents/Codex/2026-07-29/https-docs-qq-com-sheet-dqunxdhrxcndkehfk"
LABEL="com.jinyu.recruit.daily-update"
SOURCE_PLIST="$PROJECT_DIR/scripts/$LABEL.plist"
TARGET_DIR="$HOME/Library/LaunchAgents"
TARGET_PLIST="$TARGET_DIR/$LABEL.plist"

mkdir -p "$PROJECT_DIR/logs" "$TARGET_DIR"
cp "$SOURCE_PLIST" "$TARGET_PLIST"

launchctl bootout "gui/$(id -u)" "$TARGET_PLIST" >/dev/null 2>&1 || true
launchctl bootstrap "gui/$(id -u)" "$TARGET_PLIST"
launchctl enable "gui/$(id -u)/$LABEL"

echo "Installed $LABEL"
echo "Logs:"
echo "  $PROJECT_DIR/logs/daily_update.out.log"
echo "  $PROJECT_DIR/logs/daily_update.err.log"
