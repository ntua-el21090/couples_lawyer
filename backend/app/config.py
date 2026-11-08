"""App-wide settings. Secrets come from the environment, never from the code."""

import os
import secrets
from dataclasses import dataclass, field
from pathlib import Path

MODEL = os.environ.get("LAWYER_MODEL", "claude-sonnet-5-5")
MAX_ROUNDS = 3
MAX_TEXT_LENGTH = 4000
MIN_PASSCODE_LENGTH = 8

APP_DIR = Path(__file__).resolve().parent


@dataclass(frozen=True)
class Settings:
    # In production the app refuses to start without a passcode. Locally, with no passcode,
    # access is open so development stays easy.
    production: bool = False
    access_passcode: str | None = None
    # Signs the access cookie. A fresh random value means cookies stop working after a restart.
    session_secret: str = field(default_factory=lambda: secrets.token_urlsafe(32))
    session_lifetime_seconds: int = 7 * 24 * 60 * 60
    case_ttl_seconds: int = 2 * 60 * 60
    max_live_cases: int = 50
    max_lawyer_calls_per_day: int = 200
    login_max_failures: int = 10
    login_window_seconds: int = 15 * 60
    # The built frontend. Unset in development, where Vite serves the page.
    frontend_dist: Path | None = None
    photos_dir: Path = APP_DIR / "assets"

    @property
    def cookie_secure(self) -> bool:
        return self.production

    @classmethod
    def from_env(cls) -> "Settings":
        env = os.environ
        defaults = cls()
        dist = env.get("FRONTEND_DIST")
        return cls(
            production=env.get("LAWYER_ENV") == "production",
            access_passcode=env.get("ACCESS_PASSCODE") or None,
            session_secret=env.get("SESSION_SECRET") or defaults.session_secret,
            max_live_cases=int(env.get("MAX_LIVE_CASES", defaults.max_live_cases)),
            max_lawyer_calls_per_day=int(
                env.get("MAX_LAWYER_CALLS_PER_DAY", defaults.max_lawyer_calls_per_day)
            ),
            frontend_dist=Path(dist) if dist else None,
        )

    def validate(self) -> None:
        weak = not self.access_passcode or len(self.access_passcode) < MIN_PASSCODE_LENGTH
        if self.production and weak:
            raise RuntimeError(
                f"ACCESS_PASSCODE must be set, with at least {MIN_PASSCODE_LENGTH} characters, "
                "when LAWYER_ENV is production."
            )
