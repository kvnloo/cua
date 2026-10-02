// seatprobe TITLE SECONDS: an xdg_toplevel that binds EVERY wl_seat and logs, per seat, pointer
// enter/motion/button (surface-local coordinates) and keyboard enter/leave/key (UTF-8 via the seat's
// own keymap) as JSON lines on stdout. It is the oracle for the multi-seat proof: the compositor tells
// each client which seat an event came from, so a seat leak would show up as the wrong seat name.
#define _GNU_SOURCE
#include <errno.h>
#include <poll.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <time.h>
#include <unistd.h>
#include <wayland-client.h>
#include <xkbcommon/xkbcommon.h>
#include "xdg-shell-client-protocol.h"

#define MAX_SEATS 16
struct seat {
    struct wl_seat *seat; char name[64];
    struct wl_pointer *ptr; struct wl_keyboard *kbd;
    struct xkb_context *ctx; struct xkb_keymap *km; struct xkb_state *st;
};
static struct seat seats[MAX_SEATS];
static int nseats;
static struct wl_compositor *comp;
static struct wl_shm *shm;
static struct xdg_wm_base *wm;
static struct wl_surface *surf;
static const char *title;
static int cfg_w, cfg_h, configured;

static double now_s(void) { struct timespec ts; clock_gettime(CLOCK_REALTIME, &ts); return ts.tv_sec + ts.tv_nsec / 1e9; }
#define LOG(seatp, fmt, ...) do { printf("{\"t\":%.3f,\"probe\":\"%s\",\"seat\":\"%s\"," fmt "}\n", now_s(), title, (seatp)->name, ##__VA_ARGS__); fflush(stdout); } while (0)

static void p_enter(void *d, struct wl_pointer *p, uint32_t s, struct wl_surface *sf, wl_fixed_t x, wl_fixed_t y) {
    (void)p; (void)s; (void)sf; LOG((struct seat *)d, "\"ev\":\"pointer_enter\",\"x\":%.1f,\"y\":%.1f", wl_fixed_to_double(x), wl_fixed_to_double(y));
}
static void p_leave(void *d, struct wl_pointer *p, uint32_t s, struct wl_surface *sf) { (void)p; (void)s; (void)sf; LOG((struct seat *)d, "\"ev\":\"pointer_leave\""); }
static void p_motion(void *d, struct wl_pointer *p, uint32_t t, wl_fixed_t x, wl_fixed_t y) {
    (void)p; (void)t; LOG((struct seat *)d, "\"ev\":\"pointer_motion\",\"x\":%.1f,\"y\":%.1f", wl_fixed_to_double(x), wl_fixed_to_double(y));
}
static void p_button(void *d, struct wl_pointer *p, uint32_t s, uint32_t t, uint32_t b, uint32_t st) {
    (void)p; (void)s; (void)t; LOG((struct seat *)d, "\"ev\":\"pointer_button\",\"button\":%u,\"state\":%u", b, st);
}
static void p_axis(void *d, struct wl_pointer *p, uint32_t t, uint32_t a, wl_fixed_t v) { (void)d; (void)p; (void)t; (void)a; (void)v; }
static void p_frame(void *d, struct wl_pointer *p) { (void)d; (void)p; }
static void p_axis_source(void *d, struct wl_pointer *p, uint32_t s) { (void)d; (void)p; (void)s; }
static void p_axis_stop(void *d, struct wl_pointer *p, uint32_t t, uint32_t a) { (void)d; (void)p; (void)t; (void)a; }
static void p_axis_discrete(void *d, struct wl_pointer *p, uint32_t a, int32_t v) { (void)d; (void)p; (void)a; (void)v; }
static const struct wl_pointer_listener ptr_l = { p_enter, p_leave, p_motion, p_button, p_axis, p_frame, p_axis_source, p_axis_stop, p_axis_discrete, NULL, NULL };

