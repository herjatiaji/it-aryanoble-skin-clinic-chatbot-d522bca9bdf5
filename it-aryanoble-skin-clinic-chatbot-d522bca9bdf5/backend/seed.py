import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.models.base import Base
from app.models.user import User, UserType, Role, UserRole, Access, RoleAccess, UserAccess
from app.core.security import get_password_hash
import app.models # Ensure all models are loaded

async def init_db():
    print("Connecting to database...")
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    
    print("Creating tables...")
    async with engine.begin() as conn:
        # Create extension for pgvector and uuid
        await conn.execute(org_sql_text := __import__('sqlalchemy').text('CREATE EXTENSION IF NOT EXISTS "uuid-ossp";'))
        await conn.execute(org_sql_text := __import__('sqlalchemy').text('CREATE EXTENSION IF NOT EXISTS vector;'))
        
        # Tables are created via Alembic migrations now
        
    print("Seeding default user and roles...")
    
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as session:
        # Seed Accesses
        access_list = [
            "knowledge:read", "knowledge:write", "knowledge:delete",
            "users:read", "users:write", 
            "branches:read", "branches:write", 
            "categories:read", "categories:write", 
            "chats:read",
            "configuration:read", "configuration:write"
        ]
        for acc_name in access_list:
            result = await session.execute(__import__('sqlalchemy').select(Access).where(Access.name == acc_name))
            if not result.scalar_one_or_none():
                session.add(Access(name=acc_name))
        await session.commit()

        # Seed Roles and map Accesses
        roles_config = {
            "ADMIN": access_list,
            "FUNCTIONAL": ["knowledge:read", "knowledge:write"]
        }
        
        for role_name, role_accesses in roles_config.items():
            result = await session.execute(__import__('sqlalchemy').select(Role).where(Role.name == role_name))
            role = result.scalar_one_or_none()
            if not role:
                role = Role(name=role_name)
                session.add(role)
                await session.flush()
                
            # Map accesses to role
            for acc_name in role_accesses:
                result_acc = await session.execute(__import__('sqlalchemy').select(Access).where(Access.name == acc_name))
                acc = result_acc.scalar_one()
                
                result_ra = await session.execute(__import__('sqlalchemy').select(RoleAccess).where(RoleAccess.role_id == role.id, RoleAccess.access_id == acc.id))
                if not result_ra.scalar_one_or_none():
                    session.add(RoleAccess(role_id=role.id, access_id=acc.id))
                    
        await session.commit()

        # Check if admin already exists
        result = await session.execute(__import__('sqlalchemy').select(User).where(User.email == 'admin@mail.com'))
        admin_user = result.scalar_one_or_none()
        
        if not admin_user:
            admin_user = User(
                email="admin@mail.com",
                name="System Administrator",
                type=UserType.STAFF,
                password_hash=get_password_hash("admin123")
            )
            session.add(admin_user)
            await session.commit()
            
            # Assign ADMIN role
            result = await session.execute(__import__('sqlalchemy').select(Role).where(Role.name == "ADMIN"))
            admin_role = result.scalar_one_or_none()
            if admin_role:
                session.add(UserRole(user_id=admin_user.id, role_id=admin_role.id))
                await session.commit()
                
            print("Successfully seeded admin user: admin@mail.com / admin123")
        else:
            print("Admin user already exists.")
            
        # Seed Functional user
        result = await session.execute(__import__('sqlalchemy').select(User).where(User.email == 'dept@mail.com'))
        func_user = result.scalar_one_or_none()
        if not func_user:
            func_user = User(
                email="dept@mail.com",
                name="Functional 1",
                type=UserType.STAFF,
                password_hash=get_password_hash("dept123")
            )
            session.add(func_user)
            await session.commit()
            
            result = await session.execute(__import__('sqlalchemy').select(Role).where(Role.name == "FUNCTIONAL"))
            func_role = result.scalar_one_or_none()
            if func_role:
                session.add(UserRole(user_id=func_user.id, role_id=func_role.id))
                await session.commit()
            print("Successfully seeded functional user: dept@mail.com / dept123")
            
        # Seed Functional user with Write Access via UserAccess
        result = await session.execute(__import__('sqlalchemy').select(User).where(User.email == 'dept2@mail.com'))
        func_user2 = result.scalar_one_or_none()
        if not func_user2:
            func_user2 = User(
                email="dept2@mail.com",
                name="Functional 2",
                type=UserType.STAFF,
                password_hash=get_password_hash("dept123")
            )
            session.add(func_user2)
            await session.commit()
            
            result = await session.execute(__import__('sqlalchemy').select(Role).where(Role.name == "FUNCTIONAL"))
            func_role = result.scalar_one_or_none()
            if func_role:
                session.add(UserRole(user_id=func_user2.id, role_id=func_role.id))
                await session.commit()
                
            # Assign UserAccess directly for DELETE
            result_acc = await session.execute(__import__('sqlalchemy').select(Access).where(Access.name == "knowledge:delete"))
            delete_acc = result_acc.scalar_one_or_none()
            if delete_acc:
                session.add(UserAccess(user_id=func_user2.id, access_id=delete_acc.id))
                await session.commit()
            
            print("Successfully seeded functional user with delete access: dept2@mail.com / dept123")


    await engine.dispose()
    print("Done!")

if __name__ == "__main__":
    asyncio.run(init_db())
