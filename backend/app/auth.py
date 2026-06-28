"""登录认证：基于 HMAC 签名的轻量 token，零第三方依赖。

适用于个人单账号工具：登录校验 .env 中配置的账号密码，签发带过期时间的
token；后续请求通过 require_auth 依赖校验 token。token 结构为
`<base64url(payload)>.<hmac_sha256 签名>`，payload 含用户名与过期时间戳。
"""

import base64
import hashlib
import hmac
import json
import time
from typing import Optional

from fastapi import Header, HTTPException

from .config import settings


def _sign(raw: str) -> str:
    return hmac.new(
        settings.auth_secret.encode(), raw.encode(), hashlib.sha256
    ).hexdigest()


def _b64encode(data: dict) -> str:
    return base64.urlsafe_b64encode(json.dumps(data).encode()).decode().rstrip("=")


def _b64decode(raw: str) -> dict:
    pad = "=" * (-len(raw) % 4)
    return json.loads(base64.urlsafe_b64decode(raw + pad))


def create_token(username: str) -> dict:
    """签发 token，返回 {token, expires_at}（expires_at 为 Unix 秒）。"""
    expires_at = int(time.time()) + settings.auth_token_ttl
    raw = _b64encode({"u": username, "exp": expires_at})
    return {"token": f"{raw}.{_sign(raw)}", "expires_at": expires_at}


def verify_token(token: str) -> Optional[str]:
    """校验 token，有效则返回用户名，否则返回 None。"""
    if not token or "." not in token:
        return None
    raw, sig = token.rsplit(".", 1)
    if not hmac.compare_digest(sig, _sign(raw)):
        return None
    try:
        payload = _b64decode(raw)
    except Exception:
        return None
    if int(payload.get("exp", 0)) < time.time():
        return None
    return payload.get("u")


def verify_credentials(username: str, password: str) -> bool:
    """校验账号密码（常量时间比较，避免时序侧信道）。"""
    return hmac.compare_digest(username or "", settings.auth_username) and hmac.compare_digest(
        password or "", settings.auth_password
    )


def require_auth(authorization: str = Header(default="")) -> str:
    """FastAPI 依赖：从 Authorization 头校验 Bearer token，失败抛 401。"""
    token = authorization.strip()
    if token.lower().startswith("bearer "):
        token = token[7:].strip()
    username = verify_token(token)
    if not username:
        raise HTTPException(status_code=401, detail="未登录或登录已过期")
    return username
