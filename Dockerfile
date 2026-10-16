FROM node:22-bookworm-slim AS upstream
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl unzip && rm -rf /var/lib/apt/lists/*
# Official OSS release, NOT the commercial npm bundle. amd64 only until verified.
RUN mkdir -p /licenses/bitwarden /sources && \
    curl -fL --retry 3 https://github.com/bitwarden/clients/releases/download/cli-v2026.10.0/bw-oss-linux-2026.10.0.zip -o /bw.zip && \
    echo "a300959a347bd71ff571da75687c8388da2ecd747a20f0abddd18643eb9466ba  /bw.zip" | sha256sum -c - && \
    unzip /bw.zip -d /bw && chmod 755 /bw/bw
RUN curl -fL --retry 3 https://codeload.github.com/bitwarden/clients/tar.gz/b449ac1d255784380d75ef026343198891286be7 -o /sources/bitwarden-clients.tar.gz && \
    curl -fL --retry 3 https://codeload.github.com/bitwarden/sdk-internal/tar.gz/c5e53d3e82ab80fdc9fd79ebd74058399a6444b6 -o /sources/bitwarden-sdk.tar.gz && \
    tar -xzf /sources/bitwarden-clients.tar.gz --strip-components=1 -C /licenses/bitwarden --wildcards '*/LICENSE*.txt' && \
    tar -xOf /sources/bitwarden-clients.tar.gz clients-b449ac1d255784380d75ef026343198891286be7/apps/cli/package.json > /licenses/bitwarden/cli-package.json && \
    mkdir /oss-source /oss-sdk && tar -xzf /sources/bitwarden-clients.tar.gz -C /oss-source && \
    tar -xzf /sources/bitwarden-sdk.tar.gz -C /oss-sdk && \
    mkdir -p /licenses/bitwarden-sdk && cp /oss-sdk/sdk-internal-*/LICENSE* /licenses/bitwarden-sdk/ && \
    cp /oss-sdk/sdk-internal-*/crates/bitwarden-wasm-internal/npm/LICENSE /licenses/bitwarden-sdk/npm-LICENSE && \
    rm -rf /oss-source/clients-*/bitwarden_license /oss-sdk/sdk-internal-*/bitwarden_license \
        /oss-sdk/sdk-internal-*/crates/bitwarden-wasm-internal/bitwarden_license && \
    tar -czf /sources/bitwarden-clients.tar.gz -C /oss-source . && \
    tar -czf /sources/bitwarden-sdk.tar.gz -C /oss-sdk . && \
    cd /sources && sha256sum *.tar.gz > SHA256SUMS

FROM node:22-bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends python3 openssl ca-certificates tzdata && rm -rf /var/lib/apt/lists/*
COPY --from=upstream /bw/bw /usr/local/bin/bw
COPY --from=upstream /licenses /usr/share/licenses
COPY --from=upstream /sources /usr/share/warden-guard/sources
RUN BITWARDENCLI_APPDATA_DIR=/bw-build-check test "$(BITWARDENCLI_APPDATA_DIR=/bw-build-check bw --version)" = "2026.10.0" && rm -rf /bw-build-check
ARG VERSION=0.1.0
ARG REVISION=unknown
LABEL org.opencontainers.image.title="warden-guard" \
      org.opencontainers.image.source="https://github.com/AixPot/warden-guard" \
      org.opencontainers.image.version="$VERSION" \
      org.opencontainers.image.revision="$REVISION"
WORKDIR /app
COPY warden_guard /app/warden_guard
COPY LICENSE SOURCES.md NOTICE /usr/share/licenses/warden-guard/
COPY VERSION /app/VERSION
ENV PYTHONDONTWRITEBYTECODE=1 TZ=Asia/Shanghai
ENTRYPOINT ["python3", "-m", "warden_guard"]
CMD ["schedule"]
