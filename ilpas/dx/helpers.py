from typing import Dict

from pydantic import BaseModel

from ..core.models.base_model_extras import DEFAULT_SENSITIVE, DEFAULT_TRIGGER_CALLBACK
from ..core.models.types import ConfigurationSupplier, JsonValue, Sensitivity

# def extras(
#     sensitivity: Sensitivity = DEFAULT_SENSITIVE,
#     triggers_callback: bool = DEFAULT_TRIGGER_CALLBACK,
# ) -> Dict[str, JsonValue]:
#     if triggers_callback:
#         if supplier != "user":
#             raise ValueError(
#                 "triggers_callback must be True only for user supplied fields"
#             )
#     return {
#         "supplier": supplier,
#         "sensitive": sensitivity,
#         "triggers_callback": triggers_callback,
#     }
