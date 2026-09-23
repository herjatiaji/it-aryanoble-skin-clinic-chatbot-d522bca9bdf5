import logging
import uuid
from typing import Any
from sqlalchemy import text, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User, UserType, Role, UserRole, Access, RoleAccess
from app.models.category import Category
from app.models.config import AppConfig
from app.core.security import get_password_hash

logger = logging.getLogger(__name__)

DEFAULT_ADMIN_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")

DEFAULT_ACCESSES: list[tuple[str, str]] = [
    ("knowledge:read", "Permission to view and search knowledge base"),
    ("knowledge:write", "Permission to create and edit knowledge base entries"),
    ("knowledge:delete", "Permission to delete knowledge base entries"),
    ("users:read", "Permission to view user accounts"),
    ("users:write", "Permission to manage and create user accounts"),
    ("roles:read", "Permission to view roles and permissions"),
    ("roles:write", "Permission to edit roles and assign permissions"),
    ("roles:delete", "Permission to delete roles"),
    ("branches:read", "Permission to view clinic branches"),
    ("branches:write", "Permission to modify clinic branches"),
    ("categories:read", "Permission to view medical categories"),
    ("categories:write", "Permission to manage medical categories"),
    ("chats:read", "Permission to view chat history and sessions"),
    ("configuration:read", "Permission to view system configurations and logs"),
    ("configuration:write", "Permission to update system configurations and maintenance"),
    ("notifications:read", "Permission to view notifications"),
    ("notifications:write", "Permission to send notifications"),
    ("projects:read", "Permission to view knowledge projects"),
    ("projects:write", "Permission to manage knowledge projects"),
]

DEFAULT_ROLES: dict[str, list[str]] = {
    "ADMIN": [acc[0] for acc in DEFAULT_ACCESSES],
    "FUNCTIONAL": [
        "knowledge:read",
        "knowledge:write",
        "knowledge:delete",
        "categories:read",
        "projects:read",
        "projects:write",
    ],
}

