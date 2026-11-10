#!/bin/bash
# Point `systemctl --user` / `systemd-run --user` at the real user session.
# Source it in tools that manage user services:  . "$TOOLS/session.sh"
#
# The desktop shown inside the Steam Frame headset is a nested Plasma session with
# XDG_RUNTIME_DIR=/run/user/<uid>/nested_plasma and its own D-Bus; the user's systemd
# manager is not there, so `systemctl --user` fails when a tool is started from it.

_sfh_real_runtime="/run/user/$(id -u)"
if [ "${XDG_RUNTIME_DIR:-}" != "$_sfh_real_runtime" ] && [ -S "$_sfh_real_runtime/systemd/private" ]; then
    export XDG_RUNTIME_DIR="$_sfh_real_runtime"
    if [ -S "$_sfh_real_runtime/bus" ]; then
        export DBUS_SESSION_BUS_ADDRESS="unix:path=$_sfh_real_runtime/bus"
    fi
fi
