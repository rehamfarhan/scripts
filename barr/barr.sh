#!/usr/bin/env bash

pkill waybar; hyprctl dispatch 'hl.dsp.exec_cmd("/home/directpass/user_scripts/waybar/waybar_toggle.sh --on")'
