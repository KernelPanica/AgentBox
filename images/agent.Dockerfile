ARG BASE_IMAGE=debian:bookworm-slim
FROM ${BASE_IMAGE}
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends python3 ca-certificates curl iproute2 nftables util-linux tini procps libcap2-bin locales chromium tigervnc-standalone-server tigervnc-tools fluxbox xterm xdg-utils dbus-x11 fonts-dejavu-core && rm -rf /var/lib/apt/lists/* && sed -i 's/^# en_US.UTF-8/en_US.UTF-8/' /etc/locale.gen && locale-gen && groupadd -g 1000 agent && useradd -m -u 1000 -g 1000 -s /bin/bash agent
COPY runtime /opt/agentbox
COPY agentboxlib /opt/agentbox/agentboxlib
COPY runtime/browser /usr/local/bin/agentbox-browser
RUN chmod 755 /usr/local/bin/agentbox-browser && mkdir -p /workspace && chown agent:agent /workspace
ENTRYPOINT ["python3","/opt/agentbox/agent.py"]
