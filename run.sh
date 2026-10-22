#!/usr/bin/env bash
#
# Start (or stop) the full Mentora stack for local development.
#
#   backend  (FastAPI/uvicorn, auto-reload)  ->  http://127.0.0.1:8001
#   frontend (Vite dev server, HMR)          ->  http://localhost:8000
#
# The Vite dev server proxies /courses, /artifacts and /health to the backend,
# so the browser only ever talks to :8000 (no CORS).
#
# Usage:
#   ./run.sh [-i|--install] [-p|--port N] [--backend-port N] [--host H]
#   ./run.sh --omnivoice [--omnivoice-port N] [...]
#   ./run.sh [-k|--kill]
#
# Starting also stops any leftover instance of this checkout first, so a crashed
# or orphaned server can never block the next start with "port already in use".
# `--kill` is the bigger hammer: it stops every backend/frontend process of this
# checkout *and* whatever holds the configured ports.
#
# `--omnivoice` is the opt-in spoken-narration prototype: it creates a dedicated
# Python environment under tools/omnivoice_server/.venv (installing OmniVoice on
# first use), starts the local sidecar, and points the backend at it. It is not
# the default provider (DEC-TECH-007 is OPEN).
#
# Ctrl+C stops every server, including OmniVoice.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"

BACKEND_HOST="${BACKEND_HOST:-127.0.0.1}"
BACKEND_PORT="${BACKEND_PORT:-8001}"
FRONTEND_HOST="${FRONTEND_HOST:-}"
FRONTEND_PORT="${FRONTEND_PORT:-8000}"
OMNIVOICE_HOST="${OMNIVOICE_HOST:-127.0.0.1}"
OMNIVOICE_PORT="${OMNIVOICE_PORT:-8765}"
OMNIVOICE_START_TIMEOUT="${OMNIVOICE_START_TIMEOUT:-900}"
OMNIVOICE_VENV="${OMNIVOICE_VENV:-$ROOT_DIR/tools/omnivoice_server/.venv}"
OMNIVOICE_PIP_SPEC="${OMNIVOICE_PIP_SPEC:-omnivoice}"
OMNIVOICE_RUNTIME_PYTHON=""
OMNIVOICE_PID=""
RUN_OMNIVOICE=0
INSTALL=0
KILL=0

log()  { printf '\033[1;34m[run]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[run]\033[0m %s\n' "$*" >&2; }
fail() { printf '\033[1;31m[run]\033[0m %s\n' "$*" >&2; exit 1; }

usage() {
  cat <<'EOF'
Start or stop the full Mentora stack for local development.

  backend  (FastAPI/uvicorn, auto-reload)  ->  http://127.0.0.1:8001
  frontend (Vite dev server, HMR)          ->  http://localhost:8000

The Vite dev server proxies /courses, /artifacts and /health to the backend,
so the browser only ever talks to :8000 (no CORS).

Usage:
  ./run.sh [-i|--install] [-p|--port N] [--backend-port N] [--host H]
  ./run.sh --omnivoice [--omnivoice-port N] [...]
  ./run.sh [-k|--kill]

Options:
  -i, --install         install backend (pip) and frontend (npm) deps first
      --omnivoice       run the local OmniVoice sidecar and configure the backend
                        to speak slide narration with it. Creates
                        tools/omnivoice_server/.venv and installs OmniVoice if it
                        is missing. This is an opt-in prototype: DEC-TECH-007 is
                        OPEN and the default voice remains the deterministic mock.
      --omnivoice-port N
                        OmniVoice sidecar port (default 8765)
  -k, --kill            stop every backend/frontend/OmniVoice instance of this
                        checkout, plus whatever holds --backend-port / --port
                        (and --omnivoice-port when --omnivoice is given),
                        then exit (does not start anything)
      --backend-port N  backend port (default 8001)
  -p, --port N          frontend port, the one you open (default 8000;
                        --frontend-port N is the same option)
      --host H          frontend bind host, e.g. 0.0.0.0 (default: localhost)

Env:
  MENTORA_ALLOWED_HOSTS   comma-separated hostnames Vite may serve
                          (default: dev.nguynx.uk)

  OmniVoice (only with --omnivoice):
  OMNIVOICE_PYTHON        existing Python that already has omnivoice; skips the
                          managed virtualenv and never installs into it
  OMNIVOICE_VENV          managed venv path
                          (default: tools/omnivoice_server/.venv)
  OMNIVOICE_PYTHON_BIN    interpreter used to create the managed venv
                          (default: python3.12, python3.11, python3.10, python3)
  OMNIVOICE_PIP_SPEC      pip package spec (default: omnivoice)
  OMNIVOICE_PIP_EXTRA_ARGS
                          extra pip arguments, e.g. an index mirror
  OMNIVOICE_SKIP_INSTALL=1
                          never install OmniVoice; fail if it is missing
  OMNIVOICE_START_TIMEOUT seconds to wait for model load/download (default 900)
  HF_ENDPOINT             Hugging Face mirror, e.g. https://hf-mirror.com
  OMNIVOICE_*             voice and generation options are passed through to the
                          sidecar; see tools/omnivoice_server/README.md

Starting first stops any leftover instance of this checkout.
Ctrl+C stops every server.
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    -i|--install)      INSTALL=1 ;;
    -k|--kill)         KILL=1 ;;
    --omnivoice)       RUN_OMNIVOICE=1 ;;
    --omnivoice-port)  OMNIVOICE_PORT="${2:?missing value}"; shift ;;
    --backend-port)    BACKEND_PORT="${2:?missing value}"; shift ;;
    -p|--port|--frontend-port) FRONTEND_PORT="${2:?missing value}"; shift ;;
    --host)            FRONTEND_HOST="${2:?missing value}"; shift ;;
    -h|--help)         usage; exit 0 ;;
    *)                 usage >&2; fail "unknown option: $1" ;;
  esac
  shift
