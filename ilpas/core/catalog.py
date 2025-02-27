import logging
import warnings
from enum import StrEnum
from typing import Annotated, Awaitable, Callable, Dict

from fastapi import APIRouter, Body, Depends, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError

from .instance import Instance
from .integration import Integration
from .models.types import JsonValue
from .store import Labels, Store

logger = logging.getLogger(__name__)


class Catalog:
    """
    Catalog of integrations.

    IMPORTANT: Claude caught this one.
    See https://stackoverflow.com/questions/78110125/how-to-dynamically-create-fastapi-routes-handlers-for-a-list-of-pydantic-models
    Helper functions must be used to create routes handlers for each integration because of scoping and closure issues.
    """

    def __init__(
        self,
        store: Store,
        authenticate: Callable[..., Awaitable[tuple[str, Labels] | None]],
    ):
        self.finalized: bool = False
        self._store = store
        self._authenticate = authenticate
        self._integration_registry: Dict[str, Integration] = {}

    def add_integration(
        self,
        integration: Integration,
    ):
        if self.finalized:
            raise RuntimeError("Catalog is finalized, cannot add more integrations")
        if integration.spec.guid in self._integration_registry:
            raise ValueError(f"Integration {integration.spec.guid} already exists")
        Instance(
            integration
        )  # this is a temporary instance to validate the supplied config
        self._integration_registry[integration.spec.guid] = integration

    def finalize(self):
        if self.finalized:
            raise RuntimeError("Catalog is already finalized")
        self.finalized = True
        self._create_enabled_integrations_enum()  # order matters!
        self._create_dependency_functions()

    def _create_enabled_integrations_enum(self):
        members = {key.upper(): key for key in self._integration_registry.keys()}
        self._enabled_integrations_enum = StrEnum("EnabledIntegrations", members)

    def _create_dependency_functions(self):
        self._require_authentication_dep = (
            self._build_require_authentication_dependency()
        )
        self._validate_guid_dep = self._build_validate_guid_dependency()
        self._load_instance_dep = self._build_load_instance_dependency()
        self._temp_instance_dep = self._build_temp_instance_dependency()

    def _build_require_authentication_dependency(self):

        async def require_authentication(
            identity: Annotated[tuple[str, Labels] | None, Depends(self._authenticate)]
        ):
            if identity is None:
                raise HTTPException(status_code=401, detail="Not authenticated")
            return identity

        return require_authentication

    def _build_validate_guid_dependency(self):
        async def validate_guid(guid: self._enabled_integrations_enum):  # type: ignore
            if guid not in self._integration_registry:
                raise HTTPException(status_code=404, detail="Integration not found")
            return guid

        return validate_guid

    def _build_load_instance_dependency(self):

        async def load_instance(
            guid: Annotated[str, Depends(self._validate_guid_dep)],
            identity: Annotated[
                tuple[str, Labels], Depends(self._require_authentication_dep)
            ],
        ):
            integration = self._integration_registry[guid]
            instance = await Instance.restore_by_labels(
                store=self._store,
                integration=integration,
                labels=identity[1],
                namespace=identity[0],
            )
            instance.add_configuration("admin", integration.supplied_config)
            return instance

        return load_instance

    def _build_temp_instance_dependency(self):

        async def temp_instance(guid: Annotated[str, Depends(self._validate_guid_dep)]):
            integration = self._integration_registry[guid]
            return Instance(integration)

        return temp_instance

    def _build_get_catalog_info_handler(self):
        async def get_catalog_handler():
            return [
                {
                    "guid": guid,
                    "display": self._integration_registry[
                        guid
                    ].spec.display.model_dump(),
                }
                for guid in self._integration_registry
            ]

        return get_catalog_handler

    def _build_get_enabled_integrations_handler(self):
        async def get_enabled_integrations():
            return list(self._integration_registry.keys())

        return get_enabled_integrations

    def _build_get_integration_info_handler(self):
        async def get_integration(
            guid: Annotated[str, Depends(self._validate_guid_dep)]
        ):
            return self._integration_registry[guid].spec.display

        return get_integration

    def _build_get_integration_schema_handler(self):
        """
        Uses a temporary instance to avoid loading the configuration through the _load_instance_dep dependency.
        """

        async def get_integration_schema(
            temp_instance: Annotated[Instance, Depends(self._temp_instance_dep)],
        ):
            return temp_instance.get_json_schema("user")

        return get_integration_schema

    def _build_info_router(self) -> APIRouter:
        info_router = APIRouter(tags=["info"])

        get_catalog_info_handler = self._build_get_catalog_info_handler()
        get_enabled_integrations_handler = (
            self._build_get_enabled_integrations_handler()
        )
        get_integration_info_handler = self._build_get_integration_info_handler()
        get_integration_schema_handler = self._build_get_integration_schema_handler()
        info_router.get("/info")(get_catalog_info_handler)
        info_router.get("/enabled")(get_enabled_integrations_handler)
        info_router.get("/{guid}/info")(get_integration_info_handler)
        info_router.get("/{guid}/schema")(get_integration_schema_handler)

        return info_router

    def _build_get_integration_user_config_handler(self):
        async def get_integration_user_config(
            instance: Annotated[Instance, Depends(self._load_instance_dep)],
        ):
            return instance.serialize_config("user")

        return get_integration_user_config

    def _build_put_integration_user_config_handler(self):
        async def put_integration_user_config(
            instance: Annotated[Instance, Depends(self._load_instance_dep)],
            config: Annotated[Dict[str, JsonValue], Body(embed=True)],
        ):
            try:
                instance.get_model("user")(**config)
            except ValidationError as e:
                raise RequestValidationError(e.errors())
            instance.add_configuration("user", config)
            await instance.save(self._store)
            # either return success or needs to do a callback now

        return put_integration_user_config

    def _build_delete_integration_instance_handler(self):
        async def delete_integration_instance(
            instance: Annotated[Instance, Depends(self._load_instance_dep)]
        ):
            await instance.delete(self._store)

        return delete_integration_instance

    def _build_integration_config_callback_handler(self):
        async def integration_config_callback(
            guid: Annotated[str, Depends(self._validate_guid_dep)],
            request: Request,
        ):
            integration = self._integration_registry[guid]
            if integration.spec.callback is None:
                raise HTTPException(
                    status_code=404, detail="This integration does not accept callbacks"
                )
            params = request.query_params
            query_dict = dict(params.items())
            callback_config = await integration.spec.callback.process(query_dict)
            callback_key = await integration.spec.callback.key(query_dict)
            instance = await Instance.restore_by_discovery_key(
                store=self._store,
                integration=integration,
                key_type="callback",
                key=callback_key,
            )
            instance.add_configuration("callback", callback_config)
            await instance.save(self._store)
            # needs to redirect now

        return integration_config_callback

    def _build_webhook_handler(self):
        async def webhook_handler(
            request: Request, guid: Annotated[str, Depends(self._validate_guid_dep)]
        ):
            integration = self._integration_registry[guid]
            if not integration.spec.webhook:
                raise HTTPException(
                    status_code=404, detail="This integration does not accept webhooks"
                )
            if not await integration.spec.webhook.verify(
                request, integration.supplied_config
            ):
                raise HTTPException(status_code=403, detail="Invalid webhook")
            discovery_key = await integration.spec.webhook.identify(
                request, integration.supplied_config
            )
            # instance = None
            # if discovery_key:
            #     instance = await Instance.restore_by_discovery_key(
            #         store=self._store,
            #         integration=integration,
            #         key_type="webhook",
            #         key=discovery_key,
            #     )
            # do this in event handling to avoid loading instance and respond quicker
            event = await integration.spec.webhook.router(
                request, integration.supplied_config
            )
            # still need to publish event for handling
            if event.respond:
                return await event.respond(request)
            else:
                return Response(status_code=200)  # quick and decisive OK response

        return webhook_handler

    def _build_connect_router(self) -> APIRouter:
        base_router = APIRouter(
            prefix="/{guid}",
            tags=["connect"],
            dependencies=[
                Depends(self._validate_guid_dep),
            ],
        )  # base_router CANNOT have a path on /info or /schema, reserved paths for the info router

        management_router = APIRouter(
            dependencies=[
                Depends(self._require_authentication_dep),
                Depends(self._load_instance_dep),
            ]
        )
        get_integration_user_config_handler = (
            self._build_get_integration_user_config_handler()
        )
        put_integration_user_config_handler = (
            self._build_put_integration_user_config_handler()
        )
        management_router.get("/")(get_integration_user_config_handler)
        management_router.put("/")(put_integration_user_config_handler)

        """callback and webhook routers need different ways to load instance"""
        callback_router = APIRouter()
        integration_callback_handler = self._build_integration_config_callback_handler()
        callback_router.get("/callback")(integration_callback_handler)

        webhook_router = APIRouter(tags=["webhook"])
        webhook_router.post("/webhooks")(self._build_webhook_handler())

        base_router.include_router(management_router)
        base_router.include_router(callback_router)
        base_router.include_router(webhook_router)
        return base_router

    def _build_admin_router(self) -> APIRouter:
        router = APIRouter(prefix="/admin", tags=["admin"])
        raise NotImplementedError("Admin routes are not yet implemented")

    def router(
        self,
        info: bool = True,
        connect: bool = True,
        admin: bool = False,
    ) -> APIRouter:
        if not self.finalized:
            raise RuntimeError("Catalog is not finalized, cannot create router")
        catalog_router = APIRouter(prefix="/catalog", tags=["catalog"])
        if info:
            catalog_router.include_router(self._build_info_router())
        if connect:
            catalog_router.include_router(self._build_connect_router())
        if admin:
            logger.warning(
                "Admin routes are enabled. Ensure this router is properly secured."
            )
            warnings.warn(
                "Admin routes are enabled. Ensure this router is properly secured."
            )
            catalog_router.include_router(self._build_admin_router())
        return catalog_router
