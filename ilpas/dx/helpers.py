from typing import Dict

from pydantic import BaseModel

from ..core.models.base_model_extras import (
    DEFAULT_SENSITIVE,
    DEFAULT_SUPPLIER,
    DEFAULT_TRIGGER_CALLBACK,
)
from ..core.models.types import ConfigurationSupplier, JsonValue


class NoConfig(BaseModel):
    model_config = {"extra": "forbid"}


def extras(
    supplier: ConfigurationSupplier = DEFAULT_SUPPLIER,
    sensitive: bool = DEFAULT_SENSITIVE,
    triggers_callback: bool = DEFAULT_TRIGGER_CALLBACK,
) -> Dict[str, JsonValue]:
    if triggers_callback:
        if supplier != "user":
            raise ValueError(
                "triggers_callback must be True only for user supplied fields"
            )
    return {
        "supplier": supplier,
        "sensitive": sensitive,
        "triggers_callback": triggers_callback,
    }
