from typing import Optional

from pydantic import BaseModel


class Display(BaseModel):
    name: str
    description: Optional[str] = None
    logo_url: Optional[str] = None
