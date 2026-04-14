# novpn

`novpn` — статический web-интерфейс для подготовки и редактирования `amnezia_sites.json` для split-tunnel в AmneziaVPN. Приложение открывается в браузере, позволяет загружать текущий JSON, редактировать правила, проверять записи и скачивать обновлённый файл.

В сервис уже встроены два каталога:

- русские сервисы для сценария `Адреса из списка не должны открываться через VPN`
- популярные зарубежные сервисы для сценария `Адреса из списка должны открываться через VPN`

Список можно как отредактировать на основе уже выгруженного файла из приложения, так и собрать с нуля прямо в сервисе. Список, сформированный с нуля в `novpn`, без проблем импортируется в приложение AmneziaVPN.

## Как выгрузить и загрузить список split tunnel в AmneziaVPN

### Как выгрузить текущий список

1. Прервать текущее подключение VPN.
2. На основном экране нажать на `Раздельное туннелирование включено/выключено`.
3. Выбрать `Раздельное туннелирование сайтов`.
4. Справа от поля ввода адреса нажать `3 точки`.
5. Выбрать `Сохранить список сайтов`.
6. Открыть сохранённый файл в `novpn` для последующего редактирования.

### Как загрузить новый список

1. Прервать текущее подключение VPN.
2. На основном экране нажать на `Раздельное туннелирование включено/выключено`.
3. Выбрать `Раздельное туннелирование сайтов`.
4. Справа от поля ввода адреса нажать `3 точки`.
5. Выбрать `Импорт`.
6. Указать файл, который был подготовлен в `novpn`.

# Разворот сервиса на своём сервере

## Требования
Для работы сервис нужно раздавать по HTTP/HTTPS. Прямой запуск `public/index.html` через `file://` не подходит.

- `git`
- один из вариантов запуска:
  - установленный `nginx`
  - или `Docker` с `docker compose`

## Получение проекта

```bash
git clone https://github.com/poznik/novpn.git
cd novpn
```

## Развертывание в проде через nginx

Пример ниже поднимает сайт на сервере через системный `nginx` на порту `8099`.

### 1. Скопировать проект на сервер

```bash
cd /var/www
git clone https://github.com/poznik/novpn.git
```

### 2. Создать конфиг nginx

```bash
sudo nano /etc/nginx/sites-available/novpn
```

```nginx
server {
    listen 8099;
    server_name _;

    root /var/www/novpn/public;
    index index.html;

    location / {
        try_files $uri $uri/ =404;
        add_header Cache-Control "no-cache";
    }
}
```

### 3. Включить сайт

```bash
sudo ln -s /etc/nginx/sites-available/novpn /etc/nginx/sites-enabled/novpn
sudo rm -f /etc/nginx/sites-enabled/default
```

### 4. Проверить конфиг и перезапустить nginx

```bash
sudo nginx -t
sudo systemctl reload nginx
```

### 5. Открыть сервис

```text
http://IP_СЕРВЕРА:8099/
```

### 6. Если включён firewall, открыть порт

```bash
sudo ufw allow 8099/tcp
```

## Развертывание на локальном nginx

Если `nginx` установлен локально на вашей машине, можно поднять проект точно так же.

### 1. Клонировать проект

```bash
git clone https://github.com/poznik/novpn.git
cd novpn
```

### 2. Создать локальный конфиг nginx

```nginx
server {
    listen 8099;
    server_name localhost 127.0.0.1;

    root /ABS/PATH/TO/novpn/public;
    index index.html;

    location / {
        try_files $uri $uri/ =404;
        add_header Cache-Control "no-cache";
    }
}
```

### 3. Подключить конфиг и перезапустить nginx

Команды зависят от ОС и способа установки `nginx`, но общий порядок такой:

```bash
nginx -t
nginx -s reload
```

### 4. Открыть сервис

```text
http://localhost:8099/
```

## Развертывание через Docker

```bash
git clone https://github.com/poznik/novpn.git
cd novpn
docker compose up -d --build
```

После запуска сервис будет доступен по адресу:

```text
http://localhost:8099/
```

Остановить контейнеры:

```bash
docker compose down
```

## Обновление в проде

Если проект уже развернут:

```bash
cd /var/www/novpn
git pull
sudo systemctl reload nginx
```
