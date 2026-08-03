import logging
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler

logger = logging.getLogger(__name__)


def run_emergency_check(app):
    """Automatically call the existing emergency endpoint."""

    try:
        with app.app_context():
            with app.test_client() as client:
                response = client.post(
                    "/api/emergency/send-to-risk-areas",
                    json={
                        "threshold": app.config.get(
                            "AUTO_ALERT_THRESHOLD",
                            60
                        ),
                        "dry_run": app.config.get(
                            "AUTO_ALERT_DRY_RUN",
                            True
                        )
                    }
                )

                result = response.get_json()

                logger.info(
                    f"Automatic emergency check finished: {result}"
                )

    except Exception as error:
        logger.exception(
            f"Automatic emergency check failed: {error}"
        )


def start_scheduler(app):
    interval_minutes = app.config.get(
        "EMERGENCY_CHECK_INTERVAL_MINUTES",
        60
    )

    scheduler = BackgroundScheduler(
        timezone="Asia/Colombo"
    )

    scheduler.add_job(
        func=run_emergency_check,
        trigger="interval",
        minutes=interval_minutes,
        args=[app],
        id="automatic_emergency_check",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
        # Run once immediately when run.py starts.
        next_run_time=datetime.now()
    )

    scheduler.start()

    logger.info(
        f"Emergency scheduler started. "
        f"Checking every {interval_minutes} minutes."
    )

    return scheduler