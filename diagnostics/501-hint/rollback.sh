#!/bin/sh
set -eu
root=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
cd "$root"
git apply --check -R diagnostics/501-hint/change.patch
git apply -R diagnostics/501-hint/change.patch
