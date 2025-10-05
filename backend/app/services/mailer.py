"""Utility helpers for sending transactional e-mails."""
from __future__ import annotations

import asyncio
import logging
import smtplib
from email.message import EmailMessage

from ..core.config import Settings

LOGGER = logging.getLogger("prosteprawo.mailer")


class Mailer:
    """Very small SMTP client tailored for verification/reset flows."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def send_verification_email(self, recipient: str, link: str) -> None:
        subject = "Potwierdź konto w ProstePrawo"
        body = f"Kliknij w link, aby potwierdzić konto: {link}"
        await self._send(recipient, subject, body)

    async def send_password_reset_email(self, recipient: str, link: str) -> None:
        subject = "Reset hasła w ProstePrawo"
        body = f"Aby ustawić nowe hasło, otwórz link: {link}"
        await self._send(recipient, subject, body)

    async def _send(self, recipient: str, subject: str, body: str) -> None:
        if not self.settings.smtp.is_configured():
            LOGGER.info("SMTP is not configured; skipping e-mail delivery", extra={"recipient": recipient})
            return

        message = EmailMessage()
        message["From"] = self.settings.smtp.sender
        message["To"] = recipient
        message["Subject"] = subject
        message.set_content(body)

        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._deliver, message)

    def _deliver(self, message: EmailMessage) -> None:
        host = self.settings.smtp.host
        port = self.settings.smtp.port or 587
        if not host:
            LOGGER.error("SMTP host not configured; aborting send")
            return

        kwargs: dict[str, object] = {}
        if self.settings.smtp.use_tls:
            context_manager = smtplib.SMTP
            kwargs["timeout"] = 10
        else:
            context_manager = smtplib.SMTP
            kwargs["timeout"] = 10

        with context_manager(host, port, **kwargs) as client:
            if self.settings.smtp.use_tls:
                client.starttls()
            username = self.settings.smtp.username
            password = self.settings.smtp.password
            if username and password:
                client.login(username, password)
            client.send_message(message)
            LOGGER.info("Sent transactional e-mail", extra={"to": message["To"], "subject": message["Subject"]})
