"""Email crash alerts and error notification helpers."""

import asyncio
import logging
import os
import smtplib
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional, Dict, Any

logger = logging.getLogger("mantra.helpers.alerts")

_last_alert_time: Dict[str, float] = {}
ALERT_COOLDOWN_SECONDS: float = 300.0  # 5 mins per service cooldown


async def send_crash_email(
    service_name: str,
    error: Exception | str,
    context_data: Optional[Dict[str, Any]] = None,
):
    """Send automated HTML crash email on fatal errors or pipeline failures."""
    smtp_host = os.getenv("ALERT_SMTP_HOST")
    smtp_port = int(os.getenv("ALERT_SMTP_PORT", "587"))
    smtp_user = os.getenv("ALERT_SMTP_USER")
    smtp_pass = os.getenv("ALERT_SMTP_PASS")
    alert_to = os.getenv("ALERT_EMAIL_TO")

    if not all([smtp_host, smtp_user, smtp_pass, alert_to]):
        logger.debug("Crash email alert configuration incomplete — skipping email dispatch")
        return

    # Cooldown check
    now = time.time()
    last_sent = _last_alert_time.get(service_name, 0.0)
    if now - last_sent < ALERT_COOLDOWN_SECONDS:
        logger.info(f"Crash email suppressed due to cooldown window ({service_name})")
        return
    _last_alert_time[service_name] = now

    def _sync_send():
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = f"🚨 [CRITICAL ALERT] {service_name} Pipeline Error"
            msg["From"] = smtp_user
            msg["To"] = alert_to

            ctx_html = ""
            if context_data:
                rows = "".join(
                    f"<tr><td style='font-weight:bold;padding:4px 8px;border:1px solid #ddd;'>{k}</td>"
                    f"<td style='padding:4px 8px;border:1px solid #ddd;'><pre style='margin:0;'>{v}</pre></td></tr>"
                    for k, v in context_data.items()
                )
                ctx_html = f"<h3>Context Information:</h3><table style='border-collapse:collapse;width:100%;'>{rows}</table>"

            html = f"""
            <html>
            <body style="font-family: Arial, sans-serif; line-height: 1.5; color: #333;">
                <div style="background-color: #d9534f; color: white; padding: 15px; border-radius: 5px;">
                    <h2>🚨 Critical Service Failure: {service_name}</h2>
                </div>
                <div style="padding: 15px; border: 1px solid #ddd; margin-top: 15px; border-radius: 5px;">
                    <h3>Error Description:</h3>
                    <pre style="background: #f8f9fa; padding: 10px; border-radius: 4px; color: #d9534f;">{str(error)}</pre>
                    {ctx_html}
                </div>
            </body>
            </html>
            """
            msg.attach(MIMEText(html, "html"))

            with smtplib.SMTP(smtp_host, smtp_port, timeout=10.0) as server:
                server.starttls()
                server.login(smtp_user, smtp_pass)
                server.sendmail(smtp_user, alert_to.split(","), msg.as_string())
            logger.info(f"Sent crash email alert to {alert_to} for {service_name}")
        except Exception as e:
            logger.error(f"Failed to send crash email: {e}")

    await asyncio.to_thread(_sync_send)
