ARG BASE_IMAGE=debian:bookworm-slim
FROM ${BASE_IMAGE}
RUN apt-get update && apt-get install -y --no-install-recommends python3 websockify novnc nftables util-linux tini && rm -rf /var/lib/apt/lists/* && groupadd -g 900 relay && useradd -u 900 -g 900 -M -s /usr/sbin/nologin relay
COPY runtime /opt/agentbox
ENTRYPOINT ["python3","/opt/agentbox/relay.py"]
