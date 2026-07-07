import os
from pathlib import Path
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager

from .database import create_db_and_tables
from .routers import stocks, bars, watchlist, overview, strategies, auth as auth_routes, backtest, etf
from .auth import require_auth
from .config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_db_and_tables()
    yield


app = FastAPI(
    title="Stocks 复盘 API",
    description="个人股票复盘软件后端接口",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS：允许本地开发环境以及公网 IP 访问
# 警告：直接暴露到公网存在安全风险，建议配合 Nginx 基本认证或 VPN 使用
allow_origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]
# 如果配置了 PUBLIC_HOST，也加入 CORS 白名单
if settings.public_host:
    allow_origins.append(f"http://{settings.public_host}")
    allow_origins.append(f"https://{settings.public_host}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 登录接口（无需认证）
app.include_router(auth_routes.router, prefix="/api/auth", tags=["auth"])

# 业务接口统一要求登录（携带有效 Bearer token）
_protected = [Depends(require_auth)]
app.include_router(stocks.router, prefix="/api/stocks", tags=["stocks"], dependencies=_protected)
app.include_router(bars.router, prefix="/api/bars", tags=["bars"], dependencies=_protected)
app.include_router(watchlist.router, prefix="/api/watchlist", tags=["watchlist"], dependencies=_protected)
app.include_router(overview.router, prefix="/api/overview", tags=["overview"], dependencies=_protected)
app.include_router(strategies.router, prefix="/api/strategies", tags=["strategies"], dependencies=_protected)
app.include_router(backtest.router, prefix="/api/backtests", tags=["backtests"], dependencies=_protected)
app.include_router(etf.router, prefix="/api/etfs", tags=["etfs"], dependencies=_protected)


@app.get("/api/health")
def health():
    return {"status": "ok"}


# 如果前端构建产物存在，则挂载静态文件服务
# 这样生产环境只需启动后端，访问 http://公网IP:8000 即可
_dist_path = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
class ImmutableStaticFiles(StaticFiles):
    """带内容 hash 的静态资源（JS/CSS），使用长期不可变缓存。

    Vite 构建产物文件名含 hash，内容变更即文件名变更，因此可安全地长期缓存。
    """

    async def get_response(self, path: str, scope):
        response = await super().get_response(path, scope)
        if response.status_code == 200:
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return response


if _dist_path.exists() and (_dist_path / "index.html").exists():
    app.mount("/assets", ImmutableStaticFiles(directory=str(_dist_path / "assets")), name="assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        # API 路径已在上面处理，其余都返回 index.html（单页应用）
        if full_path.startswith("api/"):
            return {"detail": "Not Found"}
        # index.html 禁用强缓存（仅做协商缓存），确保前端发版后浏览器
        # 每次都能拿到最新的带 hash 资源引用，而不是加载旧入口页。
        return FileResponse(
            str(_dist_path / "index.html"),
            headers={"Cache-Control": "no-cache"},
        )
