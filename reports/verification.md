# AgentBox — результаты проверки

Дата: 2026-11-19. Это отчёт о выполненных проверках, не гарантия анонимности.
Существующая установка Claude не изменялась, её credentials не копировались.

| Область | Статус | Что проверено |
|---|---|---|
| Полный unittest набор | PASS | 41 тест, включая анализ capture и регрессии независимого ревью и локальный TCP accept/close |
| Python compileall | PASS | agentboxlib, runtime, tests; отдельно 19 production-модулей с реальным Python 3.11.2 |
| Docker/Compose | PASS | Локальный Engine 29.8.2, Compose 5.6.0; Compose config валиден |
| Сборка | PASS | agentbox-agent:local, agentbox-gateway:local, agentbox-relay:local |
| CLI control plane | PASS | configure/load/render, блокировки, строгая схема; обычный start отклоняет unhealthy gateway |
| Непривилегированная среда | PASS | PID 1 и CLI UID 1000, CapEff/Prm/Bnd/Amb=0, NoNewPrivs=1 |
| Изоляция хоста | PASS для проб | Нет Docker/DBus/host sockets; профиль не допускает host mounts/namespace/capability overrides |
| GUI | PASS | noVNC запросил пароль, подключился; терминал и Chromium визуально отображались |
| Browser sandbox | PASS | Chromium headless выполнил рендер без --no-sandbox; обычный GUI Chromium запущен |
| Сеть без VPN | PASS | 13 проверок: DNS системный/TCP/UDP, Docker DNS, literal-IP TLS, HTTPS, IPv6, LAN/metadata, identity/caps |
| Xray bootstrap | PASS | Реальные TPROXY/nft/netdev правила установлены, Xray 26.11.9 запущен UID 900 |
| Неисправный Xray/endpoint | PASS для проб | Внешний полезный обмен не проходит; тестовая конфигурация намеренно не даёт рабочего VPN |
| Падение и пересоздание Xray gateway | PASS для проб | После SIGKILL сеть закрыта; во время пересоздания 0 успешных TLS-обменов из 5 попыток за ~8 с |
| Данные | PASS | Маркер workspace сохранился после удаления/пересоздания контейнеров |
| WireGuard dataplane | PASS, локальный fixture | Два настоящих peer, TCP round trip через туннель, остановка gateway блокирует обмен |
| Forwarding без writable /proc/sys | PASS | Netlink enable/disable в dummy-interface; в WG global=0, inside=1, outside=0, tun0=1 |
| OpenVPN | NOT_RUN runtime | Allowlist/config parsing проверены unit-тестами; рабочий TLS tunnel и credentials не испытывались |
| Положительный VLESS/Xray tunnel | PASS для проб | Предоставленный отдельно VLESS/XHTTP/Reality, DNS/HTTPS/literal TLS; исходные direct/DNS/routing исключены |
| Удалённый VPN-выход | PASS для сравнения | Публичный IPv4 агента совпал с выходом через SOCKS Xray; GeoIP/страна не проверялись |
| Packet capture uplink bridge | PASS в интервале 75 с | По source MAC шлюза, все IP-источники, ARP исключён: 77/77 endpoint transport, 0 violating/unparsed |
| Packet capture физического интерфейса | NOT_RUN | Host VPN/физический интерфейс не наблюдались |
| Реальный Xray stop/recovery | MIXED | Один полный прогон 13/13 во всех фазах; в двух других отдельные DNS/TLS timeout. При остановке шлюза все пробы заблокированы во всех прогонах |
| Windows GUI/WSLg | SKIPPED | По условию пользователя нужен реальный запуск отдельного приложения; Windows-хоста для проверки нет |
| Авторизация AI-клиента | NOT_RUN | Поставляется базовая среда и контракт образов; пользовательский AI-клиент/аккаунт не настроен |
| Reboot/Docker daemon restart/host VPN | NOT_RUN | Намеренно не затрагивались другие приложения и системные службы |