done

# Checked before anything is stopped, so a bad flag never touches a running stack.
if [ "$FRONTEND_PORT" = "$BACKEND_PORT" ]; then
  fail "frontend and backend cannot share port $FRONTEND_PORT. Pick another -p/--port (or move the backend with --backend-port)."
fi
if [ "$RUN_OMNIVOICE" -eq 1 ]; then
  if [ "$OMNIVOICE_PORT" = "$FRONTEND_PORT" ] || [ "$OMNIVOICE_PORT" = "$BACKEND_PORT" ]; then
    fail "OmniVoice cannot share port $OMNIVOICE_PORT with the app. Pick another --omnivoice-port."
  fi
fi

# --- process discovery -----------------------------------------------------
# Command-line matching is the precise test. It is not sufficient on its own:
# uvicorn --reload spawns its worker (and a multiprocessing resource tracker)
# with a command line that no longer mentions uvicorn, so those two forms are
# accepted only when the process also runs with backend/ as its working
# directory. Deliberately *not* used as a signal: the executable path, because
# .venv/bin/python resolves to the base interpreter (e.g. a pyenv python) and
# would match every process started from the venv — including a pytest run.
pid_cmdline() {
  if [ -r "/proc/$1/cmdline" ]; then
    tr '\0' ' ' < "/proc/$1/cmdline" 2>/dev/null || true
  else
    ps -o args= -p "$1" 2>/dev/null || true
  fi
}

pid_cwd() {
  if [ -e "/proc/$1/cwd" ]; then
    readlink -f "/proc/$1/cwd" 2>/dev/null || true
  elif command -v lsof >/dev/null 2>&1; then
    # macOS: no /proc, so ask lsof for the cwd descriptor.
    lsof -a -p "$1" -d cwd -Fn 2>/dev/null | sed -n 's/^n//p' | head -n 1
  fi
}

pids_on_port() {
  local port="$1"
  if command -v ss >/dev/null 2>&1; then
    ss -ltnpH "sport = :$port" 2>/dev/null | grep -oE 'pid=[0-9]+' | cut -d= -f2 | sort -u
  elif command -v lsof >/dev/null 2>&1; then
    lsof -t -iTCP:"$port" -sTCP:LISTEN 2>/dev/null | sort -u
  fi
}

