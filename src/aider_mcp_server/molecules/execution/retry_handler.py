"""
Retry Handler module for robust retry logic with configurable backoff strategies.
Provides comprehensive retry functionality with async support, logging, and monitoring.
"""

import asyncio
import random
import time
from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Awaitable, Callable, Dict, List, Optional, TypeVar

from aider_mcp_server.atoms.logging.logger import get_logger
from aider_mcp_server.atoms.types.mcp_types import LoggerProtocol

T = TypeVar("T")


class BackoffStrategy(Enum):
    """Enumeration of available backoff strategies."""
    
    FIXED = "fixed"
    LINEAR = "linear"
    EXPONENTIAL = "exponential"


class RetryError(Exception):
    """Exception raised when all retry attempts are exhausted."""
    
    def __init__(self, message: str, attempts: int, last_exception: Exception) -> None:
        super().__init__(message)
        self.attempts = attempts
        self.last_exception = last_exception


class BackoffCalculator(ABC):
    """Abstract base class for backoff calculation strategies."""
    
    @abstractmethod
    def calculate_delay(self, attempt: int, base_delay: float) -> float:
        """Calculate the delay for the given attempt number."""
        pass


class FixedBackoffCalculator(BackoffCalculator):
    """Fixed delay backoff calculator."""
    
    def __init__(self, jitter: bool = True) -> None:
        self.jitter = jitter
    
    def calculate_delay(self, attempt: int, base_delay: float) -> float:
        """Calculate fixed delay with optional jitter."""
        delay = base_delay
        if self.jitter:
            # Add ±25% jitter
            jitter_factor = random.uniform(0.75, 1.25)
            delay *= jitter_factor
        return delay


class LinearBackoffCalculator(BackoffCalculator):
    """Linear backoff calculator."""
    
    def __init__(self, multiplier: float = 1.0, jitter: bool = True) -> None:
        self.multiplier = multiplier
        self.jitter = jitter
    
    def calculate_delay(self, attempt: int, base_delay: float) -> float:
        """Calculate linear backoff delay."""
        delay = base_delay * (1 + attempt * self.multiplier)
        if self.jitter:
            # Add ±25% jitter
            jitter_factor = random.uniform(0.75, 1.25)
            delay *= jitter_factor
        return delay


class ExponentialBackoffCalculator(BackoffCalculator):
    """Exponential backoff calculator."""
    
    def __init__(self, backoff_factor: float = 2.0, max_delay: float = 300.0, jitter: bool = True) -> None:
        self.backoff_factor = backoff_factor
        self.max_delay = max_delay
        self.jitter = jitter
    
    def calculate_delay(self, attempt: int, base_delay: float) -> float:
        """Calculate exponential backoff delay."""
        delay = base_delay * (self.backoff_factor ** attempt)
        delay = min(delay, self.max_delay)
        
        if self.jitter:
            # Add ±25% jitter
            jitter_factor = random.uniform(0.75, 1.25)
            delay *= jitter_factor
        
        return delay


class RetryMetrics:
    """Container for retry operation metrics."""
    
    def __init__(self) -> None:
        self.total_attempts = 0
        self.successful_operations = 0
        self.failed_operations = 0
        self.total_delay_time = 0.0
        self.exception_counts: Dict[str, int] = {}
    
    def record_attempt(self, delay: float = 0.0) -> None:
        """Record a retry attempt."""
        self.total_attempts += 1
        self.total_delay_time += delay
    
    def record_success(self) -> None:
        """Record a successful operation."""
        self.successful_operations += 1
    
    def record_failure(self, exception: Exception) -> None:
        """Record a failed operation."""
        self.failed_operations += 1
        exception_type = type(exception).__name__
        self.exception_counts[exception_type] = self.exception_counts.get(exception_type, 0) + 1
    
    def get_stats(self) -> Dict[str, Any]:
        """Get comprehensive retry statistics."""
        return {
            "total_attempts": self.total_attempts,
            "successful_operations": self.successful_operations,
            "failed_operations": self.failed_operations,
            "success_rate": (
                self.successful_operations / max(1, self.successful_operations + self.failed_operations)
            ),
            "average_attempts_per_operation": (
                self.total_attempts / max(1, self.successful_operations + self.failed_operations)
            ),
            "total_delay_time": self.total_delay_time,
            "exception_counts": self.exception_counts.copy(),
        }


