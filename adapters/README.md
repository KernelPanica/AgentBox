# Контракты адаптеров

Агент — доверенный образ на основе `agentbox-agent:local`. Он сохраняет UID/GID
1000, `/opt/agentbox`, Python, setpriv, tini, iproute2/nftables и GUI runtime.
Устанавливайте агент на этапе сборки; профиль задаёт массивы `agent.cli` и
`agent.gui`. Команды исполняются без shell interpolation. Права и mounts
профиль не расширяет. Клиенту доступны `/home/agent`, `/workspace`, `/tmp`,
`/run` и `/dev/shm`. Аппаратные устройства не передаются.

Готовый произвольный OCI-образ обычно нужно адаптировать: использовать
AgentBox как финальный stage и перенести нужный бинарник/зависимости.
Bootstrap в образах входит в доверенную базу; вредоносный OCI-образ нельзя
сделать безопасным лишь записью имени в профиль.

VPN — доверенный адаптер шлюза, а не произвольный Compose overlay. Сейчас
есть `wireguard`, `openvpn`, `xray`. Для нового протокола нужны: строгий
валидатор в `agentboxlib/config.py`, bootstrap в `runtime/gateway.py`,
зависимости в `images/gateway.Dockerfile`, dataplane policy в
`runtime/policy.py`, тесты config/packet/fault и запись в матрице испытаний.
Код не должен добавлять агенту capabilities, устройства или внешнюю сеть.
Сохраняйте endpoint allowlist и initial ip_forward=0. Firewall устанавливается
атомарно до запуска VPN/forwarding; DNS bootstrap напрямую запрещён.

WireGuard: один peer, full-tunnel IPv4. Конфиг разбирается нашим кодом,
`wg-quick` не вызывается; Address/MTU применяются отдельно, hooks и DNS
отклоняются. Используется kernel WireGuard, не `/dev/net/tun`.

OpenVPN: tun0, один транспорт, literal endpoints, inline certificates и
credentials; scripts/plugins/config includes/пути к credentials запрещены.
Серверные routes/DNS игнорируются. OpenVPN сбрасывает UID до 900; доверенный
supervisor сохраняет NET_ADMIN для восстановления default route к tun0.
Нужен `/dev/net/tun` на Docker-хосте. Привилегированный режим не используется.

Xray: JSON содержит только `outbounds`; первый — единственный VLESS,
дополнительно разрешён blackhole. `freedom` отсутствует, inbounds генерируются
AgentBox. TCP/raw, gRPC, WebSocket, XHTTP, HTTPUpgrade; TLS/Reality рекомендуются.
IPv4 endpoint обязан совпадать с allowlist. Доменные SNI/Host допустимы, но
транспортный адрес — literal IP. TPROXY TCP/UDP; ICMP не поддерживается.
Xray работает UID 900 с единственной capability NET_RAW, нужной IP_TRANSPARENT.

Новая версия/адаптер экспериментальны до packet capture и fault-тестов с
реальным туннелем. Наличие Dockerfile не означает проверенную совместимость.
