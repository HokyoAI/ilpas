from pydantic import BaseModel


class NoConfig(BaseModel):
    model_config = {"extra": "forbid"}
