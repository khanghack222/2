"""
AI Router - Multi-provider routing with circuit breaker
Pattern: Smart routing with fallback and health tracking
"""
import asyncio
import time
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from enum import Enum


class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class ProviderHealth:
    """Health metrics for a provider"""
    success_count: int = 0
    failure_count: int = 0
    total_latency_ms: float = 0
    last_success: float = 0
    last_failure: float = 0
    circuit_state: CircuitState = CircuitState.CLOSED
    circuit_opened_at: float = 0


class BaseProvider:
    """Base class for AI providers"""

    def __init__(self, name: str, api_key: str, base_url: str, model: str):
        self.name = name
        self.api_key = api_key
        self.base_url = base_url
        self.model = model
        self.health = ProviderHealth()

    async def chat(
        self,
        messages: List[Dict[str, str]],
        **kwargs
    ) -> str:
        """
        Send chat request to provider.

        Args:
            messages: List of message dicts with 'role' and 'content'
            **kwargs: Additional parameters

        Returns:
            Response text
        """
        raise NotImplementedError

    def is_healthy(self) -> bool:
        """Check if provider is healthy"""
        if self.health.circuit_state == CircuitState.OPEN:
            # Check if we should try half-open
            if time.time() - self.health.circuit_opened_at > 60:
                self.health.circuit_state = CircuitState.HALF_OPEN
                return True
            return False
        return True

    def record_success(self, latency_ms: float) -> None:
        """Record a successful request"""
        self.health.success_count += 1
        self.health.total_latency_ms += latency_ms
        self.health.last_success = time.time()

        if self.health.circuit_state == CircuitState.HALF_OPEN:
            self.health.circuit_state = CircuitState.CLOSED

    def record_failure(self) -> None:
        """Record a failed request"""
        self.health.failure_count += 1
        self.health.last_failure = time.time()

        # Open circuit after 3 consecutive failures
        if self.health.failure_count >= 3:
            self.health.circuit_state = CircuitState.OPEN
            self.health.circuit_opened_at = time.time()


class AIRouter:
    """
    Routes requests to multiple AI providers with fallback.
    Implements circuit breaker pattern for reliability.
    """

    def __init__(self, providers: List[BaseProvider]):
        """
        Initialize router with providers.

        Args:
            providers: List of AI providers (ordered by priority)
        """
        self.providers = providers
        self._lock = asyncio.Lock()

    async def chat(
        self,
        messages: List[Dict[str, str]],
        timeout: float = 30.0,
        **kwargs
    ) -> str:
        """
        Route chat request to best available provider.

        Args:
            messages: Chat messages
            timeout: Request timeout in seconds
            **kwargs: Additional parameters

        Returns:
            Response text

        Raises:
            Exception: If all providers fail
        """
        errors = []

        for provider in self.providers:
            if not provider.is_healthy():
                continue

            try:
                start_time = time.time()

                # Execute with timeout
                response = await asyncio.wait_for(
                    provider.chat(messages, **kwargs),
                    timeout=timeout
                )

                latency_ms = (time.time() - start_time) * 1000
                provider.record_success(latency_ms)

                return response

            except asyncio.TimeoutError:
                error = f"{provider.name}: Timeout"
                provider.record_failure()
                errors.append(error)

            except Exception as e:
                error = f"{provider.name}: {str(e)}"
                provider.record_failure()
                errors.append(error)

        raise Exception(f"All providers failed: {'; '.join(errors)}")

    def get_provider_health(self) -> List[Dict[str, Any]]:
        """
        Get health status of all providers.

        Returns:
            List of provider health dicts
        """
        health_data = []

        for provider in self.providers:
            total_requests = (
                provider.health.success_count +
                provider.health.failure_count
            )

            avg_latency = (
                provider.health.total_latency_ms / provider.health.success_count
                if provider.health.success_count > 0 else 0
            )

            success_rate = (
                provider.health.success_count / total_requests * 100
                if total_requests > 0 else 100
            )

            health_data.append({
                "name": provider.name,
                "model": provider.model,
                "circuit_state": provider.health.circuit_state.value,
                "success_count": provider.health.success_count,
                "failure_count": provider.health.failure_count,
                "success_rate": round(success_rate, 2),
                "avg_latency_ms": round(avg_latency, 2),
            })

        return health_data

    def reset_circuits(self) -> None:
        """Reset all circuit breakers"""
        for provider in self.providers:
            provider.health.circuit_state = CircuitState.CLOSED
            provider.health.failure_count = 0
