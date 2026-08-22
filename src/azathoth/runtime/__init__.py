"""Process-local Azathoth runtime composition."""

from azathoth.runtime.protocols import RuntimeEnvironment
from azathoth.runtime.runtime import AzathothRuntime

__all__ = [
    "AzathothRuntime",
    "RuntimeEnvironment",
]
