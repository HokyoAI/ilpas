from dataclasses import dataclass
from typing import Dict, Generic, Optional, TypeVar

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
    callback: Optional[Callback]
    health_check: Optional[Endpoint]
    endpoints: Dict[str, Endpoint]
    webhooks: Dict[str, Webhook]
