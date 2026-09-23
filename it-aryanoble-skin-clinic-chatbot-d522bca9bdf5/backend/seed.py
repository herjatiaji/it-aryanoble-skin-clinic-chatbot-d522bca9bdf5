import asyncio
import sys
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.services.db_seeder import seed_database, reset_and_reseed_database
import app.models  # Ensure all models are loaded


async def main():
    print("Connecting to database...")
    engine = create_async_engine(settings.DATABASE_URL, echo=False, pool_pre_ping=True)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    reset_mode = "--reset" in sys.argv

    async with async_session() as session:
        if reset_mode:
            print("Resetting and reseeding database tables...")
            result = await reset_and_reseed_database(session)
            print(f"Reset and reseed complete: {result}")
        else:
            print("Seeding database (idempotent)...")
            result = await seed_database(session)
            print(f"Seeding complete: {result}")

    await engine.dispose()
    print("Done!")


if __name__ == "__main__":
    asyncio.run(main())