static void k_keymap(void *d, struct wl_keyboard *k, uint32_t fmt, int fd, uint32_t size) {
    struct seat *s = d; (void)k;
    char *map = mmap(NULL, size, PROT_READ, MAP_PRIVATE, fd, 0);
    if (map != MAP_FAILED && fmt == WL_KEYBOARD_KEYMAP_FORMAT_XKB_V1) {
        if (!s->ctx) s->ctx = xkb_context_new(XKB_CONTEXT_NO_FLAGS);
        if (s->st) xkb_state_unref(s->st);
        if (s->km) xkb_keymap_unref(s->km);
        s->km = xkb_keymap_new_from_string(s->ctx, map, XKB_KEYMAP_FORMAT_TEXT_V1, XKB_KEYMAP_COMPILE_NO_FLAGS);
        s->st = s->km ? xkb_state_new(s->km) : NULL;
        munmap(map, size);
    }
    close(fd);
}
static void k_enter(void *d, struct wl_keyboard *k, uint32_t s, struct wl_surface *sf, struct wl_array *keys) {
    (void)k; (void)s; (void)sf; (void)keys; LOG((struct seat *)d, "\"ev\":\"keyboard_enter\"");
}
static void k_leave(void *d, struct wl_keyboard *k, uint32_t s, struct wl_surface *sf) { (void)k; (void)s; (void)sf; LOG((struct seat *)d, "\"ev\":\"keyboard_leave\""); }
static void k_key(void *d, struct wl_keyboard *k, uint32_t s, uint32_t t, uint32_t key, uint32_t state) {
    struct seat *se = d; (void)k; (void)s; (void)t;
    char utf8[16] = "";
    if (se->st && state == WL_KEYBOARD_KEY_STATE_PRESSED) xkb_state_key_get_utf8(se->st, key + 8, utf8, sizeof utf8);
    if (utf8[0] == '"' || utf8[0] == '\\' || (unsigned char)utf8[0] < 0x20) utf8[0] = 0;
    LOG(se, "\"ev\":\"key\",\"key\":%u,\"state\":%u,\"utf8\":\"%s\"", key, state, utf8);
}
static void k_mods(void *d, struct wl_keyboard *k, uint32_t s, uint32_t dep, uint32_t lat, uint32_t lock, uint32_t grp) {
    struct seat *se = d; (void)k; (void)s; if (se->st) xkb_state_update_mask(se->st, dep, lat, lock, 0, 0, grp);
}
static void k_repeat(void *d, struct wl_keyboard *k, int32_t r, int32_t dl) { (void)d; (void)k; (void)r; (void)dl; }
static const struct wl_keyboard_listener kbd_l = { k_keymap, k_enter, k_leave, k_key, k_mods, k_repeat };

static void seat_caps(void *d, struct wl_seat *ws, uint32_t caps) {
    struct seat *s = d;
    int hp = caps & WL_SEAT_CAPABILITY_POINTER, hk = caps & WL_SEAT_CAPABILITY_KEYBOARD;
    if (hp && !s->ptr) { s->ptr = wl_seat_get_pointer(ws); wl_pointer_add_listener(s->ptr, &ptr_l, s); }
    if (!hp && s->ptr) { wl_pointer_release(s->ptr); s->ptr = NULL; }
    if (hk && !s->kbd) { s->kbd = wl_seat_get_keyboard(ws); wl_keyboard_add_listener(s->kbd, &kbd_l, s); }
    if (!hk && s->kbd) { wl_keyboard_release(s->kbd); s->kbd = NULL; }
    LOG(s, "\"ev\":\"capabilities\",\"pointer\":%s,\"keyboard\":%s", hp ? "true" : "false", hk ? "true" : "false");
}
static void seat_name(void *d, struct wl_seat *ws, const char *name) { struct seat *s = d; (void)ws; snprintf(s->name, sizeof s->name, "%s", name); }
static const struct wl_seat_listener seat_l = { seat_caps, seat_name };

static void wm_ping(void *d, struct xdg_wm_base *w, uint32_t serial) { (void)d; xdg_wm_base_pong(w, serial); }
static const struct xdg_wm_base_listener wm_l = { wm_ping };

static void reg_global(void *d, struct wl_registry *r, uint32_t id, const char *iface, uint32_t ver) {
    (void)d;
    if (!strcmp(iface, wl_compositor_interface.name)) comp = wl_registry_bind(r, id, &wl_compositor_interface, 4);
    else if (!strcmp(iface, wl_shm_interface.name)) shm = wl_registry_bind(r, id, &wl_shm_interface, 1);
    else if (!strcmp(iface, xdg_wm_base_interface.name)) { wm = wl_registry_bind(r, id, &xdg_wm_base_interface, 1); xdg_wm_base_add_listener(wm, &wm_l, NULL); }
    else if (!strcmp(iface, wl_seat_interface.name) && nseats < MAX_SEATS) {
        struct seat *s = &seats[nseats++];
        snprintf(s->name, sizeof s->name, "?");
        s->seat = wl_registry_bind(r, id, &wl_seat_interface, ver < 5 ? ver : 5);
        wl_seat_add_listener(s->seat, &seat_l, s);
    }
}
static void reg_remove(void *d, struct wl_registry *r, uint32_t id) { (void)d; (void)r; (void)id; }
static const struct wl_registry_listener reg_l = { reg_global, reg_remove };

