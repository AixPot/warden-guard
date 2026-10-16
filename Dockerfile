FROM node:22-bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends python3 openssl ca-certificates tzdata && rm -rf /var/lib/apt/lists/*
RUN npm install -g @bitwarden/cli@2026.10.0 && test "$(bw --version)" = "2026.10.0"
WORKDIR /app
COPY warden_guard /app/warden_guard
ENV PYTHONDONTWRITEBYTECODE=1 TZ=Asia/Shanghai
ENTRYPOINT ["python3", "-m", "warden_guard"]
CMD ["schedule"]
