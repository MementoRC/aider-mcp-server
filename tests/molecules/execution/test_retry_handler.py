"""Tests for the retry handler module."""

import asyncio
import time

import pytest

from aider_mcp_server.molecules.execution.retry_handler import (
    BackoffStrategy,
    ExponentialBackoffCalculator,
    FixedBackoffCalculator,
    LinearBackoffCalculator,
    RetryError,
    RetryHandler,
    retry_with_exponential_backoff,
    retry_with_fixed_delay,
    retry_with_linear_backoff,
)


class TestFixedBackoffCalculator:
    """Test cases for FixedBackoffCalculator."""

    def test_calculate_delay_without_jitter(self):
        """Test fixed delay calculation without jitter."""
        calculator = FixedBackoffCalculator(jitter=False)
        base_delay = 2.0

        # All attempts should return the same delay
        assert calculator.calculate_delay(0, base_delay) == 2.0
        assert calculator.calculate_delay(1, base_delay) == 2.0
        assert calculator.calculate_delay(5, base_delay) == 2.0

    def test_calculate_delay_with_jitter(self):
        """Test fixed delay calculation with jitter."""
        calculator = FixedBackoffCalculator(jitter=True)
        base_delay = 2.0

        # With jitter, delays should vary but be within expected range
        delays = [calculator.calculate_delay(0, base_delay) for _ in range(10)]

        # All delays should be within 75%-125% of base delay
        for delay in delays:
            assert 1.5 <= delay <= 2.5

        # Delays should not all be identical (with high probability)
        assert len(set(delays)) > 1


class TestLinearBackoffCalculator:
    """Test cases for LinearBackoffCalculator."""

    def test_calculate_delay_without_jitter(self):
        """Test linear delay calculation without jitter."""
        calculator = LinearBackoffCalculator(multiplier=1.0, jitter=False)
        base_delay = 1.0

        assert calculator.calculate_delay(0, base_delay) == 1.0  # 1.0 * (1 + 0 * 1.0)
        assert calculator.calculate_delay(1, base_delay) == 2.0  # 1.0 * (1 + 1 * 1.0)
        assert calculator.calculate_delay(2, base_delay) == 3.0  # 1.0 * (1 + 2 * 1.0)

    def test_calculate_delay_with_custom_multiplier(self):
        """Test linear delay calculation with custom multiplier."""
        calculator = LinearBackoffCalculator(multiplier=0.5, jitter=False)
        base_delay = 2.0

        assert calculator.calculate_delay(0, base_delay) == 2.0  # 2.0 * (1 + 0 * 0.5)
        assert calculator.calculate_delay(1, base_delay) == 3.0  # 2.0 * (1 + 1 * 0.5)
        assert calculator.calculate_delay(2, base_delay) == 4.0  # 2.0 * (1 + 2 * 0.5)


class TestExponentialBackoffCalculator:
    """Test cases for ExponentialBackoffCalculator."""

    def test_calculate_delay_without_jitter(self):
        """Test exponential delay calculation without jitter."""
        calculator = ExponentialBackoffCalculator(backoff_factor=2.0, jitter=False)
        base_delay = 1.0

        assert calculator.calculate_delay(0, base_delay) == 1.0  # 1.0 * (2.0 ^ 0)
        assert calculator.calculate_delay(1, base_delay) == 2.0  # 1.0 * (2.0 ^ 1)
        assert calculator.calculate_delay(2, base_delay) == 4.0  # 1.0 * (2.0 ^ 2)
        assert calculator.calculate_delay(3, base_delay) == 8.0  # 1.0 * (2.0 ^ 3)

    def test_calculate_delay_with_max_delay(self):
        """Test exponential delay calculation with maximum delay."""
        calculator = ExponentialBackoffCalculator(backoff_factor=2.0, max_delay=5.0, jitter=False)
        base_delay = 1.0

        assert calculator.calculate_delay(0, base_delay) == 1.0
        assert calculator.calculate_delay(1, base_delay) == 2.0
        assert calculator.calculate_delay(2, base_delay) == 4.0
        assert calculator.calculate_delay(3, base_delay) == 5.0  # Capped at max_delay
        assert calculator.calculate_delay(4, base_delay) == 5.0  # Capped at max_delay


