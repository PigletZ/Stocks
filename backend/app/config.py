import configparser
from pathlib import Path
from pydantic_settings import BaseSettings
from pydantic import Field, field_validator


def _load_tushare_token() -> str:
    """从 /etc/kimi/stocks/base.conf 读取 Tushare token"""
    conf_path = Path("/etc/kimi/stocks/base.conf")
    if conf_path.exists():
        try:
            cfg = configparser.ConfigParser()
            cfg.read(conf_path, encoding="utf-8")
            return cfg.get("tushare", "token", fallback="").strip()
        except Exception:
            return ""
    return ""


class Settings(BaseSettings):
    database_url: str = "sqlite:///./stocks.db"
    tushare_token: str = ""
    public_host: str = ""  # 公网 IP 或域名，用于 CORS 白名单
    system_state_dir: str = ""  # 留空时使用 backend/.cache/system
    backup_dir: str = ""  # 留空时使用 backend/backups

    # 必须由环境变量或 backend/.env 提供，禁止回退到内置凭据。
    auth_username: str = Field(min_length=1)
    auth_password: str = Field(min_length=1)
    auth_secret: str = Field(min_length=32)
    # token 有效期（秒），默认 7 天
    auth_token_ttl: int = Field(default=7 * 24 * 3600, gt=0)

    @field_validator("auth_username", "auth_password", "auth_secret")
    @classmethod
    def _reject_blank_credentials(cls, value):
        if not value.strip():
            raise ValueError("Authentication configuration must not be blank")
        return value

    @field_validator("tushare_token", mode="before")
    @classmethod
    def _ensure_tushare_token(cls, v):
        """环境变量为空时，回退读取 /etc/kimi/stocks/base.conf"""
        if not v:
            return _load_tushare_token()
        return v

    class Config:
        env_file = Path(__file__).resolve().parent.parent / ".env"
        hide_input_in_errors = True


settings = Settings()
