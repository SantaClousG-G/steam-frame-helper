#!/bin/bash
# StatusTool wrapper: screenshot copying to ~/Pictures/Screenshots on the Frame.
exec "$(dirname "$0")/screenshots.sh" local "$@"