class TestRetryHandler:
    """Test cases for RetryHandler."""

    def test_successful_execution_no_retry(self):
        """Test successful execution without retries."""
        handler = RetryHandler(max_retries=3)

        def successful_func():
            return "success"

        result = handler.execute(successful_func)
        assert result == "success"

        metrics = handler.get_metrics()
        assert metrics["successful_operations"] == 1
        assert metrics["failed_operations"] == 0
        assert metrics["total_attempts"] == 1

    def test_retry_with_eventual_success(self):
        """Test retry mechanism with eventual success."""
        handler = RetryHandler(max_retries=3, base_delay=0.01)  # Fast retry for testing

        attempt_count = 0

        def flaky_func():
            nonlocal attempt_count
            attempt_count += 1
            if attempt_count < 3:
                raise ValueError("Temporary failure")
            return "success"

        result = handler.execute(flaky_func)
        assert result == "success"
        assert attempt_count == 3

        metrics = handler.get_metrics()
        assert metrics["successful_operations"] == 1
        assert metrics["failed_operations"] == 0
        assert metrics["total_attempts"] == 3

    def test_retry_exhaustion(self):
        """Test behavior when all retries are exhausted."""
        handler = RetryHandler(max_retries=2, base_delay=0.01)

        def always_fails():
            raise ValueError("Always fails")

        with pytest.raises(RetryError) as exc_info:
            handler.execute(always_fails)

        assert exc_info.value.attempts == 3  # max_retries + 1
        assert isinstance(exc_info.value.last_exception, ValueError)

        metrics = handler.get_metrics()
        assert metrics["successful_operations"] == 0
        assert metrics["failed_operations"] == 1
        assert metrics["total_attempts"] == 3

    def test_non_retryable_exception(self):
        """Test handling of non-retryable exceptions."""
        handler = RetryHandler(max_retries=3, retry_on_exceptions=[ValueError], stop_on_exceptions=[TypeError])

        def raises_type_error():
            raise TypeError("Non-retryable")

        with pytest.raises(TypeError):
            handler.execute(raises_type_error)

        metrics = handler.get_metrics()
        assert metrics["total_attempts"] == 1  # Should not retry

    def test_timeout_behavior(self):
        """Test timeout functionality."""
        handler = RetryHandler(max_retries=5, base_delay=0.1, timeout=0.2)

        def slow_func():
            time.sleep(0.15)
            raise ValueError("Takes too long")

        with pytest.raises((TimeoutError, RetryError)):
            handler.execute(slow_func)

    @pytest.mark.asyncio
    async def test_async_execution_success(self):
        """Test successful async execution."""
        handler = RetryHandler(max_retries=3)

        async def async_success():
            return "async_success"

        result = await handler.execute_async(async_success)
        assert result == "async_success"

        metrics = handler.get_metrics()
        assert metrics["successful_operations"] == 1

    @pytest.mark.asyncio
    async def test_async_retry_with_success(self):
        """Test async retry mechanism with eventual success."""
        handler = RetryHandler(max_retries=3, base_delay=0.01)

        attempt_count = 0

        async def async_flaky():
            nonlocal attempt_count
            attempt_count += 1
            if attempt_count < 3:
                raise ValueError("Async temporary failure")
            return "async_success"

        result = await handler.execute_async(async_flaky)
        assert result == "async_success"
        assert attempt_count == 3

    @pytest.mark.asyncio
    async def test_async_timeout(self):
        """Test async timeout functionality."""
        handler = RetryHandler(max_retries=3, base_delay=0.01, timeout=0.1)

        async def slow_async_func():
            await asyncio.sleep(0.2)
            return "too_slow"

        with pytest.raises((TimeoutError, RetryError, asyncio.TimeoutError)):
            await handler.execute_async(slow_async_func)

    def test_context_manager(self):
        """Test RetryHandler as context manager."""
        with RetryHandler(max_retries=2) as handler:
            result = handler.execute(lambda: "context_success")
            assert result == "context_success"

    def test_metrics_tracking(self):
        """Test comprehensive metrics tracking."""
        handler = RetryHandler(max_retries=2, base_delay=0.01)

        # Successful operation
        handler.execute(lambda: "success")

        # Failed operation
        try:

            def failing_operation():
                raise ValueError("test")

            handler.execute(failing_operation)
        except RetryError:
            pass

        metrics = handler.get_metrics()
        assert metrics["successful_operations"] == 1
        assert metrics["failed_operations"] == 1
        assert metrics["total_attempts"] == 4  # 1 + 3 (with retries)
        assert "ValueError" in metrics["exception_counts"]
        assert metrics["exception_counts"]["ValueError"] == 1

    def test_reset_metrics(self):
        """Test metrics reset functionality."""
        handler = RetryHandler(max_retries=1)

        # Perform some operations
        handler.execute(lambda: "test")
        assert handler.get_metrics()["successful_operations"] == 1

        # Reset metrics
        handler.reset_metrics()
        metrics = handler.get_metrics()
        assert metrics["successful_operations"] == 0
        assert metrics["failed_operations"] == 0
        assert metrics["total_attempts"] == 0


