#!/bin/bash
# Restart the pack after a reboot, sleep, or crash.
#
# Two reboots have now silently killed a running pack and its caffeinate,
# losing hours each time. This is the one command that puts everything back.
#
#   ./run_pack.sh [hours] [dogs]
#
# Check on them with:   python3 dogs.py --scoreboard
# Alert / bone:         ls ../out/dogs/DOGS_ALERT.md ../out/dogs/BONE.md

set -u
HOURS="${1:-10}"
DOGS="${2:-12}"
cd "$(dirname "$0")" || exit 1

# caffeinate -i -s: no idle sleep, no system sleep. Screen may still turn off.
if ! pgrep -x caffeinate > /dev/null; then
  nohup caffeinate -i -s > /dev/null 2>&1 &
  echo "caffeinate started"
else
  echo "caffeinate already running"
fi

if pgrep -f "dogs.py --run" > /dev/null; then
  echo "pack already running ($(pgrep -fc 'dogs.py --run') dogs) — stopping first"
  pkill -f "dogs.py --run"
  sleep 2
fi

# archive the previous round so logs never mix across runs
STAMP=$(date +%Y%m%d-%H%M)
mkdir -p "../out/dogs/round-$STAMP"
mv ../out/dogs/dogs_w*.jsonl ../out/dogs/dogs_w*.log \
   ../out/dogs/dogs_best_w*.json "../out/dogs/round-$STAMP/" 2>/dev/null

python3 -u dogs.py --pack "$HOURS" "$DOGS"
