"""
Отправка email-уведомлений.

Использует aiosmtplib (async) — не блокирует event loop.

Две функции:
  - send_lead_email   — АДМИНУ: полный отчёт + сегментация лида + Excel + TXT
  - send_user_report  — ЮЗЕРУ:  дружелюбное письмо + таблица + дисклеймер
                                + CTA «связаться с консультантом»
                                + баннер магазина (БЕЗ вложений)

Использование:
    from core.notifier import send_lead_email, send_user_report
"""

import logging
from email.message import EmailMessage
from html import escape
from typing import Optional

import aiosmtplib

from core.config import settings
from core.reports import DISCLAIMER, UserSnapshot
from core.test_engine import TestResult

logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════
#  HTML для письма АДМИНУ
# ════════════════════════════════════════════════════════════
def _build_html_body(user: UserSnapshot, result: TestResult) -> str:
    """Формируем красивый HTML для тела письма админу (с сегментацией лида)."""
    css_map = {
        "good": ("#4CAF50", "#E8F5E9"),
        "warning": ("#FF9800", "#FFF3E0"),
        "critical": ("#F44336", "#FFEBEE"),
    }

    if result.critical_count >= 3:
        segment = ("🔥 ГОРЯЧИЙ ЛИД", "#D32F2F",
                   f"{result.critical_count} систем в критическом состоянии")
    elif result.critical_count >= 1:
        segment = ("🟠 ТЁПЛЫЙ ЛИД", "#F57C00",
                   f"{result.critical_count} критическая система, {result.warning_count} warning")
    elif result.warning_count >= 3:
        segment = ("🟡 ВНИМАТЕЛЬНЫЙ ЛИД", "#FBC02D",
                   f"{result.warning_count} warning'ов")
    else:
        segment = ("🟢 ХОЛОДНЫЙ ЛИД", "#388E3C", "всё неплохо")

    referrer_block = ""
    if user.referrer_name:
        referrer_block = f"""
        <div style="background:#FFF8E1;border-left:4px solid #FFA000;padding:10px 14px;margin:12px 0;border-radius:4px">
            <p style="margin:0 0 4px 0"><b>🎁 Реферал от:</b> {escape(user.referrer_name)}</p>
            {f'<p style="margin:0;font-size:14px;color:#666">Тел: {escape(user.referrer_phone)}</p>' if user.referrer_phone else ""}
        </div>
        """

    system_blocks = []
    for sr in result.systems:
        text_color, bg_color = css_map[sr.status.value]
        system_blocks.append(f"""
        <div style="background:{bg_color};border-left:4px solid {text_color};padding:10px 14px;margin:6px 0;border-radius:4px">
            <p style="margin:0">
                <b>{sr.status.emoji} {escape(sr.system_name)}</b> &nbsp;
                <span style="color:{text_color};font-weight:bold">{sr.score}/{sr.max_score} ({sr.percentage:.0f}%)</span>
            </p>
            <p style="margin:4px 0 0 0;font-size:13px;color:#555">{escape(sr.recommendation)}</p>
        </div>
        """)
    systems_html = "".join(system_blocks)

    username_block = (
        f'<p style="margin:4px 0"><b>✈️ Username:</b> @{escape(user.platform_username)}</p>'
        if user.platform_username else ""
    )

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"></head>
<body style="font-family:Arial,sans-serif;line-height:1.5;color:#333;background:#f5f5f5;margin:0;padding:20px">
  <div style="max-width:680px;margin:0 auto;background:#fff;border-radius:8px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.08)">

    <div style="background:#4CAF50;color:#fff;padding:24px;text-align:center">
      <h2 style="margin:0;font-size:22px">🔔 ЗАЯВКА #{user.lead_number}</h2>
      <p style="margin:6px 0 0 0;font-size:14px;opacity:0.9">Wellness Test Bot</p>
    </div>

    <div style="padding:20px 24px">

      <div style="background:{segment[1]};color:#fff;padding:10px 14px;border-radius:4px;text-align:center;margin-bottom:16px">
        <p style="margin:0;font-weight:bold;font-size:16px">{segment[0]}</p>
        <p style="margin:2px 0 0 0;font-size:13px;opacity:0.95">{segment[2]}</p>
      </div>

      <div style="background:#FAFAFA;padding:14px;border-radius:4px;margin-bottom:14px">
        <p style="margin:4px 0"><b>👤 ФИО:</b> {escape(user.full_name)}</p>
        <p style="margin:4px 0"><b>📱 Телефон:</b> <a href="tel:{escape(user.phone)}" style="color:#1976D2;text-decoration:none">{escape(user.phone)}</a></p>
        <p style="margin:4px 0"><b>📡 Платформа:</b> {escape(user.platform)}</p>
        <p style="margin:4px 0"><b>🆔 User ID:</b> <code>{user.platform_user_id}</code></p>
        {username_block}
      </div>

      {referrer_block}

      <h3 style="color:#4CAF50;border-bottom:2px solid #4CAF50;padding-bottom:8px;margin:20px 0 12px 0">
        📊 Результаты по системам
      </h3>
      {systems_html}

      <p style="margin-top:24px;padding-top:14px;border-top:1px solid #eee;font-size:12px;color:#999;text-align:center">
        К письму приложены подробные отчёты в форматах TXT и Excel.<br>
        Wellness Test Bot — автоматическое уведомление.
      </p>

    </div>
  </div>
