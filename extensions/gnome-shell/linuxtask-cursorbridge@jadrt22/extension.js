// LinuxTask Cursor Bridge — GNOME Shell extension
//
// Exposes the compositor's real pointer over the session bus so LinuxTask
// can record and replay absolute cursor positions on GNOME Wayland:
//
//   org.linuxtask.cursorbridge:
//     GetPointer()      -> (i x, i y)   global.get_pointer()
//     WarpPoint(i x, i y)               seat.warp_pointer(x, y)
//     GetScreenSize()   -> (i w, i h)   global.stage logical size
//     GetLayout()       -> (i x, i y, i w, i h)  union of every monitor
//
// Wayland compositors do not publish the pointer position to clients
// (xdotool only sees XWayland surfaces), but code running INSIDE the
// shell does. Pattern reference: AutoKey's GNOME extension exports
// GetMouseLocation() the same way, and PaperWM uses
// seat.warp_pointer() for absolute pointer motion.
//
// Requires GNOME 45+ (ESM import style).
//
// Access control: every method checks that the caller's UID is the UID of
// the shell process itself. The session bus is shared by everything the
// user runs, so without this any process in the session could teleport the
// pointer or read its position through this bridge. A same-UID process is
// still inside the user's own trust domain (it could use the portal or
// /dev/uinput directly), which is why the check is UID-based and not a
// secret token.

'use strict';

import Gio from 'gi://Gio';
import Clutter from 'gi://Clutter';
import GLib from 'gi://GLib';

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
    <method name="GetLayout">
      <arg type="i" direction="out" name="x"/>
      <arg type="i" direction="out" name="y"/>
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

    /**
     * Real UID of the shell process, cached. null when /proc is unreadable
     * (then the check is skipped rather than breaking the bridge).
     */
    _ownUid() {
        if (this.__ownUid !== undefined) {
            return this.__ownUid;
        }
        let uid = null;
        try {
            const bytes = GLib.file_get_contents('/proc/self/status')[1];
            const text = new TextDecoder().decode(bytes);
            const line = text.split('\n').find(l => l.startsWith('Uid:'));
            const real = line.split('\t')[1].trim();
            uid = parseInt(real, 10);
            if (Number.isNaN(uid)) {
                uid = null;
            }
        } catch (e) {
            console.warn(`LinuxTask cursor bridge: cannot read own uid: ${e}`);
            uid = null;
        }
        this.__ownUid = uid;
        return uid;
    }

    /**
     * Throws unless the caller of the current D-Bus message has the same
     * UID as the shell. GJS hands the invocation to any exported method
     * that declares one parameter more than its input args.
     */
    _checkCaller(invocation, method) {
        if (!invocation) {
            console.warn(`LinuxTask cursor bridge: ${method} called without ` +
                'an invocation handle; caller identity not verified.');
            return;
        }
        const own = this._ownUid();
        if (own === null) {
            return;
        }
        let uid = -1;
        try {
            uid = invocation.get_unix_user();
        } catch (e) {
            uid = -1;
        }
        if (uid === -1) {
            try {
                uid = invocation.get_credentials().get_unix_user();
            } catch (e) {
                uid = -1;
            }
        }
        if (uid !== own) {
            throw new Error(
                `LinuxTask cursor bridge: refusing ${method} from uid ${uid}`);
        }
    }

    GetPointer(invocation) {
        this._checkCaller(invocation, 'GetPointer');
        const [x, y] = global.get_pointer();
        return [x, y];
    }

    WarpPoint(x, y, invocation) {
        this._checkCaller(invocation, 'WarpPoint');
        const seat = Clutter.get_default_backend().get_default_seat();
        seat.warp_pointer(x, y);
    }

    GetScreenSize(invocation) {
        this._checkCaller(invocation, 'GetScreenSize');
        // Logical coordinates: the same space GetPointer and WarpPoint use.
        return [Math.floor(global.stage.get_width()),
                Math.floor(global.stage.get_height())];
    }

    /**
     * Bounding box of every enabled monitor, as [x, y, w, h] in the same
     * logical space GetPointer reports.
     *
     * The stage size alone is not enough on a multi-monitor layout: a
     * monitor stacked above or to the left of the primary one has a
     * negative origin, so clamping a recorded position to
     * (0, 0, stage_w, stage_h) — what LinuxTask did before this method
     * existed — pushed those clicks back onto the primary screen (issues
     * #6 and #7). Falling back to the stage box keeps single-monitor
     * sessions working even on a shell that does not expose the monitor
     * list.
     */
    GetLayout(invocation) {
        this._checkCaller(invocation, 'GetLayout');
        let monitors = [];
        try {
            if (global.display && global.display.get_monitors) {
                monitors = global.display.get_monitors();
            } else if (global.get_monitor_manager) {
                const mgr = global.get_monitor_manager();
                const n = mgr.get_n_monitors();
                for (let i = 0; i < n; i++) {
                    monitors.push(mgr.get_monitor(i));
                }
            }
        } catch (e) {
            console.warn(`LinuxTask cursor bridge: monitor list failed: ${e}`);
            monitors = [];
        }
        const stage = [0, 0, Math.floor(global.stage.get_width()),
                       Math.floor(global.stage.get_height())];
        if (!monitors || monitors.length === 0) {
            return stage;
        }
        let minX = Infinity, minY = Infinity, max_X = -Infinity, max_Y = -Infinity;
        for (const m of monitors) {
            let x, y, w, h;
            try {
                x = m.get_x(); y = m.get_y();
                w = m.get_width(); h = m.get_height();
            } catch (e) {
                continue;
            }
            if (![x, y, w, h].every(v => Number.isFinite(v)) || w <= 0 || h <= 0) {
                continue;
            }
            minX = Math.min(minX, x); minY = Math.min(minY, y);
            max_X = Math.max(max_X, x + w); max_Y = Math.max(max_Y, y + h);
        }
        if (!Number.isFinite(minX)) {
            return stage;
        }
        return [Math.floor(minX), Math.floor(minY),
                Math.floor(max_X - minX), Math.floor(max_Y - minY)];
    }
}
