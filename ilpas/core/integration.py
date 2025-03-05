from dataclasses import dataclass
from typing import Awaitable, Callable

from .models.types import AM
from .specification import Specification


@dataclass
class Integration[_I: AM, _U: AM, _A: AM, _C: AM, _S: AM]:
    spec: Specification[_I, _U, _A, _C, _S]
    supplied_admin_config: Callable[[_U], _A]
    supplied_integration_config: _I
