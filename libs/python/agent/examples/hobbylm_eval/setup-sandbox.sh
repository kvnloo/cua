#!/usr/bin/env bash
# Prepare a contained headless Sway desktop. No host displays/devices/sockets.
set -euo pipefail
CACHE=${HOBBY_CACHE:-/workspace/cache/hobbylm-cua}
NAME=${HOBBY_CONTAINER:-hobbylm-cua-eval-owned}
PORT=${HOBBY_PORT:-13211}
IMAGE=ghcr.io/trycua/linux@sha256:8e4ae644f8bdee13c190b9f8edc04c64bae92feba3ce179f546ec51acceaeb31
HERE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
CACHE=$(realpath -m -- "$CACHE")
case "$CACHE" in /workspace/cache/*) ;; *) echo 'Cache must be under /workspace/cache' >&2; exit 2 ;; esac
[[ $(uname -m) == x86_64 ]] || { echo 'This pinned sandbox image is amd64 only.' >&2; exit 2; }
mkdir -p "$CACHE"
exec 9>"$CACHE/sandbox-setup.lock"
flock -n 9 || { echo 'Another setup owns this cache.' >&2; exit 2; }
for container in $(docker ps -aq); do
    while IFS= read -r source; do
        case "$source" in
            "$CACHE/rootfs"|"$CACHE/rootfs/"*)
                echo "Container $container already owns this writable rootfs." >&2
                exit 2
                ;;
        esac
    done < <(docker inspect --format '{{range .Mounts}}{{println .Source}}{{end}}' "$container")
done
if docker container inspect "$NAME" >/dev/null 2>&1; then
    echo "Container $NAME already exists. Stop/remove only your owned experiment before setup." >&2
    exit 2
fi
mkdir -p "$CACHE/rootfs"
if [[ ! -x "$CACHE/rootfs/usr/bin/sway" ]]; then
    docker pull "$IMAGE"
    source_id=$(docker create --entrypoint /bin/true "$IMAGE")
    trap 'docker rm "$source_id" >/dev/null 2>&1 || true' EXIT
    docker export "$source_id" | tar --no-same-owner -xf - -C "$CACHE/rootfs"
    docker rm "$source_id" >/dev/null
    trap - EXIT
fi
# Bind every package/data directory to NVMe. Docker's own private /proc and /dev
# remain intact, with no physical input devices or host session bus mounted.
mounts=()
for directory in usr opt etc var home tmp root; do
    mounts+=(--mount "type=bind,source=$CACHE/rootfs/$directory,target=/$directory")
done
docker run -d --name "$NAME" --memory=3g --memory-swap=3g --shm-size=512m \
    -p "127.0.0.1:$PORT:3211" "${mounts[@]}" --entrypoint /bin/sleep "$IMAGE" infinity
# Docker's generated resolver is inside this container, not the host's stub.
docker exec "$NAME" chmod 1777 /tmp /var/tmp
docker exec "$NAME" /bin/bash -c 'export DEBIAN_FRONTEND=noninteractive; apt-get update && apt-get install -y --no-install-recommends sway grim mate-calc mousepad thunar orage parole xfce4-notes python3-gi python3-pyatspi pulseaudio-utils dbus-user-session fonts-dejavu-core gsettings-desktop-schemas libglib2.0-bin'
mkdir -p "$CACHE/rootfs/opt/hobbylm"
cp "$HERE/guest-start.sh" "$CACHE/rootfs/opt/hobbylm/guest-start.sh"
chmod 755 "$CACHE/rootfs/opt/hobbylm/guest-start.sh"
docker exec -d "$NAME" /usr/bin/setpriv --reuid=1000 --regid=1000 --clear-groups \
    /usr/bin/env -i PATH=/usr/local/bin:/usr/bin:/bin HOME=/home/cua \
    /opt/hobbylm/guest-start.sh
printf 'Owned container: %s\nLoopback URL: http://127.0.0.1:%s\n' "$NAME" "$PORT"
printf 'Read /tmp/hobbylm-outputs.json, /tmp/hobbylm-desktop.env and /tmp/hobbylm-spacesd.log inside that container before evaluation.\n'
printf 'Cleanup: docker stop %q && docker rm %q\n' "$NAME" "$NAME"
