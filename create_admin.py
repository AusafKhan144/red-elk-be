import asyncio
import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.core.database import async_session_maker
from app.models.user import User, UserTierEnum, UserRoleEnum
from app.core.security import get_password_hash

async def create_admin_user():
    async with async_session_maker() as session:
        # Check if admin already exists
        from sqlalchemy import select
        result = await session.execute(
            select(User).where(User.email == "admin@aiassessment.com")
        )
        existing_admin = result.scalar_one_or_none()
        
        if existing_admin:
            print(f"⚠️ Admin user already exists: {existing_admin.email}")
            print(f"   Role: {existing_admin.role.value}")
            print(f"   Tier: {existing_admin.tier.value}")
            return existing_admin
        
        # Create admin user
        admin_user = User(
            email="admin@aiassessment.com",
            hashed_password=get_password_hash("admin123"),
            first_name="System",
            last_name="Administrator",
            company="AI Assessment Platform",
            job_title="System Administrator",
            tier=UserTierEnum.PREMIUM,
            role=UserRoleEnum.ADMIN,
            is_active=True
        )
        
        session.add(admin_user)
        await session.commit()
        await session.refresh(admin_user)
        
        print("✅ Admin user created successfully!")
        print(f"📧 Email: {admin_user.email}")
        print(f"🔑 Password: admin123")
        print(f"👤 Role: {admin_user.role.value}")
        print(f"⭐ Tier: {admin_user.tier.value}")
        print(f"🆔 ID: {admin_user.id}")
        
        return admin_user

if __name__ == "__main__":
    asyncio.run(create_admin_user())