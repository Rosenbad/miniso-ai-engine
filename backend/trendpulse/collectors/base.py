# ==============================================================================
# 名创优品 AI 产品开发智能决策引擎 - 数据采集器基类 + 限流降级 (Task 3)
# ==============================================================================
# 对应 spec §3.5 限流降级策略:
#   - 每源独立 QPS 控制
#   - 失败重试 3 次 + 指数退避 (0.5s / 1s / 2s)
#   - 熔断器: 连续失败触发降级
#   - Redis 缓存层 (1 小时 TTL)
#
# 本模块提供:
#   1. CircuitBreaker      - 熔断器状态机 (CLOSED / OPEN / HALF_OPEN)
#   2. BaseCollector       - 所有数据源采集器的抽象基类
#   3. CircuitBreakerOpenError - 熔断器开启时抛出的异常
#
# 所有具体采集器 (Task 4: 国内源 / Task 5: 海外源) 继承 BaseCollector,
# 只需实现 _fetch() 方法即可获得限流/重试/熔断/缓存能力。
# ==============================================================================

"""
数据采集器基类模块。

核心组件:
    - CircuitState        : 熔断器状态枚举
    - CircuitBreaker      - 熔断器 (3 态状态机, asyncio.Lock 异步并发安全)
    - CircuitBreakerOpenError : 熔断器开启异常
    - BaseCollector       : 采集器抽象基类 (限流 + 重试 + 熔断 + 缓存)

设计要点:
    - QPS 限流: 基于 time.monotonic() 跟踪上次调用时间, 超速时 asyncio.sleep
    - 指数退避: BACKOFF_DELAYS = [0.5, 1.0, 2.0], 重试 max_retries 次 (总尝试 max_retries+1 次)
    - 熔断器: 连续 failure_threshold 次失败 → OPEN, recovery_timeout 后 → HALF_OPEN
    - Redis 缓存: JSON 序列化, TTL = cache_ttl (默认 3600s = 1 小时)
    - 优雅降级: Redis 不可用时缓存层静默跳过, 不影响采集主流程

注: 本模块使用 asyncio.Lock 提供协程级并发安全 (async-safe),
    而非线程安全 (thread-safe)。跨线程使用需额外同步。
"""

from __future__ import annotations

import asyncio
import json
import time
from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

try:
    from loguru import logger
except ImportError:  # loguru 尚未安装时降级为标准 logging
    import logging

    logger = logging.getLogger(__name__)  # type: ignore[assignment]


# ==============================================================================
# 指数退避延迟常量 (spec §3.5: 0.5s / 1s / 2s)
# ==============================================================================

BACKOFF_DELAYS: List[float] = [0.5, 1.0, 2.0]
"""指数退避延迟序列 (秒)。

对应 spec §3.5: 失败重试 3 次 + 指数退避。
- 第 1 次重试前等待 0.5s
- 第 2 次重试前等待 1.0s
- 第 3 次重试前等待 2.0s

公式: delay = 0.5 * (2 ** attempt)，即 0.5, 1.0, 2.0, 4.0, ...
当 max_retries > len(BACKOFF_DELAYS) 时，取最后一个值 (2.0)。
"""


# ==============================================================================
# 熔断器状态枚举
# ==============================================================================


class CircuitState(Enum):
    """熔断器三态。

    状态转换:
        CLOSED  --[failure_threshold 次连续失败]--> OPEN
        OPEN    --[recovery_timeout 超时]--> HALF_OPEN
        HALF_OPEN --[成功]--> CLOSED
        HALF_OPEN --[失败]--> OPEN
    """

    CLOSED = "CLOSED"
    """正常状态，所有请求正常通过。"""

    OPEN = "OPEN"
    """熔断状态，请求快速失败 (不调用后端服务)。"""

    HALF_OPEN = "HALF_OPEN"
    """半开状态，允许探测请求以测试服务是否恢复。"""


# ==============================================================================
# 熔断器开启异常
# ==============================================================================


class CircuitBreakerOpenError(Exception):
    """熔断器处于 OPEN 状态且无缓存数据时抛出。

    属性:
        collector_name : 触发熔断的采集器名称
    """

    def __init__(self, collector_name: str, message: Optional[str] = None) -> None:
        self.collector_name = collector_name
        msg = message or (
            f"采集器 '{collector_name}' 的熔断器已开启 (OPEN)，"
            f"请求被快速拒绝且无缓存数据可用。"
        )
        super().__init__(msg)


