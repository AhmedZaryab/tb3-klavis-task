#!/usr/bin/env bash
# Run one agent trial of the task with the flags the brief and the TB3 CI use.
#
#   tools/run-trial.sh <claude|codex> <model> <job-name> [extra harbor args...]
#
# Examples:
#   tools/run-trial.sh claude anthropic/claude-opus-5-5 run-claude-1
#   tools/run-trial.sh codex  openai/gpt-6-sol          run-codex-1
#   tools/run-trial.sh claude anthropic/claude-opus-5-5 probe-2h --agent-timeout-multiplier 0.25
#
# Reads CLAUDE_CODE_OAUTH_TOKEN from .env (never committed). Codex uses the
# login stored by `codex login`. Output goes to runs/<job-name>/; the harbor
# console log is saved next to it with the token redacted.
set -euo pipefail
cd "$(dirname "$0")/.."
export PATH="$HOME/.local/bin:$HOME/.docker/bin:$PATH"

agent=$1; model=$2; job=$3; shift 3
task=${TASK:-tasks/gateway-tenant-onboarding}
mkdir -p runs
set -a; [ -f .env ] && source .env; set +a

# The auth flags use "yes" instead of the brief's "1": harbor scrubs the value of
# any env var whose name matches AUTH/OAUTH/TOKEN/KEY from every saved log, and
# "1" would erase every digit 1 in them. The parser accepts true/1/yes alike.
case "$agent" in
  claude)
    args=(--agent claude-code --ak reasoning_effort=max
          --ae CLAUDE_FORCE_OAUTH=yes --ae "CLAUDE_CODE_OAUTH_TOKEN=${CLAUDE_CODE_OAUTH_TOKEN:?set in .env}"
          --ae CLAUDE_CODE_NO_MODEL_FALLBACK=1 --ae CLAUDE_CODE_MAX_OUTPUT_TOKENS=128000) ;;
  codex)
    args=(--agent codex --ak reasoning_effort=xhigh --ae CODEX_FORCE_AUTH_JSON=yes) ;;
  *) echo "agent must be claude or codex" >&2; exit 2 ;;
esac

caffeinate -i harbor run -p "$task" --model "$model" --env docker --yes -o runs --job-name "$job" "${args[@]}" "$@" \
  2>&1 | sed -u 's/sk-ant[-][A-Za-z0-9_-]*/<token>/g' | tee "runs/$job.log"

python3 - "$job" <<'PY'
import json, sys, glob
job = sys.argv[1]
r = json.load(open(f"runs/{job}/result.json"))
for name, ev in r["stats"]["evals"].items():
    print(name, "reward:", ev["reward_stats"]["reward"], "errors:", ev["n_errors"])
PY
