"""
缓存管理器 (Cache Manager)
智能缓存工具调用结果，避免重复请求。支持 TTL 过期和 LRU 淘汰。
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Optional
from pathlib import Path
from collections import OrderedDict


@dataclass
class CacheEntry:
    key: str
    value: Any
    created_at: float
    ttl_ms: int
    access_count: int = 0
    last_accessed: float = 0.0
    source_tool: str = ""

    @property
    def is_expired(self) -> bool:
        return (time.time() - self.created_at) * 1000 > self.ttl_ms

    @property
    def age_ms(self) -> float:
        return (time.time() - self.created_at) * 1000

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "created_at": self.created_at,
            "ttl_ms": self.ttl_ms,
            "access_count": self.access_count,
            "source_tool": self.source_tool,
            "age_ms": round(self.age_ms),
            "expired": self.is_expired,
        }


class CacheManager:
    """
    智能缓存管理器。

    特性：
    - TTL 过期自动淘汰
    - LRU 淘汰（达到容量上限时）
    - 按工具名分组管理
    - 持久化到磁盘（可选）

    用法::

        cache = CacheManager(max_entries=200, default_ttl_ms=300_000)
        # 写入
        cache.set("search:小米手机价格", data, source_tool="web_search")
        # 读取
        result = cache.get("search:小米手机价格")
        if result is None:
            result = fetch_fresh_data()
            cache.set("search:小米手机价格", result, source_tool="web_search")
    """

    # 不同工具的默认 TTL
    DEFAULT_TTLS = {
        "web_search": 300_000,       # 5 分钟
        "weather": 1_800_000,        # 30 分钟
        "stock": 60_000,             # 1 分钟
        "local_file_search": 600_000,  # 10 分钟
        "device_chat": 0,            # 不缓存跨设备结果
    }

    def __init__(
        self,
        max_entries: int = 200,
        default_ttl_ms: int = 300_000,
        persist_path: Optional[str] = None,
    ):
        self._max_entries = max_entries
        self._default_ttl_ms = default_ttl_ms
        self._persist_path = Path(persist_path) if persist_path else None
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self._stats = {"hits": 0, "misses": 0, "evictions": 0}
        if self._persist_path:
            self._load()

    # ── 持久化 ────────────────────────────────────────────────

    def _load(self):
        if not self._persist_path or not self._persist_path.exists():
            return
        try:
            data = json.loads(self._persist_path.read_text(encoding="utf-8"))
            for item in data.get("entries", []):
                entry = CacheEntry(
                    key=item["key"],
                    value=item.get("value"),
                    created_at=item["created_at"],
                    ttl_ms=item["ttl_ms"],
                    access_count=item.get("access_count", 0),
                    last_accessed=item.get("last_accessed", 0),
                    source_tool=item.get("source_tool", ""),
                )
                if not entry.is_expired:
                    self._cache[entry.key] = entry
        except Exception:
            pass  # 损坏则从空缓存开始

    def _save(self):
        if not self._persist_path:
            return
        data = {
            "entries": [
                {
                    "key": e.key,
                    "value": e.value,
                    "created_at": e.created_at,
                    "ttl_ms": e.ttl_ms,
                    "access_count": e.access_count,
                    "last_accessed": e.last_accessed,
                    "source_tool": e.source_tool,
                }
                for e in self._cache.values()
                if not e.is_expired
            ]
        }
        self._persist_path.parent.mkdir(parents=True, exist_ok=True)
        self._persist_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    # ── 核心接口 ──────────────────────────────────────────────

    @staticmethod
    def make_key(tool: str, query: str, **kwargs) -> str:
        """生成缓存键"""
        raw = f"{tool}:{query}:{json.dumps(kwargs, sort_keys=True)}"
        return hashlib.md5(raw.encode()).hexdigest()

    def get(self, key: str) -> Optional[Any]:
        """获取缓存值，命中则更新访问信息"""
        entry = self._cache.get(key)
        if entry is None:
            self._stats["misses"] += 1
            return None
        if entry.is_expired:
            del self._cache[key]
            self._stats["misses"] += 1
            return None
        # LRU：移到末尾
        self._cache.move_to_end(key)
        entry.access_count += 1
        entry.last_accessed = time.time()
        self._stats["hits"] += 1
        return entry.value

    def set(
        self,
        key: str,
        value: Any,
        ttl_ms: Optional[int] = None,
        source_tool: str = "",
    ):
        """写入缓存"""
        if ttl_ms is None:
            ttl_ms = self.DEFAULT_TTLS.get(source_tool, self._default_ttl_ms)
        if ttl_ms <= 0:
            return  # TTL 为 0 表示不缓存

        now = time.time()
        entry = CacheEntry(
            key=key,
            value=value,
            created_at=now,
            ttl_ms=ttl_ms,
            access_count=0,
            last_accessed=now,
            source_tool=source_tool,
        )
        self._cache[key] = entry
        self._cache.move_to_end(key)

        # LRU 淘汰
        while len(self._cache) > self._max_entries:
            evicted_key, _ = self._cache.popitem(last=False)
            self._stats["evictions"] += 1

        if self._persist_path:
            self._save()

    def invalidate(self, key: str) -> bool:
        """删除指定缓存"""
        if key in self._cache:
            del self._cache[key]
            return True
        return False

    def clear(self, tool: Optional[str] = None):
        """清空缓存（可按工具名过滤）"""
        if tool is None:
            self._cache.clear()
        else:
            keys_to_remove = [k for k, v in self._cache.items() if v.source_tool == tool]
            for k in keys_to_remove:
                del self._cache[k]

    def cleanup_expired(self):
        """清理所有过期条目"""
        expired_keys = [k for k, v in self._cache.items() if v.is_expired]
        for k in expired_keys:
            del self._cache[k]

    # ── 查询接口 ──────────────────────────────────────────────

    @property
    def size(self) -> int:
        return len(self._cache)

    @property
    def hit_rate(self) -> float:
        total = self._stats["hits"] + self._stats["misses"]
        return self._stats["hits"] / total if total > 0 else 0.0

    def stats(self) -> dict:
        return {
            "size": self.size,
            "max_entries": self._max_entries,
            "hits": self._stats["hits"],
            "misses": self._stats["misses"],
            "hit_rate": f"{self.hit_rate:.1%}",
            "evictions": self._stats["evictions"],
        }

    def to_dict(self) -> dict:
        return {
            "stats": self.stats(),
            "entries": [e.to_dict() for e in list(self._cache.values())[-20:]],
        }
