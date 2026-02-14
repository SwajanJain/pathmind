import json
from dataclasses import dataclass
from abc import ABC, abstractmethod

import redis


class CacheBackend(ABC):
    @abstractmethod
    def get(self, key: str) -> dict | None:
        raise NotImplementedError

    @abstractmethod
    def set(self, key: str, value: dict, ttl_seconds: int) -> None:
        raise NotImplementedError

    @property
    @abstractmethod
    def hit_rate(self) -> float:
        raise NotImplementedError


@dataclass
class CacheStats:
    hits: int = 0
    misses: int = 0

    def record_hit(self) -> None:
        self.hits += 1

    def record_miss(self) -> None:
        self.misses += 1

    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return 0.0 if total == 0 else self.hits / total


class InMemoryCache(CacheBackend):
    def __init__(self) -> None:
        self._store: dict[str, dict] = {}
        self._stats = CacheStats()

    def get(self, key: str) -> dict | None:
        value = self._store.get(key)
        if value is None:
            self._stats.record_miss()
        else:
            self._stats.record_hit()
        return value

    def set(self, key: str, value: dict, ttl_seconds: int) -> None:
        self._store[key] = value

    @property
    def hit_rate(self) -> float:
        return self._stats.hit_rate


class RedisCache(CacheBackend):
    def __init__(self, redis_url: str):
        self.client = redis.Redis.from_url(redis_url, decode_responses=True)
        self._stats = CacheStats()

    def get(self, key: str) -> dict | None:
        value = self.client.get(key)
        if value is None:
            self._stats.record_miss()
            return None
        self._stats.record_hit()
        return json.loads(value)

    def set(self, key: str, value: dict, ttl_seconds: int) -> None:
        self.client.set(key, json.dumps(value), ex=ttl_seconds)

    @property
    def hit_rate(self) -> float:
        return self._stats.hit_rate


def build_cache(redis_url: str) -> CacheBackend:
    try:
        cache = RedisCache(redis_url)
        cache.client.ping()
        return cache
    except redis.RedisError:
        return InMemoryCache()
