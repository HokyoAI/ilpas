from dataclasses import dataclass
from typing import Dict, Generic, TypeVar

from .models.types import AM, JsonValue
from .specification import Specification

_A = TypeVar("_A", bound=AM)


@dataclass
class Integration(Generic[_A]):
    spec: type[Specification[_A, AM, AM, AM, AM]]
    supplied_config: _A