class TestConvenienceFunctions:
    """Test cases for convenience functions."""

    def test_retry_with_exponential_backoff(self):
        """Test exponential backoff convenience function."""
        handler = retry_with_exponential_backoff(max_retries=2, base_delay=0.01)

        result = handler.execute(lambda: "exponential_success")
        assert result == "exponential_success"

    def test_retry_with_fixed_delay(self):
        """Test fixed delay convenience function."""
        handler = retry_with_fixed_delay(max_retries=2, delay=0.01)

        result = handler.execute(lambda: "fixed_success")
        assert result == "fixed_success"

    def test_retry_with_linear_backoff(self):
        """Test linear backoff convenience function."""
        handler = retry_with_linear_backoff(max_retries=2, base_delay=0.01)

        result = handler.execute(lambda: "linear_success")
        assert result == "linear_success"


class TestRetryHandlerIntegration:
    """Integration tests for RetryHandler."""

    def test_real_world_network_retry_simulation(self):
        """Simulate network retry scenario."""
        handler = RetryHandler(
            max_retries=3,
            base_delay=0.01,
            strategy=BackoffStrategy.EXPONENTIAL,
            retry_on_exceptions=[ConnectionError, TimeoutError],
            stop_on_exceptions=[PermissionError],
        )

        attempt_count = 0

        def simulated_network_call():
            nonlocal attempt_count
            attempt_count += 1

            if attempt_count == 1:
                raise ConnectionError("Network unreachable")
            elif attempt_count == 2:
                raise TimeoutError("Request timeout")
            else:
                return {"status": "success", "data": "network_data"}

        result = handler.execute(simulated_network_call)
        assert result["status"] == "success"
        assert attempt_count == 3

    def test_resource_cleanup_with_retry(self):
        """Test retry behavior with resource cleanup tracking."""
        cleanup_calls = []

        def cleanup_resource(resource_id):
            cleanup_calls.append(resource_id)

        handler = RetryHandler(max_retries=2, base_delay=0.01)

        attempt_count = 0

        def resource_operation():
            nonlocal attempt_count
            attempt_count += 1
            resource_id = f"resource_{attempt_count}"

            try:
                if attempt_count < 3:
                    raise RuntimeError("Resource busy")
                return f"processed_{resource_id}"
            finally:
                cleanup_resource(resource_id)

        result = handler.execute(resource_operation)
        assert result == "processed_resource_3"
        assert len(cleanup_calls) == 3
        assert cleanup_calls == ["resource_1", "resource_2", "resource_3"]
