#!/usr/bin/env bash
set -euo pipefail

PUBLIC_BASE="${DELTAGRID_PUBLIC_BASE:-https://deltagrid-observer.tushar142004.workers.dev}"
FOUNDER_BASE="${DELTAGRID_FOUNDER_BASE:-https://deltagrid-founder-gateway.tushar142004.workers.dev}"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

request() {
  local url="$1"
  local headers="$2"
  local body="$3"
  curl \
    --silent \
    --show-error \
    --connect-timeout 10 \
    --max-time 25 \
    --retry 2 \
    --retry-delay 1 \
    --retry-all-errors \
    --dump-header "$headers" \
    --output "$body" \
    --write-out '%{http_code}' \
    "$url"
}

clean_headers() {
  tr -d '\r' < "$1"
}

require_header() {
  local file="$1"
  local pattern="$2"
  local label="$3"
  if ! grep -Eiq "$pattern" "$file"; then
    echo "FAIL: missing or invalid header: $label" >&2
    exit 1
  fi
}

verify_anonymous_denied() {
  local label="$1"
  local url="$2"
  local stem="$3"
  local headers_raw="$TMP/${stem}.headers.raw"
  local headers="$TMP/${stem}.headers"
  local body="$TMP/${stem}.body"
  local code

  echo "=== $label ==="
  code="$(request "$url" "$headers_raw" "$body")"
  clean_headers "$headers_raw" > "$headers"

  case "$code" in
    301|302|303|307|308)
      if ! grep -Eiq '^location:.*cloudflareaccess\.com' "$headers"; then
        echo "FAIL: $label redirected somewhere other than Cloudflare Access" >&2
        cat "$headers" >&2
        exit 1
      fi
      echo "${stem^^}_ACCESS_REDIRECT=PASS"
      ;;
    401|403)
      echo "${stem^^}_ACCESS_DENIED_ANONYMOUS=PASS"
      ;;
    *)
      echo "FAIL: anonymous $label response HTTP=$code" >&2
      exit 1
      ;;
  esac

  for forbidden in \
    "PRIVATE FOUNDER WORKSPACE" \
    "Preregistration review" \
    "Saved as revision" \
    "Founder control plane" \
    '"csrf_token"'
  do
    if grep -Fq "$forbidden" "$body"; then
      echo "FAIL: founder content was exposed before authentication at $label: $forbidden" >&2
      exit 1
    fi
  done

  echo "${stem^^}_ANONYMOUS_CONTENT_BOUNDARY=PASS"
  echo "${stem^^}_HTTP=$code"
}

echo "=== PUBLIC HOMEPAGE ==="
HOME_CODE="$(request "$PUBLIC_BASE/" "$TMP/home.headers.raw" "$TMP/home.body")"
clean_headers "$TMP/home.headers.raw" > "$TMP/home.headers"
if [ "$HOME_CODE" != "200" ]; then
  echo "FAIL: public homepage HTTP=$HOME_CODE" >&2
  exit 1
fi
for marker in \
  "A public view of a private research system." \
  "Explore Demo Mode" \
  "Founder Log in"
do
  if ! grep -Fq "$marker" "$TMP/home.body"; then
    echo "FAIL: public homepage marker missing: $marker" >&2
    exit 1
  fi
done

require_header "$TMP/home.headers" '^x-content-type-options:[[:space:]]*nosniff[[:space:]]*$' 'X-Content-Type-Options'
require_header "$TMP/home.headers" '^x-frame-options:[[:space:]]*DENY[[:space:]]*$' 'X-Frame-Options'
require_header "$TMP/home.headers" '^referrer-policy:[[:space:]]*no-referrer[[:space:]]*$' 'Referrer-Policy'
require_header "$TMP/home.headers" '^permissions-policy:' 'Permissions-Policy'
require_header "$TMP/home.headers" '^content-security-policy:' 'Content-Security-Policy'
require_header "$TMP/home.headers" '^cross-origin-opener-policy:[[:space:]]*same-origin[[:space:]]*$' 'Cross-Origin-Opener-Policy'
require_header "$TMP/home.headers" '^cross-origin-resource-policy:[[:space:]]*same-origin[[:space:]]*$' 'Cross-Origin-Resource-Policy'

