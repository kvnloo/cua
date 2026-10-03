#!/usr/bin/env bash
# FRESH-07R: recompute git patch-id --stable of the libs/ diff for every Phase 2 replay and its original commits.
# usage: patch_ids.sh <git repo with the cited commits>   (git only; prints one TSV row per replay, exits 1 on any mismatch)
set -euo pipefail
R="$1"
pid() { git -C "$R" diff "$1" "$2" -- libs/ | git -C "$R" patch-id --stable | cut -d' ' -f1; }
bad=0
printf 'replay\torig_range\torig_patch_id\treplay_range\treplay_patch_id\tequal\n'
while read -r name ob oh rb rh; do
  o=$(pid "$ob" "$oh"); r=$(pid "$rb" "$rh"); eq=no; [ -n "$o" ] && [ "$o" = "$r" ] && eq=yes
  [ "$eq" = yes ] || bad=1
  printf '%s\t%s..%s\t%s\t%s..%s\t%s\t%s\n' "$name" "$ob" "$oh" "$o" "$rb" "$rh" "$r" "$eq"
done <<'ROWS'
Rpp 0f1955d2f 45dff8f32 9a2b1d99e cec1a5b92
Rppn 45dff8f32 11a03bf51 cec1a5b92 bbe2bd6e6
Cnpp 0f1955d2f 8a2362770 9a2b1d99e 82e6d5227
G0pp cb685fad7 a761f1f1f 9a2b1d99e c99fcb3cf
GApp a761f1f1f 064d2e4ad c99fcb3cf 6f850b558
GQpp 064d2e4ad 4ac191a7c 6f850b558 8abd5789f
U0mpp cb685fad7 0944feb31 9a2b1d99e 8d6d4189a
G0mpp a761f1f1f 16d21fd56 c99fcb3cf 270ca36b2
ROWS
exit "$bad"
