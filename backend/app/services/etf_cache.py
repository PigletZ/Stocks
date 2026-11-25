"""仅保存已验证的 Tushare 数据；文件损坏或写入失败不影响在线请求。"""
import json
import logging
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from .runtime_state import get_preferences

logger = logging.getLogger(__name__)


class EtfFrameCache:
    def __init__(self, directory=None):
        self.directory = Path(directory) if directory is not None else Path(__file__).resolve().parents[2] / ".cache" / "etf"
        self._memory = {}

    def _path(self, key):
        if not re.fullmatch(r"[a-z0-9-]+", key):
            raise ValueError("Invalid ETF cache key")
        return self.directory / f"{key}.json"

    def get(self, key):
        cached = self._memory.get(key)
        if cached is None:
            try:
                payload = json.loads(self._path(key).read_text(encoding="utf-8"))
                if payload["version"] != 1 or payload["key"] != key:
                    return None
                fetched_at = datetime.fromisoformat(payload["fetched_at"])
                if fetched_at.tzinfo is None:
                    return None
                frame = pd.DataFrame(payload["frame"]["data"], columns=payload["frame"]["columns"])
                cached = (fetched_at, frame)
                self._memory[key] = cached
                self._trim_memory()
            except (OSError, ValueError, KeyError, TypeError):
                return None
        return cached[0], cached[1].copy()

    def put(self, key, frame):
        fetched_at = datetime.now(timezone.utc)
        self._memory[key] = (fetched_at, frame.copy())
        self._trim_memory()
        temporary = None
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            payload = {"version": 1, "key": key, "fetched_at": fetched_at.isoformat(),
                       "frame": json.loads(frame.to_json(orient="split", index=False, force_ascii=False))}
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.directory, suffix=".tmp", delete=False) as handle:
                temporary = handle.name
                json.dump(payload, handle, ensure_ascii=False)
            os.replace(temporary, self._path(key))
            # 与原内存缓存一致，仅保留最近写入的 100 个日线快照。
            for prefix in ('daily-', 'factor-'):
                snapshots = sorted(self.directory.glob(prefix+'*.json'), key=lambda path: path.stat().st_mtime, reverse=True)
                for old in snapshots[get_preferences().etf_snapshot_limit:]:
                    old.unlink()
        except (OSError, ValueError, TypeError):
            logger.warning("ETF 持久缓存写入失败，当前请求仍使用已获取的数据")
        finally:
            if temporary and os.path.exists(temporary):
                try:
                    os.unlink(temporary)
                except OSError:
                    pass

    def _trim_memory(self):
        for prefix in ('daily-', 'factor-'):
            keys = [key for key in self._memory if key.startswith(prefix)]
            for key in keys[:-get_preferences().etf_snapshot_limit]:
                del self._memory[key]
