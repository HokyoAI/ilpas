from typing import Callable, Dict, Optional, cast
from uuid import uuid4

from pydantic import BaseModel
from pydantic.fields import FieldInfo

from .integration import Integration
from .models.base_model_extras import DEFAULT_SENSITIVE, DEFAULT_TRIGGER_CALLBACK
from .models.errors import BadDataError, IlpasValueError
from .models.types import (
    AM,
    ConfigurationSupplier,
    InstanceConfig,
    JsonValue,
    KeyTypes,
    Sensitivity,
    ValueDict,
)
from .store import Labels, Store


class Instance[_I: AM, _U: AM, _A: AM, _C: AM, _S: AM]():

    @property
    def user_config(self) -> _U:
        return self._user_config

    @user_config.setter
    def user_config(self, value: Dict[str, JsonValue] | _U) -> None:
        if isinstance(value, BaseModel):
            self._user_config = value
        else:
            self._user_config = self.integration.spec.user_config_model(**value)

    @property
    def admin_config(self) -> _A:
        return self._admin_config

    @admin_config.setter
    def admin_config(self, value: Callable[[_U], Dict[str, JsonValue] | _A]) -> None:
        self._admin_config_func = value
        result = self._admin_config_func(self.user_config)
        if isinstance(result, BaseModel):
            self._admin_config = result
        else:
            self._admin_config = self.integration.spec.admin_config_model(**result)

    @property
    def callback_config(self) -> Optional[_C]:
        return self._callback_config

    @callback_config.setter
    def callback_config(self, value: Optional[Dict[str, JsonValue] | _C]) -> None:
        if value is None:
            self._callback_config = None
        else:
            if self.integration.spec.callback is None:
                raise IlpasValueError(
                    "Cannot set callback config to not-None value for integration without callback"
                )
            if isinstance(value, BaseModel):
                self._callback_config = value
            else:
                self._callback_config = (
                    self.integration.spec.callback.callback_config_model(**value)
                )

    @property
    def state(self) -> Optional[_S]:
        return self._state

    @state.setter
    def state(self, value: Optional[Dict[str, JsonValue] | _S]) -> None:
        if value is None:
            self._state = None
        else:
            if self.integration.spec.state_model is None:
                raise IlpasValueError(
                    "Cannot set state to not-None value for integration without state"
                )
            if isinstance(value, BaseModel):
                self._state = value
            else:
                self._state = self.integration.spec.state_model(**value)

    def __init__(
        self,
        *,
        integration: Integration[_I, _U, _A, _C, _S],
        store: Store,
        supplied_user_config: Dict[str, JsonValue],
        labels: Labels,
        namespace: Optional[str] = None,
    ) -> None:
        self.integration = integration
        self.store = store
        self.int_guid = integration.spec.guid
        self.namespace = namespace
        self.labels = labels
        self.user_config = supplied_user_config
        self.admin_config = integration.supplied_admin_config
        self.callback_config = None
        self._state = None
        self.primary_key: Optional[str] = None

    def __call__(self) -> InstanceConfig[_U, _A, _C, _S]:
        return {
            "user": self.user_config,
            "admin": self.admin_config,
            "callback": self.callback_config,
            "state": self.state,
        }

    @classmethod
    async def restore_by_primary_key(
        cls,
        *,
        store: Store,
        integration: Integration,
        primary_key: str,
        namespace: Optional[str],
    ) -> "Instance":
        """Restore the configuration from the store"""
        data = await store.get_by_primary_key(
            primary_key=primary_key, namespace=namespace
        )
        labels = data["labels"]
        value = data["value"]
        result = cls(
            integration=integration,
            store=store,
            supplied_user_config=value["user"],
            labels=labels,
            namespace=namespace,
        )
        if "callback" in value:
            result.callback_config = value["callback"]
        if "state" in value:
            result.state = value["state"]
        result.primary_key = primary_key

        return result

    @classmethod
    async def restore_by_labels(
        cls,
        *,
        store: Store,
        integration: Integration,
        labels: Labels,
        namespace: Optional[str],
    ) -> "Instance":
        """Restore the configuration from the store"""
        data = await store.get_by_labels(
            guid=integration.spec.guid, labels=labels, namespace=namespace
        )
        value = data["value"]
        primary_key = data["primary_key"]
        result = cls(
            integration=integration,
            store=store,
            supplied_user_config=value["user"],
            labels=labels,
            namespace=namespace,
        )
        if "callback" in value:
            result.callback_config = value["callback"]
        if "state" in value:
            result.state = value["state"]
        result.primary_key = primary_key

        return result

    @staticmethod
    def _full_key_helper(*, guid: str, key_type: KeyTypes, key: str) -> str:
        return f"{guid}:{key_type}:{key}"

    async def assign_discovery_key(
        self, *, key_type: KeyTypes, key: Optional[str], one_time: bool
    ) -> str:
        if not key:
            key = str(uuid4())
        full_key = self._full_key_helper(
            guid=self.int_guid,
            key_type=key_type,
            key=key,
        )
        if self.primary_key is None:
            raise IlpasValueError(
                "Instance must have primary_key to create discovery key"
            )
        await self.store._put_instance_discovery(
            key=full_key,
            primary_key=self.primary_key,
            namespace=self.namespace,
            one_time=one_time,
        )
        return key

    @classmethod
    async def restore_by_discovery_key(
        cls,
        *,
        store: Store,
        integration: Integration,
        key_type: KeyTypes,
        key: str,
    ):
        full_key = cls._full_key_helper(
            guid=integration.spec.guid,
            key_type=key_type,
            key=key,
        )
        instance_ids = await store.instance_discovery(key=full_key)
        primary_key = instance_ids[0]
        namespace = instance_ids[1]
        result = await cls.restore_by_primary_key(
            store=store,
            integration=integration,
            primary_key=primary_key,
            namespace=namespace,
        )
        return result

    def _get_extra_field[
        T
    ](
        self, field_info: FieldInfo, field_name: str, field_type: type[T], default: T
    ) -> T:
        if not field_info.json_schema_extra:
            return default
        if isinstance(field_info.json_schema_extra, dict):
            value = field_info.json_schema_extra.get(field_name, None)
            if value is None:
                return default
            elif isinstance(value, field_type):
                return value
            else:
                raise ValueError(
                    f"field {field_info.title} json_schema_extra.{field_name} must be a {field_type}"
                )
        else:
            raise ValueError(
                f"field {field_info.title} json_schema_extra must be a dict, callable is not supported"
            )

    def _get_field_sensitivity(self, field_info: FieldInfo) -> Sensitivity:
        """Check if a field is sensitive based on its FieldInfo"""
        sens_string = self._get_extra_field(
            field_info, "sensitive", str, DEFAULT_SENSITIVE
        )
        if sens_string not in ["none", "low", "high"]:
            raise ValueError(f"Invalid sensitivity {sens_string}")
        else:
            return cast(Sensitivity, sens_string)

    def _is_field_callback_trigger(self, field_info: FieldInfo) -> bool:
        """Check if a field triggers a callback based on its FieldInfo"""
        return self._get_extra_field(
            field_info, "triggers_callback", bool, DEFAULT_TRIGGER_CALLBACK
        )

    def get_model(self, supplier: ConfigurationSupplier):
        if supplier == "user":
            return self.integration.spec.user_config_model
        elif supplier == "admin":
            return self.integration.spec.admin_config_model
        elif supplier == "callback":
            if self.integration.spec.callback is None:
                raise IlpasValueError("Integration does not have a callback")
            return self.integration.spec.callback.callback_config_model
        elif supplier == "state":
            if self.integration.spec.state_model is None:
                raise IlpasValueError("Integration does not have a state model")
            return self.integration.spec.state_model
        else:
            raise IlpasValueError(f"Invalid supplier {supplier}")

    def _dump(self) -> ValueDict:
        result: ValueDict = {
            "user": self.user_config.model_dump(),
            "admin": self.admin_config.model_dump(),
        }
        if self.callback_config:
            result["callback"] = self.callback_config.model_dump()
        if self.state:
            result["state"] = self.state.model_dump()
        return result

    def serialize_config_by_supplier(
        self, supplier: ConfigurationSupplier, redact: bool = True
    ) -> Dict[str, JsonValue]:
        config_model = self.get_model(supplier)
        result = {}
        config_data = None
        if supplier == "user":
            config_data = self.user_config.model_dump()
        elif supplier == "admin":
            config_data = self.admin_config.model_dump()
        elif supplier == "callback":
            if self.callback_config is None:
                return {}
            config_data = self.callback_config.model_dump()
        elif supplier == "state":
            if self.state is None:
                return {}
            config_data = self.state.model_dump()
        else:
            raise IlpasValueError(f"Invalid supplier {supplier}")

        for field_name, field_info in config_model.__pydantic_fields__.items():
            sensitivity = self._get_field_sensitivity(field_info)
            if redact and sensitivity == "high":
                continue
            if field_name in config_data:
                result[field_name] = config_data[field_name]

        return result

    async def save(self):
        value = self._dump()
        if self.primary_key is not None:
            await self.store.put_by_primary_key(
                value=value,
                guid=self.int_guid,
                labels=self.labels,
                namespace=self.namespace,
                primary_key=self.primary_key,
            )
        else:
            pkey = await self.store.put_by_labels(
                value=value,
                guid=self.int_guid,
                labels=self.labels,
                namespace=self.namespace,
            )
            self.primary_key = pkey

    async def delete(self):
        if self.primary_key is not None:
            await self.store.delete_by_primary_key(
                primary_key=self.primary_key, namespace=self.namespace
            )
        else:
            raise IlpasValueError("Instance must have primary_key to be deleted")