# Print the given PIDs plus every descendant of them (de-duplicated).
with_descendants() {
  local queue=() seen=" " pid child index=0

  for pid in "$@"; do
    if [ -n "$pid" ] && [[ "$seen" != *" $pid "* ]]; then
      seen="$seen$pid "
      queue+=("$pid")
    fi
  done
  while [ "$index" -lt "${#queue[@]}" ]; do
    pid="${queue[$index]}"
    index=$((index + 1))
    while read -r child; do
      if [ -n "$child" ] && [[ "$seen" != *" $child "* ]]; then
        seen="$seen$child "
        queue+=("$child")
      fi
    done < <(ps -eo pid=,ppid= 2>/dev/null | awk -v parent="$pid" '$2 == parent { print $1 }')
  done
  if [ "${#queue[@]}" -gt 0 ]; then printf '%s\n' "${queue[@]}"; fi
}

matches_our_command_line() {
  local args="$1" pid="${2:-}" cwd
  case "$args" in
    *app.api.app:create_app*)
      # Another checkout can run the same app module. Prefer the working
      # directory when it is readable; an unreadable one still matches.
      cwd=""
      [ -n "$pid" ] && cwd="$(pid_cwd "$pid")"
      [ -z "$cwd" ] || [ "$cwd" = "$BACKEND_DIR" ] && return 0
      return 1 ;;
    *"$ROOT_DIR/tools/omnivoice_server/server.py"*)    return 0 ;;
    *tools/omnivoice_server/server.py*)
      # A sidecar started from this checkout with a relative path. Require its
      # cwd so another checkout's `python tools/...` is not mistaken for ours.
      [ -n "$pid" ] && [ "$(pid_cwd "$pid")" = "$ROOT_DIR" ] && return 0 ;;
    *"$FRONTEND_DIR/node_modules/.bin/vite"*)          return 0 ;;
    *"$FRONTEND_DIR/node_modules/vite/"*)              return 0 ;;
    *"$FRONTEND_DIR/node_modules/@esbuild"*)           return 0 ;;
  esac
  return 1
}

# Print the PIDs to stop.
#   scope=repo   processes of this checkout only (leftovers, orphans)
#   scope=ports  the above, plus anything holding our configured ports
collect_targets() {
  local scope="${1:-repo}"
  local -a seeds=()
  local -a spawned=()
  local pid args holder port

  while read -r pid args; do
    if [ -z "$pid" ]; then
      continue
    fi
    if matches_our_command_line "$args" "$pid"; then
      seeds+=("$pid")
    else
      case "$args" in
        *--multiprocessing-fork*|*multiprocessing.resource_tracker*)
          spawned+=("$pid") ;;
      esac
    fi
  done < <(ps -eo pid=,args= 2>/dev/null)

  # Multiprocessing children count as ours only when they run from backend/.
  for pid in ${spawned[@]+"${spawned[@]}"}; do
    if [ "$(pid_cwd "$pid")" = "$BACKEND_DIR" ]; then
      seeds+=("$pid")
    fi
  done

  if [ "$scope" = "ports" ]; then
    # --kill: the caller explicitly asked for the ports as well, so whatever
    # squats on them goes too (it is printed before it is killed). The OmniVoice
    # port is included only when this run asked for the sidecar; `--kill` alone
    # still stops our own sidecar through the command-line match above.
    local -a kill_ports=("$BACKEND_PORT" "$FRONTEND_PORT")
    if [ "$RUN_OMNIVOICE" -eq 1 ]; then
      kill_ports+=("$OMNIVOICE_PORT")
    fi
    for port in "${kill_ports[@]}"; do
      for holder in $(pids_on_port "$port"); do
        if [ -n "$holder" ]; then
          seeds+=("$holder")
        fi
      done
    done
  fi

  if [ "${#seeds[@]}" -gt 0 ]; then
    with_descendants "${seeds[@]}"
  fi
}

describe_pid() {
  local args
  args="$(pid_cmdline "$1")"
  printf '      pid %-8s %s\n' "$1" "${args:-<gone>}"
}

terminate_pids() {
  local -a targets=("$@")
  local pid attempt
  local alive=1

  log "stopping ${#targets[@]} process(es):"
  for pid in "${targets[@]}"; do describe_pid "$pid"; done

  for pid in "${targets[@]}"; do kill -TERM "$pid" 2>/dev/null || true; done

  for attempt in 1 2 3 4 5 6; do
    sleep 0.5
    alive=0
    for pid in "${targets[@]}"; do
      if kill -0 "$pid" 2>/dev/null; then alive=1; fi
    done
    if [ "$alive" -eq 0 ]; then break; fi
  done

  if [ "$alive" -ne 0 ]; then
    warn "some processes ignored SIGTERM; sending SIGKILL."
    for pid in "${targets[@]}"; do kill -KILL "$pid" 2>/dev/null || true; done
  fi
}

