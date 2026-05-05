import asyncio

from hypercorn.asyncio import serve
from hypercorn.config import Config

from service.api import app


def main() -> None:
    config = Config()
    config.bind = ["0.0.0.0:8080"]
    config.accesslog = "-"
    config.errorlog = "-"
    asyncio.run(serve(app, config))


if __name__ == "__main__":
    main()
