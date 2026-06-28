"""登录认证路由：POST /api/auth/login、GET /api/auth/me。"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..auth import create_token, require_auth, verify_credentials

router = APIRouter()


class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/login")
def login(req: LoginRequest):
    if not verify_credentials(req.username, req.password):
        raise HTTPException(status_code=401, detail="账号或密码错误")
    result = create_token(req.username)
    return {
        "token": result["token"],
        "expires_at": result["expires_at"],
        "username": req.username,
    }


@router.get("/me")
def me(username: str = Depends(require_auth)):
    """校验当前 token 是否有效，返回用户名。"""
    return {"username": username}