# Stop the stack. Returns 1 when there was nothing to stop.
stop_stack() {
  local -a targets=()
  local pid
  while read -r pid; do
    if [ -n "$pid" ]; then targets+=("$pid"); fi
  done < <(collect_targets "${1:-repo}")

  if [ "${#targets[@]}" -eq 0 ]; then
    return 1
  fi
  terminate_pids "${targets[@]}"
  return 0
}

# --- kill mode -------------------------------------------------------------
# Handled before the dependency checks so it works even with a broken venv.
if [ "$KILL" -eq 1 ]; then
  if stop_stack ports; then
    log "all Mentora backend/frontend/OmniVoice instances stopped."
  else
    log "nothing to stop (no Mentora backend/frontend/OmniVoice instance is running)."
  fi
  exit 0
fi

# --- prerequisites ---------------------------------------------------------
command -v python3 >/dev/null 2>&1 || fail "python3 not found on PATH."

if [ "$INSTALL" -eq 1 ]; then
  log "installing backend dependencies (python venv)..."
  [ -d "$BACKEND_DIR/.venv" ] || python3 -m venv "$BACKEND_DIR/.venv"
  "$BACKEND_DIR/.venv/bin/pip" install -q --upgrade pip
  "$BACKEND_DIR/.venv/bin/pip" install -q -e "$BACKEND_DIR[dev]"
  log "installing frontend dependencies (npm)..."
  command -v npm >/dev/null 2>&1 || fail "npm not found on PATH."
  ( cd "$FRONTEND_DIR" && npm install )
fi

# --- OmniVoice setup -------------------------------------------------------
# OmniVoice is a PyTorch application, so it gets its own environment. Installing
# torch into the backend venv would make every API install heavy and could make
# the backend depend on the GPU stack. `OMNIVOICE_PYTHON` is the escape hatch for
# a developer who already has a working OmniVoice environment; the managed venv
# is created and installed into on first use.
omnivoice_module_ready() {
  local python="$1"
  env -u PYTHONPATH "$python" -c 'from omnivoice import OmniVoice' >/dev/null 2>&1
}

pick_omnivoice_python() {
  local candidate
  if [ -n "${OMNIVOICE_PYTHON_BIN:-}" ]; then
    command -v "$OMNIVOICE_PYTHON_BIN" >/dev/null 2>&1 ||
      fail "OMNIVOICE_PYTHON_BIN=$OMNIVOICE_PYTHON_BIN was not found on PATH."
    printf '%s\n' "$OMNIVOICE_PYTHON_BIN"
    return
  fi
  # PyTorch regularly lags the newest CPython. Prefer a release OmniVoice's
  # dependency stack is known to support before falling back to python3.
  for candidate in python3.12 python3.11 python3.10; do
    if command -v "$candidate" >/dev/null 2>&1; then
      printf '%s\n' "$candidate"
      return
    fi
  done
  printf '%s\n' python3
}

