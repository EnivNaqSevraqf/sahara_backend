from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from main import Base, User, Role, RoleType
from passlib.context import CryptContext
import warnings

# Ignore the bcrypt warning about __about__
warnings.filterwarnings("ignore", category=UserWarning)

# Database configuration
DATABASE_URL = "postgresql://avnadmin:AVNS_DkrVvzHCnOiMVJwagav@pg-8b6fabf-sahara-team-8.f.aivencloud.com:17950/defaultdb"
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def create_dummy_users():
    db = SessionLocal()
    try:
        # First, ensure roles exist
        roles = {}
        for role_type in RoleType:
            role = db.query(Role).filter(Role.role == role_type).first()
            if not role:
                role = Role(role=role_type)
                db.add(role)
                db.commit()
            roles[role_type] = role

        # Create dummy users
        dummy_users = [
            # Professors
            {
                "name": "Professor Smith",
                "email": "smith@university.edu",
                "username": "prof_smith",
                "password": "prof123",
                "role": RoleType.PROF,
            },
            {
                "name": "Professor Johnson",
                "email": "johnson@university.edu",
                "username": "prof_johnson",
                "password": "prof123",
                "role": RoleType.PROF,
            },
            # TAs
            {
                "name": "TA Alice",
                "email": "alice@university.edu",
                "username": "ta_alice",
                "password": "ta123",
                "role": RoleType.TA,
            },
            {
                "name": "TA Bob",
                "email": "bob@university.edu",
                "username": "ta_bob",
                "password": "ta123",
                "role": RoleType.TA,
            },
            # Students
            {
                "name": "Student Carol",
                "email": "carol@university.edu",
                "username": "student_carol",
                "password": "student123",
                "role": RoleType.STUDENT,
            },
            {
                "name": "Student Dave",
                "email": "dave@university.edu",
                "username": "student_dave",
                "password": "student123",
                "role": RoleType.STUDENT,
            },
            {
                "name": "Student Eve",
                "email": "eve@university.edu",
                "username": "student_eve",
                "password": "student123",
                "role": RoleType.STUDENT,
            },
            {
                "name": "Student Frank",
                "email": "frank@university.edu",
                "username": "student_frank",
                "password": "student123",
                "role": RoleType.STUDENT,
            }
        ]

        # Add users to database
        for user_data in dummy_users:
            try:
                # Check if user already exists
                existing_user = db.query(User).filter(
                    (User.username == user_data["username"]) | 
                    (User.email == user_data["email"])
                ).first()
                
                if not existing_user:
                    new_user = User(
                        name=user_data["name"],
                        email=user_data["email"],
                        username=user_data["username"],
                        hashed_password=pwd_context.hash(user_data["password"]),
                        role_id=roles[user_data["role"]].id,
                        team_id=None  # Setting team_id as None for now
                    )
                    db.add(new_user)
                    db.commit()  # Commit each user individually
                    print(f"Added user: {user_data['name']} ({user_data['username']})")
                else:
                    print(f"User already exists: {user_data['username']} ({user_data['email']})")
            
            except Exception as e:
                print(f"Error adding user {user_data['username']}: {str(e)}")
                db.rollback()  # Rollback only the current user on error
                continue  # Continue with next user

        print("\nDummy users creation completed!")

    except Exception as e:
        print(f"Error in create_dummy_users: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    create_dummy_users()