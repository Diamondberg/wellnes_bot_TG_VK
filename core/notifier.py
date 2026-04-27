"""
Отправка email-уведомлений админу.

Использует aiosmtplib (async) — не блокирует event loop.

Поддерживает:
  - HTML-тело письма (красивая вёрстка с цветными блоками)
  - Вложения (TXT, XLSX)
  - Запасной путь — если email отключён в конфиге, функция просто молча выходит

Использование:
    from core.notifier import send_lead_email

    await send_lead_email(
        user=user_snapshot,
        result=test_result,
        txt_bytes=...,
        xlsx_bytes=...,
        txt_filename="report.txt",
        xlsx_filename="report.xlsx",
    )
"""

import logging
from email.message import EmailMessage
from typing import Optional

import aiosmtplib

from core.config import settings
from core.reports import UserSnapshot
from core.test_engine import TestResult

logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════
#  Шаблон HTML-письма
# ════════════════════════════════════════════════════════════
def _build_html_body(user: UserSnapshot, result: TestResult) -> str:
    """Формируем красивый HTML для тела письма."""
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
            <p style="margin:0 0 4px 0"><b>🎁 Реферал от:</b> {user.referrer_name}</p>
            {f'<p style="margin:0;font-size:14px;color:#666">Тел: {user.referrer_phone}</p>' if user.referrer_phone else ""}
        </div>
        """

    system_blocks = []
    for sr in result.systems:
        text_color, bg_color = css_map[sr.status.value]
        system_blocks.append(f"""
        <div style="background:{bg_color};border-left:4px solid {text_color};padding:10px 14px;margin:6px 0;border-radius:4px">
            <p style="margin:0">
                <b>{sr.status.emoji} {sr.system_name}</b> &nbsp;
                <span style="color:{text_color};font-weight:bold">{sr.score}/{sr.max_score} ({sr.percentage:.0f}%)</span>
            </p>
            <p style="margin:4px 0 0 0;font-size:13px;color:#555">{sr.recommendation}</p>
        </div>
        """)
    systems_html = "".join(system_blocks)

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
        <p style="margin:4px 0"><b>👤 ФИО:</b> {user.full_name}</p>
        <p style="margin:4px 0"><b>📱 Телефон:</b> <a href="tel:{user.phone}" style="color:#1976D2;text-decoration:none">{user.phone}</a></p>
        <p style="margin:4px 0"><b>📡 Платформа:</b> {user.platform}</p>
        <p style="margin:4px 0"><b>🆔 User ID:</b> <code>{user.platform_user_id}</code></p>
        {f'<p style="margin:4px 0"><b>✈️ Username:</b> @{user.platform_username}</p>' if user.platform_username else ""}
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
#  Отправка письма
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
        logger.info(f"✅ Email отправлен на {to_addr}")
        return True
    except aiosmtplib.errors.SMTPException as e:
        logger.error(f"❌ SMTP-ошибка при отправке email: {e}")
        return False
    except Exception as e:
        logger.error(f"❌ Не удалось отправить email: {e}")
        return False
