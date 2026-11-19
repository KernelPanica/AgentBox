# AgentBox

Изолированная среда для CLI и графических Linux-агентов с отдельным VPN.
Агент получает собственные файлы, браузер и виртуальный рабочий стол.
После настройки запуск — `./agentbox start`. Существующая установка Claude
не используется и не изменяется.

**Состояние:** первая рабочая версия. Образы собраны, CLI/GUI и блокировка
сети без VPN испытаны. WireGuard проверен между двумя локальными peer-контейнерами. Выход через
удалённого провайдера пока **не проверен**: нужен отдельный VPN-конфиг.
OpenVPN/Xray требуют положительных испытаний с рабочими credentials.
Точные результаты: [reports/verification.md](reports/verification.md).

## Требования и запуск

Linux, Python 3.11+, Docker Engine 28+, Compose 2.33.1+. Пользователю нужен
доступ к Docker. AgentBox не добавляет пользователя в группы, не устанавливает
systemd, не меняет host firewall/routing, Docker daemon или работающий VPN.
Для OpenVPN нужен `/dev/net/tun`; для WireGuard — поддержка ядра Docker-хоста.

```bash
./agentbox doctor
./agentbox build
./agentbox configure
./agentbox start
```

Образы уже собраны на этом ПК. Обычная сборка использует Debian 12. При
недоступности Docker Hub по IPv6 здесь агент/шлюз собраны с доверенным,
ранее скачанным `python:3.12-slim` (Debian 13), без изменения сети хоста:

```bash
./agentbox build --base-image python:3.12-slim
```

Сборка скачивает пакеты по сети Docker build до запуска runtime VPN; в её
контекст не входят профили, конфиги, workspace и credentials. Сетевое скрытие
региона относится к runtime агента, не к скачиванию Docker-образов.

Configure запросит отдельный VPN-конфиг и endpoint вида `IPv4:port/udp` или
`IPv4:port/tcp`. Файл должен иметь права `0600`. Его приватная копия и профиль
хранятся в `.agentbox/profiles/default/`; реальные значения не передавайте
аргументами командной строки. Примеры с заглушками — в `examples/`.

Пример неинтерактивной настройки (endpoint и путь — не секретные ключи):

```bash
chmod 600 /path/to/my-wireguard.conf
./agentbox configure --name work --vpn wireguard \
  --vpn-config /path/to/my-wireguard.conf --endpoint 203.0.113.1:51820/udp \
  --mode gui --image agentbox-agent:local --cli bash --gui agentbox-browser
```

`203.0.113.1` — пример адреса документации: валидатор его отклонит.
Подставьте публичный IPv4 своего сервера. Для Xray нужен JSON с `outbounds`,
а не весь существующий конфиг или ссылка подписки; см. `examples/xray.json.example`.
Для OpenVPN используются inline credentials/certificates, без внешних файлов.

После старта откройте напечатанный localhost URL. Пароль рабочего стола:

```bash
./agentbox password
```

Он выводится только в интерактивный терминал, не в URL/логи. noVNC спрашивает
его при подключении. VNCAuth использует 8 случайных символов (~48 бит);
интерфейс слушает только `127.0.0.1`, без TLS. Не публикуйте его через reverse
proxy/SSH на чужих пользователей. Зависимости: noVNC/websockify/TigerVNC из Debian.

## Агенты и режимы

Поставляется нейтральная среда: bash, терминал, Chromium, виртуальный дисплей.
Конкретный AI-клиент устанавливается в собственный образ на основе AgentBox:
[examples/custom-agent.Dockerfile](examples/custom-agent.Dockerfile).
Токены существующего Claude не копируются. Входите в аккаунт агента внутри
его контейнерного браузера либо импортируйте отдельный файл ключа в workspace.

```bash
./agentbox configure --profile .agentbox/profiles/coder/profile.json \
  --name coder --vpn xray --vpn-config /path/to/new-xray.json \
  --endpoint YOUR_SERVER_IPV4:443/tcp --mode cli \
  --image my-agent:1 --cli 'my-agent' --gui 'my-agent-desktop'
./agentbox start --profile .agentbox/profiles/coder/profile.json
```

`mode=gui` запускает GUI и возвращает терминал; `mode=cli` подключает CLI,
сохраняя рабочий стол для авторизации. Можно передать команду после `--`:

```bash
./agentbox start -- bash
./agentbox shell -- bash
./agentbox status
./agentbox stop
```

Одна CLI-сессия на профиль; дополнительные профили изолированы. `stop` удаляет
только контейнеры и сети своего Compose-проекта, сохраняя volumes. Обновлённый
профиль/образы применяются через stop → start. Ресурсы получают имя `agentbox-NAME-HASH`: хеш пути
профиля предотвращает смешивание одноимённых профилей. Перенос каталога
профиля меняет идентификатор ресурсов. При неготовом VPN старт
завершается ошибкой, прямого fallback нет. Gateway-only после неудачного
старта можно остановить обычной командой stop.

Browser/OAuth localhost работают внутри одного контейнера. Deep links конкретного
клиента нужно зарегистрировать в его образе; произвольные desktop-протоколы
не настраиваются автоматически. Нет clipboard sync, host browser, X11/Wayland,
D-Bus, SSH-agent, keyring, аудио и GPU основной системы.

## Файлы

По умолчанию нет bind mounts рабочих каталогов пользователя. `/workspace` и
`/home/agent` — отдельные именованные Docker volumes. Передача только явно:

```bash
./agentbox import /path/to/project /workspace/imported
./agentbox export /workspace/imported/project /path/to/new-export
```

