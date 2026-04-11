#!/usr/bin/env bash

# 1. Terminate already running waybar instances
killall -q waybar

# 2. Wait until the processes have been shut down
while pgrep -u $UID -x waybar >/dev/null; do sleep 1; done

# 3. Launch Waybar in the background
waybar &
