# ==============================================================================
# 名创优品 AI 产品开发智能决策引擎 - 数据采集器基类单元测试 (Task 3)
# ==============================================================================
# 对应 Task 3: 数据采集器基类 + 限流降级
# 覆盖:
#   1. CircuitBreaker       - 熔断器状态机 (CLOSED / OPEN / HALF_OPEN)
#   2. TestRetryMechanism   - 指数退避重试 (0.5s / 1s / 2s, 3 次)
#   3. TestBaseCollector    - collect() 主流程 / 缓存 / 限流 / 熔断联动
# ==============================================================================

"""
测试 BaseCollector 与 CircuitBreaker。

测试策略 (TDD):
  1. CircuitBreaker 状态机 - 初始 CLOSED / 3 次失败 OPEN / 超时 HALF_OPEN / 成功 CLOSED
  2. 重试机制 - 全部失败抛异常 / 中途成功返回 / 指数退避延迟正确
  3. BaseCollector - 成功采集+缓存 / 失败+熔断 / 熔断OPEN快速失败 / 缓存命中 / 限流

Mock 策略:
  - asyncio.sleep       : 避免真实延迟
  - time.monotonic       : 控制 CircuitBreaker 时间窗口
  - Redis client         : 不依赖真实 Redis
  - _fetch / _check_rate_limit : 按测试场景隔离
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock

import pytest

from trendpulse.collectors.base import (
    BACKOFF_DELAYS,
    BaseCollector,
    CircuitBreaker,
    CircuitBreakerOpenError,
    CircuitState,
)


# ==============================================================================
# 测试辅助 - 具体采集器子类
# ==============================================================================


class _TestCollector(BaseCollector):
    """BaseCollector 的具体子类，用于单元测试。

    通过 fetch_func 参数可自定义 _fetch 行为:
        - None          : 返回固定数据 [{"data": "test"}]
        - AsyncMock     : 按预设 side_effect / return_value 执行
        - callable      : 调用并返回结果
    """

    def __init__(
        self,
        fetch_func: Optional[Any] = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(name="test", **kwargs)
        self._fetch_func = fetch_func
        self.fetch_call_count: int = 0

    async def _fetch(self, **kwargs: Any) -> List[Dict[str, Any]]:
        self.fetch_call_count += 1
        if self._fetch_func is not None:
            result = self._fetch_func(**kwargs)
            # 支持 async callable
            if hasattr(result, "__await__"):
                result = await result
            return result
        return [{"data": "test"}]


# ==============================================================================
# 1. CircuitBreaker 熔断器测试
# ==============================================================================


class TestCircuitBreaker:
    """CircuitBreaker 状态机测试 - CLOSED / OPEN / HALF_OPEN 转换。"""

    # --- 初始状态 ---

    async def test_initial_state_is_closed(self) -> None:
        """新创建的 CircuitBreaker 初始状态应为 CLOSED。"""
        cb = CircuitBreaker()
        assert cb.state == CircuitState.CLOSED

    async def test_initial_failure_count_is_zero(self) -> None:
        """新创建的 CircuitBreaker 失败计数应为 0。"""
        cb = CircuitBreaker()
        assert cb.failure_count == 0

    async def test_initial_is_available(self) -> None:
        """CLOSED 状态下 is_available() 应返回 True。"""
        cb = CircuitBreaker()
        assert await cb.is_available() is True

    # --- 失败触发熔断 ---

    async def test_three_consecutive_failures_open_circuit(self) -> None:
        """连续 3 次失败后，熔断器应从 CLOSED 转为 OPEN。"""
        cb = CircuitBreaker(failure_threshold=3)
        await cb.record_failure()
        await cb.record_failure()
        # 仅 2 次失败，尚未达到阈值
        assert cb.state == CircuitState.CLOSED
        await cb.record_failure()
        # 第 3 次失败 → OPEN
        assert cb.state == CircuitState.OPEN

    async def test_is_available_false_when_open(self) -> None:
        """OPEN 状态下 is_available() 应返回 False (快速失败)。"""
        cb = CircuitBreaker(failure_threshold=3)
        for _ in range(3):
            await cb.record_failure()
        assert await cb.is_available() is False

    async def test_failure_count_increments(self) -> None:
        """每次 record_failure() 应递增失败计数。"""
        cb = CircuitBreaker(failure_threshold=5)
        await cb.record_failure()
        assert cb.failure_count == 1
        await cb.record_failure()
        assert cb.failure_count == 2

    async def test_custom_failure_threshold(self) -> None:
        """自定义 failure_threshold=5 时，第 5 次失败才触发熔断。"""
        cb = CircuitBreaker(failure_threshold=5)
        for _ in range(4):
            await cb.record_failure()
        assert cb.state == CircuitState.CLOSED
        await cb.record_failure()
        assert cb.state == CircuitState.OPEN

    # --- 成功重置 ---

    async def test_success_resets_to_closed(self) -> None:
        """record_success() 应将状态重置为 CLOSED 且失败计数归零。"""
        cb = CircuitBreaker(failure_threshold=3)
        await cb.record_failure()
        await cb.record_failure()
        assert cb.failure_count == 2
        await cb.record_success()
        assert cb.state == CircuitState.CLOSED
        assert cb.failure_count == 0

    async def test_success_resets_from_open(self) -> None:
        """OPEN 状态下 record_success() 也能重置为 CLOSED。"""
        cb = CircuitBreaker(failure_threshold=3)
        for _ in range(3):
            await cb.record_failure()
        assert cb.state == CircuitState.OPEN
        await cb.record_success()
        assert cb.state == CircuitState.CLOSED

    # --- 超时恢复 (OPEN → HALF_OPEN) ---

    async def test_recovery_timeout_transitions_to_half_open(
        self, mocker: Any
    ) -> None:
        """OPEN 状态经过 recovery_timeout 后，is_available() 触发转为 HALF_OPEN。"""
        time_now = {"t": 0.0}
        mocker.patch(
            "trendpulse.collectors.base.time.monotonic",
            side_effect=lambda: time_now["t"],
        )
        cb = CircuitBreaker(failure_threshold=3, recovery_timeout=60)
        for _ in range(3):
            await cb.record_failure()
        assert cb.state == CircuitState.OPEN
        # 时间内仍为 OPEN
        time_now["t"] = 30.0
        assert await cb.is_available() is False
        assert cb.state == CircuitState.OPEN
        # 超过 recovery_timeout → HALF_OPEN
        time_now["t"] = 61.0
        assert await cb.is_available() is True
        assert cb.state == CircuitState.HALF_OPEN

    async def test_half_open_is_available(self, mocker: Any) -> None:
        """HALF_OPEN 状态下仅首个探测请求 is_available() 返回 True。"""
        time_now = {"t": 0.0}
        mocker.patch(
            "trendpulse.collectors.base.time.monotonic",
            side_effect=lambda: time_now["t"],
        )
        cb = CircuitBreaker(failure_threshold=3, recovery_timeout=60)
        for _ in range(3):
            await cb.record_failure()
        time_now["t"] = 61.0
        # 首次: OPEN → HALF_OPEN, 占用唯一探测名额
        assert await cb.is_available() is True
        assert cb.state == CircuitState.HALF_OPEN
        # 第二次: 探测进行中, 拒绝其余请求 (避免并发多探测)
        assert await cb.is_available() is False

    async def test_half_open_success_closes_circuit(self, mocker: Any) -> None:
        """HALF_OPEN 状态下成功 → 回到 CLOSED。"""
        time_now = {"t": 0.0}
        mocker.patch(
            "trendpulse.collectors.base.time.monotonic",
            side_effect=lambda: time_now["t"],
        )
        cb = CircuitBreaker(failure_threshold=3, recovery_timeout=60)
        for _ in range(3):
            await cb.record_failure()
        time_now["t"] = 61.0
        await cb.is_available()  # → HALF_OPEN
        await cb.record_success()
        assert cb.state == CircuitState.CLOSED

    async def test_half_open_failure_reopens_circuit(self, mocker: Any) -> None:
        """HALF_OPEN 状态下失败 → 重新回到 OPEN。"""
        time_now = {"t": 0.0}
        mocker.patch(
            "trendpulse.collectors.base.time.monotonic",
            side_effect=lambda: time_now["t"],
        )
        cb = CircuitBreaker(failure_threshold=3, recovery_timeout=60)
        for _ in range(3):
            await cb.record_failure()
        time_now["t"] = 61.0
        await cb.is_available()  # → HALF_OPEN
        await cb.record_failure()
        assert cb.state == CircuitState.OPEN

    async def test_half_open_probe_reset_allows_next_probe(self, mocker: Any) -> None:
        """探测完成后 (record_failure 复位标志) 允许下一次探测。"""
        time_now = {"t": 0.0}
        mocker.patch(
            "trendpulse.collectors.base.time.monotonic",
            side_effect=lambda: time_now["t"],
        )
        cb = CircuitBreaker(failure_threshold=3, recovery_timeout=60)
        for _ in range(3):
            await cb.record_failure()
        time_now["t"] = 61.0
        # 首个探测请求被允许
        assert await cb.is_available() is True
        # 探测进行中, 第二个被拒
        assert await cb.is_available() is False
        # 探测失败 → 复位标志, 回到 OPEN
        await cb.record_failure()
        assert cb.state == CircuitState.OPEN
        # 再次超过 recovery_timeout → 允许新的探测
        time_now["t"] = 122.0
        assert await cb.is_available() is True
        # 新的探测进行中, 再次被拒
        assert await cb.is_available() is False

    async def test_half_open_probe_reset_on_success(self, mocker: Any) -> None:
        """探测成功后 (record_success 复位标志) 状态回到 CLOSED。"""
        time_now = {"t": 0.0}
        mocker.patch(
            "trendpulse.collectors.base.time.monotonic",
            side_effect=lambda: time_now["t"],
        )
        cb = CircuitBreaker(failure_threshold=3, recovery_timeout=60)
        for _ in range(3):
            await cb.record_failure()
        time_now["t"] = 61.0
        # 首个探测请求被允许
        assert await cb.is_available() is True
        # 探测进行中, 第二个被拒
        assert await cb.is_available() is False
        # 探测成功 → 复位标志, 回到 CLOSED
        await cb.record_success()
        assert cb.state == CircuitState.CLOSED
        # CLOSED 状态下所有请求均可通过
        assert await cb.is_available() is True
        assert await cb.is_available() is True

    async def test_within_recovery_timeout_stays_open(self, mocker: Any) -> None:
        """OPEN 状态在 recovery_timeout 之内应保持 OPEN。"""
        time_now = {"t": 0.0}
        mocker.patch(
            "trendpulse.collectors.base.time.monotonic",
            side_effect=lambda: time_now["t"],
        )
        cb = CircuitBreaker(failure_threshold=3, recovery_timeout=60)
        for _ in range(3):
            await cb.record_failure()
        time_now["t"] = 59.0  # 未超时
        assert await cb.is_available() is False
        assert cb.state == CircuitState.OPEN

    async def test_recovery_timeout_boundary(self, mocker: Any) -> None:
        """恰好等于 recovery_timeout 时应转为 HALF_OPEN (>= 判断)。"""
        time_now = {"t": 0.0}
        mocker.patch(
            "trendpulse.collectors.base.time.monotonic",
            side_effect=lambda: time_now["t"],
        )
        cb = CircuitBreaker(failure_threshold=3, recovery_timeout=60)
        for _ in range(3):
            await cb.record_failure()
        time_now["t"] = 60.0  # 恰好等于
        assert await cb.is_available() is True
        assert cb.state == CircuitState.HALF_OPEN


# ==============================================================================
# 2. 重试机制测试
# ==============================================================================


class TestRetryMechanism:
    """_retry_with_backoff 指数退避重试测试。"""

    # --- 全部失败 ---

    async def test_all_failures_raises_after_max_attempts(self, mocker: Any) -> None:
        """全部失败时，func 被调用 (max_retries + 1) 次后抛出最后一个异常。"""
        mocker.patch(
            "trendpulse.collectors.base.asyncio.sleep", new=mocker.AsyncMock()
        )
        collector = _TestCollector(max_retries=3)
        func = AsyncMock(side_effect=RuntimeError("network error"))

        with pytest.raises(RuntimeError, match="network error"):
            await collector._retry_with_backoff(func)

        # max_retries=3 → 总尝试 4 次 (1 次初始 + 3 次重试)
        assert func.call_count == 4

    async def test_all_failures_with_custom_retries(self, mocker: Any) -> None:
        """max_retries=5 时总尝试 6 次 (1 次初始 + 5 次重试)。"""
        mocker.patch(
            "trendpulse.collectors.base.asyncio.sleep", new=mocker.AsyncMock()
        )
        collector = _TestCollector(max_retries=5)
        func = AsyncMock(side_effect=ValueError("fail"))

        with pytest.raises(ValueError):
            await collector._retry_with_backoff(func)

        assert func.call_count == 6

    # --- 中途成功 ---

    async def test_success_on_second_attempt(self, mocker: Any) -> None:
        """第 2 次尝试成功时返回数据，不再重试。"""
        mocker.patch(
            "trendpulse.collectors.base.asyncio.sleep", new=mocker.AsyncMock()
        )
        collector = _TestCollector(max_retries=3)
        func = AsyncMock(side_effect=[RuntimeError("fail"), [{"data": "ok"}]])

        result = await collector._retry_with_backoff(func)

        assert result == [{"data": "ok"}]
        assert func.call_count == 2

    async def test_success_on_first_attempt_no_sleep(self, mocker: Any) -> None:
        """第 1 次就成功时不触发任何 sleep。"""
        sleep_mock = mocker.patch(
            "trendpulse.collectors.base.asyncio.sleep", new=mocker.AsyncMock()
        )
        collector = _TestCollector(max_retries=3)
        func = AsyncMock(return_value=[{"data": "ok"}])

        result = await collector._retry_with_backoff(func)

        assert result == [{"data": "ok"}]
        assert func.call_count == 1
        sleep_mock.assert_not_called()

    async def test_success_on_third_attempt(self, mocker: Any) -> None:
        """第 3 次尝试成功时返回数据，不再继续重试。"""
        mocker.patch(
            "trendpulse.collectors.base.asyncio.sleep", new=mocker.AsyncMock()
        )
        collector = _TestCollector(max_retries=3)
        func = AsyncMock(
            side_effect=[
                RuntimeError("fail1"),
                RuntimeError("fail2"),
                [{"data": "ok"}],
            ]
        )

        result = await collector._retry_with_backoff(func)

        assert result == [{"data": "ok"}]
        assert func.call_count == 3

    # --- 指数退避延迟 ---

    async def test_backoff_delays_constant(self) -> None:
        """验证 BACKOFF_DELAYS 常量为 [0.5, 1.0, 2.0]。"""
        assert BACKOFF_DELAYS == [0.5, 1.0, 2.0]

    async def test_exponential_backoff_sleep_calls(self, mocker: Any) -> None:
        """max_retries=3 (4 次尝试) 时 sleep 被调用 3 次，延迟依次为 0.5/1.0/2.0s。"""
        sleep_mock = mocker.patch(
            "trendpulse.collectors.base.asyncio.sleep", new=mocker.AsyncMock()
        )
        collector = _TestCollector(max_retries=3)
        func = AsyncMock(side_effect=RuntimeError("fail"))

        with pytest.raises(RuntimeError):
            await collector._retry_with_backoff(func)

        # max_retries=3 → 4 次尝试 → 3 次 sleep (在第 1/2/3 次失败后)
        # 延迟序列完整覆盖 BACKOFF_DELAYS = [0.5, 1.0, 2.0]
        assert sleep_mock.await_count == 3
        actual_delays = [
            call.args[0] if call.args else call.kwargs.get("delay")
            for call in sleep_mock.call_args_list
        ]
        assert actual_delays == [0.5, 1.0, 2.0]

    async def test_exponential_backoff_all_three_delays(self, mocker: Any) -> None:
        """max_retries=4 (5 次尝试) 时 4 次 sleep 延迟为 0.5/1.0/2.0/2.0s (超出后取末值)。"""
        sleep_mock = mocker.patch(
            "trendpulse.collectors.base.asyncio.sleep", new=mocker.AsyncMock()
        )
        collector = _TestCollector(max_retries=4)
        func = AsyncMock(side_effect=RuntimeError("fail"))

        with pytest.raises(RuntimeError):
            await collector._retry_with_backoff(func)

        # max_retries=4 → 5 次尝试 → 4 次 sleep
        # 第 4 次退避超出 BACKOFF_DELAYS 长度, 取末值 2.0
        assert sleep_mock.await_count == 4
        actual_delays = [
            call.args[0] if call.args else call.kwargs.get("delay")
            for call in sleep_mock.call_args_list
        ]
        assert actual_delays == [0.5, 1.0, 2.0, 2.0]

    async def test_retry_passes_kwargs_to_func(self, mocker: Any) -> None:
        """_retry_with_backoff 应将 kwargs 透传给 func。"""
        mocker.patch(
            "trendpulse.collectors.base.asyncio.sleep", new=mocker.AsyncMock()
        )
        collector = _TestCollector(max_retries=3)
        func = AsyncMock(return_value=[{"data": "ok"}])

        await collector._retry_with_backoff(func, keyword="test", region="china")

        func.assert_called_once_with(keyword="test", region="china")


# ==============================================================================
# 3. BaseCollector 主流程测试
# ==============================================================================


class TestBaseCollector:
    """BaseCollector.collect() 主流程及缓存/限流/熔断联动测试。"""

    # --- 构造器 ---

    def test_default_construction(self) -> None:
        """默认构造应设置合理的默认值。"""
        collector = _TestCollector()
        assert collector.name == "test"
        assert collector.qps_limit == 1.0
        assert collector.cache_ttl == 3600
        assert collector.max_retries == 3
        assert isinstance(collector.circuit_breaker, CircuitBreaker)

    def test_custom_circuit_breaker(self) -> None:
        """传入自定义 CircuitBreaker 时应直接使用。"""
        custom_cb = CircuitBreaker(failure_threshold=5, recovery_timeout=120)
        collector = _TestCollector(circuit_breaker=custom_cb)
        assert collector.circuit_breaker is custom_cb

    def test_custom_parameters(self) -> None:
        """自定义 qps_limit / cache_ttl / max_retries 应正确设置。"""
        collector = _TestCollector(
            qps_limit=5.0, cache_ttl=1800, max_retries=5
        )
        assert collector.qps_limit == 5.0
        assert collector.cache_ttl == 1800
        assert collector.max_retries == 5

    def test_max_retries_validation_rejects_zero(self) -> None:
        """max_retries=0 时应抛出 ValueError (避免空循环导致 AssertionError)。"""
        with pytest.raises(ValueError, match="max_retries must be >= 1"):
            _TestCollector(max_retries=0)

    def test_max_retries_validation_rejects_negative(self) -> None:
        """max_retries<0 时应抛出 ValueError。"""
        with pytest.raises(ValueError, match="max_retries must be >= 1"):
            _TestCollector(max_retries=-1)

    # --- 成功采集 ---

    async def test_successful_collect_returns_data(self, mocker: Any) -> None:
        """成功采集应返回 _fetch 的数据。"""
        mocker.patch.object(_TestCollector, "_check_rate_limit", new=mocker.AsyncMock())
        mocker.patch.object(
            _TestCollector, "_get_cached", new=mocker.AsyncMock(return_value=None)
        )
        set_cached = mocker.patch.object(
            _TestCollector, "_set_cached", new=mocker.AsyncMock()
        )
        collector = _TestCollector()

        result = await collector.collect(keyword="侘寂风")

        assert result == [{"data": "test"}]
        set_cached.assert_awaited_once()

    async def test_successful_collect_caches_result(self, mocker: Any) -> None:
        """成功采集应将结果写入缓存。"""
        mocker.patch.object(_TestCollector, "_check_rate_limit", new=mocker.AsyncMock())
        mocker.patch.object(
            _TestCollector, "_get_cached", new=mocker.AsyncMock(return_value=None)
        )
        set_cached = mocker.patch.object(
            _TestCollector, "_set_cached", new=mocker.AsyncMock()
        )
        collector = _TestCollector(cache_ttl=7200)

        await collector.collect(keyword="侘寂风")

        set_cached.assert_awaited_once()
        # 验证缓存写入的参数
        call_args = set_cached.call_args
        cached_key = call_args.args[0] if call_args.args else call_args[0][0]
        cached_data = call_args.args[1] if len(call_args.args) > 1 else call_args[0][1]
        assert "侘寂风" in cached_key
        assert cached_data == [{"data": "test"}]

    async def test_successful_collect_records_success(self, mocker: Any) -> None:
        """成功采集应调用 circuit_breaker.record_success()。"""
        mocker.patch.object(_TestCollector, "_check_rate_limit", new=mocker.AsyncMock())
        mocker.patch.object(
            _TestCollector, "_get_cached", new=mocker.AsyncMock(return_value=None)
        )
        mocker.patch.object(_TestCollector, "_set_cached", new=mocker.AsyncMock())
        collector = _TestCollector()
        # 直接替换实例方法为 AsyncMock (record_success 的真实行为已在
        # TestCircuitBreaker 中测试，此处仅验证调用)
        record_success = mocker.AsyncMock()
        collector.circuit_breaker.record_success = record_success

        await collector.collect(keyword="test")

        record_success.assert_awaited_once()

    # --- 失败处理 ---

    async def test_failed_collect_raises_exception(self, mocker: Any) -> None:
        """采集失败 (重试耗尽) 应抛出异常。"""
        mocker.patch.object(_TestCollector, "_check_rate_limit", new=mocker.AsyncMock())
        mocker.patch.object(
            _TestCollector, "_get_cached", new=mocker.AsyncMock(return_value=None)
        )
        mocker.patch.object(_TestCollector, "_set_cached", new=mocker.AsyncMock())
        mocker.patch(
            "trendpulse.collectors.base.asyncio.sleep", new=mocker.AsyncMock()
        )
        collector = _TestCollector(max_retries=3)
        collector._fetch = AsyncMock(side_effect=RuntimeError("network error"))

        with pytest.raises(RuntimeError, match="network error"):
            await collector.collect(keyword="test")

    async def test_failed_collect_records_failure(self, mocker: Any) -> None:
        """采集失败应调用 circuit_breaker.record_failure()。"""
        mocker.patch.object(_TestCollector, "_check_rate_limit", new=mocker.AsyncMock())
        mocker.patch.object(
            _TestCollector, "_get_cached", new=mocker.AsyncMock(return_value=None)
        )
        mocker.patch.object(_TestCollector, "_set_cached", new=mocker.AsyncMock())
        mocker.patch(
            "trendpulse.collectors.base.asyncio.sleep", new=mocker.AsyncMock()
        )
        collector = _TestCollector(max_retries=3)
        collector._fetch = AsyncMock(side_effect=RuntimeError("fail"))
        # 直接替换实例方法为 AsyncMock (record_failure 的真实行为已在
        # TestCircuitBreaker 中测试，此处仅验证调用)
        record_failure = mocker.AsyncMock()
        collector.circuit_breaker.record_failure = record_failure

        with pytest.raises(RuntimeError):
            await collector.collect(keyword="test")

        record_failure.assert_awaited_once()

    async def test_failed_collect_returns_cached_fallback(self, mocker: Any) -> None:
        """采集失败且有缓存时，应返回缓存数据而非抛异常。"""
        mocker.patch.object(_TestCollector, "_check_rate_limit", new=mocker.AsyncMock())
        mocker.patch.object(_TestCollector, "_set_cached", new=mocker.AsyncMock())
        mocker.patch(
            "trendpulse.collectors.base.asyncio.sleep", new=mocker.AsyncMock()
        )

        cached_data = [{"cached": "fallback"}]
        # 第一次 _get_cached (缓存检查) 返回 None，第二次 (失败回退) 返回缓存
        get_cached = mocker.patch.object(
            _TestCollector,
            "_get_cached",
            new=mocker.AsyncMock(side_effect=[None, cached_data]),
        )
        collector = _TestCollector(max_retries=3)
        collector._fetch = AsyncMock(side_effect=RuntimeError("fail"))

        result = await collector.collect(keyword="test")

        assert result == cached_data
        assert get_cached.await_count == 2

    # --- 熔断器联动 ---

    async def test_circuit_breaker_open_fails_fast(self, mocker: Any) -> None:
        """熔断器 OPEN 时 collect() 快速失败，不调用 _fetch。"""
        collector = _TestCollector()
        # 触发熔断
        for _ in range(collector.circuit_breaker._failure_threshold):
            await collector.circuit_breaker.record_failure()
        assert collector.circuit_breaker.state == CircuitState.OPEN

        collector._fetch = AsyncMock(return_value=[{"data": "test"}])

        with pytest.raises(CircuitBreakerOpenError):
            await collector.collect(keyword="test")

        collector._fetch.assert_not_called()

    async def test_circuit_breaker_open_returns_cached(self, mocker: Any) -> None:
        """熔断器 OPEN 且有缓存时，应返回缓存数据而非抛异常。"""
        cached_data = [{"cached": "data"}]
        mocker.patch.object(
            _TestCollector,
            "_get_cached",
            new=mocker.AsyncMock(return_value=cached_data),
        )
        collector = _TestCollector()
        for _ in range(collector.circuit_breaker._failure_threshold):
            await collector.circuit_breaker.record_failure()

        collector._fetch = AsyncMock()
        result = await collector.collect(keyword="test")

        assert result == cached_data
        collector._fetch.assert_not_called()

    async def test_three_failed_collects_trip_circuit_breaker(self, mocker: Any) -> None:
        """3 次连续采集失败后，熔断器应转为 OPEN。"""
        mocker.patch.object(_TestCollector, "_check_rate_limit", new=mocker.AsyncMock())
        mocker.patch.object(
            _TestCollector, "_get_cached", new=mocker.AsyncMock(return_value=None)
        )
        mocker.patch.object(_TestCollector, "_set_cached", new=mocker.AsyncMock())
        mocker.patch(
            "trendpulse.collectors.base.asyncio.sleep", new=mocker.AsyncMock()
        )
        collector = _TestCollector(max_retries=3)
        collector._fetch = AsyncMock(side_effect=RuntimeError("fail"))

        # 前 3 次失败
        for i in range(3):
            with pytest.raises(RuntimeError):
                await collector.collect(keyword="test")

        # 熔断器应已 OPEN
        assert collector.circuit_breaker.state == CircuitState.OPEN

    # --- 缓存测试 ---

    async def test_cache_hit_returns_cached_without_fetch(self, mocker: Any) -> None:
        """缓存命中时直接返回缓存数据，不调用 _fetch。"""
        mocker.patch.object(_TestCollector, "_check_rate_limit", new=mocker.AsyncMock())
        cached_data = [{"cached": "data"}]
        mocker.patch.object(
            _TestCollector,
            "_get_cached",
            new=mocker.AsyncMock(return_value=cached_data),
        )
        set_cached = mocker.patch.object(
            _TestCollector, "_set_cached", new=mocker.AsyncMock()
        )
        collector = _TestCollector()
        collector._fetch = AsyncMock(return_value=[{"fresh": "data"}])

        result = await collector.collect(keyword="test")

        assert result == cached_data
        collector._fetch.assert_not_called()
        set_cached.assert_not_called()

    async def test_cache_key_generation(self) -> None:
        """_cache_key 应基于 name + kwargs 生成，且参数顺序无关。"""
        collector = _TestCollector()
        key1 = collector._cache_key(keyword="test", region="china")
        key2 = collector._cache_key(region="china", keyword="test")
        assert key1 == key2
        assert "test" in key1
        assert "china" in key1
        assert "test" in key1  # name="test"

    async def test_cache_key_different_kwargs(self) -> None:
        """不同 kwargs 应生成不同 cache key。"""
        collector = _TestCollector()
        key1 = collector._cache_key(keyword="A")
        key2 = collector._cache_key(keyword="B")
        assert key1 != key2

    async def test_get_cached_returns_none_on_miss(self, mocker: Any) -> None:
        """Redis 返回 None 时 _get_cached 应返回 None。"""
        mock_redis = mocker.AsyncMock()
        mock_redis.get.return_value = None
        mocker.patch(
            "shared.redis_client.get_redis_client", return_value=mock_redis
        )
        collector = _TestCollector()
        result = await collector._get_cached("test_key")
        assert result is None

    async def test_get_cached_returns_data_on_hit(self, mocker: Any) -> None:
        """Redis 返回 JSON 字符串时 _get_cached 应反序列化为 list。"""
        mock_redis = mocker.AsyncMock()
        mock_redis.get.return_value = json.dumps([{"data": "cached"}])
        mocker.patch(
            "shared.redis_client.get_redis_client", return_value=mock_redis
        )
        collector = _TestCollector()
        result = await collector._get_cached("test_key")
        assert result == [{"data": "cached"}]

    async def test_get_cached_handles_redis_error(self, mocker: Any) -> None:
        """Redis 异常时 _get_cached 应优雅降级返回 None。"""
        mocker.patch(
            "shared.redis_client.get_redis_client",
            side_effect=ConnectionError("redis down"),
        )
        collector = _TestCollector()
        result = await collector._get_cached("test_key")
        assert result is None

    async def test_set_cached_writes_to_redis(self, mocker: Any) -> None:
        """_set_cached 应调用 Redis SET 并设置 TTL。"""
        mock_redis = mocker.AsyncMock()
        mocker.patch(
            "shared.redis_client.get_redis_client", return_value=mock_redis
        )
        collector = _TestCollector(cache_ttl=3600)
        await collector._set_cached("key", [{"data": "test"}])
        mock_redis.set.assert_awaited_once()
        call = mock_redis.set.call_args
        # 验证参数: key, value, ex
        assert call.args[0] == "key"
        assert json.loads(call.args[1]) == [{"data": "test"}]
        assert call.kwargs.get("ex") == 3600

    async def test_set_cached_handles_redis_error(self, mocker: Any) -> None:
        """Redis 异常时 _set_cached 应静默失败 (不影响采集流程)。"""
        mocker.patch(
            "shared.redis_client.get_redis_client",
            side_effect=ConnectionError("redis down"),
        )
        collector = _TestCollector()
        # 不应抛出异常
        await collector._set_cached("key", [{"data": "test"}])

    # --- 限流测试 ---

    async def test_rate_limit_no_sleep_on_first_call(self, mocker: Any) -> None:
        """首次调用 _check_rate_limit 不应触发 sleep。"""
        sleep_mock = mocker.patch(
            "trendpulse.collectors.base.asyncio.sleep", new=mocker.AsyncMock()
        )
        mocker.patch(
            "trendpulse.collectors.base.time.monotonic", return_value=1000.0
        )
        collector = _TestCollector(qps_limit=1.0)

        await collector._check_rate_limit()

        sleep_mock.assert_not_called()

    async def test_rate_limit_sleeps_on_rapid_second_call(self, mocker: Any) -> None:
        """连续快速调用第二次应触发 sleep (QPS 限流)。"""
        sleep_mock = mocker.patch(
            "trendpulse.collectors.base.asyncio.sleep", new=mocker.AsyncMock()
        )
        mocker.patch(
            "trendpulse.collectors.base.time.monotonic", return_value=1000.0
        )
        collector = _TestCollector(qps_limit=1.0)  # 1 QPS → 间隔 1.0s

        await collector._check_rate_limit()  # 首次: 无 sleep
        sleep_mock.assert_not_called()

        await collector._check_rate_limit()  # 第二次: elapsed=0 < 1.0 → sleep
        sleep_mock.assert_awaited_once()
        sleep_duration = sleep_mock.call_args.args[0]
        assert sleep_duration == pytest.approx(1.0)

    async def test_rate_limit_no_sleep_after_interval(self, mocker: Any) -> None:
        """超过最小间隔后调用不应触发 sleep。"""
        sleep_mock = mocker.patch(
            "trendpulse.collectors.base.asyncio.sleep", new=mocker.AsyncMock()
        )
        # 固定时间 1000.0，通过手动设置 _last_call_time 模拟时间推进
        mocker.patch(
            "trendpulse.collectors.base.time.monotonic", return_value=1000.0
        )
        collector = _TestCollector(qps_limit=1.0)

        await collector._check_rate_limit()  # 首次: t=1000, _last_call_time 更新为 1000
        # 手动将 _last_call_time 设为 2 秒前，模拟 elapsed = 2.0 > 1.0
        collector._last_call_time = 998.0
        await collector._check_rate_limit()  # elapsed=2.0 > 1.0 → 不 sleep

        sleep_mock.assert_not_called()

    async def test_rate_limit_high_qps(self, mocker: Any) -> None:
        """高 QPS 限制下间隔很短 (qps=10 → 间隔 0.1s)。"""
        sleep_mock = mocker.patch(
            "trendpulse.collectors.base.asyncio.sleep", new=mocker.AsyncMock()
        )
        mocker.patch(
            "trendpulse.collectors.base.time.monotonic", return_value=1000.0
        )
        collector = _TestCollector(qps_limit=10.0)  # 10 QPS → 间隔 0.1s

        await collector._check_rate_limit()
        await collector._check_rate_limit()  # elapsed=0 < 0.1 → sleep(0.1)

        sleep_mock.assert_awaited_once()
        sleep_duration = sleep_mock.call_args.args[0]
        assert sleep_duration == pytest.approx(0.1)

    # --- _fetch 抽象方法 ---

    def test_base_collector_is_abstract(self) -> None:
        """BaseCollector 不能被直接实例化 (抽象类)。"""
        with pytest.raises(TypeError):
            BaseCollector(name="test")  # type: ignore[abstract]
