# Build AgentBox base first: ./agentbox build
FROM agentbox-agent:local
USER root
# Install your Linux agent here from its official source, with a pinned version.
# Prefer a fixed package/archive checksum; never copy host home or credentials.
# RUN ...
# Keep python3, /opt/agentbox, nft/ip/setpriv/tini and the desktop runtime intact.
# Profile selects the executable; entrypoint is always controlled by AgentBox.
# docker build -t my-agent:1 -f examples/custom-agent.Dockerfile .
