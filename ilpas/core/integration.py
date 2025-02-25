from dataclasses import dataclass
from typing import Dict, Generic, TypeVar

from pydantic import BaseModel
from pydantic.types import JsonValue

from .models.display import Display
from .models.endpoint import Endpoint
from .models.webhook import Webhook

_AC = TypeVar("_AC", bound=BaseModel)


@dataclass
class Specification(Generic[_AC]):
    guid: str
    display: Display
    endpoints: Dict[str, Endpoint]
    webhooks: Dict[str, Webhook]
    config_model: type[_AC]


@dataclass
class Integration(Generic[_AC]):
    spec: Specification[_AC]
    final_config_model: type[_AC]
    supplied_config: Dict[str, JsonValue]
