#!/usr/bin/env bash
# FRESH-07: prove every file under orig/ is blob-identical to the accepted packet it came from.
#   orig_manifest.sh <repo> <packet-dir> > orig/MANIFEST.tsv   (columns: orig path, source commit, source path, blob, equal)
set -uo pipefail
R="$1"; PK="$2"
declare -A SRC=(
  [r2-10r]="c183b95e35f5af7f2548dec3720b58a65214d9da docs/experiments/r2-10r-recert-2026-10-03"
  [n-04]="9d7d8d7a5fe4888eb7a48342d9fc32b1da5a29b2 docs/experiments/n-04-native-composition-rprime-2026-10-03"
  [own-20p]="64081dded4e0a3ddf144e68ab1ea43579f85f572 docs/experiments/own-20p-guard-port-a11y-2026-10-03"
  [own-20q]="44116546d54047f01d7318eecbc2f36303ec1013 docs/experiments/own-20q-a11y-triggers-dialog-markfree-2026-10-03"
)
bad=0
printf 'orig_path\tsource_commit\tsource_path\tblob\tequal\n'
for k in r2-10r n-04 own-20p own-20q; do
  read -r c p <<< "${SRC[$k]}"
  while IFS= read -r f; do
    rel="${f#"$PK/orig/$k/"}"
    want="$(git -C "$R" rev-parse "$c:$p/$rel" 2>/dev/null || echo missing)"
    have="$(git -C "$R" hash-object "$f")"
    eq=no; [ "$want" = "$have" ] && eq=yes || bad=$((bad + 1))
    printf 'orig/%s/%s\t%s\t%s/%s\t%s\t%s\n' "$k" "$rel" "${c:0:9}" "$p" "$rel" "$have" "$eq"
  done < <(find "$PK/orig/$k" -type f ! -path '*/__pycache__/*' | sort)
done
[ "$bad" -eq 0 ] || { echo "MISMATCH $bad" >&2; exit 1; }
