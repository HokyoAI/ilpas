from typing import Dict, Generic, List, Literal, Optional, TypeVar, cast

from pydantic import BaseModel, create_model
from pydantic.fields import FieldInfo
from pydantic.types import JsonValue

from .models.types import ConfigurationState, ConfigurationSupplier
from .store import Store

DEFAULT_SUPPLIER: ConfigurationSupplier = "user"
DEFAULT_SENSITIVE: bool = False


class Nothing(BaseModel):
    model_config = {"extra": "forbid"}


class ConfigurationRequirement(BaseModel):
    name: str
    required: bool
    supplier: ConfigurationSupplier
    sensitive: bool = False


def extras(
    supplier: ConfigurationSupplier = DEFAULT_SUPPLIER,
    sensitive: bool = DEFAULT_SENSITIVE,
) -> Dict[str, JsonValue]:
    return {"supplier": supplier, "sensitive": sensitive}


_T = TypeVar("_T", bound=BaseModel)


class ConfigurationManager(Generic[_T]):

    def _is_field_required(self, field_info: FieldInfo) -> bool:
        """Check if a field is required based on its FieldInfo"""
        return field_info.is_required()

    def _is_field_sensitive(self, field_info: FieldInfo) -> bool:
        """Check if a field is sensitive based on its FieldInfo"""

        if not field_info.json_schema_extra:
            return DEFAULT_SENSITIVE
        if isinstance(field_info.json_schema_extra, dict):
            sensitive_value = field_info.json_schema_extra.get("sensitive", None)
            if sensitive_value is None:
                return DEFAULT_SENSITIVE
            elif isinstance(sensitive_value, bool):
                return sensitive_value
            else:
                raise ValueError(
                    f"field {field_info.title} json_schema_extra.sensitive must be a bool"
                )
        else:
            raise ValueError(
                f"field {field_info.title} json_schema_extra must be a dict, callable is not supported"
            )

    def _get_field_supplier(self, field_info: FieldInfo) -> ConfigurationSupplier:
        """Get the supplier for a field based on its FieldInfo"""

        if not field_info.json_schema_extra:
            return DEFAULT_SUPPLIER
        if isinstance(field_info.json_schema_extra, dict):
            supplier_value = field_info.json_schema_extra.get("supplier", None)
            if supplier_value is None:
                return DEFAULT_SUPPLIER
            elif isinstance(supplier_value, str) and supplier_value in [
                "admin",
                "user",
                "callback",
            ]:
                return cast(ConfigurationSupplier, supplier_value)
            else:
                raise ValueError(
                    f"field {field_info.title} json_schema_extra.supplier must be a str and one of 'admin', 'user', 'callback'"
                )
        else:
            raise ValueError(
                f"field {field_info.title} json_schema_extra must be a dict, callable is not supported"
            )

    def _build_requirements(self) -> None:
        """Build the requirements for the configuration based on the model"""
        self._requirements: Dict[str, ConfigurationRequirement] = {}
        fields = self.config_class.__pydantic_fields__
        for field_name, field_info in fields.items():
            required = self._is_field_required(field_info)
            sensitive = self._is_field_sensitive(field_info)
            supplier = self._get_field_supplier(field_info)
            self._requirements[field_name] = ConfigurationRequirement(
                name=field_name,
                required=required,
                supplier=supplier,
                sensitive=sensitive,
            )

    def __init__(self, config_class: type[_T]):
        self.config_class = config_class
        self._config_data: Dict[str, JsonValue] = {}
        self._state: ConfigurationState = "pending"
        self._build_requirements()

    @classmethod
    async def restore(
        cls,
        config_class: type[_T],
        store: Store,
        primary_key: str,
        namespace: Optional[str],
    ) -> "ConfigurationManager":
        """Restore the configuration from the store"""
        result = cls(config_class)
        data = (await store.get_by_primary_key(primary_key, namespace))["value"]
        for supplier, config in data.items():
            result.add_configuration(supplier, config)
        return result

    def _update_state(self) -> None:
        """Update the configuration state based on requirements and provided data"""
        required_fields = [
            req.name for req in self._requirements.values() if req.required
        ]

        if all(field in self._config_data for field in required_fields):
            self._state = "complete"
        elif len(self._config_data) > 0:
            self._state = "partial"
        else:
            self._state = "pending"

    def get_model(self, supplier: ConfigurationSupplier) -> type[BaseModel]:
        """Generate a Pydantic model for fields from a specific source"""
        # Create a dynamic Pydantic model for the matching fields
        field_defs = {}

        for field_name, field_info in self.config_class.__pydantic_fields__.items():
            field_supplier = self._get_field_supplier(field_info)
            if field_supplier != supplier:
                continue
            else:
                field_defs[field_name] = (field_info.annotation, field_info)

        title = f"{self.config_class.__name__}[{supplier}]"

        DynamicModel = create_model(title, **field_defs)
        return DynamicModel

    def add_configuration(
        self, supplier: ConfigurationSupplier, config_data: Dict[str, JsonValue]
    ):
        model = self.get_model(supplier)
        model(**config_data)
        self._config_data.update(config_data)
        self._update_state()

    def get_json_schema(self, supplier: ConfigurationSupplier) -> Dict[str, JsonValue]:
        """Generate JSON schema for fields from a specific source"""

        return self.get_model(supplier=supplier).model_json_schema()

    def serialize_config(self, supplier: ConfigurationSupplier) -> Dict[str, JsonValue]:
        supplier_model = self.get_model(supplier)
        supplier_data = {
            field_name: self._config_data[field_name]
            for field_name in supplier_model.__pydantic_fields__.keys()
            if field_name in self._config_data
        }
        return supplier_data

    def get_requirements(
        self, supplier: ConfigurationSupplier
    ) -> List[ConfigurationRequirement]:
        """Get list of missing requirements for a specific source"""
        return [
            req
            for req in self._requirements.values()
            if req.supplier == supplier and req.name not in self._config_data
        ]

    def build_model(self) -> Optional[_T]:
        """Try to build the final configuration model"""
        return self.config_class(**self._config_data)
