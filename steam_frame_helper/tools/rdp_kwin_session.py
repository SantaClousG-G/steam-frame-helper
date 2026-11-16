#!/usr/bin/python3
"""Stand-in for KWin's session interface in RDP (xrdp) sessions.

RDP sessions run Openbox instead of KWin (SteamOS has no kwin_x11, see rdp_wm.sh). Plasma's
logout asks KWin to close its windows first (org.kde.KWin /Session closeWaylandWindows) and,
with nobody answering, gives up: "Log out" does nothing. This answers those calls the way KWin
does when it has nothing to close, so the logout goes on. It runs on the session's own bus and
ends with it.
"""

import gi

gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib  # noqa: E402

INTERFACE = """
<node>
  <interface name="org.kde.KWin.Session">
    <method name="setState"><arg type="u" direction="in"/></method>
    <method name="aboutToSaveSession"><arg type="s" direction="in"/></method>
    <method name="finishSaveSession"><arg type="s" direction="in"/></method>
    <method name="quit"/>
    <method name="closeWaylandWindows"><arg type="b" direction="out"/></method>
  </interface>
</node>
"""

loop = GLib.MainLoop()


def on_call(connection, sender, path, interface, method, params, invocation):
    if method == "closeWaylandWindows":
        invocation.return_value(GLib.Variant("(b)", (True,)))   # no windows of ours to close
    else:
        invocation.return_value(None)


def on_bus(connection, name):
    node = Gio.DBusNodeInfo.new_for_xml(INTERFACE)
    if hasattr(connection, "register_object_with_closures2"):   # PyGObject 3.52+
        connection.register_object_with_closures2("/Session", node.interfaces[0], on_call, None, None)
    else:
        connection.register_object("/Session", node.interfaces[0], on_call, None, None)
    connection.set_exit_on_close(False)
    connection.connect("closed", lambda *args: loop.quit())   # the session ended


def main():
    # replaced by a real KWin if one starts; ends when the name is taken or the bus goes away
    Gio.bus_own_name(Gio.BusType.SESSION, "org.kde.KWin", Gio.BusNameOwnerFlags.ALLOW_REPLACEMENT,
                     on_bus, None, lambda *args: loop.quit())
    loop.run()


if __name__ == "__main__":
    main()