ensure_omnivoice() {
  local python
  if [ -n "${OMNIVOICE_PYTHON:-}" ]; then
    if command -v "$OMNIVOICE_PYTHON" >/dev/null 2>&1; then
      OMNIVOICE_PYTHON="$(command -v "$OMNIVOICE_PYTHON")"
    fi
    [ -x "$OMNIVOICE_PYTHON" ] ||
      fail "OMNIVOICE_PYTHON=$OMNIVOICE_PYTHON is not an executable Python."
    omnivoice_module_ready "$OMNIVOICE_PYTHON" ||
      fail "OMNIVOICE_PYTHON=$OMNIVOICE_PYTHON cannot import omnivoice. Install it in that environment (pip install omnivoice), or unset OMNIVOICE_PYTHON to let ./run.sh create $OMNIVOICE_VENV."
    OMNIVOICE_RUNTIME_PYTHON="$OMNIVOICE_PYTHON"
    log "using existing OmniVoice environment: $OMNIVOICE_PYTHON"
    return
  fi

  if [ ! -x "$OMNIVOICE_VENV/bin/python" ]; then
    python="$(pick_omnivoice_python)"
    log "creating OmniVoice environment with $python (first run only)..."
    env -u PYTHONPATH "$python" -m venv "$OMNIVOICE_VENV" ||
      fail "could not create the OmniVoice virtualenv at $OMNIVOICE_VENV."
  fi
  python="$OMNIVOICE_VENV/bin/python"

  if omnivoice_module_ready "$python"; then
    OMNIVOICE_RUNTIME_PYTHON="$python"
    return
  fi

  if [ "${OMNIVOICE_SKIP_INSTALL:-0}" = "1" ]; then
    fail "OmniVoice is not installed in $OMNIVOICE_VENV and OMNIVOICE_SKIP_INSTALL=1."
  fi

  log "installing OmniVoice into $OMNIVOICE_VENV ..."
  log "the first install downloads PyTorch and its dependencies; this can take several minutes."
  env -u PYTHONPATH "$python" -m pip install --upgrade pip >/dev/null 2>&1 || true

  # Linux without an NVIDIA GPU: the default PyPI torch wheel pulls the CUDA
  # runtime (several GB). The CPU index gives the same API in a much smaller
  # install. macOS wheels already carry MPS support, so nothing special there.
  if [ "$(uname -s)" = "Linux" ] && ! command -v nvidia-smi >/dev/null 2>&1; then
    if ! env -u PYTHONPATH "$python" -c 'import torch, torchaudio' >/dev/null 2>&1; then
      log "no NVIDIA GPU detected; installing CPU-only PyTorch first..."
      if ! env -u PYTHONPATH "$python" -m pip install torch torchaudio \
        --index-url https://download.pytorch.org/whl/cpu; then
        warn "CPU PyTorch install failed; letting OmniVoice resolve PyTorch instead."
      fi
    fi
  fi

  # OMNIVOICE_PIP_EXTRA_ARGS is intentionally word-split so a mirror/index URL
  # can be supplied, e.g. OMNIVOICE_PIP_EXTRA_ARGS='--extra-index-url ...'.
  # shellcheck disable=SC2086
  env -u PYTHONPATH "$python" -m pip install ${OMNIVOICE_PIP_EXTRA_ARGS:-} "$OMNIVOICE_PIP_SPEC" ||
    fail "OmniVoice installation failed. If the base Python is too new for PyTorch, set OMNIVOICE_PYTHON_BIN=python3.12 (and remove $OMNIVOICE_VENV to recreate it), or point OMNIVOICE_PYTHON at an environment that already has omnivoice."

  omnivoice_module_ready "$python" ||
    fail "OmniVoice installed but cannot be imported in $OMNIVOICE_VENV."
  OMNIVOICE_RUNTIME_PYTHON="$python"
  log "OmniVoice installed."
}

UVICORN_BIN="$BACKEND_DIR/.venv/bin/uvicorn"
VITE_BIN="$FRONTEND_DIR/node_modules/.bin/vite"

[ -x "$UVICORN_BIN" ] || fail "backend venv not ready. Run: ./run.sh --install"
[ -x "$VITE_BIN" ]    || fail "frontend deps not installed. Run: ./run.sh --install"

if [ "$RUN_OMNIVOICE" -eq 1 ]; then
  case "$OMNIVOICE_START_TIMEOUT" in
    ''|*[!0-9]*) fail "OMNIVOICE_START_TIMEOUT must be a number of seconds." ;;
  esac
  ensure_omnivoice
fi

# --- stop leftovers --------------------------------------------------------
if stop_stack repo; then
  log "leftover instance stopped; starting fresh."
fi

# --- port checks -----------------------------------------------------------
# Anything still listening is not ours (our own leftovers were just stopped).
port_listening() {
  local port="$1"
  if command -v ss >/dev/null 2>&1; then
    ss -ltnH "sport = :$port" 2>/dev/null | grep -q .
  elif command -v lsof >/dev/null 2>&1; then
    lsof -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1
  else
    return 1
  fi
}

port_conflict() {
  local port="$1" label="$2"
  if port_listening "$port"; then
    warn "port $port ($label) is held by a process that is not part of this checkout:"
    local holder
    for holder in $(pids_on_port "$port"); do describe_pid "$holder"; done
    fail "free port $port, or re-run with --kill / change the port with --$label-port (frontend: -p/--port)."
  fi
}

