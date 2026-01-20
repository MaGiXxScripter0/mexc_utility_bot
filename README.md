# MEXC Telegram Bot

Telegram бот для получения информации о криптовалютных парах с бирж MEXC и Gate.io.

## Особенности

- Получение информации о фьючерсных контрактах
- Отображение спотовых цен
- Агрегация данных с нескольких бирж
- Поддержка команд в группах
- MarkdownV2 форматирование

## Команды

- `/start` - Приветственное сообщение
- `/mexc <symbol>` - Информация с MEXC (например: `/mexc BTC_USDT`)
- `/gate <symbol>` - Информация с Gate.io (например: `/gate BTC_USDT`)
- `/cex <symbol>` - Агрегированная информация с обеих бирж (например: `/cex BTC`)

## Запуск

### Локально

1. Установите зависимости:
```bash
pip install -r requirements.txt
```

2. Создайте файл `.env` на основе `env.example`:
```bash
cp env.example .env
```

3. Заполните переменные окружения в `.env`

4. Запустите бота:
```bash
python main.py
```

### Docker

1. Создайте файл `.env` на основе `env.example`

2. Соберите и запустите через Docker Compose:
```bash
docker-compose up --build
```

Или в фоне:
```bash
docker-compose up -d --build
```

### Остановка

```bash
docker-compose down
```

## Переменные окружения

- `BOT_TOKEN` - Токен Telegram бота
- `MEXC_API_KEY` - API ключ MEXC
- `MEXC_API_SECRET` - API секрет MEXC
- `GATE_API_KEY` - API ключ Gate.io
- `GATE_API_SECRET` - API секрет Gate.io

## Архитектура

Проект использует чистую архитектуру (Clean Architecture):

- `domain/` - бизнес-логика
- `application/` - сервисы приложения
- `infrastructure/` - внешние зависимости (API клиенты, HTTP клиент)
- `core/` - конфигурация, логирование, утилиты
- `bot/` - обработчики команд Telegram

## Логирование

Логи сохраняются в папку `logs/` при запуске через Docker.
