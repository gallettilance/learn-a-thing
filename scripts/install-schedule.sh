#!/bin/bash
# Install macOS launchd job for 11pm nightly local runs.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PLIST="$HOME/Library/LaunchAgents/com.research.nightly-learning.plist"
LOG_DIR="$ROOT/logs"
mkdir -p "$LOG_DIR"

API_KEY="${CURSOR_API_KEY:-}"
if [[ -z "$API_KEY" ]]; then
  echo "CURSOR_API_KEY is required for scheduled runs (launchd does not read ~/.zshrc)."
  read -rsp "Enter CURSOR_API_KEY (or press Enter to skip): " API_KEY
  echo
fi

ENV_BLOCK='    <key>PATH</key>
    <string>/usr/local/bin:/usr/bin:/bin:/opt/homebrew/bin</string>'

if [[ -n "$API_KEY" ]]; then
  ENV_BLOCK="$ENV_BLOCK
    <key>CURSOR_API_KEY</key>
    <string>$API_KEY</string>"
fi

cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.research.nightly-learning</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>$ROOT/scripts/nightly-local.sh</string>
  </array>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key>
    <integer>23</integer>
    <key>Minute</key>
    <integer>0</integer>
  </dict>
  <key>StandardOutPath</key>
  <string>$LOG_DIR/nightly.log</string>
  <key>StandardErrorPath</key>
  <string>$LOG_DIR/nightly.err</string>
  <key>EnvironmentVariables</key>
  <dict>
$ENV_BLOCK
  </dict>
</dict>
</plist>
EOF

launchctl unload "$PLIST" 2>/dev/null || true
launchctl load "$PLIST"

echo "Installed: $PLIST"
echo "Runs daily at 11:00 PM local time"
echo "Logs: $LOG_DIR/nightly.log"
if [[ -n "$API_KEY" ]]; then
  echo "CURSOR_API_KEY: stored in plist EnvironmentVariables"
else
  echo "WARNING: No CURSOR_API_KEY in plist — scheduled runs will fail until you add it"
fi
echo "Unload: launchctl unload $PLIST"
