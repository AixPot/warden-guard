#!/usr/bin/env bash
set -euo pipefail
: "${IMAGE:?}" "${DIGEST:?}" "${GITHUB_REF_NAME:?}"
[[ "$GITHUB_REF_NAME" =~ ^v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$ ]]
[[ "$DIGEST" =~ ^sha256:[a-f0-9]{64}$ ]]
cd "$(git rev-parse --show-toplevel)"
test "$GITHUB_REF_NAME" = "v$(git show HEAD:VERSION)"
# Build in a new directory: failed runs leave the old dist intact; successful
# reruns cannot include old assets or SHA256SUMS in its own checksum list.
test ! -L dist
stage=$(mktemp -d .release-assets.XXXXXX)
id=
cleanup() {
    if [[ -n "$id" ]]; then docker rm "$id" >/dev/null || true; fi
    rm -rf -- "$stage"
}
trap cleanup EXIT
# Explicit tracked files only, never operational state, env or evidence.
files=(LICENSE NOTICE SOURCES.md VERSION README.md Dockerfile .dockerignore compose.yaml compose.build.yaml credentials.example.json docs/operations.md warden_guard tests scripts .github)
git archive --format=tar.gz --prefix="warden-guard-${GITHUB_REF_NAME}/" HEAD "${files[@]}" > "$stage/warden-guard-${GITHUB_REF_NAME}.tar.gz"
git archive --format=zip --prefix="warden-guard-${GITHUB_REF_NAME}/" HEAD "${files[@]}" > "$stage/warden-guard-${GITHUB_REF_NAME}.zip"
git show HEAD:compose.yaml > "$stage/compose.yaml"
printf '%s@%s\n' "$IMAGE" "$DIGEST" > "$stage/image-digest.txt"
# Copy sources from the EXACT image digest, not a moving tag or source ref.
docker pull "$IMAGE@$DIGEST"
id=$(docker create "$IMAGE@$DIGEST")
docker cp "$id:/usr/share/warden-guard/sources/bitwarden-clients.tar.gz" "$stage/"
docker cp "$id:/usr/share/warden-guard/sources/bitwarden-sdk.tar.gz" "$stage/"
printf '# %s\n\nImage (linux/amd64): `%s@%s`\n\nProject source is MIT; Bitwarden CLI OSS is GPL-3.0. See NOTICE and SOURCES.md.\nUpstream corresponding source archives are included.\n' "$GITHUB_REF_NAME" "$IMAGE" "$DIGEST" > "$stage/release-notes.md"
(cd "$stage" && sha256sum -- * > SHA256SUMS && sha256sum -c SHA256SUMS)
rm -rf -- dist
mv -- "$stage" dist
