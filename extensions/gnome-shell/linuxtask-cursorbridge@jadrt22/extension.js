// LinuxTask Cursor Bridge — GNOME Shell extension
//
// Exposes the compositor's real pointer over the session bus so LinuxTask
// can record and replay absolute cursor positions on GNOME Wayland:
//
//   org.linuxtask.cursorbridge:
//     GetPointer()      -> (i x, i y)   global.get_pointer()
//     WarpPoint(i x, i y)               seat.warp_pointer(x, y)
//     GetScreenSize()   -> (i w, i h)   global.stage logical size
//
// Wayland compositors do not publish the pointer position to clients
// (xdotool only sees XWayland surfaces), but code running INSIDE the
// shell does. Pattern reference: AutoKey's GNOME extension exports
// GetMouseLocation() the same way, and PaperWM uses
// seat.warp_pointer() for absolute pointer motion.
//
// Requires GNOME 45+ (ESM import style).

'use strict';

import Gio from 'gi://Gio';
import Clutter from 'gi://Clutter';

const BUS_NAME = 'org.linuxtask.cursorbridge';
const OBJ_PATH = '/org/linuxtask/CursorBridge';

const IFACE_XML = `
<node>
  <interface name="org.linuxtask.cursorbridge">
    <method name="GetPointer">
      <arg type="i" direction="out" name="x"/>
      <arg type="i" direction="out" name="y"/>
    </method>
    <method name="WarpPoint">
      <arg type="i" direction="in" name="x"/>
      <arg type="i" direction="in" name="y"/>
    </method>
    <method name="GetScreenSize">
      <arg type="i" direction="out" name="w"/>
      <arg type="i" direction="out" name="h"/>
    </method>
  </interface>
</node>`;

export default class LinuxTaskCursorBridge {
    enable() {
        // REPLACE: a stale owner left by a previous shell session must
        // not shadow the freshly-loaded extension.
        this._id = Gio.bus_own_name(Gio.BusType.SESSION, BUS_NAME,
            Gio.BusNameOwnerFlags.REPLACE,
            this._onBusAcquired.bind(this), null, null);
    }

    disable() {
        if (this._impl) {
            this._impl.unexport();
            this._impl = null;
        }
        this._conn = null;
        if (this._id) {
            Gio.bus_unown_name(this._id);
            this._id = 0;
        }
    }

    _onBusAcquired(conn) {
        this._conn = conn;
        this._impl = Gio.DBusExportedObject.wrapJSObject(IFACE_XML, this);
        this._impl.export(conn, OBJ_PATH);
    }

    GetPointer() {
        const [x, y] = global.get_pointer();
        return [x, y];
    }

    WarpPoint(x, y) {
        const seat = Clutter.get_default_backend().get_default_seat();
        seat.warp_pointer(x, y);
    }

    GetScreenSize() {
        // Logical coordinates: the same space GetPointer and WarpPoint use.
        return [Math.floor(global.stage.get_width()),
                Math.floor(global.stage.get_height())];
    }
}