port_conflict "$BACKEND_PORT" backend
port_conflict "$FRONTEND_PORT" frontend
if [ "$RUN_OMNIVOICE" -eq 1 ]; then
  port_conflict "$OMNIVOICE_PORT" omnivoice
fi

# Vite reads this to proxy API calls to the backend.
export MENTORA_BACKEND_ORIGIN="${MENTORA_BACKEND_ORIGIN:-http://127.0.0.1:$BACKEND_PORT}"

# A sidecar bound to 0.0.0.0 is still reached over loopback by this machine.
OMNIVOICE_PROBE_HOST="$OMNIVOICE_HOST"
[ "$OMNIVOICE_PROBE_HOST" = "0.0.0.0" ] && OMNIVOICE_PROBE_HOST="127.0.0.1"

if [ "$RUN_OMNIVOICE" -eq 1 ]; then
  export MENTORA_TTS_PROVIDER=omnivoice
  export MENTORA_OMNIVOICE_URL="http://$OMNIVOICE_PROBE_HOST:$OMNIVOICE_PORT"
fi

# --- lifecycle -------------------------------------------------------------
# Each server runs in its own process group (setsid) so that cleanup can take
# down the whole tree. uvicorn --reload forks a worker and vite forks esbuild:
# if a parent dies unexpectedly those children are reparented to init, survive
# `pkill -P <parent>`, and keep the port busy — which makes the next ./run.sh
# fail with "port already in use".
pids=()
roles=()

start_server() {
  local role="$1" dir="$2"
  shift 2
  # `setsid` keeps the pid (it is not a group leader), so $! is also the PGID.
  # macOS has no setsid(1); python3's os.setsid() + exec does the same thing.
  if command -v setsid >/dev/null 2>&1; then
    ( cd "$dir" && exec setsid "$@" ) &
  else
    ( cd "$dir" && exec python3 -c 'import os, sys; os.setsid(); os.execvp(sys.argv[1], sys.argv[1:])' "$@" ) &
  fi
  pids+=("$!")
  roles+=("$role")
}

cleanup() {
  trap - INT TERM EXIT
  printf '\n'
  log "stopping servers..."
  local pid
  for pid in ${pids[@]+"${pids[@]}"}; do
    [ -n "$pid" ] || continue
    # Negative pid = the whole process group (the server plus its children).
    kill -TERM -- "-$pid" 2>/dev/null || kill -TERM "$pid" 2>/dev/null || true
  done
  sleep 0.5
  for pid in ${pids[@]+"${pids[@]}"}; do
    [ -n "$pid" ] || continue
    kill -KILL -- "-$pid" 2>/dev/null || kill -KILL "$pid" 2>/dev/null || true
  done
  wait 2>/dev/null || true
}

# A signal must never resume the script: `wait -n -p exited_pid` *unsets* its
# target variable when the wait is interrupted, so falling back into the
# reporting code below would die under `set -u` with a confusing
# "exited_pid: unbound variable" instead of a clean shutdown.
on_interrupt() {
  cleanup
  exit 130
}
trap on_interrupt INT TERM
trap cleanup EXIT

# --- OmniVoice sidecar -----------------------------------------------------
# The sidecar owns PyTorch and the model. Wait for /health before starting the
# backend: otherwise the first few narration requests would be answered by the
# text fallback while the model is still downloading, which looks like a broken
# voice rather than a warm-up.
omnivoice_health() {
  local url="http://$OMNIVOICE_PROBE_HOST:$OMNIVOICE_PORT/health"
  if command -v curl >/dev/null 2>&1; then
    curl -fsS --max-time 2 "$url" >/dev/null 2>&1
  else
    env -u PYTHONPATH "$OMNIVOICE_RUNTIME_PYTHON" -c \
      'import sys, urllib.request; urllib.request.urlopen(sys.argv[1], timeout=2)' \
      "$url" >/dev/null 2>&1
  fi
}

