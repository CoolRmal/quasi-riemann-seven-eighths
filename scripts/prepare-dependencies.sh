#!/usr/bin/env bash
set -euo pipefail

# Preserve the upstream dependencies and their unchanged Lean 4.34.1 compatibility patches.
# Run this before any root Lake command so Lake reads the patched package configurations.
task_root=$(cd "$(dirname "$0")/.." && pwd)

prepare_dependency() {
  local name=$1 url=$2 commit=$3
  local directory="$task_root/.lake/packages/$name"
  local compatibility_patch="$task_root/patches/$name-lean4341.patch"
  test -f "$compatibility_patch"

  if [[ ! -d "$directory/.git" ]]; then
    if [[ -e "$directory" ]]; then
      printf 'Dependency path exists without Git metadata: %s\n' "$directory" >&2
      return 1
    fi
    mkdir -p "$(dirname "$directory")"
    git init "$directory"
    git -C "$directory" remote add origin "$url"
    git -C "$directory" fetch --depth 1 origin "$commit"
    git -C "$directory" checkout --detach "$commit"
  fi

  test "$(git -C "$directory" rev-parse HEAD)" = "$commit"
  test "$(git -C "$directory" remote get-url origin)" = "$url"

  if git -C "$directory" apply --reverse --check "$compatibility_patch" >/dev/null 2>&1; then
    printf '%s compatibility patch already applied; verified.\n' "$name"
  else
    git -C "$directory" apply --check "$compatibility_patch"
    git -C "$directory" apply "$compatibility_patch"
    git -C "$directory" apply --reverse --check "$compatibility_patch"
    printf '%s compatibility patch applied; verified.\n' "$name"
  fi

  printf '%s dependency: %s\nCompatibility patch: %s\n' \
    "$name" "$commit" "$compatibility_patch"
}

prepare_dependency rellich-kondrachov \
  https://github.com/abenenson/rellich-kondrachov.git \
  70f85d4c1bf99c6e7d61e8be4daa6f3664d08d23
prepare_dependency PrimeNumberTheoremAnd \
  https://github.com/AlexKontorovich/PrimeNumberTheoremAnd.git \
  c39a751132c88b6e8080b74c74023fd95b3d8be0
