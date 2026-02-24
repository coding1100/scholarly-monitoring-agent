from __future__ import annotations

import asyncio
import signal

from app.core.logging import logger, setup_logging
from app.db.session import dispose_engine, ensure_data_dir, init_schema_if_needed
from app.worker.scheduler import MonitorJobScheduler


async def run_worker() -> None:
    setup_logging()
    ensure_data_dir()
    await init_schema_if_needed()

    scheduler = MonitorJobScheduler()
    await scheduler.start()

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()

    for signame in ("SIGINT", "SIGTERM"):
        sig = getattr(signal, signame, None)
        if sig is None:
            continue
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:
            # Windows event loops may not support this.
            pass

    logger.info("worker_running")
    try:
        await stop_event.wait()
    except KeyboardInterrupt:
        logger.info("worker_keyboard_interrupt")
    finally:
        await scheduler.stop()
        await dispose_engine()
        logger.info("worker_stopped")


def main() -> None:
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
