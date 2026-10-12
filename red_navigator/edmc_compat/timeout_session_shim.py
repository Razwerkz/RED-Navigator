"""
Shim module for EDMC's timeout_session module.
Provides HTTP session with timeout.
"""
from __future__ import annotations
import requests
from typing import Any, Optional

# Default timeout in seconds
DEFAULT_TIMEOUT = 30.0

class TimeoutSession(requests.Session):
    """Session with default timeout on all requests."""
    
    def __init__(self, timeout: float = DEFAULT_TIMEOUT, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self.default_timeout = timeout
    
    def request(self, method: str, url: str, *args: Any, **kwargs: Any) -> Any:
        if 'timeout' not in kwargs:
            kwargs['timeout'] = self.default_timeout
        return super().request(method, url, *args, **kwargs)

def new_session(timeout: float = DEFAULT_TIMEOUT) -> TimeoutSession:
    """Create a new TimeoutSession."""
    return TimeoutSession(timeout=timeout)

__all__ = ['TimeoutSession', 'new_session']