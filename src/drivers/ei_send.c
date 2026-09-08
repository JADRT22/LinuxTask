#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <poll.h>
#include <libei.h>

static struct ei *ei_ctx = NULL;
static struct ei_device *ei_dev = NULL;
static int device_ready = 0;

static int handle_events(int block) {
    struct pollfd pfd;
    pfd.fd = ei_get_fd(ei_ctx);
    pfd.events = POLLIN | POLLHUP | POLLERR;

    if (block || device_ready) {
        int rc = poll(&pfd, 1, block ? 5000 : 0);
        if (rc < 0) return -1;
        if (rc == 0) return 0;
    }

    ei_dispatch(ei_ctx);

    struct ei_event *ev;
    while ((ev = ei_get_event(ei_ctx)) != NULL) {
        enum ei_event_type t = ei_event_get_type(ev);
        switch (t) {
        case EI_EVENT_CONNECT:
            fprintf(stderr, "ei: connected\n");
            break;
        case EI_EVENT_DISCONNECT:
            fprintf(stderr, "ei: disconnected\n");
            ei_event_unref(ev);
            return -1;
        case EI_EVENT_SEAT_ADDED: {
            struct ei_seat *seat = ei_event_get_seat(ev);
            fprintf(stderr, "ei: seat added: %s\n", ei_seat_get_name(seat));
            ei_seat_bind_capabilities(seat,
                EI_DEVICE_CAP_POINTER,
                EI_DEVICE_CAP_POINTER_ABSOLUTE,
                EI_DEVICE_CAP_BUTTON,
                NULL);
            break;
        }
        case EI_EVENT_DEVICE_ADDED:
            ei_dev = ei_event_get_device(ev);
            fprintf(stderr, "ei: device added\n");
            break;
        case EI_EVENT_DEVICE_RESUMED:
            fprintf(stderr, "ei: device resumed\n");
            ei_device_start_emulating(ei_dev, 1);
            device_ready = 1;
            break;
        case EI_EVENT_DEVICE_PAUSED:
            fprintf(stderr, "ei: device paused\n");
            device_ready = 0;
            break;
        default:
            break;
        }
        ei_event_unref(ev);
    }
    return 0;
}

int main(int argc, char **argv) {
    int socket_fd = -1;

    for (int i = 1; i < argc; i++) {
        if (strncmp(argv[i], "--socketfd=", 11) == 0) {
            socket_fd = atoi(argv[i] + 11);
        }
    }

    if (socket_fd < 0) {
        fprintf(stderr, "Usage: %s --socketfd=<fd>\n", argv[0]);
        return 1;
    }

    ei_ctx = ei_new_sender(NULL);
    if (!ei_ctx) {
        fprintf(stderr, "ei: failed to create context\n");
        return 1;
    }

    if (ei_setup_backend_fd(ei_ctx, socket_fd) < 0) {
        fprintf(stderr, "ei: failed to setup backend fd\n");
        ei_unref(ei_ctx);
        return 1;
    }

    while (!device_ready) {
        if (handle_events(1) < 0) {
            fprintf(stderr, "ei: connection failed\n");
            ei_unref(ei_ctx);
            return 1;
        }
    }

    setbuf(stdout, NULL);
    printf("EI_READY\n");

    char line[512];
    while (fgets(line, sizeof(line), stdin)) {
        if (line[0] == 'q' || line[0] == 0) break;

        double a, b;
        int c, s;

        handle_events(0);

        if (sscanf(line, "m %lf %lf", &a, &b) == 2) {
            if (device_ready && ei_dev) {
                ei_device_pointer_motion(ei_dev, a, b);
                ei_device_frame(ei_dev, ei_now(ei_ctx));
                printf("OK\n");
            }
        } else if (sscanf(line, "a %lf %lf", &a, &b) == 2) {
            if (device_ready && ei_dev) {
                ei_device_pointer_motion_absolute(ei_dev, a, b);
                ei_device_frame(ei_dev, ei_now(ei_ctx));
                printf("OK\n");
            }
        } else if (sscanf(line, "b %d %d", &c, &s) == 2) {
            if (device_ready && ei_dev) {
                ei_device_button_button(ei_dev, (uint32_t)c, s);
                ei_device_frame(ei_dev, ei_now(ei_ctx));
                printf("OK\n");
            }
        } else if (sscanf(line, "s %lf %lf", &a, &b) == 2) {
            if (device_ready && ei_dev) {
                ei_device_scroll_delta(ei_dev, a, b);
                ei_device_frame(ei_dev, ei_now(ei_ctx));
                printf("OK\n");
            }
        } else {
            printf("ERR\n");
        }
    }

    if (ei_dev) {
        ei_device_stop_emulating(ei_dev);
        ei_device_unref(ei_dev);
    }
    ei_disconnect(ei_ctx);
    ei_unref(ei_ctx);
    return 0;
}
