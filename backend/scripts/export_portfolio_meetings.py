import json
import uuid
from pathlib import Path

from sqlalchemy import create_engine, text

from app.core.config import settings


OUTPUT_FILE = Path("../portfolio_meetings.json")


def main():
    # Safety: this script must read from the ORIGINAL database,
    # never from the Neon portfolio database.
    if "neon.tech" in settings.database_url.lower():
        raise RuntimeError(
            "SAFETY STOP: DATABASE_URL points to Neon. "
            "Run this exporter only against the original database."
        )

    engine = create_engine(
        settings.database_url,
        pool_pre_ping=True,
    )

    # IMPORTANT:
    # Deliberately select ONLY fields approved for the public portfolio.
    query = text(
        """
        SELECT
            source,
            topic,
            start_time,
            duration_minutes
        FROM meetings
        ORDER BY start_time DESC NULLS LAST
        """
    )

    meetings = []

    with engine.connect() as connection:
        rows = connection.execute(query)

        for row in rows:
            meetings.append(
                {
                    # Generate a completely new ID.
                    # Do not expose the original database UUID.
                    "id": str(uuid.uuid4()),
                    "source": row.source,
                    "topic": row.topic,
                    "start_time": (
                        row.start_time.isoformat()
                        if row.start_time
                        else None
                    ),
                    "duration_minutes": row.duration_minutes,
                }
            )

    with OUTPUT_FILE.open(
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            meetings,
            file,
            ensure_ascii=False,
            indent=2,
        )

    print(
        f"SAFE EXPORT COMPLETE: {len(meetings)} meetings"
    )

    print(
        f"OUTPUT: {OUTPUT_FILE.resolve()}"
    )

    print(
        "Exported fields: "
        "id (new), source, topic, start_time, duration_minutes"
    )


if __name__ == "__main__":
    main()