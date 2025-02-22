from dataclasses import dataclass


@dataclass
class Webhook:
    url: str
    method: str
    headers: dict
    body: dict
