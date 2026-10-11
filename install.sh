#!/usr/bin/env bash
# loopmarket's installer: puts `loop` (and `odag`) on your PATH and starts
# its setup. One line:
#
#   curl -fsSL https://raw.githubusercontent.com/petfold/loopmarket/main/install.sh | bash
#
# Needs no sudo. It installs uv (https://docs.astral.sh/uv/) for you if you
# lack it, and through uv a Python of loop's own, so your system's Python is
# left as it is. If a Swarm (Bee) node answers at $BEE_API (default
# http://localhost:1633) it installs the Swarm version; otherwise the local
# one, whose offers stay on this machine until you add a node.
#
#   install.sh --uninstall    removes loop (asking before it deletes your key)
#
# For testing: LOOPMARKET_REF=main installs from GitHub instead of PyPI, and
# LOOP_SETUP=0 skips the setup at the end.
set -euo pipefail

BEE_API="${BEE_API:-http://localhost:1633}"
# loop's own Python. 3.12 while coincurve, the Swarm version's secp256k1
# library, has no release for 3.14 (loopmarket CLAUDE.md, "Upstream to watch").
LOOP_PYTHON="${LOOP_PYTHON:-3.12}"
LOOP_HOME_DIR="${LOOP_HOME:-$HOME/.loopmarket}"

say() { printf 'loop install: %s\n' "$*"; }

# Questions come from the terminal even when this script is piped into bash.
ask() {
    local answer=""
    if [ -r /dev/tty ]; then read -r -p "$1" answer </dev/tty || true; fi
    printf '%s' "$answer"
}

find_uv() {
    for uv in "$(command -v uv 2>/dev/null || true)" "$HOME/.local/bin/uv" "$HOME/.cargo/bin/uv"; do
        if [ -n "$uv" ] && [ -x "$uv" ]; then printf '%s' "$uv"; return 0; fi
    done
    return 1
}

if [ "${1:-}" = "--uninstall" ]; then
    if UV="$(find_uv)"; then "$UV" tool uninstall loopmarket || true; fi
    if [ -d "$LOOP_HOME_DIR" ]; then
        say "your settings, books and loop key are in $LOOP_HOME_DIR"
        say "whoever holds the key in $LOOP_HOME_DIR/config can act as you: keep a copy if you may want it again"
        case "$(ask "Delete $LOOP_HOME_DIR? [y/N] ")" in
            y|Y|yes) rm -rf "$LOOP_HOME_DIR"; say "deleted $LOOP_HOME_DIR" ;;
            *) say "kept $LOOP_HOME_DIR" ;;
        esac
    fi
    say "loop is uninstalled (uv stays; 'uv self uninstall' removes it if you installed it for loop)"
    exit 0
fi

# 1. uv
if ! UV="$(find_uv)"; then
    say "installing uv, the tool that gives loop its own Python..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    UV="$(find_uv)" || { say "uv did not install; see https://docs.astral.sh/uv/"; exit 1; }
fi

# 2. a Swarm node?
if curl -fsS -m 3 "$BEE_API/health" >/dev/null 2>&1; then
    EXTRAS="[swarm,chain,sig]"
    say "a Swarm (Bee) node answers at $BEE_API: installing the Swarm version"
else
    EXTRAS=""
    say "no Swarm (Bee) node at $BEE_API: installing the local version (your offers stay on this machine until you add a node; then run this again)"
fi

# 3. loop, and odag beside it
if [ -n "${LOOPMARKET_REF:-}" ]; then
    SPEC="loopmarket${EXTRAS} @ git+https://github.com/petfold/loopmarket@${LOOPMARKET_REF}"
else
    SPEC="loopmarket${EXTRAS}"
fi
say "installing $SPEC with Python $LOOP_PYTHON..."
"$UV" tool install --force --python "$LOOP_PYTHON" --with-executables-from ontodag "$SPEC"
"$UV" tool update-shell >/dev/null 2>&1 || true
BIN="$("$UV" tool dir --bin)"

# 4. the setup
if [ "${LOOP_SETUP:-1}" != "0" ]; then
    if [ -r /dev/tty ]; then
        "$BIN/loop" setup </dev/tty
    else
        "$BIN/loop" setup --defaults
    fi
fi
say "done. Open a new terminal (so loop is on your PATH), then:  loop give apple 5"
