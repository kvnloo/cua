// seatctl: create a wlr virtual pointer and/or virtual keyboard bound to ONE named wl_seat and drive it.
//   seatctl --list
//   seatctl --seat NAME [--move X Y] [--extent W H] [--click] [--type TEXT] [--hold MS]
// Steps run in argument order. --hold keeps the virtual devices attached (so get_seats lists them).
// The compositor (sway) attaches a virtual device to the seat passed at creation
// (zwlr_virtual_pointer_manager_v1.create_virtual_pointer(seat) / zwp_virtual_keyboard_manager_v1
// .create_virtual_keyboard(seat)); no seat config "attach" rule is involved.
#define _GNU_SOURCE
#include <linux/input-event-codes.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <time.h>
#include <unistd.h>
#include <wayland-client.h>
#include <xkbcommon/xkbcommon.h>
#include "wlr-virtual-pointer-unstable-v1-client-protocol.h"
#include "virtual-keyboard-unstable-v1-client-protocol.h"

#define MAX_SEATS 16
struct seat { struct wl_seat *seat; char name[64]; };
static struct seat seats[MAX_SEATS];
static int nseats;
static struct zwlr_virtual_pointer_manager_v1 *vptr_mgr;
static struct zwp_virtual_keyboard_manager_v1 *vkbd_mgr;

static void seat_caps(void *d, struct wl_seat *s, uint32_t caps) { (void)d; (void)s; (void)caps; }
static void seat_name(void *d, struct wl_seat *s, const char *name) {
    struct seat *st = d; (void)s; snprintf(st->name, sizeof st->name, "%s", name);
}
static const struct wl_seat_listener seat_listener = { seat_caps, seat_name };

static void reg_global(void *d, struct wl_registry *r, uint32_t id, const char *iface, uint32_t ver) {
    (void)d;
    if (!strcmp(iface, wl_seat_interface.name) && nseats < MAX_SEATS) {
        seats[nseats].seat = wl_registry_bind(r, id, &wl_seat_interface, ver < 5 ? ver : 5);
        wl_seat_add_listener(seats[nseats].seat, &seat_listener, &seats[nseats]);
        nseats++;
    } else if (!strcmp(iface, zwlr_virtual_pointer_manager_v1_interface.name)) {
        vptr_mgr = wl_registry_bind(r, id, &zwlr_virtual_pointer_manager_v1_interface, 1);
    } else if (!strcmp(iface, zwp_virtual_keyboard_manager_v1_interface.name)) {
        vkbd_mgr = wl_registry_bind(r, id, &zwp_virtual_keyboard_manager_v1_interface, 1);
    }
}
static void reg_remove(void *d, struct wl_registry *r, uint32_t id) { (void)d; (void)r; (void)id; }
static const struct wl_registry_listener reg_listener = { reg_global, reg_remove };

static uint32_t now_ms(void) {
    struct timespec ts; clock_gettime(CLOCK_MONOTONIC, &ts);
    return (uint32_t)(ts.tv_sec * 1000 + ts.tv_nsec / 1000000);
}

static struct xkb_keymap *keymap;
// Find an evdev keycode (+ whether shift is needed) producing keysym for c.
static int key_for_char(char c, int *shift) {
    xkb_keysym_t want = xkb_utf32_to_keysym((uint32_t)(unsigned char)c);
    for (xkb_keycode_t kc = xkb_keymap_min_keycode(keymap); kc <= xkb_keymap_max_keycode(keymap); kc++) {
        for (int level = 0; level < 2; level++) {
            const xkb_keysym_t *syms;
            int n = xkb_keymap_key_get_syms_by_level(keymap, kc, 0, level, &syms);
            if (n == 1 && syms[0] == want) { *shift = level; return (int)kc - 8; }
        }
    }
    return -1;
}

