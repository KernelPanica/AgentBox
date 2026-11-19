# Optional diagnostics only. Never used as the agent or runtime gateway.
FROM agentbox-gateway:local
RUN apt-get update && apt-get install -y --no-install-recommends tcpdump && rm -rf /var/lib/apt/lists/*
ENTRYPOINT ["tcpdump"]
