#!/usr/bin/env bash
# Submit one ticket through the running stack and print what happened to it.
#
#   ./scripts/demo.sh                      # default ticket
#   ./scripts/demo.sh "Subject" "Body"     # your own
#
# Expects the stack to be up (make up) and Ollama to be running.

set -euo pipefail

RECEIVER="${TICKET_RECEIVER_URL:-http://localhost:8001}"
API_KEY="${API_KEY:-dev-local-key}"

SUBJECT="${1:-Cannot sign in}"
BODY="${2:-I forgot my password and the reset email never arrives. I already checked spam.}"

bold() { printf '\033[1m%s\033[0m\n' "$1"; }
dim()  { printf '\033[2m%s\033[0m\n' "$1"; }

for service in "$RECEIVER/health" "${RAG_ENGINE_URL:-http://localhost:8002}/health" \
               "${AGENT_URL:-http://localhost:8003}/health"; do
  if ! curl -fsS --max-time 3 "$service" >/dev/null 2>&1; then
    echo "error: $service is not responding. Is the stack up? Try 'make up'." >&2
    exit 1
  fi
done

bold "Submitting ticket"
dim  "  subject: $SUBJECT"
dim  "  body:    $BODY"
echo

response=$(curl -fsS -X POST "$RECEIVER/api/tickets" \
  -H "content-type: application/json" \
  -H "x-api-key: $API_KEY" \
  -d "$(cat <<JSON
{
  "subject": $(printf '%s' "$SUBJECT" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))'),
  "body": $(printf '%s' "$BODY" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))'),
  "customer": {
    "external_id": "demo:$(date +%s)",
    "email": "demo@customer.example",
    "name": "Demo Customer",
    "tier": "standard"
  },
  "channel": "api",
  "priority": "normal",
  "external_ref": "demo-$(date +%s)-$RANDOM",
  "tags": ["demo"],
  "metadata": {}
}
JSON
)")

TICKET_ID=$(printf '%s' "$response" | python3 -c 'import json,sys; print(json.load(sys.stdin)["ticket_id"])')
bold "Ticket $TICKET_ID accepted"
echo

# The agent runs in the background; a local 7B model typically needs 20-90s.
printf 'Waiting for the agent'
for _ in $(seq 1 60); do
  status=$(curl -fsS "$RECEIVER/api/tickets/$TICKET_ID" \
    | python3 -c 'import json,sys; print(json.load(sys.stdin)["status"])')
  case "$status" in
    resolved|escalated|failed) echo; break ;;
    *) printf '.'; sleep 3 ;;
  esac
done
echo

# A temp file for the renderer, not a heredoc: `python3 - <<HEREDOC` would
# consume the heredoc as python3's own script (satisfying the `-` stdin-script
# argument) and leave nothing on stdin for json.load() to read the piped curl
# output from - the two redirections can't share one stdin.
render_script="$(mktemp)"
trap 'rm -f "$render_script"' EXIT
cat > "$render_script" <<'PY'
import json, sys, textwrap

status = sys.argv[1]
messages = json.load(sys.stdin)

label = {"resolved": "\033[32mRESOLVED\033[0m", "escalated": "\033[33mESCALATED\033[0m"}
print(f"Status: {label.get(status, status.upper())}\n")

for message in messages:
    if message["sender"] == "customer":
        continue
    meta = message.get("metadata_json") or {}
    print(f"\033[1m{message['sender'].upper()}\033[0m", end="")
    if "confidence" in meta:
        print(f"  (confidence {meta['confidence']:.2f})", end="")
    print()
    for paragraph in message["message"].split("\n"):
        print(textwrap.fill(paragraph, width=78, initial_indent="  ", subsequent_indent="  ")
              if paragraph.strip() else "")
    if meta.get("citations"):
        print(f"\n  \033[2mSources: {', '.join(meta['citations'][:3])}\033[0m")
    print()
PY
curl -fsS "$RECEIVER/api/tickets/$TICKET_ID/messages" | python3 "$render_script" "$status"

echo "Full ticket:  curl -s $RECEIVER/api/tickets/$TICKET_ID | python3 -m json.tool"
echo "Stats:        curl -s $RECEIVER/api/stats | python3 -m json.tool"
