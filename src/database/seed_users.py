from sqlalchemy.orm import Session

from src.authentication.roles_type import RoleType
from src.database.repositories.user_repository import UserRepository
from src.utils.hasher import get_password_hash


def seed_default_users(db: Session):
    users = UserRepository.list_users(db)
    if len(users) > 0:
        print("Users already exist in the database, skipping seeding.")
        return

    try:
        default_users = [
            {"name": "admin", "password": "admin123", "role": RoleType.ADMIN},
            {"name": "operator", "password": "operator123", "role": RoleType.OPERATOR},
            {"name": "user", "password": "user123", "role": RoleType.UNAOTHORIZED},
        ]

        for user in default_users:
            existing_user = UserRepository.get_user_by_name(db, user["name"])
            if not existing_user:
                hashed_password = get_password_hash(user["password"])
                UserRepository.create_user(
                    db,
                    name=user["name"],
                    hashed_password=hashed_password,
                    role=user["role"]
                )
                print(f"Created user: {user['name']} with role: {user['role']}")
            else:
                print(f"User {user['name']} already exists, skipping...")

        print("Default users seeded successfully!")
    except Exception as e:
        print(f"Error seeding users: {str(e)}")
    finally:
        db.close()
