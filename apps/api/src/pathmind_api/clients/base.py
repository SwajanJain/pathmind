import asyncio
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import httpx


class DownstreamError(RuntimeError):
    def __init__(self, source: str, message: str):
        super().__init__(message)
        self.source = source


@dataclass
class HealthResult:
    status: str
    latency_ms: int | None = None
    error: str | None = None


class CircuitBreaker:
    def __init__(self, failure_threshold: int = 5, recovery_timeout_seconds: int = 60):
        self.failure_threshold = failure_threshold
        self.recovery_timeout_seconds = recovery_timeout_seconds
        self.failure_count = 0
        self.open_until: datetime | None = None

    def allow_request(self) -> bool:
        if self.open_until is None:
            return True
        now = datetime.now(timezone.utc)
        return now >= self.open_until

    def record_success(self) -> None:
        self.failure_count = 0
        self.open_until = None

    def record_failure(self) -> None:
        self.failure_count += 1
        if self.failure_count >= self.failure_threshold:
            self.open_until = datetime.now(timezone.utc) + timedelta(seconds=self.recovery_timeout_seconds)


class BaseHttpClient:
    def __init__(
        self,
        name: str,
        base_url: str,
        timeout_seconds: float = 15,
        max_retries: int = 2,
    ) -> None:
        self.name = name
        self.max_retries = max_retries
        self.client = httpx.AsyncClient(base_url=base_url, timeout=timeout_seconds)
        self.circuit_breaker = CircuitBreaker()

    async def close(self) -> None:
        await self.client.aclose()

    async def request(self, method: str, url: str, **kwargs) -> httpx.Response:
        if not self.circuit_breaker.allow_request():
            raise DownstreamError(self.name, f"{self.name} circuit is open")

        wait_seconds = [1, 3]
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                response = await self.client.request(method, url, **kwargs)
                response.raise_for_status()
                self.circuit_breaker.record_success()
                return response
            except (httpx.HTTPError, httpx.TimeoutException) as exc:
                self.circuit_breaker.record_failure()
                last_error = exc
                if attempt >= self.max_retries:
                    break
                await asyncio.sleep(wait_seconds[min(attempt, len(wait_seconds) - 1)])
        raise DownstreamError(self.name, str(last_error))

    async def ping(self, path: str = "/") -> HealthResult:
        start = time.perf_counter()
        try:
            await self.request("GET", path)
        except DownstreamError as exc:
            return HealthResult(status="down", error=str(exc))
        latency_ms = int((time.perf_counter() - start) * 1000)
        return HealthResult(status="up", latency_ms=latency_ms)