class RetryHandler:
    """
    Handles retry logic with configurable backoff strategies and comprehensive monitoring.
    
    Supports both sync and async operations with detailed logging and metrics collection.
    """
    
    def __init__(
        self,
        max_retries: int = 3,
        base_delay: float = 1.0,
        strategy: BackoffStrategy = BackoffStrategy.EXPONENTIAL,
        retry_on_exceptions: Optional[List[type]] = None,
        stop_on_exceptions: Optional[List[type]] = None,
        timeout: Optional[float] = None,
        logger_name: Optional[str] = None,
        **strategy_kwargs: Any,
    ) -> None:
        """
        Initialize the RetryHandler.
        
        Args:
            max_retries: Maximum number of retry attempts
            base_delay: Base delay in seconds for backoff calculation
            strategy: Backoff strategy to use
            retry_on_exceptions: List of exceptions to retry on (None = all exceptions)
            stop_on_exceptions: List of exceptions to never retry on
            timeout: Overall timeout for the operation (including retries)
            logger_name: Custom logger name (uses module name if None)
            **strategy_kwargs: Additional arguments for backoff strategy
        """
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.retry_on_exceptions = retry_on_exceptions or [Exception]
        self.stop_on_exceptions = stop_on_exceptions or []
        self.timeout = timeout
        
        self._logger: LoggerProtocol = get_logger(logger_name or __name__)
        self._metrics = RetryMetrics()
        
        # Initialize backoff calculator based on strategy
        self._backoff_calculator = self._create_backoff_calculator(strategy, **strategy_kwargs)
        
        self._logger.info(
            f"RetryHandler initialized: max_retries={max_retries}, "
            f"strategy={strategy.value}, base_delay={base_delay}s"
        )
    
    def _create_backoff_calculator(self, strategy: BackoffStrategy, **kwargs: Any) -> BackoffCalculator:
        """Create the appropriate backoff calculator based on strategy."""
        if strategy == BackoffStrategy.FIXED:
            return FixedBackoffCalculator(**kwargs)
        elif strategy == BackoffStrategy.LINEAR:
            return LinearBackoffCalculator(**kwargs)
        elif strategy == BackoffStrategy.EXPONENTIAL:
            return ExponentialBackoffCalculator(**kwargs)
        else:
            raise ValueError(f"Unknown backoff strategy: {strategy}")
    
    def _should_retry(self, exception: Exception) -> bool:
        """Determine if the exception should trigger a retry."""
        # Check stop conditions first
        for stop_exception in self.stop_on_exceptions:
            if isinstance(exception, stop_exception):
                return False
        
        # Check retry conditions
        for retry_exception in self.retry_on_exceptions:
            if isinstance(exception, retry_exception):
                return True
        
        return False
    
    def execute(
        self,
        func: Callable[..., T],
        *args: Any,
        **kwargs: Any,
    ) -> T:
        """
        Execute a function with retry logic.
        
        Args:
            func: Function to execute
            *args: Arguments to pass to the function
            **kwargs: Keyword arguments to pass to the function
        
        Returns:
            The result of the successful function call
        
        Raises:
            RetryError: If all retry attempts are exhausted
        """
        operation_start_time = time.time()
        last_exception: Optional[Exception] = None
        
        for attempt in range(self.max_retries + 1):
            try:
                self._logger.debug(f"Executing function attempt {attempt + 1}/{self.max_retries + 1}")
                
                # Check timeout
                if self.timeout and (time.time() - operation_start_time) > self.timeout:
                    raise TimeoutError(f"Operation timeout after {self.timeout}s")
                
                result = func(*args, **kwargs)
                
                if attempt > 0:
                    self._logger.info(f"Function succeeded on attempt {attempt + 1}")
                
                # Record the successful attempt
                self._metrics.record_attempt()
                self._metrics.record_success()
                return result
                
            except Exception as e:
                last_exception = e
                
                # Record the failed attempt
                self._metrics.record_attempt()
                
                self._logger.warning(
                    f"Function failed on attempt {attempt + 1}: {type(e).__name__}: {e}"
                )
                
                if not self._should_retry(e):
                    self._logger.error(f"Non-retryable exception: {type(e).__name__}")
                    self._metrics.record_failure(e)
                    raise e
                
                if attempt < self.max_retries:
                    delay = self._backoff_calculator.calculate_delay(attempt, self.base_delay)
                    
                    # Check if delay would exceed timeout
                    if self.timeout and (time.time() - operation_start_time + delay) > self.timeout:
                        self._logger.warning("Delay would exceed timeout, skipping retry")
                        break
                    
                    self._logger.info(f"Retrying in {delay:.2f}s...")
                    time.sleep(delay)
                else:
                    self._logger.error(f"All {self.max_retries + 1} attempts exhausted")
        
        # All retries exhausted
        self._metrics.record_failure(last_exception or Exception("Unknown error"))
        raise RetryError(
            f"All {self.max_retries + 1} attempts failed",
            self.max_retries + 1,
            last_exception or Exception("Unknown error"),
        )
    
    async def execute_async(
        self,
        func: Callable[..., Awaitable[T]],
        *args: Any,
        **kwargs: Any,
    ) -> T:
        """
        Execute an async function with retry logic.
        
        Args:
            func: Async function to execute
            *args: Arguments to pass to the function
            **kwargs: Keyword arguments to pass to the function
        
        Returns:
            The result of the successful function call
        
        Raises:
            RetryError: If all retry attempts are exhausted
        """
        operation_start_time = time.time()
        last_exception: Optional[Exception] = None
        
        for attempt in range(self.max_retries + 1):
            try:
                self._logger.debug(f"Executing async function attempt {attempt + 1}/{self.max_retries + 1}")
                
                # Check timeout
                if self.timeout and (time.time() - operation_start_time) > self.timeout:
                    raise TimeoutError(f"Operation timeout after {self.timeout}s")
                
                if self.timeout:
                    remaining_timeout = self.timeout - (time.time() - operation_start_time)
                    result = await asyncio.wait_for(func(*args, **kwargs), timeout=remaining_timeout)
                else:
                    result = await func(*args, **kwargs)
                
                if attempt > 0:
                    self._logger.info(f"Async function succeeded on attempt {attempt + 1}")
                
                # Record the successful attempt
                self._metrics.record_attempt()
                self._metrics.record_success()
                return result
                
            except Exception as e:
                last_exception = e
                
                # Record the failed attempt
                self._metrics.record_attempt()
                
                self._logger.warning(
                    f"Async function failed on attempt {attempt + 1}: {type(e).__name__}: {e}"
                )
                
                if not self._should_retry(e):
                    self._logger.error(f"Non-retryable exception: {type(e).__name__}")
                    self._metrics.record_failure(e)
                    raise e
                
                if attempt < self.max_retries:
                    delay = self._backoff_calculator.calculate_delay(attempt, self.base_delay)
                    
                    # Check if delay would exceed timeout
                    if self.timeout and (time.time() - operation_start_time + delay) > self.timeout:
                        self._logger.warning("Delay would exceed timeout, skipping retry")
                        break
                    
                    self._logger.info(f"Retrying in {delay:.2f}s...")
                    await asyncio.sleep(delay)
                else:
                    self._logger.error(f"All {self.max_retries + 1} attempts exhausted")
        
        # All retries exhausted
        self._metrics.record_failure(last_exception or Exception("Unknown error"))
        raise RetryError(
            f"All {self.max_retries + 1} attempts failed",
            self.max_retries + 1,
            last_exception or Exception("Unknown error"),
        )
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get retry operation metrics."""
        return self._metrics.get_stats()
    
    def reset_metrics(self) -> None:
        """Reset retry operation metrics."""
        self._metrics = RetryMetrics()
        self._logger.debug("Retry metrics reset")
    
    def __enter__(self) -> "RetryHandler":
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Context manager exit."""
        if exc_type is not None:
            self._logger.error(f"RetryHandler context exited with exception: {exc_type.__name__}")


