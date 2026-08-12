"""Email sending abstraction.

R1.A uses a thin abstraction. In development, MailHog captures all SMTP
 traffic. In production, a real SMTP server is used. Tests can patch
 `send_email` or `EmailService.send` directly.
"""

import smtplib
import ssl
from email.message import EmailMessage
from typing import Protocol

from app.config import get_settings


class EmailBackend(Protocol):
    """Protocol for email backends."""

    def send(self, to_email: str, subject: str, body: str) -> None: ...


class _MailHogBackend:
    """Development backend that sends to MailHog."""

    def send(self, to_email: str, subject: str, body: str) -> None:
        settings = get_settings()
        host = settings.smtp_host or "localhost"
        port = settings.smtp_port or 1025
        msg = EmailMessage()
        msg["From"] = settings.smtp_from or "dev@example.com"
        msg["Reply-To"] = settings.smtp_reply_to
        msg["To"] = to_email
        msg["Subject"] = subject
        msg.set_content(body)
        with smtplib.SMTP(host, port) as server:
            server.send_message(msg)


class _SMTPBackend:
    """Production SMTP backend.

    Auto-detects the connection method:
    - Port 465 → implicit SSL (SMTP_SSL).
    - Port 587 (or any other) → STARTTLS (SMTP + starttls if enabled).
    """

    def send(self, to_email: str, subject: str, body: str) -> None:
        settings = get_settings()
        if not settings.smtp_host or not settings.smtp_user:
            raise RuntimeError("SMTP is not configured")

        msg = EmailMessage()
        msg["From"] = settings.smtp_from or settings.smtp_user
        msg["Reply-To"] = settings.smtp_reply_to
        msg["To"] = to_email
        msg["Subject"] = subject
        msg.set_content(body)

        port = settings.smtp_port
        if port == 465:
            # Implicit SSL — wrap the connection from the start.
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(settings.smtp_host, port, context=context) as server:
                server.login(
                    settings.smtp_user,
                    settings.smtp_password.get_secret_value() if settings.smtp_password else "",
                )
                server.send_message(msg)
        else:
            # STARTTLS — plain connection, upgrade if configured.
            with smtplib.SMTP(settings.smtp_host, port) as server:
                if settings.smtp_tls:
                    server.starttls()
                server.login(
                    settings.smtp_user,
                    settings.smtp_password.get_secret_value() if settings.smtp_password else "",
                )
                server.send_message(msg)


class EmailService:
    """Application email service."""

    def __init__(self, backend: EmailBackend | None = None) -> None:
        self._backend = backend or self._default_backend()

    @staticmethod
    def _default_backend() -> EmailBackend:
        settings = get_settings()
        if settings.smtp_host and settings.smtp_host not in ("localhost", "mailhog"):
            return _SMTPBackend()
        return _MailHogBackend()

    def send(self, to_email: str, subject: str, body: str) -> None:
        """Send an email, logging any failures without raising.

        Email delivery is a best-effort side effect and must never break
        the calling operation. The token is persisted in the database
        regardless, so the user can complete verification/reset via the
        database token even if the email fails to send.

        Only network/SMTP errors are swallowed. Programmer errors
        (``TypeError``, ``AttributeError``, …) are intentionally NOT
        caught — they should fail loudly during development.
        """
        try:
            self._backend.send(to_email, subject, body)
        except (smtplib.SMTPException, OSError, RuntimeError) as exc:
            from app.core.logging import get_logger

            get_logger(__name__).warning(
                "Email send failed (to=%s subject=%s): %s",
                to_email,
                subject,
                exc,
            )

    def send_verification_email(self, to_email: str, token: str) -> None:
        settings = get_settings()
        base = settings.base_url.rstrip("/")
        subject = "Verify your email address"
        body = (
            f"Your verification token is: {token}\n\n"
            f"Go to {base}/verify-email and paste the token above, "
            f"or visit the website and navigate to the Verify Email page.\n\n"
            f"If you did not create an account, you can ignore this email."
        )
        self.send(to_email, subject, body)

    def send_password_reset_email(self, to_email: str, token: str) -> None:
        settings = get_settings()
        base = settings.base_url.rstrip("/")
        subject = "Reset your password"
        body = (
            f"Your password reset token is: {token}\n\n"
            f"Go to {base}/reset-password and paste the token above, "
            f"or visit the website and navigate to Reset Password.\n\n"
            f"If you did not request a password reset, you can ignore this email."
        )
        self.send(to_email, subject, body)

    def send_invite_email(self, to_email: str, token: str) -> None:
        settings = get_settings()
        base = settings.base_url.rstrip("/")
        subject = "You have been invited to join Neighborhood Tool Sharing"
        body = (
            f"You have been invited to join Neighborhood Tool Sharing!\n\n"
            f"Your invite token is: {token}\n\n"
            f"Go to {base}/register and enter your details "
            f"along with the invite token above to create your account.\n\n"
            f"The invite link expires in 7 days."
        )
        self.send(to_email, subject, body)
