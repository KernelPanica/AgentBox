ARG BASE_IMAGE=debian:bookworm-slim
FROM ${BASE_IMAGE}
ARG XRAY_VERSION=26.11.9
RUN apt-get update && apt-get install -y --no-install-recommends python3 ca-certificates curl iproute2 nftables util-linux tini wireguard-tools openvpn unzip procps && rm -rf /var/lib/apt/lists/* && groupadd -g 900 vpn && useradd -u 900 -g 900 -M -s /usr/sbin/nologin vpn
RUN set -eu; arch="$(dpkg --print-architecture)"; case "$arch" in amd64) archive=Xray-linux-64.zip;; arm64) archive=Xray-linux-arm64-v8a.zip;; *) exit 1;; esac; url="https://github.com/XTLS/Xray-core/releases/download/v${XRAY_VERSION}/${archive}"; curl -fLSs --retry 2 "$url" -o /tmp/xray.zip; curl -fLSs --retry 2 "$url.dgst" -o /tmp/xray.dgst; python3 -c 'import hashlib; assert hashlib.sha256(open("/tmp/xray.zip","rb").read()).hexdigest() in open("/tmp/xray.dgst").read().lower(), "Xray digest mismatch"'; unzip /tmp/xray.zip xray -d /usr/local/bin; rm /tmp/xray.*; chmod 755 /usr/local/bin/xray
COPY runtime /opt/agentbox
COPY agentboxlib /opt/agentbox/agentboxlib
ENTRYPOINT ["python3","/opt/agentbox/gateway.py"]
