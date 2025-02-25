import logging
import sys
from enum import Enum

from fastapi import FastAPI

try:
    import click
except ImportError:
    raise ImportError("cli extra required to run cli. Use pip install ilpas[cli]")

# TODO move CLI config to environment variables/settings
# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class RunMode(str, Enum):
    API = "api"
    WORKER = "worker"
    MIGRATIONS = "migrate"


class Config:
    def __init__(self):
        self.debug: bool = False
        self.port: int = 8000
        self.worker_queue: str = "default"
        self.migration_timeout: int = 300


pass_config = click.make_pass_decorator(Config, ensure=True)


@click.group()
@click.option("--debug/--no-debug", default=False, help="Enable debug mode")
@click.pass_context
def cli(ctx: click.Context, debug: bool):
    """Application runner that supports multiple run modes: API server, Worker, and Migrations."""
    ctx.obj = Config()
    ctx.obj.debug = debug

    if debug:
        logging.getLogger().setLevel(logging.DEBUG)


@cli.command()
@click.option("--host", "-h", default="0.0.0.0", help="Host to bind to")
@click.option("--port", "-p", default=8000, help="Port to bind to")
@pass_config
def api(config: Config, host: str, port: int):
    """Run the FastAPI server."""
    config.port = port
    logger.debug(f"Debug mode: {config.debug}")

    try:
        app = FastAPI()

        logger.info(f"Starting API server on {host}:{port}")

        api_main(host=host, port=port)
        logger.info("API server stopped successfully")
    except Exception as e:
        logger.error(f"Failed to start API server: {e}")
        sys.exit(1)


@cli.command()
@click.option("--queue", "-q", default="default", help="Worker queue to process")
@click.option("--concurrency", "-c", default=1, help="Number of worker processes")
@pass_config
def worker(config: Config, queue: str, concurrency: int):
    """Run the Hatchet Worker."""
    config.worker_queue = queue
    logger.info(
        f"Starting Hatchet Worker on queue '{queue}' with concurrency {concurrency}"
    )
    logger.debug(f"Debug mode: {config.debug}")

    try:
        # Import and run Hatchet worker here
        logger.info("Initializing Hatchet Worker...")
        from core.workflows.worker import worker

        worker.start()

    except Exception as e:
        logger.error(f"Failed to start worker: {e}")
        sys.exit(1)


@cli.command()
@click.option("--timeout", "-t", default=300, help="Migration timeout in seconds")
@click.option("--dry-run/--no-dry-run", default=False, help="Perform a dry run")
@click.option("--all", "-a", is_flag=True, help="Run all migrations")
@click.option(
    "--public/--no-public", default=False, help="Run public schema migrations"
)
@click.option(
    "--org/--no-org", default=False, help="Run organization schema migrations"
)
@click.option(
    "--project/--no-project", default=False, help="Run project schema migrations"
)
@pass_config
def migrate(
    config: Config,
    timeout: int,
    dry_run: bool,
    all: bool,
    public: bool,
    org: bool,
    project: bool,
):
    """Run database migrations."""
    logger.debug(f"Debug mode: {config.debug}")

    try:
        # Import and run migrations here
        from core.migrations.main import main as migrations_main

        logger.info("Running database migrations...")

        if all:
            public = True
            org = True
            project = True
        # Pass the flags to migrations_main
        migrations_main(
            public=public,
            org=org,
            project=project,
        )

        logger.info("Migrations completed successfully")
    except Exception as e:
        logger.error(f"Failed to run migrations: {e}")
        sys.exit(1)


if __name__ == "__main__":
    cli()
