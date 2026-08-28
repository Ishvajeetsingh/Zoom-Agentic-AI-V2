import json
from pathlib import Path

from sqlalchemy import create_engine, text

from app.core.config import settings


INPUT_FILE = Path("../portfolio_meetings.json")


def main():
    # --------------------------------------------------------
    # SAFETY CHECK
    # --------------------------------------------------------

    if "neon.tech" not in settings.database_url.lower():
        raise RuntimeError(
            "SAFETY STOP: This importer may only run "
            "against the Neon portfolio database."
        )

    if not INPUT_FILE.exists():
        raise RuntimeError(
            f"Portfolio meeting file not found: "
            f"{INPUT_FILE.resolve()}"
        )

    # --------------------------------------------------------
    # LOAD SANITIZED JSON
    # --------------------------------------------------------

    with INPUT_FILE.open(
        "r",
        encoding="utf-8",
    ) as file:
        meetings = json.load(file)

    allowed_fields = {
        "id",
        "source",
        "topic",
        "start_time",
        "duration_minutes",
    }

    for index, meeting in enumerate(meetings):
        unexpected = (
            set(meeting.keys())
            - allowed_fields
        )

        if unexpected:
            raise RuntimeError(
                f"SAFETY STOP: Meeting {index} contains "
                f"unexpected fields: {sorted(unexpected)}"
            )

    # --------------------------------------------------------
    # CONNECT TO NEON
    # --------------------------------------------------------

    engine = create_engine(
        settings.database_url,
        pool_pre_ping=True,
    )

    # --------------------------------------------------------
    # ENSURE PORTFOLIO DB IS EMPTY
    # --------------------------------------------------------

    with engine.begin() as connection:

        existing_count = connection.execute(
            text(
                """
                SELECT COUNT(*)
                FROM meetings
                """
            )
        ).scalar_one()

        if existing_count != 0:
            raise RuntimeError(
                "SAFETY STOP: Portfolio meetings table "
                f"is not empty ({existing_count} rows)."
            )

        # ----------------------------------------------------
        # INSERT ONLY SAFE FIELDS
        # ----------------------------------------------------

        insert_query = text(
            """
            INSERT INTO meetings (
                id,
                source,
                topic,
                start_time,
                duration_minutes,
                metadata
            )
            VALUES (
                CAST(:id AS uuid),
                :source,
                :topic,
                CAST(:start_time AS timestamptz),
                :duration_minutes,
                CAST('{}' AS jsonb)
            )
            """
        )

        for meeting in meetings:

            connection.execute(
                insert_query,
                {
                    "id": meeting["id"],
                    "source": meeting["source"],
                    "topic": meeting["topic"],
                    "start_time": meeting["start_time"],
                    "duration_minutes": meeting[
                        "duration_minutes"
                    ],
                },
            )

    print(
        f"PORTFOLIO IMPORT COMPLETE: "
        f"{len(meetings)} meetings"
    )

    print(
        "Imported fields only: "
        "new id, source, topic, start_time, "
        "duration_minutes"
    )


if __name__ == "__main__":
    main()