"""No-op metrics shim.

The Prometheus-scale monitoring subsystem was removed in Phase 0 (unused
weight for a self-hosted tool). The job processor still calls into this
module's API for metrics — kept as a no-op so that code needs no changes.
"""

from contextlib import contextmanager
from functools import wraps


class _NullMetrics:
    """Swallows any metrics call (record_rate, increment_error_count, ...)."""

    def __getattr__(self, _name):
        def _noop(*args, **kwargs):
            return None
        return _noop


def get_job_metrics():
    return _NullMetrics()


def get_stage_metrics(_stage_name):
    return _NullMetrics()


def get_pipeline_metrics():
    return _NullMetrics()


def timed(*_args, **_kwargs):
    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            return await func(*args, **kwargs)

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            return func(*args, **kwargs)

        import asyncio
        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper
    return decorator


@contextmanager
def timer(*_args, **_kwargs):
    yield
