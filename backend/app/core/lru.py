"""零依赖有界 LRU 缓存。

用于 Sample / 变换 / DataFrame 等常驻对象的缓存，防止无界增长导致
长时间运行后内存耗尽（对应审计 P0-N1）。
"""

from collections import OrderedDict
from typing import Generic, TypeVar

K = TypeVar("K")
V = TypeVar("V")


class LRUCache(Generic[K, V]):
    """有界 LRU 缓存：超出 maxsize 时淘汰最久未使用的条目。"""

    __slots__ = ("_data", "maxsize")

    def __init__(self, maxsize: int = 10) -> None:
        if maxsize < 1:
            raise ValueError("maxsize 必须 >= 1")
        self._data: OrderedDict[K, V] = OrderedDict()
        self.maxsize = maxsize

    def get(self, key: K) -> V | None:
        if key not in self._data:
            return None
        self._data.move_to_end(key)
        return self._data[key]

    def put(self, key: K, value: V) -> None:
        if key in self._data:
            self._data.move_to_end(key)
        self._data[key] = value
        while len(self._data) > self.maxsize:
            self._data.popitem(last=False)

    def pop(self, key: K) -> V | None:
        return self._data.pop(key, None)

    def clear(self) -> None:
        self._data.clear()

    def __len__(self) -> int:
        return len(self._data)

    def __contains__(self, key: K) -> bool:
        return key in self._data
