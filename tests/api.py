import uvicorn
from fastapi import FastAPI, Request
from pydantic import BaseModel, Field

from ilpas.core.catalog import Catalog
from ilpas.core.instance import Instance, Labels
from ilpas.core.integration import Integration, Specification
from ilpas.core.models.callback import Callback
from ilpas.core.models.display import Display
from ilpas.dx.helpers import extras
from ilpas.dx.in_memory_store import InMemoryStore


# Step 1: Integration Writer creates the base integration
class SlackIntegrationConfig(BaseModel):
    """Base Slack integration configuration defined by the integration writer"""

    api_key: str = Field(
        ...,
        description="Slack API token",
        json_schema_extra=extras("admin", sensitivity="high"),
    )


Slack = Specification(
    guid="slack_latest",
    display=Display(
        name="Slack",
        description="Slack integration",
        logo_url="https://slack.com/favicon.ico",
    ),
    config_model=SlackIntegrationConfig,
    callback=None,
    health_check=None,
    endpoints={},
    webhooks={},
)

SlackV2 = Specification(
    guid="slack_v2",
    display=Display(
        name="Slack V2",
        description="Slack integration V2",
        logo_url="https://slack.com/favicon.ico",
    ),
    config_model=SlackIntegrationConfig,
    callback=Callback(),
    health_check=None,
    endpoints={},
    webhooks={},
)


# Step 2: Admin extends the configuration for their specific use case
class CustomSlackConfig(SlackIntegrationConfig):
    """Admin's extended Slack configuration"""

    default_channel: str = Field(..., json_schema_extra=extras("user"))
    notification_prefix: str = Field(
        default="[ALERT]", json_schema_extra=extras("user")
    )
    rate_limit: int = Field(default=100, gt=0, json_schema_extra=extras("user"))


slack = Integration(
    spec=Slack,
    final_config_model=CustomSlackConfig,
    supplied_config={"api_key": "xoxb-123456789012-123456789012-123456789012"},
)


class CustomSlackConfigV2(SlackIntegrationConfig):
    """Admin's extended Slack configuration"""

    default_channel: str = Field(..., json_schema_extra=extras("user"))
    refresh_token: str = Field(
        default="foo", json_schema_extra=extras("callback", sensitive=True)
    )


slack_v2 = Integration(
    spec=SlackV2,
    final_config_model=CustomSlackConfigV2,
    supplied_config={"api_key": "xoxb-123456789012-123456789012-123456789012"},
)


app = FastAPI()


async def authenticate(blah: int):
    import random

    if random.randint(0, 1) == 0:
        return None

    labels: Labels = {"blah": blah}
    return "placeholder_ns", labels


catalog = Catalog(authenticate=authenticate, store=InMemoryStore())

catalog.add_integration(slack)
catalog.add_integration(slack_v2)
catalog.finalize()

router = catalog.router()
app.include_router(router)

uvicorn.run(app, host="0.0.0.0", port=8000)