DEFAULT_CATEGORIES: list[str] = [
    # --- 1. Test Case & Procedural Classifications ---
    "Active Acne Management",
    "Comedonal Acne Management",
    "Inflammatory Acne Management",
    "Acne Scar & Texture Improvement",
    "Acne-Prone Skin Care",
    "Sensitive-Skin Friendly Acne Care",
    "Oil & Sebum Control",
    "Pore Cleansing & Decongestion",
    "Large Pore Management",
    "Extraction-Based Treatment",
    "Exfoliation-Based Treatment",
    "Low/No-Downtime Treatment",
    "Non-Invasive Acne Treatment",
    "Procedure with Downtime",
    "Maintenance Care",
    "Maintenance / Routine Care",
    "Regeneration / Collagen Stimulation",
    "Skin Rejuvenation",
    "Brightening",
    "Pico Laser",
    "Dummy Fractional Laser Treatment",

    # --- 2. Clinical Acne & Blemishes ---
    "Acne Vulgaris",
    "Cystic Acne",
    "Nodular Acne",
    "Post-Inflammatory Hyperpigmentation",
    "Post-Inflammatory Erythema",
    "Malassezia Folliculitis",
    "Back Acne",
    "Body Acne",
    "Blackheads",
    "Whiteheads",

    # --- 3. Pigmentation & Tone ---
    "Skin Radiance",
    "Melasma",
    "Dark Spots",
    "Freckles",
    "Solar Lentigines",
    "Dull Skin",
    "Uneven Skin Tone",
    "Periorbital Dark Circles",
    "Axillary Hyperpigmentation",
    "Body Fold Hyperpigmentation",
    "Photodamage Repair",

    # --- 4. Anti-Aging & Skin Architecture ---
    "Fine Lines",
    "Wrinkles",
    "Skin Laxity",
    "Skin Firming",
    "Facial Volume Loss",
    "Forehead Rhytids",
    "Crow's Feet",
    "Nasolabial Folds",
    "Marionette Lines",
    "Neck Rejuvenation",
    "Decolletage Rejuvenation",
    "Photoaging Defense",

    # --- 5. Barrier, Sensitivity & Dermatology ---
    "Sensitive Skin",
    "Skin Barrier Repair",
    "Facial Erythema",
    "Facial Flushing",
    "Atopic Dermatitis",
    "Eczema",
    "Seborrheic Dermatitis",
    "Contact Dermatitis",
    "Rosacea",
    "Psoriasis",
    "Cutaneous Xerosis",
    "Dehydrated Skin",
    "Cutaneous Allergy",
    "Urticaria",
    "Keratosis Pilaris",

    # --- 6. Pores, Sebum & Texture ---
    "Enlarged Pores",
    "Excess Sebum",
    "Rough Skin Texture",
    "Milia",
    "Sebaceous Hyperplasia",

    # --- 7. Trichology & Scalp Dermatology ---
    "Hair Loss",
    "Hair Thinning",
    "Androgenetic Alopecia",
    "Alopecia Areata",
    "Dandruff",
    "Scalp Pruritus",
    "Scalp Seborrhea",
    "Hair Shaft Damage",
    "Scalp Detoxification",
    "Follicle Growth Stimulation",
    "Premature Graying",

    # --- 8. Body Care & Specialized Aesthetics ---
    "Stretch Marks",
    "Cellulite",
    "Body Xerosis",
    "Hyperhidrosis",
    "Hand Dermatitis",
    "Foot Dermatitis",
    "Hypertrophic Scars",
    "Keloids",
    "Dermatological Supplements",

    # --- 9. Demographics & Ecosystem Programs ---
    "Men's Skincare",
    "Adolescent Skincare",
    "Pediatric Skincare",
    "Pregnancy-Safe Skincare",
    "Geriatric Skincare",
    "ERHA Ultimate Acne Cure",
    "ERHA Ultimate Anti-Aging",
    "ERHA Ultimate Brightening",
    "ERHA Ultimate Hair Care",
    "Dermies Max Clear Program",
    "Dermies Max Bright Program",
    "Dermies Max Hair Program",

    # --- 10. OTC Formulations & Product Formats ---
    "Facial Cleanser",
    "Micellar Solution",
    "Cleansing Balm",
    "Cleansing Oil",
    "Facial Toner",
    "Clarifying Lotion",
    "Treatment Essence",
    "Face Serum",
    "Ampoule",
    "Skin Booster",
    "Daily Moisturizer",
    "Day Cream",
    "Night Cream",
    "Barrier Restorative Cream",
    "Hydrating Gel",
    "Facial Sunscreen",
    "Tinted Sunscreen",
    "Sunstick",
    "Acne Spot Gel",
    "Hydrocolloid Patch",
    "Chemical Exfoliant",
    "Physical Scrub",
    "Sheet Mask",
    "Hydrogel Mask",
    "Clay Mask",
    "Sleeping Mask",
    "Eye Cream",
    "Eye Serum",
    "Lip Balm",
    "Lip Serum",
    "Calming Face Mist",
    "Body Wash",
    "Body Lotion",
    "Body Serum",
    "Body Scrub",
    "Hair Shampoo",
    "Hair Conditioner",
    "Hair Mask",
    "Hair Tonic",
    "Scalp Serum",
    "Clinical Deodorant",

    # --- 11. Clinical Treatments & Modalities ---
    "Medical Facial",
    "Comedone Extraction",
    "Chemical Peeling",
    "Glow Peel",
    "Microdermabrasion",
    "Hydrafacial",
    "Fractional CO2 Laser",
    "Intense Pulsed Light",
    "Microneedling",
    "RF Microneedling",
    "Platelet-Rich Plasma",
    "Polynucleotide Booster",
    "Salmon DNA",
    "Botulinum Toxin",
    "Dermal Fillers",
    "Thread Lift",
    "HIFU Lifting",
    "Radiofrequency Tightening",
    "Laser Hair Removal",
    "Electrocautery",
    "Intralesional Steroid Injection",
    "LED Phototherapy",
    "Intravenous Micronutrient Infusion",
]

DEFAULT_APP_CONFIGS: dict[str, str] = {
    "GLOBAL_TOKEN_LIMIT_ACTIVE": "false",
    "GLOBAL_BRANCH_LIMIT_ACTIVE": "false",
    "GLOBAL_THRESHOLD_ACTIVE": "false",
    "GLOBAL_SPKK_LIMIT_ACTIVE": "false",
    "GLOBAL_GP_LIMIT_ACTIVE": "false",
    "GLOBAL_TOKEN_THRESHOLD": "1000000",
    "GLOBAL_TOKEN_LIMIT": "3000000",
    "TOKEN_LIMIT_SPKK": "500000",
    "TOKEN_LIMIT_GP": "250000",
    "TIME_LIMIT_PER_SESSION": "30",
    "LLM_ACTIVE_PROVIDER": "openai",
    "LLM_ACTIVE_MODEL_NAME": "gpt-5.4-mini",
}

ALL_TABLES: list[str] = [
    "chat_message",
    "chat_session",
    "knowledge_chunk",
    "knowledge_category",
    "knowledge",
    "projects",
    "user_category_exclusion",
    "user_branch",
    "user_token_usage",
    "ingestion_token_usage",
    "user_access",
    "user_role",
    "role_access",
    "users",
    "role",
    "access",
    "branches",
    "categories",
    "app_config",
]


