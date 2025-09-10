import os
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from dotenv import load_dotenv


def create_database():
    # Configuration
    DB_NAME = os.getenv("DATABASE_NAME")
    DB_USER = os.getenv("DATABASE_USER")
    DB_PASSWORD = os.getenv("DATABASE_PASSWORD")
    DB_HOST = os.getenv("DATABASE_HOST")
    DB_PORT = os.getenv("DATABASE_PORT")

    # Connect to default database
    connection = psycopg2.connect(
        dbname="postgres",
        user=DB_USER,
        password=DB_PASSWORD,
        host=DB_HOST,
        port=DB_PORT,
    )
    connection.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    cursor = connection.cursor()

    # Create database
    try:
        cursor.execute(f"CREATE DATABASE {DB_NAME};")
        print(f"Database '{DB_NAME}' created successfully.")
    except psycopg2.errors.DuplicateDatabase:
        print(f"Database '{DB_NAME}' already exists.")

    cursor.close()
    connection.close()


def main():
    # Load .env file
    load_dotenv()

    print("Creating database...")
    create_database()


if __name__ == "__main__":
    main()