# ==============================================================================
# CircuitBreaker 熔断器
# ==============================================================================


class CircuitBreaker:
    """熔断器 - 基于 asyncio.Lock 的异步并发安全状态机。

    状态:
        CLOSED    : 正常，允许请求
        OPEN      : 熔断，快速拒绝 (可降级返回缓存)
        HALF_OPEN : 探测，仅允许「单个」请求测试恢复 (并发探测会被拒绝)

    配置:
        failure_threshold : 连续失败次数阈值 (默认 3)
        recovery_timeout  : OPEN → HALF_OPEN 恢复等待秒数 (默认 60)

    用法:
        cb = CircuitBreaker(failure_threshold=3, recovery_timeout=60)
        if await cb.is_available():
            try:
                data = await fetch()
                await cb.record_success()
            except Exception:
                await cb.record_failure()
                raise
        else:
            raise CircuitBreakerOpenError("source")

    异步并发安全 (async-safe, 非线程安全):
        所有状态变更方法 (record_success / record_failure / is_available)
        均通过 asyncio.Lock 保护，适合协程并发场景。
        asyncio.Lock 仅保证协程级互斥，跨线程使用需额外同步。
    """

    def __init__(
        self,
        failure_threshold: int = 3,
        recovery_timeout: float = 60,
    ) -> None:
        self._failure_threshold: int = failure_threshold
        self._recovery_timeout: float = recovery_timeout
        self._state: CircuitState = CircuitState.CLOSED
        self._failure_count: int = 0
        self._opened_at: float = 0.0
        self._lock: asyncio.Lock = asyncio.Lock()
        # HALF_OPEN 探测标志: 同一时刻仅允许单个探测请求通过,
        # 由 is_available() 置位, record_success()/record_failure() 复位。
        self._probe_in_progress: bool = False

    # --- 只读属性 ---

    @property
    def state(self) -> CircuitState:
        """当前熔断器状态 (不含自动转换，仅返回内部状态)。"""
        return self._state

    @property
    def failure_count(self) -> int:
        """当前连续失败计数。"""
        return self._failure_count

    @property
    def failure_threshold(self) -> int:
        """失败阈值配置。"""
        return self._failure_threshold

    @property
    def recovery_timeout(self) -> float:
        """恢复超时配置 (秒)。"""
        return self._recovery_timeout

    # --- 状态变更方法 (异步, 协程安全) ---

    async def record_success(self) -> None:
        """记录一次成功请求。

        - 重置失败计数为 0
        - 将状态设为 CLOSED (无论之前是 CLOSED / HALF_OPEN / OPEN)
        - 复位 HALF_OPEN 探测标志, 允许后续新的探测周期
        """
        async with self._lock:
            self._failure_count = 0
            self._probe_in_progress = False
            if self._state is not CircuitState.CLOSED:
                logger.debug(
                    f"CircuitBreaker: {self._state.value} → CLOSED (成功重置)"
                )
            self._state = CircuitState.CLOSED

    async def record_failure(self) -> None:
        """记录一次失败请求。

        - 递增失败计数
        - 若失败计数 >= failure_threshold，状态转为 OPEN 并记录开启时间
        - 若当前为 HALF_OPEN，直接转回 OPEN (探测失败)
        - 复位 HALF_OPEN 探测标志, 允许下一个 recovery_timeout 后的新探测
        """
        async with self._lock:
            self._probe_in_progress = False
            # HALF_OPEN 状态下任何失败都立即重回 OPEN
            if self._state is CircuitState.HALF_OPEN:
                self._state = CircuitState.OPEN
                self._opened_at = time.monotonic()
                logger.warning(
                    f"CircuitBreaker: HALF_OPEN → OPEN (探测请求失败)"
                )
                return

            self._failure_count += 1
            if self._failure_count >= self._failure_threshold:
                self._state = CircuitState.OPEN
                self._opened_at = time.monotonic()
                logger.warning(
                    f"CircuitBreaker: CLOSED → OPEN "
                    f"(连续失败 {self._failure_count}/{self._failure_threshold})"
                )

    async def is_available(self) -> bool:
        """检查是否允许请求通过。

        - CLOSED    → True
        - OPEN      → 检查是否超过 recovery_timeout，若是则转为 HALF_OPEN
                      并占用唯一探测名额返回 True
        - HALF_OPEN → 仅首个探测请求返回 True (置位 _probe_in_progress)，
                      其余并发请求返回 False (避免多个探测同时打到后端)

        返回:
            True  : 请求可以继续
            False : 请求应被快速拒绝 (熔断中 / 探测名额已被占用)
        """
        async with self._lock:
            if self._state is CircuitState.CLOSED:
                return True

            if self._state is CircuitState.OPEN:
                # 检查恢复超时
                elapsed = time.monotonic() - self._opened_at
                if elapsed >= self._recovery_timeout:
                    self._state = CircuitState.HALF_OPEN
                    self._probe_in_progress = True
                    logger.info(
                        f"CircuitBreaker: OPEN → HALF_OPEN "
                        f"(恢复超时 {self._recovery_timeout}s 已过, 允许单个探测)"
                    )
                    return True
                return False

            # HALF_OPEN: 仅允许单个探测请求, 探测进行中则拒绝其余请求
            if self._probe_in_progress:
                return False
            self._probe_in_progress = True
            return True