# Convenience functions for common retry patterns
def retry_with_exponential_backoff(
    max_retries: int = 3,
    base_delay: float = 1.0,
    backoff_factor: float = 2.0,
    max_delay: float = 300.0,
    jitter: bool = True,
    **kwargs: Any,
) -> RetryHandler:
    """Create a RetryHandler with exponential backoff strategy."""
    return RetryHandler(
        max_retries=max_retries,
        base_delay=base_delay,
        strategy=BackoffStrategy.EXPONENTIAL,
        backoff_factor=backoff_factor,
        max_delay=max_delay,
        jitter=jitter,
        **kwargs,
    )


def retry_with_fixed_delay(
    max_retries: int = 3,
    delay: float = 1.0,
    jitter: bool = True,
    **kwargs: Any,
) -> RetryHandler:
    """Create a RetryHandler with fixed delay strategy."""
    return RetryHandler(
        max_retries=max_retries,
        base_delay=delay,
        strategy=BackoffStrategy.FIXED,
        jitter=jitter,
        **kwargs,
    )


def retry_with_linear_backoff(
    max_retries: int = 3,
    base_delay: float = 1.0,
    multiplier: float = 1.0,
    jitter: bool = True,
    **kwargs: Any,
) -> RetryHandler:
    """Create a RetryHandler with linear backoff strategy."""
    return RetryHandler(
        max_retries=max_retries,
        base_delay=base_delay,
        strategy=BackoffStrategy.LINEAR,
        multiplier=multiplier,
        jitter=jitter,
        **kwargs,
    )