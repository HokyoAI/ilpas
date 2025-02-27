from dataclasses import dataclass
from typing import Awaitable, Callable, Dict, Generic, Optional, TypeVar

from fastapi import Request
from pydantic import BaseModel

from .models.callback import Callback
from .models.display import Display
from .models.endpoint import Endpoint
from .models.webhook import Webhook

_T = TypeVar("_T", bound=BaseModel)


@dataclass
class Specification(Generic[_T]):
    guid: str
    display: Display
    config_model: type[_T]
    endpoints: Dict[str, Endpoint]
    health_check: Optional[Endpoint]
    callback: Optional[Callback]
    webhook: Optional[Webhook]