</body></html>"""


# ════════════════════════════════════════════════════════════
#  Отправка письма АДМИНУ
# ════════════════════════════════════════════════════════════
async def send_lead_email(
    user: UserSnapshot,
    result: TestResult,
    txt_bytes: bytes,
    xlsx_bytes: bytes,
    txt_filename: str = "report.txt",
    xlsx_filename: str = "report.xlsx",
    recipient: Optional[str] = None,
) -> bool:
    """
    Отправить письмо админу по итогам прохождения теста.

    Возвращает True если отправлено, False если email отключён или ошибка.
    Не падает при ошибках — только логирует.
    """
    if not settings.email_enabled:
        logger.info("📧 Email отключён в конфиге — пропускаем отправку")
        return False

    to_addr = recipient or settings.email_to
    if not to_addr:
        logger.warning("📧 Не указан адресат — пропускаем отправку")
        return False

    if result.critical_count >= 3:
        subject_marker = "🔥"
    elif result.critical_count >= 1:
        subject_marker = "🟠"
    elif result.warning_count >= 3:
        subject_marker = "🟡"
    else:
        subject_marker = "🟢"

    subject = (
        f"{subject_marker} Заявка #{user.lead_number}: "
        f"{user.full_name} | {user.phone}"
    )

    msg = EmailMessage()
    msg["From"] = settings.email_user
    msg["To"] = to_addr
    msg["Subject"] = subject

    msg.set_content(
        f"Заявка #{user.lead_number}\n"
        f"ФИО: {user.full_name}\n"
        f"Телефон: {user.phone}\n\n"
        f"Подробности — в HTML-версии письма и приложенных файлах."
    )

    msg.add_alternative(_build_html_body(user, result), subtype="html")

    msg.add_attachment(
        txt_bytes,
        maintype="text",
        subtype="plain",
        filename=txt_filename,
    )
    msg.add_attachment(
        xlsx_bytes,
        maintype="application",
        subtype="vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=xlsx_filename,
    )

    try:
        await aiosmtplib.send(
            msg,
            hostname=settings.email_host,
            port=settings.email_port,
            start_tls=True,
            username=settings.email_user,
            password=settings.email_password,
            timeout=30,
        )
        logger.info(f"✅ Email админу отправлен на {to_addr}")
        return True
    except aiosmtplib.errors.SMTPException as e:
        logger.error(f"❌ SMTP-ошибка при отправке письма админу: {e}")
        return False
    except Exception as e:
        logger.error(f"❌ Не удалось отправить письмо админу: {e}")
        return False


# ════════════════════════════════════════════════════════════
#  Баннер магазина для письма ЮЗЕРУ
# ════════════════════════════════════════════════════════════
def _build_shop_banner_html() -> str:
    """
    Баннер «загляните в магазин» под кнопкой консультанта.

    Сейчас: один статичный баннер из настроек.

    В будущем (отдельный шаг): здесь будет логика выбора баннера в зависимости
    от результатов теста — например, разные офферы для проблем с ЖКТ,
    нервной системой и т.д. Поэтому функция уже изолирована — потом просто
    примет на вход TestResult и будет выбирать нужный шаблон.
    """
    title = escape(settings.shop_banner_title)
    text = escape(settings.shop_banner_text)
    button = escape(settings.shop_banner_button)
    url = escape(settings.shop_banner_url)
    emoji = settings.shop_banner_emoji  # эмодзи не эскейпим — это юникод-символ

    # Тёплый оранжево-розовый градиент — отличается от зелёного консультанта,
    # чтобы юзер визуально различал «связаться» и «магазин»
    return f"""
    <div style="background:linear-gradient(135deg,#FFF3E0 0%,#FCE4EC 100%);border:1px solid #FFCCBC;border-radius:10px;padding:20px;margin:16px 0;text-align:center">
        <div style="font-size:32px;line-height:1;margin-bottom:8px">{emoji}</div>
        <p style="margin:0 0 6px 0;font-size:15px;color:#BF360C;font-weight:600">
          {title}
        </p>
        <p style="margin:0 0 14px 0;font-size:13px;color:#5D4037;line-height:1.5">
          {text}
        </p>
        <a href="{url}"
           style="display:inline-block;background:#FF7043;color:#fff;text-decoration:none;padding:11px 24px;border-radius:8px;font-size:14px;font-weight:500">
          {button}
        </a>
    </div>
    """


# ════════════════════════════════════════════════════════════
#  HTML для письма ЮЗЕРУ
# ════════════════════════════════════════════════════════════
def _build_user_html_body(user: UserSnapshot, result: TestResult) -> str:
    """
    Формируем HTML для письма ЮЗЕРУ.

    Отличия от админского:
      - дружелюбный тон ("Спасибо за прохождение")
      - НЕТ сегментации ("горячий лид" и т.п.) — это внутренняя кухня
      - НЕТ telegram user_id, username, инфы о реферере
      - ЕСТЬ CTA-баннер «связаться с консультантом»
      - ЕСТЬ баннер магазина под ним
      - дисклеймер заметнее
    """
    # Цвета по статусам — мягче, без "F44336" в лоб юзеру
    css_map = {
        "good":     ("#2E7D32", "#E8F5E9", "Всё в порядке"),
        "warning":  ("#E65100", "#FFF3E0", "Требуется внимание"),
        "critical": ("#C62828", "#FFEBEE", "Рекомендуется консультация"),
    }

    # Таблица результатов
    rows_html = []
    for sr in result.systems:
        text_color, bg_color, status_label = css_map[sr.status.value]
        rows_html.append(f"""
        <tr>
          <td style="padding:10px 12px;border-bottom:1px solid #eee;background:{bg_color}">
            <b>{sr.status.emoji} {escape(sr.system_name)}</b>
          </td>
          <td style="padding:10px 12px;border-bottom:1px solid #eee;text-align:center;background:{bg_color};font-weight:bold;color:{text_color};white-space:nowrap">
            {sr.percentage:.0f}%
          </td>
          <td style="padding:10px 12px;border-bottom:1px solid #eee;background:{bg_color};color:{text_color};font-size:13px;white-space:nowrap">
            {status_label}
          </td>
        </tr>
        """)
    table_rows = "".join(rows_html)

    # Дисклеймер из core/reports.py — превращаем в HTML-абзацы
    disclaimer_paragraphs = "".join(
        f'<p style="margin:6px 0;font-size:13px;color:#555;line-height:1.6">{escape(line)}</p>'
        for line in DISCLAIMER.split("\n") if line.strip()
    )

    consultant_url = escape(settings.consultant_contact_url)
    shop_banner = _build_shop_banner_html()

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"></head>
<body style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Arial,sans-serif;line-height:1.5;color:#333;background:#f5f5f5;margin:0;padding:20px">
  <div style="max-width:600px;margin:0 auto;background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.08)">

    <!-- Шапка -->
    <div style="background:linear-gradient(135deg,#1D9E75 0%,#34B587 100%);color:#fff;padding:28px 24px;text-align:center">
      <h1 style="margin:0;font-size:24px;font-weight:600">🌿 Wellness Test</h1>
      <p style="margin:8px 0 0 0;font-size:15px;opacity:0.95">Спасибо за прохождение теста!</p>
    </div>

    <div style="padding:24px">

      <!-- Приветствие -->
      <p style="margin:0 0 14px 0;font-size:15px;color:#333">
        Здравствуйте, <b>{escape(user.full_name)}</b>!
      </p>
      <p style="margin:0 0 20px 0;font-size:14px;color:#555;line-height:1.6">
        Вы прошли наш экспресс-тест на состояние основных систем организма.
        Ниже — ваши результаты. Скоро с вами свяжется консультант
        для подробной расшифровки.
      </p>

      <!-- Таблица результатов -->
      <h3 style="color:#1D9E75;font-size:16px;margin:20px 0 12px 0;border-bottom:2px solid #1D9E75;padding-bottom:6px">
        📊 Результаты по системам
      </h3>
      <table style="width:100%;border-collapse:collapse;border-radius:6px;overflow:hidden;margin-bottom:20px">
        <thead>
          <tr style="background:#FAFAFA">
            <th style="padding:10px 12px;text-align:left;font-size:13px;color:#666;border-bottom:1px solid #ddd">Система</th>
            <th style="padding:10px 12px;text-align:center;font-size:13px;color:#666;border-bottom:1px solid #ddd">Балл</th>
            <th style="padding:10px 12px;text-align:left;font-size:13px;color:#666;border-bottom:1px solid #ddd">Статус</th>
          </tr>
        </thead>
        <tbody>
          {table_rows}
        </tbody>
      </table>

      <!-- CTA: связаться с консультантом -->
      <div style="background:linear-gradient(135deg,#E8F5E9 0%,#F1F8F4 100%);border:1px solid #C8E6C9;border-radius:10px;padding:18px;margin:24px 0 0 0;text-align:center">
        <p style="margin:0 0 6px 0;font-size:15px;color:#1D9E75;font-weight:600">
          💬 Остались вопросы?
        </p>
        <p style="margin:0 0 14px 0;font-size:13px;color:#555;line-height:1.5">
          Наш консультант поможет разобраться с результатами<br>
          и подскажет, на что стоит обратить внимание.
        </p>
        <a href="{consultant_url}"
           style="display:inline-block;background:#1D9E75;color:#fff;text-decoration:none;padding:11px 24px;border-radius:8px;font-size:14px;font-weight:500">
          Написать консультанту →
        </a>
      </div>

      <!-- Баннер магазина (под кнопкой консультанта) -->
      {shop_banner}

      <!-- Дисклеймер -->
      <div style="background:#FFF8E1;border-left:4px solid #FFB300;padding:14px 16px;border-radius:4px;margin-top:24px">
        <p style="margin:0 0 8px 0;font-size:14px;color:#E65100;font-weight:600">
          ⚠️ Важное уведомление
        </p>
        {disclaimer_paragraphs}
      </div>

      <!-- Подвал -->
      <p style="margin-top:24px;padding-top:14px;border-top:1px solid #eee;font-size:12px;color:#999;text-align:center;line-height:1.6">
        Это письмо отправлено автоматически в ответ на прохождение теста.<br>
        🌿 Берегите своё здоровье!
      </p>

    </div>
  </div>
</body></html>"""


