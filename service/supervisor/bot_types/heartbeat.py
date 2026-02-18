import asyncio

from service.supervisor.events import BotEventWriter


async def run_heartbeat_bot(
    bot_id: str,
    owner_client_id: str,
    interval_seconds: int,
    event_writer: BotEventWriter,
) -> None:
    try:
        while True:
            event_writer.emit(
                bot_id=bot_id,
                owner_client_id=owner_client_id,
                event_type="HEARTBEAT",
                message=f"Heartbeat emitted every {interval_seconds}s",
            )
            await asyncio.sleep(interval_seconds)
    except asyncio.CancelledError:
        raise
