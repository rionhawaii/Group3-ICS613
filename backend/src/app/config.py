"""Application settings loaded from environment variables."""

from pathlib import Path
from typing import Annotated

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    """Project-wide configuration.

    Values are read from environment variables or a ``.env`` file.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Application
    app_name: str = "Neighborhood Tool Sharing API"  #: Name used in responses and logs.
    debug: bool = Field(default=False)  #: Enable FastAPI debug mode / verbose logs.
    # Environment name. ``production`` enables stricter checks (the
    # SECRET_KEY dev-placeholder rejection below); ``development`` / ``test``
    # tolerate the standard ``change-me-...`` / ``replace-with-...`` placeholders
    # so a fresh checkout can run with the default ``.env`` for local dev.
    environment: str = Field(
        default="production",
        description=(
            "Deployment environment name. Set to ``development`` or ``test`` "
            "to relax the SECRET_KEY dev-placeholder check. "
            "(env: ENVIRONMENT)"
        ),
    )

    # Security — secret_key has no default; an explicit value (>= 32 chars) is required.
    # In debug mode a short dev key is allowed; production refuses to start without a
    # strong key. The ``debug`` flag is a backstop for local hacking.
    secret_key: SecretStr = Field(
        description=(
            "HMAC signing key for JWT tokens. **Required.** Must be at least 32 chars. "
            "Generate with: python -c 'import secrets; print(secrets.token_urlsafe(48))' "
            "(env: SECRET_KEY)."
        ),
    )
    access_token_expire_minutes: int = Field(
        default=60,
        description="Access token lifetime in minutes (env: ACCESS_TOKEN_EXPIRE_MINUTES).",
    )
    refresh_token_expire_days: int = Field(
        default=7,
        description="Refresh token lifetime in days (env: REFRESH_TOKEN_EXPIRE_DAYS).",
    )
    algorithm: str = Field(
        default="HS256",
        description="JWT signing algorithm (env: ALGORITHM).",
    )
    # JWT audience and issuer. ``aud`` and ``iss`` are standard claims that
    # bind tokens to this service. If you ever federate (e.g. share auth with
    # another backend) you'd want a different ``aud`` per service; for now
    # the same value is used everywhere. The values are checked on decode
    # so a token minted by another service that uses the same SECRET_KEY
    # can't be replayed against this API.
    jwt_audience: str = Field(
        default="toolsharing-api",
        description=("JWT ``aud`` claim — must match on decode. (env: JWT_AUDIENCE)"),
    )
    jwt_issuer: str = Field(
        default="toolsharing-api",
        description=("JWT ``iss`` claim — must match on decode. (env: JWT_ISSUER)"),
    )

    # Database (asyncpg)
    database_url: str = Field(
        default="postgresql+asyncpg://ics613user:ics613password@localhost:5432/toolsharing",
        description="AsyncPG connection string (env: DATABASE_URL).",
    )

    # CORS — ``NoDecode`` keeps pydantic-settings from JSON-decoding the
    # comma-separated env value before our custom validator runs. The
    # validator below handles both forms (str → list[str], list[str] → list[str]).
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:5173"],
        description=(
            "Comma-separated list of allowed CORS origins "
            "(env: CORS_ORIGINS, e.g. 'http://localhost:5173,https://app.example.com')."
        ),
    )

    # Frontend / deployment
    base_url: str = Field(
        default="http://localhost:5173",
        description="Base URL of the frontend, used in email links (env: BASE_URL).",
    )

    # Static/media uploads
    media_dir: Path = Field(
        default=Path("media"),
        description="Directory for uploaded tool photos, relative to the working directory (env: MEDIA_DIR).",
    )
    max_upload_size_bytes: int = Field(
        default=5 * 1024 * 1024,  # 5 MB
        description="Maximum size per uploaded file in bytes (env: MAX_UPLOAD_SIZE_BYTES, default 5 MB).",
    )

    # Email (SMTP)
    smtp_host: str = Field(
        default="localhost",
        description="SMTP server hostname (env: SMTP_HOST). Set to a real host in production.",
    )
    smtp_port: int = Field(
        default=1025,
        description="SMTP server port (env: SMTP_PORT). Default 1025 for MailHog; 587 for real SMTP with TLS.",
    )
    smtp_user: str | None = Field(
        default=None,
        description="SMTP username (env: SMTP_USER). Required for real SMTP.",
    )
    smtp_password: SecretStr | None = Field(
        default=None,
        description="SMTP password (env: SMTP_PASSWORD). Required for real SMTP.",
    )
    smtp_tls: bool = Field(
        default=False,
        description="Enable STARTTLS for SMTP (env: SMTP_TLS, default false for local MailHog).",
    )
    smtp_from: str = Field(
        default="noreply@example.com",
        description="Sender address for outgoing emails (env: SMTP_FROM).",
    )
    smtp_reply_to: str = Field(
        default="noreply@example.com",
        description="Reply-To address for outgoing emails — a dead address so "
        "replies do not reach a real inbox (env: SMTP_REPLY_TO).",
    )

    # Scheduler
    disable_scheduler: bool = Field(
        default=False,
        description="If true, the APScheduler background jobs will not start (env: DISABLE_SCHEDULER).",
    )
    # Scheduler timing (in days). All defaults match the previous hard-coded
    # constants in ``services/scheduler.py`` so existing behavior is preserved.
    scheduler_grace_period_days: int = Field(
        default=3,
        ge=1,
        description=(
            "Days after a reservation's start_date before an un-picked-up "
            "APPROVED reservation is auto-cancelled. "
            "(env: SCHEDULER_GRACE_PERIOD_DAYS)"
        ),
    )
    scheduler_escalation_days: int = Field(
        default=7,
        ge=1,
        description=(
            "Days after a reservation's end_date before a PICKED_UP reservation "
            "is escalated (overdue notification sent to borrower). "
            "(env: SCHEDULER_ESCALATION_DAYS)"
        ),
    )
    scheduler_hard_escalation_days: int = Field(
        default=14,
        ge=1,
        description=(
            "Days after a reservation's end_date before the reservation is "
            "auto-force-returned (releases the tool, stops notification loop). "
            "Must be > scheduler_escalation_days. "
            "(env: SCHEDULER_HARD_ESCALATION_DAYS)"
        ),
    )
    scheduler_token_retention_days: int = Field(
        default=30,
        ge=1,
        description=(
            "Days an expired token (email verification, password reset, invite) "
            "is kept before being deleted by the cleanup job. "
            "(env: SCHEDULER_TOKEN_RETENTION_DAYS)"
        ),
    )
    scheduler_notification_dedup_hours: int = Field(
        default=24,
        ge=1,
        description=(
            "Hours to suppress duplicate RESERVATION_OVERDUE notifications for the "
            "same user. The soft-escalation job runs hourly but only emits a "
            "notification if none has been sent to this user within this window. "
            "(env: SCHEDULER_NOTIFICATION_DEDUP_HOURS)"
        ),
    )

    # Rate limiting (per-process, in-memory). Defaults are production-tight
    # to block credential stuffing and email-bombing: 10/min on auth
    # endpoints and 10/hr for registration. Raise via env vars in dev/e2e
    # environments if tests exercise more requests than that from one IP.
    rate_limit_login_per_minute: int = Field(
        default=10,
        ge=1,
        description=(
            "Max login attempts per client IP per minute. (env: RATE_LIMIT_LOGIN_PER_MINUTE)"
        ),
    )
    rate_limit_forgot_password_per_minute: int = Field(
        default=10,
        ge=1,
        description=(
            "Max forgot-password requests per client IP per minute. "
            "(env: RATE_LIMIT_FORGOT_PASSWORD_PER_MINUTE)"
        ),
    )
    rate_limit_resend_verification_per_minute: int = Field(
        default=10,
        ge=1,
        description=(
            "Max resend-verification requests per client IP per minute. "
            "(env: RATE_LIMIT_RESEND_VERIFICATION_PER_MINUTE)"
        ),
    )
    rate_limit_register_per_hour: int = Field(
        default=10,
        ge=1,
        description=(
            "Max registration attempts per client IP per hour. (env: RATE_LIMIT_REGISTER_PER_HOUR)"
        ),
    )

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _parse_cors_origins(cls, value: str | list[str]) -> list[str]:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @field_validator("media_dir", mode="before")
    @classmethod
    def _ensure_path(cls, value: str | Path) -> Path:
        return Path(value)

    @field_validator("secret_key", mode="before")
    @classmethod
    def _validate_secret_key(cls, value: str | SecretStr) -> SecretStr:
        """Enforce minimum length on the JWT signing key."""
        raw = value.get_secret_value() if isinstance(value, SecretStr) else value
        if not raw or len(raw) < 32:
            raise ValueError(
                "SECRET_KEY must be at least 32 characters. "
                "Generate one with: python -c 'import secrets; print(secrets.token_urlsafe(48))'"
            )
        return SecretStr(raw)

    @model_validator(mode="after")
    def _reject_dev_placeholders_in_production(self) -> "Settings":
        """Reject obvious dev placeholders, but only outside dev/test.

        In ``development`` or ``test`` environments the standard
        ``change-me-in-production-...`` / ``replace-with-...`` placeholders
        are tolerated so a fresh checkout can run with the default ``.env``
        for local dev without generating a real key. In ``production`` the
        operator must run ``python -c 'import secrets; print(secrets.token_urlsafe(48))'``
        and use that. The check runs at startup so a bad key fails fast.

        The default ``environment`` is ``production`` so a missing env var
        doesn't accidentally disable the check. Set
        ``TOOLSHARING_ENVIRONMENT=development`` in your local ``.env`` to
        run with a placeholder key.
        """
        if self.environment.lower() in ("development", "test", "dev"):
            return self
        raw = self.secret_key.get_secret_value()
        lowered = raw.lower()
        if "change-me" in lowered or "replace-with" in lowered:
            raise ValueError(
                "SECRET_KEY looks like a dev placeholder but "
                f"environment={self.environment!r}. "
                "Generate a real key with: "
                "python -c 'import secrets; print(secrets.token_urlsafe(48))'"
            )
        return self


def get_settings() -> Settings:
    """Return a fresh Settings instance.

    Not cached: tests rely on being able to mutate ``os.environ`` and get a
    new instance that re-reads the current values. Caching here previously
    caused subtle test failures where a patched env var was ignored.
    """
    return Settings()