# ==============================================================================
# BaseCollector 采集器抽象基类
# ==============================================================================


class BaseCollector(ABC):
    """数据采集器抽象基类。

    提供四大核心能力 (spec §3.5 限流降级策略):
        1. QPS 限流     : 每源独立 QPS 控制，超速时自动 sleep
        2. 指数退避重试 : 失败重试 max_retries 次，延迟 0.5s / 1s / 2s
        3. 熔断器       : 连续失败触发降级，OPEN 时快速失败
        4. Redis 缓存   : 1 小时 TTL，避免重复采集

    子类只需实现 ``_fetch()`` 方法即可获得全部能力。

    构造参数:
        name            : 采集器名称 (如 "xiaohongshu", "tiktok")
        qps_limit       : 每秒最大查询数 (默认 1.0)
        cache_ttl       : 缓存存活时间秒 (默认 3600 = 1 小时)
        max_retries     : 最大「重试」次数 (默认 3, 总尝试次数 = max_retries + 1)
        circuit_breaker : 可选的 CircuitBreaker 实例 (不传则自动创建)

    用法示例::

        class XiaohongshuCollector(BaseCollector):
            async def _fetch(self, keyword: str, **kwargs):
                # 实际 HTTP 请求逻辑
                response = await self._client.get(...)
                return response.json()["data"]

        collector = XiaohongshuCollector(
            name="xiaohongshu",
            qps_limit=2.0,
            cache_ttl=3600,
        )
        data = await collector.collect(keyword="侘寂风")
    """

    def __init__(
        self,
        name: str,
        qps_limit: float = 1.0,
        cache_ttl: int = 3600,
        max_retries: int = 3,
        circuit_breaker: Optional[CircuitBreaker] = None,
    ) -> None:
        # 校验 max_retries: 必须 >= 1 (避免 range(max_retries) 为空导致
        # last_exc 未赋值, 进而触发 AssertionError)
        if max_retries < 1:
            raise ValueError(
                f"max_retries must be >= 1 (got {max_retries}); "
                f"max_retries 表示重试次数, 总尝试次数 = max_retries + 1"
            )

        self.name: str = name
        self.qps_limit: float = qps_limit
        self.cache_ttl: int = cache_ttl
        self.max_retries: int = max_retries
        self.circuit_breaker: CircuitBreaker = circuit_breaker or CircuitBreaker()

        # 限流状态
        # 最小调用间隔 = 1 / QPS (QPS=1 → 间隔 1s, QPS=10 → 间隔 0.1s)
        self._min_interval: float = (
            1.0 / qps_limit if qps_limit > 0 else 0.0
        )
        self._last_call_time: float = 0.0
        # 限流锁: 保护「读取 _last_call_time → sleep → 更新 _last_call_time」
        # 整段读-睡-写操作, 避免并发协程竞态导致 QPS 失效 (async-safe)
        self._rate_lock: asyncio.Lock = asyncio.Lock()

    # ==================================================================
    # 抽象方法 - 子类必须实现
    # ==================================================================

    @abstractmethod
    async def _fetch(self, **kwargs: Any) -> List[Dict[str, Any]]:
        """执行实际的数据采集 (子类实现)。

        参数:
            **kwargs : 采集参数 (如 keyword, region, limit 等)

        返回:
            采集到的数据列表，每个元素为 dict

        异常:
            采集失败时抛出任意异常，由 _retry_with_backoff 处理重试
        """
        raise NotImplementedError

    # ==================================================================
    # collect() - 主入口
    # ==================================================================

    async def collect(self, **kwargs: Any) -> List[Dict[str, Any]]:
        """采集数据的主入口 (含熔断/限流/缓存/重试)。

        流程 (spec §3.5):
            1. 检查熔断器 — OPEN 时尝试缓存降级，无缓存则抛 CircuitBreakerOpenError
            2. 检查缓存   — 命中则直接返回 (不调用 _fetch, 不消耗限流配额)
            3. 检查限流   — 距上次调用不足 _min_interval 则 sleep
            4. 重试采集   — _fetch + 指数退避重试 (1 次初始 + max_retries 次重试)
            5. 成功       — record_success + 写缓存
            6. 失败       — record_failure + 尝试缓存降级，无缓存则抛异常

        注: 缓存检查先于限流检查, 这样缓存命中时无需付出限流等待代价。

        参数:
            **kwargs : 传递给 _fetch 的采集参数

        返回:
            采集到的数据列表

        异常:
            CircuitBreakerOpenError : 熔断器 OPEN 且无缓存
            Exception               : _fetch 重试耗尽后的最后一个异常 (无缓存时)
        """
        cache_key: str = self._cache_key(**kwargs)

        # --- Step 1: 熔断器检查 ---
        if not await self.circuit_breaker.is_available():
            # 熔断器 OPEN: 尝试缓存降级
            cached = await self._get_cached(cache_key)
            if cached is not None:
                logger.info(
                    f"[{self.name}] 熔断器 OPEN，返回缓存数据 "
                    f"(key={cache_key})"
                )
                return cached
            raise CircuitBreakerOpenError(self.name)

        # --- Step 2: 缓存检查 (先于限流, 命中则不消耗限流配额) ---
        cached = await self._get_cached(cache_key)
        if cached is not None:
            logger.debug(f"[{self.name}] 缓存命中 (key={cache_key})")
            return cached

        # --- Step 3: QPS 限流 ---
        await self._check_rate_limit()

        # --- Step 4: 重试采集 ---
        try:
            data = await self._retry_with_backoff(self._fetch, **kwargs)
        except Exception as exc:
            # --- Step 6 (失败): 记录失败 + 缓存降级 ---
            await self.circuit_breaker.record_failure()
            logger.error(
                f"[{self.name}] 采集失败 (重试 {self.max_retries} 次后仍失败): {exc}"
            )
            # 尝试缓存降级
            fallback = await self._get_cached(cache_key)
            if fallback is not None:
                logger.warning(
                    f"[{self.name}] 采集失败，返回缓存降级数据 (key={cache_key})"
                )
                return fallback
            raise

        # --- Step 5 (成功): 记录成功 + 写缓存 ---
        await self.circuit_breaker.record_success()
        await self._set_cached(cache_key, data)
        logger.info(
            f"[{self.name}] 采集成功: {len(data)} 条数据已缓存 (key={cache_key})"
        )
        return data

    # ==================================================================
    # 指数退避重试
    # ==================================================================

    async def _retry_with_backoff(
        self,
        func: Callable[..., Any],
        *args: Any,
        **kwargs: Any,
    ) -> List[Dict[str, Any]]:
        """对 func 执行指数退避重试。

        策略:
            - 总尝试次数 = max_retries + 1 (1 次初始尝试 + max_retries 次重试)
            - 每次失败后等待 BACKOFF_DELAYS[attempt] 秒 (0.5 / 1.0 / 2.0)
            - 成功则立即返回
            - 全部失败则抛出最后一个异常

        注: ``max_retries`` 表示「重试次数」而非「总尝试次数」。
            例: max_retries=3 → 4 次尝试 (1 初始 + 3 重试), 3 次退避
            (0.5s / 1.0s / 2.0s)。这与 spec §3.5
            「失败重试 3 次 + 指数退避 (0.5s / 1s / 2s)」一致。

        参数:
            func     : 要重试的异步可调用对象
            *args    : 位置参数 (透传给 func)
            **kwargs : 关键字参数 (透传给 func)

        返回:
            func 的返回值

        异常:
            所有 (max_retries + 1) 次尝试均失败后，抛出最后一个异常
        """
        last_exc: Optional[BaseException] = None
        total_attempts: int = self.max_retries + 1
        for attempt in range(total_attempts):
            try:
                return await func(*args, **kwargs)
            except Exception as exc:
                last_exc = exc
                if attempt < self.max_retries:
                    # 非最后一次尝试: 等待退避后重试
                    # 获取退避延迟: 超出 BACKOFF_DELAYS 长度时取最后一个
                    delay: float = BACKOFF_DELAYS[
                        min(attempt, len(BACKOFF_DELAYS) - 1)
                    ]
                    logger.debug(
                        f"[{self.name}] 第 {attempt + 1}/{total_attempts} 次尝试失败, "
                        f"{delay}s 后重试: {exc}"
                    )
                    await asyncio.sleep(delay)

        # 所有尝试均失败。
        # max_retries >= 1 已在 __init__ 校验, 循环至少执行一次, last_exc 必已赋值;
        # 此处用显式判空替代 assert, 避免极端情况下 AssertionError 掩盖真实异常。
        if last_exc is not None:
            raise last_exc

    # ==================================================================
    # QPS 限流
    # ==================================================================

    async def _check_rate_limit(self) -> None:
        """QPS 限流检查 — 距上次调用不足 _min_interval 时 sleep。

        实现 (异步并发安全):
            - 通过 _rate_lock 保护「读取 _last_call_time → sleep → 更新时间」
              整段读-睡-写操作, 避免并发协程同时读到旧的 _last_call_time
              而全部跳过等待, 导致 QPS 限流失效
            - 若 elapsed < _min_interval，sleep (interval - elapsed)
            - 更新 _last_call_time 为当前时间
        """
        if self._min_interval <= 0:
            return

        async with self._rate_lock:
            now: float = time.monotonic()
            elapsed: float = now - self._last_call_time
            if elapsed < self._min_interval:
                wait: float = self._min_interval - elapsed
                logger.debug(
                    f"[{self.name}] QPS 限流: 等待 {wait:.3f}s "
                    f"(QPS={self.qps_limit}, 已过 {elapsed:.3f}s)"
                )
                await asyncio.sleep(wait)

            self._last_call_time = time.monotonic()

    # ==================================================================
    # Redis 缓存
    # ==================================================================

    async def _get_cached(self, key: str) -> Optional[List[Dict[str, Any]]]:
        """从 Redis 读取缓存数据。

        - Redis 返回 None (key 不存在) → 返回 None
        - Redis 返回 JSON 字符串 → 反序列化为 list[dict] 返回
        - Redis 不可用 / 异常 → 静默返回 None (优雅降级)

        参数:
            key : 缓存键

        返回:
            缓存数据列表，或 None (未命中/异常)
        """
        try:
            from shared.redis_client import get_redis_client

            client = get_redis_client()
            raw: Optional[str] = await client.get(key)
            if raw is None:
                return None
            return json.loads(raw)  # type: ignore[no-any-return]
        except Exception as exc:
            logger.debug(f"[{self.name}] 缓存读取失败 (降级跳过): {exc}")
            return None

    async def _set_cached(self, key: str, data: List[Dict[str, Any]]) -> None:
        """将数据写入 Redis 缓存。

        - JSON 序列化后写入，TTL = self.cache_ttl
        - Redis 不可用 / 异常 → 静默跳过 (不影响采集流程)

        参数:
            key  : 缓存键
            data : 要缓存的数据列表
        """
        try:
            from shared.redis_client import get_redis_client

            client = get_redis_client()
            await client.set(key, json.dumps(data, ensure_ascii=False), ex=self.cache_ttl)
        except Exception as exc:
            logger.debug(f"[{self.name}] 缓存写入失败 (降级跳过): {exc}")

    def _cache_key(self, **kwargs: Any) -> str:
        """根据采集器名称和参数生成缓存键。

        格式: ``collector:{name}:{k1}={v1}:{k2}={v2}:...``

        参数按 key 排序，确保相同参数 (不同顺序) 生成相同键。

        参数:
            **kwargs : 采集参数

        返回:
            缓存键字符串
        """
        sorted_items = sorted(kwargs.items())
        parts = [f"{k}={v}" for k, v in sorted_items]
        return f"collector:{self.name}:{':'.join(parts)}"


# ==============================================================================
# 模块导出
# ==============================================================================

__all__ = [
    "BACKOFF_DELAYS",
    "CircuitState",
    "CircuitBreaker",
    "CircuitBreakerOpenError",
    "BaseCollector",
]
