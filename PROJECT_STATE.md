# Wellness Test Bot — состояние проекта

**Последнее обновление:** 12.05.2026
**Текущий чат:** VK Mini App — интеграция (реквизиты получены, начинаем код)

---

## 1. Инфраструктура

| Параметр | Значение |
|---|---|
| Сервер | `81.177.3.73` (Debian 11) |
| Python | 3.11 |
| Путь к проекту на сервере | `/opt/well_test_tg` |
| Домен Mini App | `https://app.wellnesstest.ru` (HTTPS, Let's Encrypt) |
| Лендинг | `wellnesstest.ru` (отдельный shared-хостинг, **не трогаем**) |
| Локальный путь (Windows) | `C:\wellness_bot_vk_tg` |
| Репозиторий | github.com/Diamondberg/wellnes_bot_TG_VK |
| БД | PostgreSQL 13, `wellness_db`, юзер `wellness` |
| Systemd-сервисы | `wellness-api.service`, `wellness-bot.service` |
| TG-бот | @WellnessTest_bot (aiogram 3.13) |
| ВК-группа | vk.com/zdorovyakov (group ID = `142579735`) |
| VK Mini App | App ID = `54517827` |

### VK credentials (значения — только в `.env` на сервере, НЕ в чат)
- `VK_APP_ID` — публичный, можно в чате (`54517827`)
- `VK_GROUP_ID` — публичный (`142579735`)
- `VK_SECURE_KEY` — **секрет**, только в `.env`
- `VK_SERVICE_TOKEN` — **секрет**, только в `.env`
- `VK_COMMUNITY_TOKEN` — **секрет**, права `messages` + `manage`, только в `.env`

### SSH-подсказка
```
ssh -o ServerAliveInterval=60 root@81.177.3.73
```

### Деплой
```
# локально (Windows)
cd C:\wellness_bot_vk_tg
git add <files>
git commit -m "..."
git push origin main

# на сервере
cd /opt/well_test_tg
git pull
sudo systemctl restart wellness-api
sudo systemctl restart wellness-bot   # если правил bot/
```

---

## 2. Что готово

- ✅ Шаг 1: фундамент + БД (модели с `tenant_id` под SaaS)
- ✅ Шаг 2: API (FastAPI)
- ✅ Шаг 3: TG-бот (aiogram 3.13)
- ✅ Шаг 4: Mini App (фронт на Alpine.js)
- ✅ Шаг 4.5: email юзеру с результатами
- ✅ Шаг 5.1: реферальная система (ссылки `?start=invite_<id>`)
- ✅ Шаг 5.2: дистрибьютор (фоллбэк-реферер)
- ✅ Баг с `tg_user_id=999000111` на TG Desktop
- ✅ Баг с остаточными данными при смене TG-юзера на смартфоне (12.05.2026)
- ✅ VK Mini App зарегистрирован, реквизиты получены (12.05.2026)

---

## 3. В работе сейчас — VK Mini App, интеграция

**Стадия:** реквизиты на руках, переходим к коду. План пошагово, чтобы не сломать TG-ветку.

### Шаг VK-1 — конфиг и `.env` (фундамент)
- [ ] В `core/config.py` (или где у нас Settings) добавить поля:
  - `vk_app_id: int`
  - `vk_group_id: int`
  - `vk_secure_key: str`
  - `vk_service_token: str`
  - `vk_community_token: str`
- [ ] Дописать в `.env` на сервере (значения подставит пользователь сам).
- [ ] Локальный `.env.example` обновить (без значений, только ключи).
- [ ] Проверить, что `check_setup.py` валидирует наличие новых переменных.

### Шаг VK-2 — БД
- [ ] Поле `vk_user_id` в модели User уже должно быть (проверить). Если нет — миграция alembic.
- [ ] Корректно проставлять `first_platform` (`tg` / `vk`) при первой регистрации.
- [ ] Мэтчинг по телефону в рамках `tenant_id` остаётся; добавляется связь `vk_user_id` ↔ существующая запись, если телефон совпал.

### Шаг VK-3 — бэкенд: валидация VK launch params
- [ ] Endpoint `POST /api/vk/auth` (или в существующий auth-роутер):
  - принимает строку launch params от фронта,
  - проверяет подпись по `secure_key` (стандартный алгоритм VK: HMAC-SHA256 от отсортированных `vk_*` параметров, потом base64url),
  - возвращает наш внутренний токен/сессию ровно как для TG.
- [ ] Ошибка подписи → 401. Никаких "если не сходится — пускаем".

### Шаг VK-4 — фронт: определение платформы
- [ ] В `frontend/index.html` добавить детектор:
  - есть `Telegram.WebApp.initData` → платформа `tg` (как сейчас),
  - есть VK launch params в URL (`vk_user_id`, `vk_app_id`, `sign`...) → платформа `vk`, подключить VK Bridge,
  - иначе → `browser` (текущее поведение с заглушкой).
- [ ] VK Bridge: `<script src="https://unpkg.com/@vkontakte/vk-bridge/dist/browser.min.js"></script>` и `vkBridge.send('VKWebAppInit')`.
- [ ] `ownerId` для localStorage: для VK берём `vk_user_id` из launch params.

### Шаг VK-5 — VK-бот (Long Poll группы)
- [ ] Отдельный процесс/сервис (по аналогии с `wellness-bot.service`), либо доп. таск в существующем боте.
- [ ] Использовать `vk_api` или `aiohttp` + сырой Long Poll. Решим, когда дойдём.
- [ ] Минимум: приём `message_new`, отправка уведомления рефереру через `messages.send` (community token).

### Шаг VK-6 — шаринг через VK Bridge
- [ ] Кнопки "поделиться на стене / отправить другу": `VKWebAppShare`, `VKWebAppShowWallPostBox`.
- [ ] Реф-ссылка VK: формат `https://vk.com/app54517827#invite_<platform_user_id>` (внутри VK Mini App параметры идут через hash).

**Принципы:**
- Все секреты — только в `.env`, в коде только `settings.vk_*`.
- Никаких хардкодов под "одного арендатора", `tenant_code` остаётся.
- TG-ветку не трогаем без причины. Любая правка `frontend/index.html` — с проверкой, что TG по-прежнему работает.

---

## 4. Бэклог (после VK)

### Доработки
- [ ] Письмо с результатами: кнопки соцсетей (TG/VK/Max) вместо одной зелёной
- [ ] Дизайн на всех платформах — после сбора скриншотов

### Конфигурация (через .env)
- [ ] При необходимости — `SHOP_BANNER_*`

### Большие этапы
- [ ] Max Mini App (после VK)
- [ ] **Монетизация (2)** — копипаст-продажа
- [ ] **Монетизация (3)** — аренда (биллинг, мультитенантность, ЛК, "засыпание")

---

## 5. Модели монетизации (для контекста)

1. **MVP для себя** — текущий этап.
2. **Полная продажа** — деплой клиенту, копипаст + замена `.env`.
3. **Аренда** — мультитенантность + биллинг + ЛК + автоблокировка.

---

## 6. Известные тонкости

- В коде везде `tenant_id`. Сейчас всегда `default` — не убирать, под SaaS.
- Юзеры мэтчатся по **телефону в рамках tenant'а**. Один человек = одна запись на tenant.
- В `frontend/index.html` ключ localStorage: `wellness_app_state_v1`. В стейте `ownerId` (TG/VK user id или null в браузере).
- Реф-ссылка TG: `https://t.me/WellnessTest_bot?start=invite_<platform_user_id>`.
- Реф-ссылка VK (план): `https://vk.com/app54517827#invite_<platform_user_id>`.
- Фоллбэк-реферер = дистрибьютор.
- В браузере вне TG `currentUserPlatformId` возвращает заглушку `999000111` (для генерации реф-ссылок). `ownerId` возвращает `null`. Не путать.

---

## 7. Как использовать этот файл

Перед открытием нового чата:
1. Открой архив проекта.
2. Замени `PROJECT_STATE.md` в корне на актуальную версию.
3. Заархивируй и кинь в новый чат с одним сообщением: "Вот состояние проекта".

В новом чате Claude:
1. Сначала открывает этот файл.
2. Только потом смотрит код.
