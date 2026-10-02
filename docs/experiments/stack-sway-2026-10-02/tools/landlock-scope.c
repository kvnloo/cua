// landlock-scope <cmd> [args...]
// Exec <cmd> inside a Landlock domain scoped for abstract unix sockets and signals (Landlock ABI >= 6).
// Inside the domain a process can only connect() to abstract unix sockets bound by processes in the
// same domain, and can only signal processes in the same domain. Filesystem and TCP are not
// restricted. Used by cua-sway-session.sh because hostless masks the host's *path* sockets with
// tmpfs but shares the network namespace, so host abstract sockets (e.g. @/tmp/.X11-unix/X0 from
// the host Xwayland) stay connectable without this scope. Refuses (exit 111) if the kernel lacks it.
#define _GNU_SOURCE
#include <linux/landlock.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <sys/prctl.h>
#include <sys/syscall.h>
#include <unistd.h>

int main(int argc, char **argv) {
    if (argc < 2) { fprintf(stderr, "usage: landlock-scope <cmd> [args...]\n"); return 2; }
    long abi = syscall(SYS_landlock_create_ruleset, NULL, 0, LANDLOCK_CREATE_RULESET_VERSION);
    if (abi < 6) { fprintf(stderr, "landlock-scope: landlock ABI %ld < 6 (%s); refusing\n", abi, strerror(errno)); return 111; }
    struct landlock_ruleset_attr attr;
    memset(&attr, 0, sizeof attr);
    attr.scoped = LANDLOCK_SCOPE_ABSTRACT_UNIX_SOCKET | LANDLOCK_SCOPE_SIGNAL;
    int fd = (int)syscall(SYS_landlock_create_ruleset, &attr, sizeof attr, 0);
    if (fd < 0) { perror("landlock-scope: create_ruleset"); return 111; }
    if (prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0)) { perror("landlock-scope: no_new_privs"); return 111; }
    if (syscall(SYS_landlock_restrict_self, fd, 0)) { perror("landlock-scope: restrict_self"); return 111; }
    close(fd);
    setenv("CUA_LANDLOCK_SCOPE", "abstract-unix,signal", 1);
    execvp(argv[1], argv + 1);
    perror("landlock-scope: exec");
    return 127;
}