async def reset_database(session: AsyncSession) -> dict[str, Any]:
    """
    Safely truncates all application database tables with CASCADE in PostgreSQL.
    Dynamically discovers all tables in the public schema (preserving alembic_version).
    """
    logger.warning("Starting database table truncation...")

    # Ensure extensions exist
    await session.execute(text('CREATE EXTENSION IF NOT EXISTS "uuid-ossp";'))
    await session.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))

    # Dynamically find all public tables excluding migration metadata
    res = await session.execute(
        text("SELECT tablename FROM pg_tables WHERE schemaname = 'public' AND tablename != 'alembic_version';")
    )
    db_tables = [row[0] for row in res.fetchall()]
    target_tables = db_tables if db_tables else ALL_TABLES

    if target_tables:
        quoted_tables = [f'"{tbl}"' for tbl in target_tables]
        tables_joined = ", ".join(quoted_tables)
        truncate_stmt = text(f"TRUNCATE TABLE {tables_joined} RESTART IDENTITY CASCADE;")
        await session.execute(truncate_stmt)
        await session.commit()

    logger.info(f"Successfully truncated tables: {target_tables}")
    return {
        "truncated_tables": target_tables,
        "count": len(target_tables),
    }


async def seed_database(
    session: AsyncSession,
    admin_email: str = "admin@mail.com",
    admin_password: str = "Erhadermies@123",
) -> dict[str, Any]:
    """
    Idempotently seeds accesses, roles, default admin user, medical categories, and base app config.
    """
    logger.info("Starting database seeding...")
    summary: dict[str, Any] = {
        "accesses_seeded": 0,
        "roles_seeded": 0,
        "admin_created": False,
        "categories_seeded": 0,
        "configs_seeded": 0,
    }

    # 1. Seed Accesses
    for acc_name, acc_desc in DEFAULT_ACCESSES:
        res = await session.execute(select(Access).where(Access.name == acc_name))
        existing_acc = res.scalar_one_or_none()
        if not existing_acc:
            session.add(Access(name=acc_name, description=acc_desc))
            summary["accesses_seeded"] += 1
        elif not existing_acc.description and acc_desc:
            existing_acc.description = acc_desc
    await session.commit()

    # 2. Seed Roles and map Accesses
    for role_name, role_accesses in DEFAULT_ROLES.items():
        res_role = await session.execute(select(Role).where(Role.name == role_name))
        role = res_role.scalar_one_or_none()
        if not role:
            role = Role(name=role_name)
            session.add(role)
            await session.flush()
            summary["roles_seeded"] += 1

        for acc_name in role_accesses:
            res_acc = await session.execute(select(Access).where(Access.name == acc_name))
            acc = res_acc.scalar_one_or_none()
            if acc:
                res_ra = await session.execute(
                    select(RoleAccess).where(
                        RoleAccess.role_id == role.id,
                        RoleAccess.access_id == acc.id,
                    )
                )
                if not res_ra.scalar_one_or_none():
                    session.add(RoleAccess(role_id=role.id, access_id=acc.id))
    await session.commit()

    # 3. Seed Default Admin User
    res_admin = await session.execute(select(User).where(User.email == admin_email))
    admin_user = res_admin.scalar_one_or_none()
    if not admin_user:
        admin_user = User(
            id=DEFAULT_ADMIN_USER_ID,
            email=admin_email,
            name="System Administrator",
            type=UserType.STAFF,
            password_hash=get_password_hash(admin_password),
            ecosystem="ERHA",
        )
        session.add(admin_user)
        await session.commit()

        # Assign ADMIN role to user
        res_role_admin = await session.execute(select(Role).where(Role.name == "ADMIN"))
        admin_role = res_role_admin.scalar_one_or_none()
        if admin_role:
            session.add(UserRole(user_id=admin_user.id, role_id=admin_role.id))
            await session.commit()
        summary["admin_created"] = True
        logger.info(f"Created default admin account: {admin_email}")

    # 4. Seed Medical Categories
    for cat_name in DEFAULT_CATEGORIES:
        res_cat = await session.execute(select(Category).where(Category.name == cat_name))
        if not res_cat.scalar_one_or_none():
            session.add(Category(name=cat_name))
            summary["categories_seeded"] += 1
    await session.commit()

    # 5. Seed Default AppConfig
    for cfg_key, cfg_val in DEFAULT_APP_CONFIGS.items():
        res_cfg = await session.execute(select(AppConfig).where(AppConfig.key == cfg_key))
        if not res_cfg.scalar_one_or_none():
            session.add(AppConfig(key=cfg_key, value=cfg_val))
            summary["configs_seeded"] += 1
    await session.commit()

    logger.info(f"Database seeding completed: {summary}")
    return summary


async def reset_and_reseed_database(
    session: AsyncSession,
    admin_email: str = "admin@mail.com",
    admin_password: str = "Erhadermies@123",
) -> dict[str, Any]:
    """
    Executes database table reset followed immediately by re-seeding default data.
    """
    reset_info = await reset_database(session)
    seed_info = await seed_database(session, admin_email=admin_email, admin_password=admin_password)
    return {
        "reset": reset_info,
        "seed": seed_info,
    }
