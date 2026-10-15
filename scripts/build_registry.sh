#!/bin/sh
# Rebuild the offline crate registry from vendor/kitchen/Cargo.toml.
#
# Only what the kitchen manifest locks is synced, so this needs the network
# once. The result is what the agents resolve against at /vendor/registry, with
# no network at all -- which is the point: a crate that is not here has to come
# through the window.
set -eu

REPO_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
KITCHEN="$REPO_DIR/vendor/kitchen"
OUT="$REPO_DIR/vendor/registry"
CARGO_HOME_DIR="$REPO_DIR/vendor/.cargo-home"

mkdir -p "$CARGO_HOME_DIR" "$OUT"
printf '[registries.crates-io]\nprotocol = "sparse"\n' > "$CARGO_HOME_DIR/config.toml"

export CARGO_HOME="$CARGO_HOME_DIR"
export PATH="$CARGO_HOME/bin:$HOME/.cargo/bin:$PATH"

echo "== resolving the kitchen lockfile"
# The committed Cargo.lock is the registry's definition. Regenerating it on every
# build moved every crate to whatever crates.io carried that day and left the
# checkout dirty, so it is resolved only when it is absent; REFRESH_LOCK=1 is the
# deliberate way to move it.
if [ ! -f "$KITCHEN/Cargo.lock" ] || [ "${REFRESH_LOCK:-0}" = "1" ]; then
    (cd "$KITCHEN" && cargo generate-lockfile)
else
    echo "   kept the committed Cargo.lock (REFRESH_LOCK=1 to re-resolve)"
fi

echo "== installing the registry tool"
command -v cargo-local-registry >/dev/null 2>&1 || cargo install -q --locked cargo-local-registry
export PATH="$CARGO_HOME/bin:$PATH"

echo "== syncing crates"
rm -rf "$OUT.tmp"
(cd "$KITCHEN" && cargo local-registry --sync Cargo.lock "$OUT.tmp")
rm -rf "$OUT"
mv "$OUT.tmp" "$OUT"
echo "   $(ls "$OUT"/*.crate | wc -l) crates in $OUT"
