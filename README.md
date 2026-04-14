# Amnezia Split-Tunnel Editor

Лёгкое web-приложение для редактирования JSON-файла исключений раздельного туннелирования Amnezia. Вся обработка — в браузере, DNS-резолв через DoH (Cloudflare → Google fallback).

## Dev (локально)

Python 3 (есть на Ubuntu 24.04 из коробки):

```bash
cd public
python3 -m http.server 8099
```

Открыть http://localhost:8099

## Prod (Docker)

```bash
docker compose up -d --build
```

Приложение доступно на http://localhost:8099

## Формат строк редактора

- `10.0.0.0/8` — сеть (CIDR)
- `1.2.3.4` — отдельный IP
- `example.com 1.2.3.4` — домен + IP
- `example.com` — только домен, IP будет дорезолвен при нажатии "Проверить"
