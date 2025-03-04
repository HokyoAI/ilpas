import asyncio
import logging
from enum import StrEnum
from typing import Annotated, Awaitable, Callable, Dict, List

from fastapi import APIRouter, Body, Depends, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from hatchet_sdk import Hatchet
from pydantic import ValidationError

from .httpx import HttpxAsyncClient
from .hub import Event, HatchetListener, Hub, Listener
from .instance import Instance
from .integration import Integration
from .models.config_response import (
    ConfigResponse,
    RedirectNotRequired,
    RedirectRequired,
)
from .models.errors import IlpasValueError, NotFoundException
from .models.types import AM, JsonValue
from .store import Labels, Store

logger = logging.getLogger(__name__)


class Catalog:
    """
    Catalog of integrations.

    All api paths are prefixed with /catalog and should end with a trailing slash (Except for webhooks, special case).

    IMPORTANT: Claude caught this one.
    See https://stackoverflow.com/questions/78110125/how-to-dynamically-create-fastapi-routes-handlers-for-a-list-of-pydantic-models
    Helper functions must be used to create routes handlers for legacy method of creating routes for each integration
    because of scoping and closure issues.
    """

    def __init__(
        self,
        *,
        store: Store,
        hatchet: Hatchet,
        additional_listeners: List[Listener] = [],
    ):
        self.finalized: bool = False
        self._store = store
        self._hub = Hub()
        self._hub.register(HatchetListener(hatchet))
        for listener in additional_listeners:
            self._hub.register(listener)
        self._integration_registry: Dict[str, Integration[AM, AM, AM, AM]] = {}

    def add_integration(self, *, integration: Integration[AM, AM, AM, AM]):
        if self.finalized:
            raise RuntimeError("Catalog is finalized, cannot add more integrations")
        if integration.spec.guid in self._integration_registry:
            raise ValueError(f"Integration {integration.spec.guid} already exists")

        self._integration_registry[integration.spec.guid] = integration

    def finalize(self):
        if self.finalized:
            raise RuntimeError("Catalog is already finalized")
        self.finalized = True

    def router(
        self,
        *,
        http_authenticate: Callable[..., Awaitable[tuple[str, Labels] | None]],
        include_info: bool = True,
        include_connect: bool = True,
    ) -> APIRouter:
        if not self.finalized:
            raise RuntimeError("Catalog is not finalized, cannot create router")

        # order matters !
        self._http_authenticate = http_authenticate
        self._create_enabled_integrations_enum()
        self._create_dependency_functions()

        catalog_router = APIRouter(prefix="/catalog", tags=["catalog"])
        if include_info:
            catalog_router.include_router(self._build_info_router())
        if include_connect:
            catalog_router.include_router(self._build_connect_router())

        return catalog_router

    def worker(self):
        if not self.finalized:
            raise RuntimeError("Catalog is not finalized, cannot create worker")

    def _create_enabled_integrations_enum(self):
        members = {key.upper(): key for key in self._integration_registry.keys()}
        self._enabled_integrations_enum = StrEnum("EnabledIntegrations", members)

    def _create_dependency_functions(self):
        self._require_authentication_dep = (
            self._build_require_authentication_dependency()
        )
        self._validate_guid_dep = self._build_validate_guid_dependency()
        self._try_load_instance_dep = self._build_try_load_instance_dependency()
        self._require_instance_dep = self._build_require_instance_dependency()

    def _build_require_authentication_dependency(self):

        async def require_authentication(
            identity: Annotated[
                tuple[str, Labels] | None, Depends(self._http_authenticate)
            ]
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

    def _build_try_load_instance_dependency(self):

        async def try_load_instance(
            guid: Annotated[str, Depends(self._validate_guid_dep)],
            identity: Annotated[
                tuple[str, Labels], Depends(self._require_authentication_dep)
            ],
        ) -> Instance | None:
            """Load an instance from the store. If not found, return None"""
            try:
                integration = self._integration_registry[guid]
                instance = await Instance.restore_by_labels(
                    store=self._store,
                    integration=integration,
                    namespace=identity[0],
                    labels=identity[1],
                )  # will raise NotFoundException if not found
                return instance
            except NotFoundException:
                return None

        return try_load_instance

    def _build_require_instance_dependency(self):
        async def require_instance(
            instance: Annotated[Instance | None, Depends(self._try_load_instance_dep)],
        ) -> Instance:
            """Load an instance from the store. If not found, raise an error."""
            if instance is None:
                raise HTTPException(status_code=404, detail="Instance not found")
            return instance

        return require_instance

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
            guid: Annotated[str, Depends(self._validate_guid_dep)],
        ):
            return self._integration_registry[
                guid
            ].spec.user_config_model.model_json_schema()

        return get_integration_schema

    def _build_info_router(self) -> APIRouter:
        info_router = APIRouter(tags=["info"])

        get_catalog_info_handler = self._build_get_catalog_info_handler()
        get_enabled_integrations_handler = (
            self._build_get_enabled_integrations_handler()
        )
        get_integration_info_handler = self._build_get_integration_info_handler()
        get_integration_schema_handler = self._build_get_integration_schema_handler()
        info_router.get("/info/")(get_catalog_info_handler)
        info_router.get("/enabled/")(get_enabled_integrations_handler)
        info_router.get("/{guid}/info/")(get_integration_info_handler)
        info_router.get("/{guid}/schema/")(get_integration_schema_handler)

        return info_router

    def _build_get_instance_handler(self):
        async def get_instance(
            instance: Annotated[
                Instance, Depends(self._require_instance_dep)
            ],  # will throw 404 if not found
        ):
            return instance.serialize_config_by_supplier("user")

        return get_instance

    def _build_create_instance_handler(self):
        async def create_instance(
            guid: Annotated[str, Depends(self._validate_guid_dep)],
            identity: Annotated[
                tuple[str, Labels], Depends(self._require_authentication_dep)
            ],
            instance: Annotated[Instance | None, Depends(self._try_load_instance_dep)],
            config: Annotated[Dict[str, JsonValue], Body(embed=True)],
        ) -> ConfigResponse:
            if instance is not None:
                raise HTTPException(status_code=409, detail="Instance already exists")
            integration = self._integration_registry[guid]
            instance = Instance(
                integration=integration,
                store=self._store,
                supplied_user_config=config,
                namespace=identity[0],
                labels=identity[1],
            )

            await instance.save()
            if not instance.primary_key:
                raise HTTPException(
                    status_code=500, detail="Instance was not saved correctly"
                )

            if integration.spec.callback:
                state_key = await instance.assign_discovery_key(
                    key_type="callback", key=None, one_time=True
                )
                uri = await integration.spec.callback.uri(
                    user_config=instance.user_config,
                    admin_config=instance.admin_config,
                    state_key=state_key,
                )
                return RedirectRequired(
                    config=instance.serialize_config_by_supplier("user"),
                    redirect_uri=uri,
                )

            else:
                if integration.spec.setup:
                    pass  # push setup event
                return RedirectNotRequired(
                    config=instance.serialize_config_by_supplier("user")
                )

        return create_instance

    def _build_update_instance_handler(self):
        async def update_instance(
            instance: Annotated[Instance, Depends(self._require_instance_dep)],
            config: Annotated[Dict[str, JsonValue], Body(embed=True)],
        ) -> ConfigResponse:
            try:
                instance.get_model("user")(**config)
            except ValidationError as e:
                raise RequestValidationError(e.errors())
            trigger_callback = instance.add_configuration("user", config)
            await instance.save(self._store)
            if trigger_callback:
                callback = instance.integration.spec.callback
                if not callback:
                    raise IlpasValueError(
                        "Configuration cannot trigger a callback if the spec does not have a callback"
                    )
                uri, key = await asyncio.gather(
                    *[callback.uri(config), callback.key(config)]
                )
                await instance.create_discovery_key(
                    store=self._store, key_type="callback", key=key
                )
                return RedirectRequired(
                    config=instance.serialize_config("user"),
                    redirect_uri=uri,
                )
            else:
                return RedirectNotRequired(config=instance.serialize_config("user"))

        return update_instance

    def _build_delete_instance_handler(self):
        async def delete_instance(
            instance: Annotated[Instance, Depends(self._require_instance_dep)]
        ):
            await instance.delete()

        return delete_instance

    def _build_callback_handler(self):
        async def callback(
            guid: Annotated[str, Depends(self._validate_guid_dep)],
            request: Request,
        ):
            integration = self._integration_registry[guid]
            if integration.spec.callback is None:
                raise HTTPException(
                    status_code=404, detail="This integration does not accept callbacks"
                )
            query_dict = dict(request.query_params.items())
            state_key = await integration.spec.callback.identify(
                query_params=query_dict
            )
            instance = await Instance.restore_by_discovery_key(
                store=self._store,
                integration=integration,
                key_type="callback",
                key=state_key,
            )
            callback_config = await integration.spec.callback.process(
                query_params=query_dict,
                user_config=instance.user_config,
                admin_config=instance.admin_config,
            )
            instance.callback_config = callback_config

            return await integration.spec.callback.respond(
                query_params=query_dict,
                user_config=instance.user_config,
                admin_config=instance.admin_config,
                callback_config=callback_config,
            )

        return callback

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
            ]
        )
        get_instance_handler = self._build_get_instance_handler()
        create_instance_handler = self._build_create_instance_handler()
        update_instance_handler = self._build_update_instance_handler()
        delete_instance_handler = self._build_delete_instance_handler()
        management_router.get("/")(get_instance_handler)
        management_router.post("/", response_model=ConfigResponse)(
            create_instance_handler
        )
        management_router.put("/", response_model=ConfigResponse)(
            update_instance_handler
        )
        management_router.delete("/")(delete_instance_handler)

        """callback and webhook routers need different ways to load instance"""
        callback_router = APIRouter()
        callback_handler = self._build_callback_handler()
        callback_router.get("/callback/")(callback_handler)

        webhook_router = APIRouter(tags=["webhook"])
        webhook_handler = self._build_webhook_handler()
        webhook_router.post("/webhooks{rest_of_path:path}")(webhook_handler)

        base_router.include_router(management_router)
        base_router.include_router(callback_router)
        base_router.include_router(webhook_router)
        return base_router
