#!/usr/bin/env bash
# collect_gh_reads.sh <branches-file>  >  <out.jsonl>
#
# Read-only gh reads for the kvnloo/cua#74 fresh review (no writes; nothing is posted):
#   - trycua/cua PRs 4316, 4336, 4394 (pinned heads) and 4529, 4531 (merged; recorded): head, state, merge commit
#   - kvnloo/cua PRs 84, 105, 106: head, state
#   - trycua/cua main head
#   - every fork branch the queue cites (one per line in <branches-file>; `make_queue.py --list-branches`), via
#     git/ref/heads/<branch>; a 404 is recorded as sha null (expected for held privacy candidates)
# `make_queue.py --assemble-gh <out.jsonl>` turns the lines into raw/gh-reads.json.
set -euo pipefail
branches="$1"
echo "{\"kind\":\"read_start\",\"utc\":\"$(date -u +%FT%TZ)\"}"
for p in 4316 4336 4394 4529 4531; do
  gh api "repos/trycua/cua/pulls/$p" --jq '{kind:"pr",repo:"trycua/cua",number:.number,state:.state,merged:.merged,head_sha:.head.sha,merge_commit_sha:.merge_commit_sha,merged_at:.merged_at}'
done
for p in 84 105 106; do
  gh api "repos/kvnloo/cua/pulls/$p" --jq '{kind:"pr",repo:"kvnloo/cua",number:.number,state:.state,merged:.merged,head_sha:.head.sha,merge_commit_sha:.merge_commit_sha,merged_at:.merged_at}'
done
gh api "repos/trycua/cua/commits/main" --jq '{kind:"upstream_main",sha:.sha,date:.commit.committer.date}'
while IFS= read -r b; do
  [ -n "$b" ] || continue
  if sha="$(gh api "repos/kvnloo/cua/git/ref/heads/$b" --jq '.object.sha' 2>/dev/null)"; then
    echo "{\"kind\":\"branch\",\"branch\":\"$b\",\"sha\":\"$sha\"}"
  else
    echo "{\"kind\":\"branch\",\"branch\":\"$b\",\"sha\":null}"
  fi
done < "$branches"
echo "{\"kind\":\"read_end\",\"utc\":\"$(date -u +%FT%TZ)\"}"