`reports/unit-tests.log`, `reports/fault-smoke.json` и
`reports/wireguard-fixture.json` содержат исходные результаты на этом ПК.
JSON/logs не входят в переносимый архив исходников.

Первоначальный smoke-проход имел 11 проверок; итоговый fault-smoke — 13,
с реальными DNS TCP/UDP запросами. Прозрачный прокси может подтвердить TCP
handshake до соединения с сервером, поэтому успех literal-IP теперь требует
TLS с проверкой сертификата и HTTP-ответа, а не только connect().

WireGuard fixture использует отдельную локальную Docker-подсеть
11.254.253.0/29 и responder 1.1.1.1 внутри peer. Это не удалённый провайдер
и не запрос к внешнему сервису 1.1.1.1. Все созданные fixture контейнеры,
сети и volumes удалены. Сохранены исходники, образы и приватные тестовые
файлы/отчёты; реальные пользовательские файлы не импортировались.

Base images: агент и шлюз испытывались на ранее скачанном python:3.12-slim
(Debian 13), relay — Debian 12. Default Dockerfile base Debian 12 требует
отдельного полного повторения тестов перед выпуском с этим base. Переключение
на локальный base потребовалось из-за отказа Docker Hub по IPv6; host
networking, настройки Docker и VPN не изменялись.

Независимое ревью: исправлены смешивание одноимённых профилей и обход
защищённых путей импорта через `..`. Дополнительно исправлен пропуск
OpenVPN endpoint validation при tab whitespace. Все регрессии прошли
RED→GREEN; итоговый набор зелёный. Секреты и VPN-конфиги в ревью не передавались.

Реальный Xray проверялся в приватном профиле `xray-test`; исходный полный
клиентский конфиг сокращён до одного VLESS outbound. Файл и credentials не
входят в исходный архив. Профиль использует localhost-порт 16090. Пробы
показали работающий удалённый туннель и одинаковый публичный IPv4 у агента
и gateway SOCKS; регион по GeoIP не запрашивался.

Результаты повторов не скрыты: первый fault run имел отказ HTTPS в normal
и literal TLS в recovered; второй прошёл полностью; третий, одновременно
с capture, имел один отказ TCP DNS в recovered. Во всех трёх остановленный
шлюз блокировал полезный сетевой обмен. Отдельная серия DNS: SOCKS TCP 8/8,
TPROXY TCP 12/12, но более ранние UDP/TCP запросы имели отдельные таймауты.
Причина нестабильности не установлена; ограничения firewall не ослаблялись.

При live-запуске найдена и исправлена несовместимость NAT f-string с Python
3.11, пропущенная сборкой агент/шлюз на Python 3.12. Регрессия воспроизведена
реальным Python 3.11.2, затем 19 модулей успешно скомпилированы. Добавлены
HTTP healthcheck relay и требование готовности всех трёх сервисов.

Независимое ревью capture выявило слепую зону фильтра source IP: прямая
пересылка могла сохранить IP агента. Итоговый фильтр использует source MAC
uplink шлюза без ограничения IP-источника; четыре теста включают такой
неразрешённый пакет, IPv6/unknown и пустой capture. Удаление временного
observer выполняется в отдельном finally, старт проверок разрешён после
подтверждения tcpdump readiness. Итоговый 75-секундный capture содержит
77 сводок endpoint transport и ни одной посторонней/неразобранной сводки.
ARP исключён из этой проверки; физический интерфейс не наблюдался.

Ограничения свидетельства: пробы и конечный интервал capture не исключают
все возможные утечки. Нужны дальнейшая диагностика стабильности реального
соединения, физический capture и испытания на каждой новой комбинации
клиента, адаптера и хоста. Kernel exploits, аккаунтные признаки и содержимое
сообщений не покрываются контейнеризацией. Windows/macOS/ARM не испытаны;
графическая Windows-адаптация пропущена по условию пользователя.
