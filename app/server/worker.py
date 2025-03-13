import asyncio
import logging

import pytz
from apps.files.worker import remove_deleted_directories, remove_deleted_files
from apscheduler.schedulers.asyncio import AsyncIOScheduler

irst_timezone = pytz.timezone("Asia/Tehran")
logging.getLogger("apscheduler").setLevel(logging.WARNING)


async def worker():
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        remove_deleted_files, "cron", hour=3, minute=30, timezone=irst_timezone
    )
    scheduler.add_job(
        remove_deleted_directories, "cron", hour=3, minute=30, timezone=irst_timezone
    )
    # scheduler.add_job(remove_old_access_files, "cron", hour=3, minute=30, timezone=irst_timezone)

    scheduler.start()

    try:
        await asyncio.Event().wait()
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        scheduler.shutdown()
