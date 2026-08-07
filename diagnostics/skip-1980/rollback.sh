#!/bin/sh
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
cp "$root/backups/3627226191/moods/archive.moods.checkpoint.before-skip-1980.jsonl" \
  "$root/backups/3627226191/moods/archive.moods.checkpoint.jsonl"
test "$(shasum -a 256 "$root/backups/3627226191/moods/archive.moods.checkpoint.jsonl" | awk '{print $1}')" = \
  "a29882fd4333023c3b71550eeed397d21caca82b74b0b2f4c52f112c1fb0d0b7"
