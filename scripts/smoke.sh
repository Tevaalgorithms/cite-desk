#!/usr/bin/env bash
# Quick checks of a running CiteDesk (for example right after a deploy). Changes no data.
#   scripts/smoke.sh https://handbook.example.com
set -u
base="${1:?usage: scripts/smoke.sh BASE_URL}"
base="${base%/}"
failed=0

check() {  # name, expected, actual
  if [ "$2" = "$3" ]; then echo "PASS  $1"; else echo "FAIL  $1 (expected $2, got $3)"; failed=1; fi
}

check "API health"                       "200" "$(curl -s -o /dev/null -w '%{http_code}' "$base/health")"
check "API ready (database reachable)"   "200" "$(curl -s -o /dev/null -w '%{http_code}' "$base/ready")"
check "web app loads"                    "200" "$(curl -s -o /dev/null -w '%{http_code}' "$base/")"
check "chat refuses requests with no sign-in" "401" "$(curl -s -o /dev/null -w '%{http_code}' -X POST "$base/v1/chat" -H 'content-type: application/json' -d '{"question":"hi"}')"
check "admin API refuses requests with no sign-in" "401" "$(curl -s -o /dev/null -w '%{http_code}' "$base/v1/admin/documents")"
check "interactive API docs are not exposed" "404" "$(curl -s -o /dev/null -w '%{http_code}' "$base/docs")"
check "nosniff header present" "1" "$(curl -s -D - -o /dev/null "$base/health" | grep -ic '^x-content-type-options: nosniff')"
check "server version header hidden" "0" "$(curl -s -D - -o /dev/null "$base/" | grep -ic '^server:')"

if [ "$failed" -eq 0 ]; then echo "All smoke checks passed."; else echo "Some smoke checks FAILED."; fi
exit "$failed"
