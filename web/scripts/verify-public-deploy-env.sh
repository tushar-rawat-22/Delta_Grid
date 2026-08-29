#!/usr/bin/env bash
set -euo pipefail

required=(
  CLOUDFLARE_API_TOKEN
  CLOUDFLARE_ACCOUNT_ID
)
missing=()

for name in "${required[@]}"; do
  if [[ -z "${!name:-}" ]]; then
    missing+=("$name")
  fi
done

if ((${#missing[@]})); then
  printf 'Public production deployment configuration is incomplete. Missing: %s\n' "${missing[*]}" >&2
  printf 'Configure the missing values in the protected public-production GitHub environment; never print or paste secret values into logs.\n' >&2
  exit 1
fi

echo 'Public production deployment configuration preflight passed.'