static void draw(void) {
    int w = cfg_w > 0 ? cfg_w : 400, h = cfg_h > 0 ? cfg_h : 300, stride = w * 4, size = stride * h;
    int fd = memfd_create("seatprobe", MFD_CLOEXEC);
    if (fd < 0 || ftruncate(fd, size) < 0) return;
    uint32_t *px = mmap(NULL, size, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0);
    uint32_t color = (title[0] == 'L') ? 0xff3366aa : 0xffaa6633;
    for (int i = 0; i < w * h; i++) px[i] = color;
    munmap(px, size);
    struct wl_shm_pool *pool = wl_shm_create_pool(shm, fd, size);
    struct wl_buffer *buf = wl_shm_pool_create_buffer(pool, 0, w, h, stride, WL_SHM_FORMAT_ARGB8888);
    wl_shm_pool_destroy(pool); close(fd);
    wl_surface_attach(surf, buf, 0, 0);
    wl_surface_damage(surf, 0, 0, w, h);
    wl_surface_commit(surf);
}
static void xs_configure(void *d, struct xdg_surface *xs, uint32_t serial) { (void)d; xdg_surface_ack_configure(xs, serial); configured = 1; draw(); }
static const struct xdg_surface_listener xs_l = { xs_configure };
static void tl_configure(void *d, struct xdg_toplevel *t, int32_t w, int32_t h, struct wl_array *st) { (void)d; (void)t; (void)st; cfg_w = w; cfg_h = h; }
static void tl_close(void *d, struct xdg_toplevel *t) { (void)d; (void)t; exit(0); }
static const struct xdg_toplevel_listener tl_l = { tl_configure, tl_close, NULL, NULL };

int main(int argc, char **argv) {
    if (argc < 3) { fprintf(stderr, "usage: seatprobe TITLE SECONDS\n"); return 2; }
    title = argv[1];
    double until = now_s() + atof(argv[2]);
    struct wl_display *dpy = wl_display_connect(NULL);
    if (!dpy) { fprintf(stderr, "seatprobe: cannot connect to WAYLAND_DISPLAY\n"); return 3; }
    struct wl_registry *reg = wl_display_get_registry(dpy);
    wl_registry_add_listener(reg, &reg_l, NULL);
    wl_display_roundtrip(dpy); wl_display_roundtrip(dpy);
    if (!comp || !shm || !wm) { fprintf(stderr, "seatprobe: missing compositor/shm/xdg_wm_base\n"); return 4; }
    surf = wl_compositor_create_surface(comp);
    struct xdg_surface *xs = xdg_wm_base_get_xdg_surface(wm, surf);
    xdg_surface_add_listener(xs, &xs_l, NULL);
    struct xdg_toplevel *tl = xdg_surface_get_toplevel(xs);
    xdg_toplevel_add_listener(tl, &tl_l, NULL);
    xdg_toplevel_set_title(tl, title);
    xdg_toplevel_set_app_id(tl, "cua-seatprobe");
    wl_surface_commit(surf);
    printf("{\"t\":%.3f,\"probe\":\"%s\",\"ev\":\"start\",\"seats\":%d}\n", now_s(), title, nseats); fflush(stdout);
    struct pollfd pfd = { wl_display_get_fd(dpy), POLLIN, 0 };
    while (now_s() < until) {
        while (wl_display_prepare_read(dpy) != 0) wl_display_dispatch_pending(dpy);
        wl_display_flush(dpy);
        if (poll(&pfd, 1, 100) > 0) wl_display_read_events(dpy); else wl_display_cancel_read(dpy);
        if (wl_display_dispatch_pending(dpy) < 0) break;
    }
    printf("{\"t\":%.3f,\"probe\":\"%s\",\"ev\":\"exit\"}\n", now_s(), title);
    return 0;
}
