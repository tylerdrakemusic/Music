#!/usr/bin/env bash
set -euo pipefail

root="${1:-.}"
warning_bytes=$((50 * 1024 * 1024))
blocking_bytes=$((100 * 1024 * 1024))
blocking=0

while IFS= read -r -d '' path; do
  size=$(stat -c '%s' "$root/$path")
  if [ "$size" -ge "$blocking_bytes" ]; then
    echo "::error file=$path::tracked file is at or above 100 MiB ($size bytes)"
    blocking=1
  elif [ "$size" -ge "$warning_bytes" ]; then
    echo "::warning file=$path::tracked file is at or above 50 MiB ($size bytes)"
  fi
done < <(git -C "$root" ls-files -z)

if [ "$blocking" -ne 0 ]; then
  exit 1
fi