"""路由日期校验，非法输入返回客户端错误，避免未捕获 ValueError 变成 500。"""
from datetime import date
from fastapi import HTTPException


def parse_iso_date(value: str) -> date:
    try:
        if not isinstance(value, str) or len(value) != 10:
            raise ValueError("invalid ISO date")
        return date.fromisoformat(value)
    except (ValueError, TypeError):
        raise HTTPException(400, "日期格式应为有效的 YYYY-MM-DD 日期") from None
