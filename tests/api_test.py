import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel

from ilpas.core.catalog import Catalog
from ilpas.core.integration import Display, Integration, Specification


class SlackAdminConfig(BaseModel):
    token: str


Slack = Specification(
    guid="slack.latest",
    display=Display(
        name="Slack",
        description="Slack integration",
        logo_url="https://slack.com/favicon.ico",
    ),
    endpoints={},
    webhooks={},
    admin_config_model=SlackAdminConfig,
)

SlackV2 = Specification(
    guid="slack.v2",
    display=Display(
        name="Slack V2",
        description="Slack integration V2",
        logo_url="https://slack.com/favicon.ico",
    ),
    endpoints={},
    webhooks={},
    admin_config_model=SlackAdminConfig,
)


class SlackUserConfig(BaseModel):
    model_config = {"extra": "forbid"}
    channel: str


slack = Integration(
    spec=Slack,
    admin_config=Slack.admin_config_model(
        token="xoxb-123456789012-123456789012-123456789012"
    ),
    user_config_model=SlackUserConfig,
)


class SlackV2UserConfig(BaseModel):
    model_config = {"extra": "forbid"}
    channel: str
    blah: str


slack_v2 = Integration(
    spec=SlackV2,
    admin_config=SlackV2.admin_config_model(
        token="xoxb-123456789012-123456789012-123456789012"
    ),
    user_config_model=SlackV2UserConfig,
)


app = FastAPI()

catalog = Catalog()

catalog.add_integration(slack)
catalog.add_integration(slack_v2)

routers = catalog.serve()

for router in routers:
    app.include_router(router)

uvicorn.run(app, host="0.0.0.0", port=8000)
