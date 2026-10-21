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
#   ./run.sh [-k|--kill]
#
# Starting also stops any leftover instance of this checkout first, so a crashed
# or orphaned server can never block the next start with "port already in use".
# `--kill` is the bigger hammer: it stops every backend/frontend process of this
# checkout *and* whatever holds the configured ports.
#
# Ctrl+C stops both servers.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"

BACKEND_HOST="${BACKEND_HOST:-127.0.0.1}"
BACKEND_PORT="${BACKEND_PORT:-8001}"
FRONTEND_HOST="${FRONTEND_HOST:-}"
FRONTEND_PORT="${FRONTEND_PORT:-8000}"
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
  ./run.sh [-k|--kill]

Options:
  -i, --install         install backend (pip) and frontend (npm) deps first
  -k, --kill            stop every backend/frontend instance of this checkout,
                        plus whatever holds --backend-port / --port,
                        then exit (does not start anything)
      --backend-port N  backend port (default 8001)
  -p, --port N          frontend port, the one you open (default 8000;
                        --frontend-port N is the same option)
      --host H          frontend bind host, e.g. 0.0.0.0 (default: localhost)

Env:
  MENTORA_ALLOWED_HOSTS   comma-separated hostnames Vite may serve
                          (default: dev.nguynx.uk)

Starting first stops any leftover instance of this checkout.
Ctrl+C stops both servers.
EOF
}

while [ $# -gt 0 ]; do
  case "$1" in
    -i|--install)      INSTALL=1 ;;
    -k|--kill)         KILL=1 ;;
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
  local args="$1"
  case "$args" in
    *app.api.app:create_app*)                          return 0 ;;
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
  local pid args holder

  while read -r pid args; do
    if [ -z "$pid" ]; then
      continue
    fi
    if matches_our_command_line "$args"; then
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
    # squats on them goes too (it is printed before it is killed).
    for holder in $(pids_on_port "$BACKEND_PORT") $(pids_on_port "$FRONTEND_PORT"); do
      if [ -n "$holder" ]; then
        seeds+=("$holder")
      fi
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
    log "all Mentora backend/frontend instances stopped."
  else
    log "nothing to stop (no Mentora backend/frontend instance is running)."
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

UVICORN_BIN="$BACKEND_DIR/.venv/bin/uvicorn"
VITE_BIN="$FRONTEND_DIR/node_modules/.bin/vite"

[ -x "$UVICORN_BIN" ] || fail "backend venv not ready. Run: ./run.sh --install"
[ -x "$VITE_BIN" ]    || fail "frontend deps not installed. Run: ./run.sh --install"

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

# Vite reads this to proxy API calls to the backend.
export MENTORA_BACKEND_ORIGIN="${MENTORA_BACKEND_ORIGIN:-http://127.0.0.1:$BACKEND_PORT}"

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
