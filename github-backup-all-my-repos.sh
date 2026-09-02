#!/usr/bin/env bash
set -euo pipefail

if [ $# -ne 1 ]; then
  echo "usage: $(basename "$0") <backup-dir>" >&2
  exit 2
fi

BACKUP_DIR="$1"
LIST_SCRIPT="$(dirname "$(readlink -f "$0")")/github-list-all-my-repos.sh"
ME="$(gh api user --jq .login)"

mkdir -p "$BACKUP_DIR"

failed=()

while read -r url; do
  slug="${url#git@github.com:}"
  slug="${slug%.git}"
  owner="${slug%%/*}"
  name="${slug#*/}"

  if [ "$owner" = "$ME" ]; then
    dir="$name"
  else
    dir="$owner-$name"
  fi
  path="$BACKUP_DIR/$dir"

  if [ -d "$path/.git" ]; then
    echo ":: fetch $dir"
    git -C "$path" fetch --all --prune --tags || failed+=("$url")
  else
    echo ":: clone $dir"
    git clone "$url" "$path" || failed+=("$url")
  fi
done < <("$LIST_SCRIPT")

if [ ${#failed[@]} -gt 0 ]; then
  echo
  echo "failed (${#failed[@]}):"
  printf '  %s\n' "${failed[@]}"
  exit 1
fi
