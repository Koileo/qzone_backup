#!/bin/sh
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
cd "$root"
git apply --check -R diagnostics/mood-filter/change.patch
git apply -R diagnostics/mood-filter/change.patch
