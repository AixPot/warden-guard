#!/usr/bin/env bash
# Synthetic accounts only. No production hosts, credentials, ports or volumes.
set -euo pipefail
image=${WG_ACCEPTANCE_IMAGE:-warden-guard:acceptance}
root=$(cd "$(dirname "$0")/.." && pwd)
work=$(mktemp -d "${TMPDIR:?set TMPDIR to a scratch directory}/wg-accept.XXXXXX")
name="wg-isolated-${RANDOM}-${RANDOM}"
vault="$name-vault"
cleanup() {
  docker rm -f "$name" "$vault" >/dev/null 2>&1 || true
  rm -rf -- "$work"
}
trap cleanup EXIT
# Only this derived test image installs ssh-keygen; the release image is unchanged.
printf 'FROM %s\nRUN apt-get update && apt-get install -y --no-install-recommends openssh-client && rm -rf /var/lib/apt/lists/*\n' "$image" > "$work/Dockerfile"
docker build -q -t "$name-tools" "$work" >/dev/null
docker run -d --name "$vault" --network none \
  --tmpfs /data:rw,nosuid,nodev,size=128m -e SIGNUPS_ALLOWED=true \
  -e DOMAIN=https://127.0.0.1:8443 vaultwarden/server:1.37.4 >/dev/null
# No published ports. Both vault data and credentials/profile/state are tmpfs.
docker run --name "$name" --network "container:$vault" \
  --tmpfs /run/warden-guard:rw,nosuid,nodev,size=512m \
  --tmpfs /state:rw,nosuid,nodev,size=128m \
  -e WG_ISOLATED_ACCEPTANCE=yes -v "$root/tests:/tests:ro" \
  --entrypoint sh "$name-tools" -c \
  'python3 -u /tests/live_acceptance.py 2>/run/warden-guard/acceptance-errors; status=$?; if [ "$status" -ne 0 ]; then printf "{\"acceptance_failed\":true}\n"; fi; exit "$status"'
