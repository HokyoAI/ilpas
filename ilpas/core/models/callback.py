from dataclasses import dataclass
from typing import Awaitable, Callable, Dict

from .types import JsonValue


@dataclass
class Callback:
    process: Callable[[Dict[str, str]], Awaitable[Dict[str, JsonValue]]]
    key: Callable[[Dict[str, str]], Awaitable[str]]
