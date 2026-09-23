#!/usr/bin/env bash
# Preview the widget in a floating window, outside the running shell.
#   ./preview.sh                          # live data
#   AI_USAGE_MOCK=partial_failure ./preview.sh
set -euo pipefail

SRC=${CAELESTIA_SRC:-/etc/xdg/quickshell/caelestia}
HERE=$(cd "$(dirname "$(readlink -f "$0")")" && pwd)
DIR=$(mktemp -d "${XDG_RUNTIME_DIR:-/tmp}/ai-usage-preview.XXXXXX")
trap 'rm -rf "$DIR"' EXIT

for d in components modules services utils assets; do
    ln -s "$SRC/$d" "$DIR/$d"
done
ln -s "$HERE/shell/aiusage" "$DIR/aiusage"
ln -s "$HERE/shell/preview/shell.qml" "$DIR/shell.qml"

# The fetcher is resolved from ~/.local/bin unless AI_USAGE_BIN is set.
export AI_USAGE_BIN=${AI_USAGE_BIN:-$HERE/bin/ai-usage}
qs -p "$DIR"
