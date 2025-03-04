from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Awaitable, Callable, Dict, Generic, List, Optional, TypeVar

from fastapi import Request, Response
from hatchet_sdk import Workflow
from pydantic import BaseModel

from .httpx import HttpxAsyncClient, HttpxResponse
from .hub import Event

_A = TypeVar("_A", bound=BaseModel)
_U = TypeVar("_U", bound=BaseModel)
_C = TypeVar("_C", bound=BaseModel)
_S = TypeVar("_S", bound=BaseModel)


class NoConfig(BaseModel):
    model_config = {"extra": "forbid"}


class AnyConfig(BaseModel):
    model_config = {"extra": "allow"}


class Display(BaseModel):
    name: str
    description: Optional[str] = None
    logo_url: Optional[str] = None


class Callback(Generic[_U, _A, _C], ABC):
    callback_config_model: type[_C]

    @classmethod
    @abstractmethod
    async def uri(cls, *, user_config: _U, admin_config: _A, state_key: str) -> str:
        """Should return the uri to redirect user to"""
        ...

    @classmethod
    @abstractmethod
    async def identify(
        cls,
        *,
        query_params: Dict[str, str],
    ) -> str:
        """Should return the state key for the callback"""
        ...

    @classmethod
    @abstractmethod
    async def process(
        cls,
        *,
        user_config: _U,
        admin_config: _A,
        query_params: Dict[str, str],
    ) -> _C: ...

    @classmethod
    @abstractmethod
    async def respond(
        cls,
        *,
        user_config: _U,
        admin_config: _A,
        callback_config: _C,
        query_params: Dict[str, str],
    ) -> Response:
        """Should return the response to the callback request"""
        ...


class Endpoint(Generic[_U, _A, _C, _S], ABC):

    @classmethod
    @abstractmethod
    async def __call__(
        cls,
        *,
        client: HttpxAsyncClient,
        user_config: _U,
        admin_config: _A,
        callback_config: _C,
        state: _S,
        **kwargs,
    ) -> HttpxResponse:
        pass


class Webhook(Generic[_A, _U, _C, _S], ABC):

    @classmethod
    @abstractmethod
    async def identify(
        cls,
        request: Request,
    ) -> Optional[str]:
        """Returns instance discovery key of the instance that the webhook is for, or None if not instance specific"""
        ...

    @classmethod
    @abstractmethod
    async def verify(
        cls,
        request: Request,
        admin_config: _A,
        user_config: _U,
        callback_config: _C,
        state: _S,
    ) -> bool:
        """Verify that the webhook is from the correct source"""
        ...

    @classmethod
    @abstractmethod
    async def router(
        cls,
        request: Request,
        admin_config: _A,
        user_config: _U,
        callback_config: _C,
        state: _S,
    ) -> Event:
        """Process the webhook and return a Event"""
        ...

    @classmethod
    @abstractmethod
    async def respond(
        cls,
        request: Request,
        event: Event,
        admin_config: _A,
        user_config: _U,
        callback_config: _C,
        state: _S,
    ) -> Response:
        """Respond to the webhook request"""
        ...


class Specification(Generic[_U, _A, _C, _S], ABC):
    """
    Abstract base class for specifications.
    Subclasses must define all required class attributes.
    Specifications are never instantiated.
    All of their properties are class properties and methods are class methods.
    These are simply convenient ways to group related models and functions.

    The integration's endpoints should be present as class properties, and should be equal to an Endpoint instance.

    All events should be present as class properties, and should be equal to an Event class. These are used to
    dispatch events to listeners.
    """

    guid: str
    display: Display
    user_config_model: type[_U]
    admin_config_model: type[_A]
    callback: Optional[Callback[_U, _A, _C]]
    state_model: Optional[type[_S]]
    setup: Optional[Workflow]
    maintenance: Optional[
        List[Workflow]
    ]  # Must have cron expression or they will never be called
    # possibly change to self scheduling workflows that schedule themselves at the end of the workflow
    teardown: Optional[Workflow]
    webhook: Optional[Webhook[_U, _A, _C, _S]]
