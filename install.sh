#!/usr/bin/env bash
# loopmarket's installer: puts `loop` (and `odag`) on your PATH and starts
# its setup. One line:
#
#   curl -fsSL https://raw.githubusercontent.com/petfold/loopmarket/main/install.sh | bash
#
# Needs no sudo. It installs uv (https://docs.astral.sh/uv/) for you if you
# lack it; loop runs on your system's Python when that can run it, and uv
# fetches one for loop alone only when it cannot (your system's Python is
# left as it is either way). If a Swarm (Bee) node answers at $BEE_API (default
# http://localhost:1633) it installs the Swarm version; otherwise the local
# one, whose offers stay on this machine until you add a node.
#
#   install.sh --uninstall    removes loop (asking before it deletes your key)
#
# For testing: LOOPMARKET_REF=main installs from GitHub instead of PyPI, and
# LOOP_SETUP=0 skips the setup at the end.
set -euo pipefail

BEE_API="${BEE_API:-http://localhost:1633}"
LOOP_HOME_DIR="${LOOP_HOME:-$HOME/.loopmarket}"

say() { printf 'loop install: %s\n' "$*"; }

# Questions come from the terminal even when this script is piped into bash;
# without one (a script, a container) every question takes its default.
have_tty() { ( exec </dev/tty ) 2>/dev/null; }
ask() {
    local answer=""
    if have_tty; then read -r -p "$1" answer </dev/tty || true; fi
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

# 2. a Swarm node? And which Pythons can run loop: any from 3.11; the Swarm
# version below 3.14 while coincurve, its secp256k1 library, has no release
# for 3.14 (loopmarket CLAUDE.md, "Upstream to watch").
if curl -fsS -m 3 "$BEE_API/health" >/dev/null 2>&1; then
    EXTRAS="[swarm,chain,sig]"
    PYTHONS="${LOOP_PYTHON:->=3.11,<3.14}"
    say "a Swarm (Bee) node answers at $BEE_API: installing the Swarm version"
else
    EXTRAS=""
    PYTHONS="${LOOP_PYTHON:->=3.11}"
    say "no Swarm (Bee) node at $BEE_API: installing the local version (your offers stay on this machine until you add a node; then run this again)"
fi

# 3. loop, and odag beside it
if [ -n "${LOOPMARKET_REF:-}" ]; then
    SPEC="loopmarket${EXTRAS} @ git+https://github.com/petfold/loopmarket@${LOOPMARKET_REF}"
else
    SPEC="loopmarket${EXTRAS}"
fi
# A Python already installed that can run loop is used; uv fetches one only
# when none can.
if PY="$("$UV" python find --python-preference system "$PYTHONS" 2>/dev/null)"; then
    say "loop runs on the Python at $PY"
elif [ -n "$EXTRAS" ]; then
    say "no installed Python can run the Swarm version (it needs 3.11 to 3.13 until coincurve supports 3.14): fetching one for loop alone"
else
    say "no installed Python can run loop (it needs 3.11 or later): fetching one for loop alone"
fi
say "installing $SPEC..."
"$UV" tool install --force --python-preference system --python "$PYTHONS" \
    --with-executables-from ontodag "$SPEC"
"$UV" tool update-shell >/dev/null 2>&1 || true
BIN="$("$UV" tool dir --bin)"

# 4. the setup
if [ "${LOOP_SETUP:-1}" != "0" ]; then
    if have_tty; then
        "$BIN/loop" setup </dev/tty
    else
        "$BIN/loop" setup --defaults
    fi
fi
say "done. Open a new terminal (so loop is on your PATH), then:  loop give apple 5"