int main(int argc, char **argv) {
    struct wl_display *dpy = wl_display_connect(NULL);
    if (!dpy) { fprintf(stderr, "seatctl: cannot connect to WAYLAND_DISPLAY\n"); return 3; }
    struct wl_registry *reg = wl_display_get_registry(dpy);
    wl_registry_add_listener(reg, &reg_listener, NULL);
    wl_display_roundtrip(dpy); wl_display_roundtrip(dpy);

    const char *seat_name_arg = NULL;
    for (int i = 1; i < argc; i++) if (!strcmp(argv[i], "--seat") && i + 1 < argc) seat_name_arg = argv[i + 1];
    if (argc > 1 && !strcmp(argv[1], "--list")) {
        printf("{\"seats\":[");
        for (int i = 0; i < nseats; i++) printf("%s\"%s\"", i ? "," : "", seats[i].name);
        printf("],\"virtual_pointer_manager\":%s,\"virtual_keyboard_manager\":%s}\n",
               vptr_mgr ? "true" : "false", vkbd_mgr ? "true" : "false");
        return 0;
    }
    struct wl_seat *seat = NULL;
    for (int i = 0; i < nseats; i++) if (seat_name_arg && !strcmp(seats[i].name, seat_name_arg)) seat = seats[i].seat;
    if (!seat) { fprintf(stderr, "seatctl: no wl_seat named %s\n", seat_name_arg ? seat_name_arg : "(none)"); return 4; }
    if (!vptr_mgr || !vkbd_mgr) { fprintf(stderr, "seatctl: compositor lacks virtual pointer/keyboard managers\n"); return 5; }

    struct zwlr_virtual_pointer_v1 *ptr = NULL;
    struct zwp_virtual_keyboard_v1 *kbd = NULL;
    uint32_t ext_w = 0, ext_h = 0;
    for (int i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "--seat")) { i++; continue; }
        if (!strcmp(argv[i], "--extent") && i + 2 < argc) { ext_w = atoi(argv[i + 1]); ext_h = atoi(argv[i + 2]); i += 2; continue; }
        if (!strcmp(argv[i], "--move") || !strcmp(argv[i], "--click")) {
            if (!ptr) {
                ptr = zwlr_virtual_pointer_manager_v1_create_virtual_pointer(vptr_mgr, seat);
                // Settle (see --type): clients bind wl_pointer only after the capability event.
                for (int t = 0; t < 250; t += 50) { wl_display_roundtrip(dpy); usleep(50000); }
            }
            if (!strcmp(argv[i], "--move") && i + 2 < argc) {
                uint32_t x = atoi(argv[i + 1]), y = atoi(argv[i + 2]); i += 2;
                if (!ext_w || !ext_h) { fprintf(stderr, "seatctl: --extent W H required before --move\n"); return 6; }
                zwlr_virtual_pointer_v1_motion_absolute(ptr, now_ms(), x, y, ext_w, ext_h);
                zwlr_virtual_pointer_v1_frame(ptr);
                printf("{\"seat\":\"%s\",\"op\":\"move\",\"x\":%u,\"y\":%u}\n", seat_name_arg, x, y);
            } else {
                zwlr_virtual_pointer_v1_button(ptr, now_ms(), BTN_LEFT, WL_POINTER_BUTTON_STATE_PRESSED);
                zwlr_virtual_pointer_v1_frame(ptr);
                wl_display_roundtrip(dpy);
                zwlr_virtual_pointer_v1_button(ptr, now_ms(), BTN_LEFT, WL_POINTER_BUTTON_STATE_RELEASED);
                zwlr_virtual_pointer_v1_frame(ptr);
                printf("{\"seat\":\"%s\",\"op\":\"click\"}\n", seat_name_arg);
            }
            wl_display_roundtrip(dpy);
            continue;
        }
        if (!strcmp(argv[i], "--type") && i + 1 < argc) {
            const char *text = argv[++i];
            if (!kbd) {
                struct xkb_context *ctx = xkb_context_new(XKB_CONTEXT_NO_FLAGS);
                struct xkb_rule_names names = { .layout = "us" };
                keymap = xkb_keymap_new_from_names(ctx, &names, XKB_KEYMAP_COMPILE_NO_FLAGS);
                char *km = xkb_keymap_get_as_string(keymap, XKB_KEYMAP_FORMAT_TEXT_V1);
                size_t len = strlen(km) + 1;
                int fd = memfd_create("seatctl-keymap", MFD_CLOEXEC);
                if (fd < 0 || write(fd, km, len) != (ssize_t)len) { perror("seatctl: keymap"); return 7; }
                kbd = zwp_virtual_keyboard_manager_v1_create_virtual_keyboard(vkbd_mgr, seat);
                zwp_virtual_keyboard_v1_keymap(kbd, WL_KEYBOARD_KEYMAP_FORMAT_XKB_V1, fd, len);
                wl_display_roundtrip(dpy);
                close(fd); free(km);
                // A Shift tap absorbs the first-event loss on fresh headless wlroots seats
                // (same workaround as cua-driver's wayland/virtual_keyboard.rs).
                zwp_virtual_keyboard_v1_key(kbd, now_ms(), KEY_LEFTSHIFT, WL_KEYBOARD_KEY_STATE_PRESSED);
                zwp_virtual_keyboard_v1_key(kbd, now_ms(), KEY_LEFTSHIFT, WL_KEYBOARD_KEY_STATE_RELEASED);
                wl_display_roundtrip(dpy);
                // Settle: the seat just gained the keyboard capability; clients bind wl_keyboard
                // asynchronously and miss keys sent before that bind reaches the compositor.
                for (int t = 0; t < 250; t += 50) { wl_display_roundtrip(dpy); usleep(50000); }
            }
            for (const char *p = text; *p; p++) {
                int shift = 0, code = key_for_char(*p, &shift);
                if (code < 0) { fprintf(stderr, "seatctl: no key for '%c'\n", *p); return 8; }
                if (shift) zwp_virtual_keyboard_v1_key(kbd, now_ms(), KEY_LEFTSHIFT, WL_KEYBOARD_KEY_STATE_PRESSED);
                zwp_virtual_keyboard_v1_key(kbd, now_ms(), code, WL_KEYBOARD_KEY_STATE_PRESSED);
                zwp_virtual_keyboard_v1_key(kbd, now_ms(), code, WL_KEYBOARD_KEY_STATE_RELEASED);
                if (shift) zwp_virtual_keyboard_v1_key(kbd, now_ms(), KEY_LEFTSHIFT, WL_KEYBOARD_KEY_STATE_RELEASED);
                wl_display_roundtrip(dpy);
            }
            printf("{\"seat\":\"%s\",\"op\":\"type\",\"text\":\"%s\"}\n", seat_name_arg, text);
            continue;
        }
        if (!strcmp(argv[i], "--hold") && i + 1 < argc) {
            int ms = atoi(argv[++i]);
            fflush(stdout);
            for (int t = 0; t < ms; t += 50) { wl_display_roundtrip(dpy); usleep(50000); }
            continue;
        }
        fprintf(stderr, "seatctl: bad argument %s\n", argv[i]); return 2;
    }
    fflush(stdout);
    if (ptr) zwlr_virtual_pointer_v1_destroy(ptr);
    if (kbd) zwp_virtual_keyboard_v1_destroy(kbd);
    wl_display_roundtrip(dpy);
    wl_display_disconnect(dpy);
    return 0;
}
