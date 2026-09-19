# Запуск и размещение

## Локально через Docker

Из корня репозитория:

```bash
docker compose up --build
```

Интерфейс: http://localhost:8080. Документация API: http://localhost:8000/docs.
Два контейнера: React SPA через nginx и отдельный FastAPI. nginx направляет `/api/`
на backend, поэтому браузер работает с одним origin. Все вычисления выполняет API.

## Локальная разработка

Нужны Python 3.12 и Node.js 22 LTS с npm.

```bash
python -m venv .venv
```

Windows PowerShell:

```powershell
.venv/Scripts/python -m pip install -r requirements-dev.txt
cd frontend
npm ci
cd ..
.venv/Scripts/python tools/dev.py
```

Linux/macOS:

```bash
.venv/bin/python -m pip install -r requirements-dev.txt
cd frontend
npm ci
cd ..
.venv/bin/python tools/dev.py
```

Интерфейс разработки: http://localhost:5173. Vite проксирует `/api/` на порт 8000.

## Render

`render.yaml` описывает отдельный бесплатный Python Web Service и Static Site.
Подключите GitHub-репозиторий `https://github.com/listeik/project_for_xak`
через **New → Blueprint** в Render и выберите ветку `master`.
Перед первым развёртыванием задайте:

- `VITE_API_BASE_URL` у фронтенда: HTTPS origin бэкенда без завершающего `/api/v1`.
- `ALLOWED_ORIGINS` у бэкенда: HTTPS origin фронтенда; несколько адресов разделяются запятыми.

Эти значения являются адресами, а не секретами. Секреты нельзя включать в переменные `VITE_*`,
поскольку они попадают в браузерную сборку.

Автодеплой использует `commit`: новая версия разворачивается после каждого push
в подключённую ветку GitHub, без ожидания CI. Автотесты пока отложены;
CI устанавливает зависимости, проверяет комплектность исходных данных,
компилирует Python и собирает фронтенд.
Путь проверки здоровья: `/api/v1/health`. Для SPA задан возврат `index.html` на клиентских маршрутах.

Используйте реальные адреса, показанные Render: имена поддоменов могут отличаться
от имён сервисов. После изменения `VITE_API_BASE_URL` пересоберите фронтенд;
эта переменная включается в браузерную сборку. После изменения `ALLOWED_ORIGINS`
перезапустите или переразверните бэкенд.

Remote `origin` остаётся на GitVerse. Remote `github` указывает на
`https://github.com/listeik/project_for_xak.git`. Обновление сайта запускается командой:

```bash
git push github master
```

Изменения должны быть предварительно закоммичены. Push только в `origin`
не обновляет GitHub и не запускает Render. Автоматическая синхронизация двух
репозиториев не включена.

## Ограничения бесплатного сервера

Render Free засыпает после 15 минут без трафика; запуск после простоя занимает около минуты.
Память ограничена 512 МБ, поэтому массовые расчёты нужно предварительно измерить.
Файловая система сервера непостоянна. Приложение сохраняет планы через скачивание JSON
и повторную загрузку; выгрузки формируются в памяти. Пользовательские планы не хранятся
в глобальных переменных сервера. Пользовательские аккаунты и общая база планов в эту версию
не входят.

Источники: [Render Free](https://render.com/docs/free),
[автоматическое развёртывание](https://render.com/docs/deploys),
[GitVerse CI](https://gitverse.ru/docs/cicd/docs/workflow).
