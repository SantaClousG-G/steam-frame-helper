#!/bin/bash
# StatusTool wrapper: screenshot copying to the PC (Pictures\SteamFrame).
exec "$(dirname "$0")/screenshots.sh" pc "$@"
