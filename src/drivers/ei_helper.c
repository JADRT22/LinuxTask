#include <libei.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <signal.h>

static struct ei *ei_ctx = NULL;
static struct ei_device *ei_dev = NULL;
static int running = 1;

static void handle_connect(struct ei *ei) {
    fprintf(stderr, "ei: connected\n");
}

static void handle_disconnect(struct ei *ei) {
    fprintf(stderr, "ei: disconnected\n");
    running = 0;
}

static void handle_capabilities(struct ei *ei, enum ei_capability cap, int enabled) {
    fprintf(stderr, "ei: capability %d %s\n", cap, enabled ? "enabled" : "disabled");
}

static int handle_event(int fd) {
    if (!ei_ctx) return -1;
    int ret = ei_dispatch(ei_ctx);
    if (ret < 0) {
        fprintf(stderr, "ei: dispatch error: %d\n", ret);
        return -1;
    }
    return 0;
}

int main(int argc, char *argv[]) {
    if (argc < 2) {
        fprintf(stderr, "Usage: %s <command>\n", argv[0]);
        fprintf(stderr, "  m X Y    - move cursor to absolute position X,Y\n");
        fprintf(stderr, "  d DX DY  - move cursor relative DX,DY\n");
        fprintf(stderr, "  c BUTTON - click button (1=left, 2=right, 3=middle)\n");
        return 1;
    }

    const char *socket_path = getenv("EIS_SOCKET");
    if (!socket_path) {
        socket_path = "/run/user/1000/kwin-xwayland-eis-socket.1067";
    }

    ei_ctx = ei_new_sender(NULL);
    if (!ei_ctx) {
        fprintf(stderr, "ei: failed to create context\n");
        return 1;
    }

    if (ei_connect_socket(ei_ctx, socket_path) < 0) {
        fprintf(stderr, "ei: failed to connect to %s\n", socket_path);
        ei_unref(ei_ctx);
        return 1;
    }

    fprintf(stderr, "ei: connected to %s\n", socket_path);

    // Dispatch until we get capabilities
    int timeout = 50;
    while (timeout-- > 0) {
        int ret = ei_dispatch(ei_ctx);
        if (ret < 0) break;

        enum ei_event_type t = ei_get_event(ei_ctx);
        if (t == EI_EVENT_NONE) {
            ei_dispatch(ei_ctx);
            usleep(10000);
            continue;
        }

        if (t == EI_EVENT_CONNECT) {
            handle_connect(ei_ctx);
        } else if (t == EI_EVENT_DISCONNECT) {
            handle_disconnect(ei_ctx);
            break;
        } else if (t == EI_EVENT_CAPABILITY) {
            struct ei_event *ev = ei_get_event(ei_ctx);
            handle_capabilities(ei_ctx, ei_event_get_capability(ev), ei_event_capability_is_enabled(ev));
        }

        ei_event_unref(ei_get_event(ei_ctx));
    }

    // Create pointer device
    ei_dev = ei_device_new_pointer(ei_ctx, "LinuxTask Pointer");
    if (!ei_dev) {
        fprintf(stderr, "ei: failed to create pointer device\n");
        ei_unref(ei_ctx);
        return 1;
    }
    ei_device_start(ei_dev);
    fprintf(stderr, "ei: pointer device created and started\n");

    // Process commands
    if (strcmp(argv[1], "m") == 0 && argc >= 4) {
        double x = atof(argv[2]);
        double y = atof(argv[3]);
        fprintf(stderr, "ei: move to %f,%f\n", x, y);
        ei_device_pointer_motion_absolute(ei_dev, x, y);
        ei_device_frame(ei_dev);
    } else if (strcmp(argv[1], "d") == 0 && argc >= 4) {
        double dx = atof(argv[2]);
        double dy = atof(argv[3]);
        fprintf(stderr, "ei: move relative %f,%f\n", dx, dy);
        ei_device_pointer_motion(ei_dev, dx, dy);
        ei_device_frame(ei_dev);
    } else if (strcmp(argv[1], "c") == 0 && argc >= 3) {
        int button = atoi(argv[2]);
        fprintf(stderr, "ei: click button %d\n", button);
        ei_device_pointer_button(ei_dev, button, 1);
        ei_device_frame(ei_dev);
        usleep(50000);
        ei_device_pointer_button(ei_dev, button, 0);
        ei_device_frame(ei_dev);
    }

    // Wait for events to be processed
    usleep(100000);

    ei_device_stop(ei_dev);
    ei_device_unref(ei_dev);
    ei_disconnect(ei_ctx);
    ei_unref(ei_ctx);
    return 0;
}

