from dataclasses import dataclass
from typing import Awaitable, Callable, Dict, Generic, Optional, TypeVar

from fastapi import Request, Response
from pydantic import BaseModel

_T = TypeVar("_T", bound=BaseModel)


class WebhookEvent:
    uid: str
    respond: Optional[Callable[[Request], Awaitable[Response]]]


@dataclass
class Webhook(Generic[_T]):
    identify: Callable[
        [Request, _T], Awaitable[Optional[str]]
    ]  # returns instance discovery key of the instance that the webhook is for, or None if not instance specific
    verify: Callable[[Request, _T], Awaitable[bool]]  # returns True if webhook is valid
    router: Callable[[Request, _T], Awaitable[WebhookEvent]]  # returns webhook event