wait_for_omnivoice() {
  local waited=0 next_note=10
  while [ "$waited" -lt "$OMNIVOICE_START_TIMEOUT" ]; do
    if omnivoice_health; then
      log "OmniVoice ready at http://$OMNIVOICE_PROBE_HOST:$OMNIVOICE_PORT"
      return 0
    fi
    if ! kill -0 "$OMNIVOICE_PID" 2>/dev/null; then
      fail "the OmniVoice sidecar exited while loading. Read the messages above; if this is the first run, check that PyTorch installed for $OMNIVOICE_RUNTIME_PYTHON."
    fi
    if [ "$waited" -ge "$next_note" ]; then
      warn "waiting for OmniVoice (${waited}s); the first run downloads the model from Hugging Face."
      next_note=$((next_note + 30))
    fi
    sleep 2
    waited=$((waited + 2))
  done
  fail "OmniVoice did not become ready within ${OMNIVOICE_START_TIMEOUT}s. Increase OMNIVOICE_START_TIMEOUT, or set HF_ENDPOINT=https://hf-mirror.com if the model download is slow."
}

if [ "$RUN_OMNIVOICE" -eq 1 ]; then
  log "starting OmniVoice -> http://$OMNIVOICE_HOST:$OMNIVOICE_PORT (prototype; first run downloads the model)"
  start_server omnivoice "$ROOT_DIR" \
    env -u PYTHONPATH "$OMNIVOICE_RUNTIME_PYTHON" \
    "$ROOT_DIR/tools/omnivoice_server/server.py" \
    --host "$OMNIVOICE_HOST" --port "$OMNIVOICE_PORT"
  OMNIVOICE_PID="${pids[$((${#pids[@]} - 1))]}"
  wait_for_omnivoice
  log "voice: OmniVoice local prototype (backend MENTORA_TTS_PROVIDER=omnivoice)"
fi

log "starting backend  -> http://$BACKEND_HOST:$BACKEND_PORT"
# `env -u PYTHONPATH`: this shell exports a ROS 2 PYTHONPATH that breaks the venv.
start_server backend "$BACKEND_DIR" \
  env -u PYTHONPATH "$UVICORN_BIN" app.api.app:create_app --factory \
  --host "$BACKEND_HOST" --port "$BACKEND_PORT" --reload

log "starting frontend -> http://${FRONTEND_HOST:-localhost}:$FRONTEND_PORT"
vite_args=(--port "$FRONTEND_PORT" --strictPort)
[ -n "$FRONTEND_HOST" ] && vite_args+=(--host "$FRONTEND_HOST")
start_server frontend "$FRONTEND_DIR" "$VITE_BIN" "${vite_args[@]}"

log "ready. Press Ctrl+C to stop."
if [ "$RUN_OMNIVOICE" -eq 1 ]; then
  log "spoken narration is live: open http://localhost:$FRONTEND_PORT/classroom, start a class, and allow sound in the teacher tab."
fi

# Wait for whichever server exits first, then take the other one down with it:
# a half-running stack (e.g. Vite up, API gone) only produces confusing
# "upload failed" errors in the browser.
exited_pid=""
status=0
if (( BASH_VERSINFO[0] > 5 || (BASH_VERSINFO[0] == 5 && BASH_VERSINFO[1] >= 1) )); then
  wait -n -p exited_pid || status=$?
  # Defensive: `wait -p` leaves the variable unset if a trap interrupted it.
  exited_pid="${exited_pid:-}"
elif (( BASH_VERSINFO[0] > 4 || (BASH_VERSINFO[0] == 4 && BASH_VERSINFO[1] >= 3) )); then
  wait -n || status=$?
else
  # bash 3.2 (macOS /bin/bash) has no `wait -n`: poll until one server is gone.
  while [ -z "$exited_pid" ]; do
    for pid in "${pids[@]}"; do
      if ! kill -0 "$pid" 2>/dev/null; then
        exited_pid="$pid"
        wait "$pid" || status=$?
        break
      fi
    done
    [ -n "$exited_pid" ] || sleep 1
  done
fi

role="a server"
for index in "${!pids[@]}"; do
  if [ -n "${exited_pid:-}" ] && [ "${pids[index]}" = "${exited_pid:-}" ]; then
    role="the ${roles[index]} server (pid $exited_pid)"
  fi
done

if [ "$status" -eq 0 ]; then
  warn "$role exited cleanly; shutting down the rest."
else
  warn "$role exited unexpectedly with status $status; shutting down the rest."
  warn "check the output above for the cause, then re-run ./run.sh to restart."
fi