# ════════════════════════════════════════════════════════════
#  Отправка письма ЮЗЕРУ
# ════════════════════════════════════════════════════════════
async def send_user_report(
    user_email: str,
    user: UserSnapshot,
    result: TestResult,
) -> bool:
    """
    Отправить юзеру копию отчёта на его email.

    Отличия от send_lead_email:
      - адресат — email юзера (берётся из формы)
      - НЕТ вложений вообще (ни TXT, ни Excel) — всё в HTML-теле
      - HTML дружелюбный, без сегментации лида
      - есть CTA «связаться с консультантом»
      - есть баннер магазина

    Возвращает True если отправлено, False если SMTP не настроен или ошибка.
    Не падает при ошибках — только логирует.
    """
    if not user_email:
        logger.info("📧 У юзера нет email — пропускаем")
        return False

    if not settings.email_smtp_configured:
        logger.info("📧 SMTP не настроен — пропускаем отправку юзеру")
        return False

    subject = f"🌿 Ваши результаты Wellness Test — заявка #{user.lead_number}"

    msg = EmailMessage()
    msg["From"] = settings.email_user
    msg["To"] = user_email
    msg["Subject"] = subject

    # Plain-text fallback (для почтовиков без HTML).
    # Не дублируем сюда детальный отчёт — этот текст видят только в редких
    # клиентах без HTML-рендеринга, которых ~0%.
    msg.set_content(
        f"Здравствуйте, {user.full_name}!\n\n"
        f"Спасибо за прохождение Wellness Test. Заявка #{user.lead_number}.\n\n"
        f"Подробные результаты — в HTML-версии этого письма.\n\n"
        f"Связаться с консультантом: {settings.consultant_contact_url}\n\n"
        f"--\n"
        f"Это письмо отправлено автоматически.\n"
        f"Берегите своё здоровье! 🌿"
    )

    msg.add_alternative(_build_user_html_body(user, result), subtype="html")

    # ВАЖНО: НИКАКИХ вложений в письме юзеру.
    # Полный детальный отчёт (TXT/Excel) идёт ТОЛЬКО админу, см. send_lead_email.

    try:
        await aiosmtplib.send(
            msg,
            hostname=settings.email_host,
            port=settings.email_port,
            start_tls=True,
            username=settings.email_user,
            password=settings.email_password,
            timeout=30,
        )
        logger.info(f"✅ Email юзеру отправлен на {user_email}")
        return True
    except aiosmtplib.errors.SMTPException as e:
        logger.error(f"❌ SMTP-ошибка при отправке письма юзеру ({user_email}): {e}")
        return False
    except Exception as e:
        logger.error(f"❌ Не удалось отправить письмо юзеру ({user_email}): {e}")
        return False
