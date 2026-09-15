# Experimental: libei / InputCapture PoC

Isolated experiment with [libei](https://gitlab.freedesktop.org/libinput/libei) —
emulating input via the InputCapture/EIS socket exposed by Mutter and KWin.

**Not built, installed or referenced by the application.** Nothing under
`src/`, `tools/` or CI imports or compiles these files; they live here for
reference only. In particular:

- `src/drivers/ei_send` (compiled ELF) previously sat inside `src/drivers/`
  and would be bundled into the AppImage (`build.sh` copies `src/drivers/`
  wholesale). It has been removed from the source tree.
- `ei_send.c` is the more recent prototype: a long-lived process speaking a
  line protocol (`m`/`a`/`b`/`s` commands over stdin) on top of
  `ei_setup_backend_fd()` — designed to receive a socket fd from a Portal
  RemoteDesktop `ConnectToEIS` call.
- `ei_helper.c` is an older one-shot CLI using legacy libei APIs
  (`ei_device_new_pointer`, `ei_device_start`) that no longer exist in
  current libei. Kept for history only; it does not compile against
  modern libei.

If this experiment is ever resumed, the realistic path is:
Portal RemoteDesktop → `ConnectToEIS` → pass the returned fd to a rebuilt
`ei_send` → replace/augment the GNOME and KDE drivers with an EI backend.
