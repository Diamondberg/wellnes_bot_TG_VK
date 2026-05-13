"""
Валидация launch params от VK Mini App.

Как работает VK:
  При открытии Mini App VK дописывает в URL параметры вида
  ?vk_user_id=123&vk_app_id=54517827&...&sign=BASE64URL_HMAC
  Параметр `sign` — это HMAC-SHA256 от отсортированной строки
  остальных vk_* параметров, ключ — secure_key приложения.

Фронт берёт `window.location.search` (без ведущего '?') и шлёт сюда.
Если подпись валидна → возвращаем vk_user_id (фронт сохраняет, бэк доверяет).
Если нет → 401.
"""

import base64
import hashlib
import hmac
from urllib.parse import parse_qsl

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from core.config import settings

router = APIRouter()


class VKAuthRequest(BaseModel):
    """Строка launch params как пришла из window.location.search (без '?')."""
    launch_params: str


class VKAuthResponse(BaseModel):
    ok: bool
    vk_user_id: int
    vk_app_id: int


def _verify_launch_params(query_string: str, secure_key: str) -> dict | None:
    """
    Проверка подписи VK launch params.

    Алгоритм (документация VK):
      1. Распарсить query string в пары (key, value).
      2. Оставить только пары, где key начинается с 'vk_'.
      3. Отсортировать по ключу.
      4. Собрать обратно в строку 'k1=v1&k2=v2&...'.
      5. HMAC-SHA256 от этой строки с ключом secure_key.
      6. Закодировать в base64url БЕЗ паддинга ('=' в конце убрать).
      7. Сравнить с параметром 'sign' из исходной строки.

    Возвращает dict с vk_* параметрами при успехе, иначе None.
    """
    # parse_qsl сохраняет порядок и не теряет пустые значения
    pairs = parse_qsl(query_string, keep_blank_values=True)
    if not pairs:
        return None

    sign = None
    vk_pairs = []
    for k, v in pairs:
        if k == "sign":
            sign = v
        elif k.startswith("vk_"):
            vk_pairs.append((k, v))

    if not sign or not vk_pairs:
        return None

    vk_pairs.sort(key=lambda kv: kv[0])
    canonical = "&".join(f"{k}={v}" for k, v in vk_pairs)

    digest = hmac.new(
        secure_key.encode("utf-8"),
        canonical.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    expected = base64.urlsafe_b64encode(digest).decode("utf-8").rstrip("=")

    if not hmac.compare_digest(expected, sign):
        return None

    return dict(vk_pairs)


@router.post("/vk/verify", response_model=VKAuthResponse)
async def vk_verify(req: VKAuthRequest):
    """Проверить подпись VK launch params, вернуть vk_user_id."""
    params = _verify_launch_params(req.launch_params, settings.vk_secure_key)
    if params is None:
        raise HTTPException(status_code=401, detail="Invalid VK signature")

    # Дополнительно: убедимся, что приложение — наше
    app_id_str = params.get("vk_app_id", "")
    try:
        app_id = int(app_id_str)
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid vk_app_id")
    if app_id != settings.vk_app_id:
        raise HTTPException(status_code=401, detail="Wrong app")

    try:
        vk_user_id = int(params.get("vk_user_id", ""))
    except ValueError:
        raise HTTPException(status_code=401, detail="Missing vk_user_id")

    return VKAuthResponse(ok=True, vk_user_id=vk_user_id, vk_app_id=app_id)