Назначение должно отсутствовать. Не передавайте папку с ключами, профилями
или другими секретами. Обмен ограничен 64 MiB, симлинки, устройства и tar
path traversal отклоняются. Агент видит все импортированные файлы и может
отправить их через VPN. Секрет самого агента доступен агенту; VPN-секреты
видит только шлюз. Root/Docker-администратор может читать volumes/секреты.
Шифрование на диске не предоставляется.

## Сеть и ограничения

Агент подключён к internal isolated bridge. Единственный маршрут — выделенный
VPN-шлюз. nftables блокирует Docker DNS, LAN/link-local/metadata и IPv6.
На внешнем интерфейсе шлюза разрешены только IP/порты VPN endpoint, включая
netdev-фильтр. При падении VPN правила сохраняются. При пересоздании шлюза
глобальный/default forwarding изначально выключен. После firewall через
netlink включается только forwarding внутренних интерфейсов и туннеля;
на uplink он остаётся выключенным. `/proc/sys` остаётся read-only.
Отдельный UI-relay передаёт VNC; forwarding и произвольный OUTPUT у него закрыты.

UTC/en_US.UTF-8, нейтральное имя и отдельный browser profile скрывают некоторые
локальные признаки. **Гарантии анонимности нет:** аккаунт, язык сообщений,
файлы, fingerprints ядра/CPU и задержки могут раскрыть регион. Docker делит
ядро с хостом, поэтому не является защитой от любого kernel exploit.
Публичные сервисы на WAN-адресе пользователя могут оставаться достижимыми
через VPN как обычные интернет-сервисы.

Для bind mounts конфигурации создаётся приватная копия в нейтральном
`/tmp/agentbox-runtime-*`, чтобы `/proc/mountinfo` не показывал путь с именем
хостового пользователя. Stop очищает эту копию; источники остаются в приватном
каталоге профиля. Это не скрывает все метаданные общего ядра.

Хостовый VPN может перехватить транспорт нового шлюза. При проблемах смотрите
маршруты/провайдера самостоятельно; AgentBox не переносит исключение маршрута
существующего Claude. Никаких автозапусков или поправок host routing нет.

Browser sandbox включён. Профиль seccomp основан на upstream Moby profile
из предыдущего развёртывания, с разрешением clone/setns/unshare/chroot для
вложенного browser sandbox; файл — `runtime/seccomp.json`. Это расширяет
поверхность ядра. Прикладные PID 1/CLI имеют UID 1000, bounding capabilities=0
и no-new-privileges. Для CLI доверенный Docker launcher делает root exec
только фиксированного execute.py, который необратимо сбрасывает права до
запуска указанной команды. Не запускайте вручную root-команды внутри агента.

Образы приложений и адаптеров доверенные; произвольный вредоносный OCI-образ
не становится безопасным только из-за профиля. Windows/macOS-only клиенты,
host services, KVM/GPU/USB, требование privileged не поддерживаются.
Новые VPN добавляются кодовым адаптером по [контракту](adapters/README.md).

## Проверки

```bash
python3 -m unittest discover -s tests -v
python3 -m compileall -q agentboxlib runtime tests
# Только тестовые ресурсы agentbox-smoke, без настоящего VPN:
python3 tests/smoke.py
python3 tests/smoke.py down
# Более длительные, прерывающие только свои тестовые контейнеры:
python3 tests/fault_smoke.py
python3 tests/wireguard_fixture.py
# На настроенном профиле с отдельным VPN:
./agentbox test
# Прерывает сеть текущего профиля и восстанавливает gateway:
./agentbox test --faults
```

Smoke намеренно обходит VPN health dependency только в тестовом проекте,
чтобы испытать закрытую сеть и GUI без credentials. Рабочий start этого не делает.
`test` выдаёт точный JSON; пропущенный capture/сценарий не объявляется пройденным.
Пробы — ограниченное свидетельство, не математическое доказательство отсутствия
любого обхода. Для полного аудита нужен capture на uplink и повторение аварий.

Capture: возьмите uplink имя bridge из `docker network inspect
agentbox-NAME-HASH_uplink`, включите `tcpdump -n -i BRIDGE` с фильтром исходного IP
шлюза из runtime/network.json; разрешены только endpoint IP/transport/port и
ARP к gateway. Сопоставьте с физическим интерфейсом и host VPN, не пишите
payload/ключи. Не очищайте общие nftables/iptables и не перезапускайте Docker.

## Обновление и удаление

Сохраните работу, `./agentbox stop`, пересоберите образы, затем start.
Сборка Xray закреплена на 26.11.9, SHA256 сверяется с upstream `.dgst` по TLS;
это не независимая подпись. Debian-пакеты проверяются apt, базовые tags могут
меняться: для воспроизводимого выпуска используйте BASE_IMAGE с `@sha256` и
свои закреплённые client binaries. Ни фоновых обновлений, ни автозагрузки нет.

После stop удалить данные можно вручную, указав **только** volumes своего
проекта `agentbox-NAME-HASH_home` и `agentbox-NAME-HASH_workspace`, затем приватный
каталог его профиля. Это удалит входы и файлы агента. Не используйте Docker
prune и не удаляйте ресурсы Claude/других проектов.


WireGuard fixture создаёт локальную тестовую Docker-подсеть `11.254.253.0/29`
с публичным по форме endpoint, чтобы не ослаблять production-валидатор.
Адрес 1.1.1.1 внутри peer — локальный тестовый responder. Проверка не означает
успешный выход к Cloudflare или внешнему VPN. Подсеть проверяется на пересечение
с уже существующими Docker-сетями, все fixture-ресурсы удаляются автоматически.
