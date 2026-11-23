import configparser
import os
from pathlib import Path
from pydantic_settings import BaseSettings
from pydantic import Field, field_validator


SERVICE_CONFIG_PATH = Path("/etc/kimi/stocks/base.conf")


def _load_service_config(section) -> dict:
    """兼容命名键及节内独立一行密钥，不把解析异常或凭据输出到日志。"""
    conf_path = SERVICE_CONFIG_PATH
    if conf_path.exists():
        try:
            cfg = configparser.ConfigParser(allow_no_value=True, interpolation=None)
            cfg.optionxform = str
            cfg.read(conf_path, encoding="utf-8")
            if not cfg.has_section(section):
                return {}
            items = list(cfg.items(section))
            values = {key.lower(): value.strip() for key, value in items if value is not None}
            bare = [key.strip() for key, value in items if value is None and key.startswith("sk-")]
            if len(bare) == 1 and not any(values.get(key) for key in ("api_key", "key", "token")):
                values["api_key"] = bare[0]
            return values
        except Exception:
            return {}
    return {}


def _load_tushare_token() -> str:
    return _load_service_config("tushare").get("token", "")


class Settings(BaseSettings):
    database_url: str = "sqlite:///./stocks.db"
    tushare_token: str = ""
    public_host: str = ""  # 公网 IP 或域名，用于 CORS 白名单
    system_state_dir: str = ""  # 留空时使用 backend/.cache/system
    backup_dir: str = ""  # 留空时使用 backend/backups
    # 可选的 OpenAI 兼容 Chat Completions 服务；只在手动审阅时调用。
    ai_base_url: str = ""
    ai_api_key: str = Field(default="", repr=False)
    ai_model: str = ""
    ai_timeout_seconds: int = Field(default=45, ge=5, le=90)

    @field_validator("ai_base_url", "ai_api_key", "ai_model", mode="before")
    @classmethod
    def _load_kimi_configuration(cls, value, info):
        if value and str(value).strip():
            return str(value).strip()
        values = _load_service_config("kimi")
        key = os.environ.get("AI_API_KEY") or next((values.get(name) for name in ("api_key", "key", "token") if values.get(name)), "")
        if info.field_name == "ai_api_key":
            return key
        if info.field_name == "ai_base_url":
            return values.get("base_url") or ("https://api.kimi.com/coding/v1" if key.startswith("sk-kimi-") else "https://api.moonshot.cn/v1")
        return values.get("model") or ("k3" if key.startswith("sk-kimi-") else "kimi-k3")

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
