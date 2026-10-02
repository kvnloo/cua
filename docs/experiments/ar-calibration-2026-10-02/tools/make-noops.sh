#!/usr/bin/env bash
# Creates the 10 no-op calibration branches ar/calib/noop01..10 from the champion (git + sed only).
set -euo pipefail
WT=<lanes>/ar-calib; CH=457bc65d45b2a87ac080b281ea777f8914002c29
P=libs/cua-driver/rust/crates/platform-linux/src
N=$P/atspi/native.rs; FG=$P/input/focus_guard.rs; TG=$P/input/targeted.rs; MD=$P/input/mod.rs
cd "$WT"
mk() { # name file line sed-expr kind description
  local name=$1 file=$2 line=$3 expr=$4 kind=$5 desc=$6
  git switch -q -c "ar/calib/$name" "$CH"
  sed -i "${line}${expr}" "$file"
  [ "$(git diff --numstat | awk '{print $1+$2}')" = "2" ] || { echo "bad diff for $name"; git diff; exit 1; }
  git add -u
  git -c user.name="Kevin Rajan" -c user.email="7121943+kvnloo@users.noreply.github.com" commit -q \
    -m "calib(ar): no-op $name, $desc (known answer: no KEEP)" \
    -m "Calibration candidate for the autoresearch evaluator ($kind no-op): behaviour on every path is unchanged. At most one of the ten no-op diffs may be kept." \
    -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
  echo "$name $(git rev-parse HEAD) $kind"
}
mk noop01 $N 3658 's/Duration::from_millis(50)/Duration::from_micros(50_000)/' const-equivalent "perform_action_ref sleep written in microseconds"
mk noop02 $N 3629 's/"interface proxies unavailable: {e}"/"AT-SPI interface proxies unavailable: {e}"/' string-layout "perform_action_ref error text reworded"
mk noop03 $N 3507 's/"Action unavailable: {e}"/"Action interface unavailable: {e}"/' string-layout "perform_action error text reworded"
mk noop04 $N 3773 's/Duration::from_millis(500)/Duration::from_millis(250 * 2)/' const-equivalent "focus_element_ref deadline written as 250 * 2"
mk noop05 $N 4221 's/"doAction failed: {e}"/"doAction call failed: {e}"/' string-layout "actuate_chain error text reworded"
mk noop06 $N 4324 's/Duration::from_millis(50)/Duration::from_micros(50_000)/' const-equivalent "select_item_in_chain sleep written in microseconds"
mk noop07 $FG 47 's/Duration::from_millis(30)/Duration::from_micros(30_000)/' const-equivalent "SETTLE_POLL written in microseconds"
mk noop08 $FG 716 's/could not restore {:?}/could not restore focus {:?}/' string-layout "restore_if_changed_opts log text reworded"
mk noop09 $TG 425 's/XTest input would/XTest input events would/' string-layout "ensure_point_hits refusal text reworded"
mk noop10 $MD 2260 's/Duration::from_millis(250)/Duration::from_micros(250_000)/' const-equivalent "EFFECT_SETTLE written in microseconds"
git switch -q --detach "$CH"
