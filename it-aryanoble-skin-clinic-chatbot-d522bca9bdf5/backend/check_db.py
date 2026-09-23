import asyncio
from app.core.database import AsyncSessionLocal
from sqlalchemy import text

async def main():
    async with AsyncSessionLocal() as session:
        # Restore active status for approved documents in knowledge table
        await session.execute(text("UPDATE knowledge SET deleted_at = NULL WHERE status = 'APPROVED'"))
        await session.commit()
        res = await session.execute(text("SELECT id, status, deleted_at, title, file_name FROM knowledge WHERE status = 'APPROVED' AND deleted_at IS NULL"))
        for row in res.fetchall():
            print("RESTORED APPROVED KNOWLEDGE ROW:", row)

if __name__ == "__main__":
    asyncio.run(main())
