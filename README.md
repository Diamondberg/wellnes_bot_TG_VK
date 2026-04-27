# Wellness Bot v2 — Шаг 1: Фундамент + БД

## Что в этом шаге

✅ Структура проекта  
✅ Конфиг с валидацией (`core/config.py`)  
✅ Async-подключение к PostgreSQL  
✅ Модели БД с заделом под SaaS (`tenant_id` везде)  
✅ Alembic для миграций  
✅ Скрипт самопроверки  

❌ Бот ещё **НЕ работает** — это придёт на Шаге 3.

---

## Установка (Windows, Python 3.10)

### 1. Распакуй архив

Распакуй проект в удобную папку, например `C:\Projects\wellness_bot_v2\`.

### 2. Создай виртуальное окружение

Открой **PowerShell** или **cmd** в папке проекта:

```powershell
cd C:\Projects\wellness_bot_v2
py -3.10 -m venv venv
venv\Scripts\activate
```

После активации в начале строки появится `(venv)`.

### 3. Поставь зависимости

```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Это займёт 1-2 минуты.

### 4. Поставь PostgreSQL

Если ещё не установлен — см. инструкцию из чата ("Часть 1️⃣").  
Создай базу `wellness_bot` через pgAdmin.

### 5. Создай .env

Скопируй `.env.example` в `.env`:

```powershell
copy .env.example .env
```

Открой `.env` в любом редакторе и заполни:

| Переменная | Что ставить |
|---|---|
| `BOT_TOKEN` | Токен твоего TG-бота от @BotFather |
| `ADMIN_ID` | Твой Telegram ID |
| `DATABASE_URL` | Замени `postgres123` на пароль, который ты задал при установке PostgreSQL |
| `EMAIL_*` | Если нужны email-уведомления — заполни. Иначе оставь пустыми. |
| `PROXY_URL` | Если запускаешь из РФ — заполни. Иначе оставь пустым. |
| `TENANT_*` | Имя/ИНН/контакты "арендатора" (пока это ты сам) |

### 6. Накати миграцию (создаст таблицы в БД)

```powershell
alembic revision --autogenerate -m "initial schema"
alembic upgrade head
```

Первая команда сгенерит файл миграции в `alembic/versions/`.  
Вторая — применит его (создаст таблицы).

### 7. Проверь что всё работает

```powershell
python check_setup.py
```

Если всё ок, увидишь:

```
═══════════════════════════════════════════
  ✅ ШАГ 1 ПРОЙДЕН УСПЕШНО
═══════════════════════════════════════════
```

---

## Проверка через pgAdmin (опционально)

1. Открой pgAdmin → `Servers` → `PostgreSQL 16` → `Databases` → `wellness_bot` → `Schemas` → `public` → `Tables`
2. Должны быть: `tenants`, `users`, `answers`, `referrals`, `alembic_version`
3. Правый клик на `tenants` → `View/Edit Data` → `All Rows` — увидишь свою запись арендатора

---

## Если что-то не получилось

Скопируй **полный текст ошибки** в чат — разберёмся.

Чаще всего проблемы такие:
- ❌ "password authentication failed" → неверный пароль в `DATABASE_URL`
- ❌ "could not connect to server" → PostgreSQL не запущен (запусти службу)
- ❌ "database wellness_bot does not exist" → не создал базу через pgAdmin
- ❌ "ModuleNotFoundError: No module named 'aiogram'" → не активировал venv или не поставил requirements

---

## Структура проекта

```
wellness_bot_v2/
├── .env                    ← твои секреты (создашь сам)
├── .env.example            ← шаблон
├── requirements.txt
├── alembic.ini
├── alembic/
│   ├── env.py
│   ├── script.py.mako
│   └── versions/           ← здесь появятся миграции
├── core/
│   ├── __init__.py
│   └── config.py           ← конфиг (pydantic)
├── db/
│   ├── __init__.py
│   ├── engine.py           ← async-движок
│   └── models.py           ← Tenant, User, Answer, Referral
├── platforms/
│   ├── telegram/           ← (пусто, будет на Шаге 3)
│   ├── vk/                 ← (для будущего)
│   └── max/                ← (для будущего)
└── check_setup.py          ← самопроверка
```
