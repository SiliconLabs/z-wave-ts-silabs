#!/bin/bash
# Sanitize branch name to be a valid Conan package channel
# Following Conan naming restrictions: https://docs.conan.io/2/reference/conanfile/attributes.html#name

set -euo pipefail

if [ $# -ne 1 ]; then
  echo "Usage: $0 <branch_name>" >&2
  exit 1
fi

CHANNEL="$1"
CHANNEL=$(echo "$CHANNEL" | tr '[:upper:]' '[:lower:]')
CHANNEL=$(echo "$CHANNEL" | sed 's/[^a-z0-9_+.-]/_/g')
CHANNEL=$(echo "$CHANNEL" | sed 's/^[^a-z0-9_]/_/')
CHANNEL=$(echo "$CHANNEL" | cut -c1-100)

echo "$CHANNEL"
