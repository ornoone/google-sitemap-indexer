#!/usr/bin/env bash
set -euo pipefail

PORT=${PORT:-${1:-80}}
URI=${URI:-${2:-healthy}}
HOSTNAME=${HOSTNAME:-localhost}

curl --fail http://localhost:$PORT/$URI -H "Host: ${HOSTNAME}" &> /dev/null || exit 1