if [[ "$PUBLIC_BASE" == *.workers.dev ]]; then
  require_header "$TMP/home.headers" '^x-robots-tag:[[:space:]]*noindex,[[:space:]]*nofollow[[:space:]]*$' 'workers.dev X-Robots-Tag'
fi

echo "PUBLIC_HOMEPAGE=PASS"
echo "PUBLIC_SECURITY_HEADERS=PASS"


echo "=== PUBLIC RESEARCH DEMO ==="
RESEARCH_CODE="$(request "$PUBLIC_BASE/research" "$TMP/research.headers.raw" "$TMP/research.body")"
if [ "$RESEARCH_CODE" != "200" ]; then
  echo "FAIL: public research demo HTTP=$RESEARCH_CODE" >&2
  exit 1
fi
for marker in \
  "DEMO MODE" \
  "SANITIZED FIXTURES" \
  "NOT LIVE" \
  "NO WRITES" \
  "Log in for Founder Mode"
do
  if ! grep -Fq "$marker" "$TMP/research.body"; then
    echo "FAIL: public research marker missing: $marker" >&2
    exit 1
  fi
done

for forbidden in \
  "PRIVATE FOUNDER WORKSPACE" \
  "Saved as revision" \
  "Research saved" \
  '"csrf_token"'
do
  if grep -Fq "$forbidden" "$TMP/research.body"; then
    echo "FAIL: founder-only marker appeared in public research HTML: $forbidden" >&2
    exit 1
  fi
done

echo "PUBLIC_RESEARCH_DEMO=PASS"
echo "PUBLIC_PRIVATE_MARKER_SCAN=PASS"


echo "=== ROBOTS POLICY ==="
ROBOTS_CODE="$(request "$PUBLIC_BASE/robots.txt" "$TMP/robots.headers.raw" "$TMP/robots.body")"
if [ "$ROBOTS_CODE" != "200" ]; then
  echo "FAIL: robots.txt HTTP=$ROBOTS_CODE" >&2
  exit 1
fi
grep -Fq 'User-agent: *' "$TMP/robots.body" || { echo 'FAIL: robots user-agent rule missing' >&2; exit 1; }
grep -Fq 'Allow: /' "$TMP/robots.body" || { echo 'FAIL: robots public allow rule missing' >&2; exit 1; }
if grep -Fq 'Disallow: /' "$TMP/robots.body"; then
  echo 'FAIL: robots.txt blocks the public product' >&2
  exit 1
fi
echo "ROBOTS_POLICY=PASS"


verify_anonymous_denied \
  "FOUNDER RESEARCH WORKSPACE ANONYMOUS BOUNDARY" \
  "$FOUNDER_BASE/research" \
  "founder_research"

verify_anonymous_denied \
  "FOUNDER CONTROL PLANE ANONYMOUS BOUNDARY" \
  "$FOUNDER_BASE/founder" \
  "founder_control"

verify_anonymous_denied \
  "FOUNDER RESEARCH API ANONYMOUS BOUNDARY" \
  "$FOUNDER_BASE/api/research/v1/bootstrap" \
  "founder_research_api"

verify_anonymous_denied \
  "MACHINE API ANONYMOUS BOUNDARY" \
  "$FOUNDER_BASE/agent/v1/status" \
  "machine_api"


echo "=============================================="
echo "DELTAGRID_LIVE_PUBLIC_PRIVATE_BOUNDARY=PASS"
echo "PUBLIC_HOME_HTTP=$HOME_CODE"
echo "PUBLIC_RESEARCH_HTTP=$RESEARCH_CODE"
echo "ROBOTS_HTTP=$ROBOTS_CODE"
echo "ANONYMOUS_PRIVATE_SURFACE_COUNT=4"
echo "=============================================="
