import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
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


async def slack_uri(data: dict):
    return "https://slack.com/oauth/v2/authorize?client_id={client_id}&scope={scopes}&redirect_uri={redirect_uri}"


slack_callback = Callback()


Slack = Specification(
    guid="slack_latest",
    display=Display(
        name="Slack",
        description="Slack integration",
        logo_url="https://slack.com/favicon.ico",
    ),
    config_model=SlackIntegrationConfig,
    endpoints={},
    callback=None,
    health_check=None,
    webhook=None,
)

SlackV2 = Specification(
    guid="slack_v2",
    display=Display(
        name="Slack V2",
        description="Slack integration V2",
        logo_url="https://slack.com/favicon.ico",
    ),
    config_model=SlackIntegrationConfig,
    endpoints={},
    callback=None,
    health_check=None,
    webhook=None,
)


# Step 2: Admin extends the configuration for their specific use case
class CustomSlackConfig(SlackIntegrationConfig):
    """Admin's extended Slack configuration"""

    default_channel: str = Field(
        ..., json_schema_extra=extras("user"), min_length=1
    )  # IMPORTANT: min_length=1, might write a helper function to apply this to all required strings
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
    scopes: str = Field(..., json_schema_extra=extras("user", triggers_callback=True))
    refresh_token: str = Field(
        default="foo", json_schema_extra=extras("callback", sensitivity="high")
    )


slack_v2 = Integration(
    spec=SlackV2,
    final_config_model=CustomSlackConfigV2,
    supplied_config={"api_key": "xoxb-123456789012-123456789012-123456789012"},
)


app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


async def authenticate():
    labels: Labels = {}
    return "placeholder_ns", labels


catalog = Catalog(authenticate=authenticate, store=InMemoryStore())

catalog.add_integration(slack)
catalog.add_integration(slack_v2)
catalog.finalize()

router = catalog.router()
app.include_router(router)
