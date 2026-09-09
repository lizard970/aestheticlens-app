import os

from .repositories import PostgreSQLRepository


def main() -> None:
    database_url = os.getenv("AESTHETICLENS_DATABASE_URL", "").strip()
    PostgreSQLRepository(database_url).migrate()
    print("PostgreSQL schema is ready.")


if __name__ == "__main__":
    main()
