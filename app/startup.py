from app.database import create_tables
import app.beer_tracker


def startup() -> None:
    # this function is called before the first request
    create_tables()
    app.beer_tracker.create()
