import configparser
from pathlib import Path
from pydantic_settings import BaseSettings
from pydantic import field_validator


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


def _load_high_privilege_tushare_token() -> str:
    """从 /etc/kimi/stocks/base.conf 读取高权限 Tushare token"""
    conf_path = Path("/etc/kimi/stocks/base.conf")
    if conf_path.exists():
        try:
            cfg = configparser.ConfigParser()
            cfg.read(conf_path, encoding="utf-8")
            return cfg.get("high_privilege_tushare", "token", fallback="").strip()
        except Exception:
            return ""
    return ""


class Settings(BaseSettings):
    database_url: str = "sqlite:///./stocks.db"
    tushare_token: str = ""
    high_privilege_tushare_token: str = ""
    public_host: str = ""  # 公网 IP 或域名，用于 CORS 白名单，如 120.25.245.13

    # 登录认证（个人工具，单账号即可）。可在 .env 中覆盖。
    auth_username: str = "root"
    auth_password: str = "root@123"
    # token 签名密钥，生产环境务必在 .env 中改成随机值
    auth_secret: str = "stocks-default-secret-change-me"
    # token 有效期（秒），默认 7 天
    auth_token_ttl: int = 7 * 24 * 3600

    @field_validator("tushare_token", mode="before")
    @classmethod
    def _ensure_tushare_token(cls, v):
        """环境变量为空时，回退读取 /etc/kimi/stocks/base.conf"""
        if not v:
            return _load_tushare_token()
        return v

    @field_validator("high_privilege_tushare_token", mode="before")
    @classmethod
    def _ensure_high_privilege_tushare_token(cls, v):
        """环境变量为空时，回退读取 /etc/kimi/stocks/base.conf"""
        if not v:
            return _load_high_privilege_tushare_token()
        return v

    class Config:
        env_file = ".env"


settings = Settings()
