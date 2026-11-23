"""系统管理的非敏感设置与运行记录，原子写入，独立于业务数据库。"""
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ..config import settings

BACKEND_DIR = Path(__file__).resolve().parents[2]


def utc_now():
    return datetime.now(timezone.utc)


def redact(value):
    value = str(value)
    for secret in (settings.tushare_token, settings.auth_password, settings.auth_secret, settings.ai_api_key):
        if secret:
            value = value.replace(secret, "[已隐藏]")
    return re.sub(r"(?i)\b(token|password|secret|authorization)\s*[:=]\s*[^\s,;]+", r"\1=[已隐藏]", value)


class RuntimeStore:
    def __init__(self, directory=None):
        self.directory = Path(directory or settings.system_state_dir or BACKEND_DIR / ".cache" / "system")

    def path(self, name):
        if not re.fullmatch(r"[a-z0-9-]+", name):
            raise ValueError("Invalid system state name")
        return self.directory / f"{name}.json"

    def read(self, name):
        try:
            path = self.path(name)
            if path.stat().st_size > 1024 * 1024:
                return None
            value = json.loads(path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else None
        except (OSError, ValueError, TypeError):
            return None

    def write(self, name, value):
        self.directory.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.directory, suffix=".tmp", delete=False) as handle:
                temporary = handle.name
                json.dump(value, handle, ensure_ascii=False, allow_nan=False)
            os.chmod(temporary, 0o600)
            os.replace(temporary, self.path(name))
        finally:
            if temporary and os.path.exists(temporary):
                os.unlink(temporary)


class SystemPreferences(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    request_timeout: int = Field(default=10, ge=3, le=30)
    retry_cooldown: int = Field(default=30, ge=10, le=300)
    data_ready_hour: int = Field(default=21, ge=16, le=23)
    calendar_cache_seconds: int = Field(default=86400, ge=3600, le=604800)
    etf_basic_cache_seconds: int = Field(default=3600, ge=300, le=86400)
    etf_daily_cache_seconds: int = Field(default=300, ge=60, le=3600)
    etf_snapshot_limit: int = Field(default=100, ge=20, le=365)


def get_preferences(store=None):
    payload = (store or RuntimeStore()).read("preferences")
    try:
        return SystemPreferences.model_validate(payload["values"]) if payload else SystemPreferences()
    except (KeyError, TypeError, ValidationError):
        return SystemPreferences()


def save_preferences(preferences, store=None):
    (store or RuntimeStore()).write("preferences", {"values": preferences.model_dump(), "updated_at": utc_now().isoformat()})
    return preferences.model_dump()
