"""Tushare 官方 HTTP 协议适配，避免 SDK 将 HTTP 故障静默转为空表。"""
from functools import partial
from time import monotonic

import pandas as pd
import requests


class TushareError(RuntimeError):
    pass


class TushareClient:
    # https://tushare.pro/document/2?doc_id=40
    URL = "https://api.tushare.pro"

    def __init__(self, token, timeout=10):
        self._token = token
        self._timeout = timeout
        self._retry_at = 0
        self._failure = ""

    def _unavailable(self, message):
        # 一次故障后短暂退避，避免同一观察台请求连续等待多个超时。
        self._failure = message
        self._retry_at = monotonic() + 30
        raise TushareError(message) from None

    def query(self, api_name, fields="", **params):
        if monotonic() < self._retry_at:
            raise TushareError(self._failure)
        try:
            response = requests.post(
                self.URL,
                json={"api_name": api_name, "token": self._token,
                      "params": params, "fields": fields},
                timeout=self._timeout,
                allow_redirects=False,
            )
        except requests.RequestException:
            self._unavailable("Tushare 连接失败或超时，请稍后重试")
        if response.status_code != 200:
            self._unavailable(f"Tushare 上游服务异常（HTTP {response.status_code}），请稍后重试")
        try:
            result = response.json()
            if not isinstance(result, dict) or "code" not in result:
                raise ValueError("missing response code")
            if result["code"] != 0:
                message = str(result.get("msg") or "接口请求失败")
                if self._token:
                    message = message.replace(self._token, "[已隐藏]")
                raise TushareError(f"Tushare：{message[:200]}")
            data = result["data"]
            if not isinstance(data["fields"], list) or not isinstance(data["items"], list):
                raise ValueError("invalid data shape")
            return pd.DataFrame(data["items"], columns=data["fields"])
        except (ValueError, KeyError, TypeError):
            self._unavailable("Tushare 返回的数据格式异常，请稍后重试")

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        return partial(self.query, name)
