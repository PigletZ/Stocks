"""Tushare 官方 HTTP 协议适配，避免 SDK 将 HTTP 故障静默转为空表。"""
from functools import partial
from time import monotonic

import pandas as pd
import requests

from .runtime_state import get_preferences, redact


class TushareError(RuntimeError):
    def __init__(self, message, kind="upstream", code=None, http_status=None):
        super().__init__(message)
        self.kind, self.code, self.http_status = kind, code, http_status


class TushareClient:
    # https://tushare.pro/document/2?doc_id=40
    URL = "https://api.tushare.pro"

    def __init__(self, token, timeout=None):
        self._token = token
        self._timeout = timeout
        self._retry_at = 0
        self._failure = ""

    def _unavailable(self, message, kind="upstream", http_status=None):
        # 一次故障后短暂退避，避免同一观察台请求连续等待多个超时。
        self._failure = TushareError(message, kind=kind, http_status=http_status)
        self._retry_at = monotonic() + get_preferences().retry_cooldown
        raise self._failure from None

    def query(self, api_name, fields="", **params):
        if monotonic() < self._retry_at:
            raise self._failure
        try:
            response = requests.post(
                self.URL,
                json={"api_name": api_name, "token": self._token,
                      "params": params, "fields": fields},
                timeout=self._timeout if self._timeout is not None else get_preferences().request_timeout,
                allow_redirects=False,
            )
        except requests.RequestException:
            self._unavailable("Tushare 连接失败或超时，请稍后重试", kind="connection")
        if response.status_code != 200:
            kind = "rate_limit" if response.status_code == 429 else "permission" if response.status_code == 403 else "auth" if response.status_code == 401 else "upstream"
            self._unavailable(f"Tushare 上游服务异常（HTTP {response.status_code}），请稍后重试", kind=kind, http_status=response.status_code)
        try:
            result = response.json()
            if not isinstance(result, dict) or "code" not in result:
                raise ValueError("missing response code")
            if result["code"] != 0:
                message = str(result.get("msg") or "接口请求失败")
                if self._token:
                    message = message.replace(self._token, "[已隐藏]")
                kind = ("permission" if result["code"] == 2002 or "权限" in message or "permission" in message.lower() else
                        "rate_limit" if "频次" in message or "频率" in message else
                        "auth" if "token" in message.lower() or "认证" in message else "api_error")
                raise TushareError(f"Tushare：{redact(message)[:200]}", kind=kind, code=result["code"])
            data = result["data"]
            if not isinstance(data["fields"], list) or not isinstance(data["items"], list):
                raise ValueError("invalid data shape")
            return pd.DataFrame(data["items"], columns=data["fields"])
        except (ValueError, KeyError, TypeError):
            self._unavailable("Tushare 返回的数据格式异常，请稍后重试", kind="protocol")

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        return partial(self.query, name)
