"""
Database initialization and demonstration data seeding.
"""
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models.base import Base
from models.user import User
from models.resource import Resource
from models.schedule import Schedule

DB_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'database.db')
DATABASE_URL = f"sqlite:///{DB_FILE}"

engine = create_engine(DATABASE_URL, echo=False, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db(reseed: bool = False):
    """Create all tables and seed required demonstration data."""
    if reseed and os.path.exists(DB_FILE):
        try:
            os.remove(DB_FILE)
        except Exception:
            pass

    Base.metadata.create_all(bind=engine)
    seed_demo_data()


def seed_demo_data():
    """Seed the exact demonstration data mandated by the assessment requirements."""
    session = SessionLocal()
    try:
        # Check if users already exist
        if session.query(User).count() == 0:
            users = [
                User(id="user1", username="user1", name="Alice", role="USER", status="ACTIVE"),
                User(id="user2", username="user2", name="Bob", role="USER", status="ACTIVE"),
                User(id="admin", username="admin", name="Administrator", role="ADMINISTRATOR", status="ACTIVE")
            ]
            session.add_all(users)
            session.commit()

        # Check if resources already exist
        if session.query(Resource).count() == 0:
            demo_resources = [
                {"id": "R101", "name": "Weathering With You", "rate": 499.0, "availability": 10, "status": "ACTIVE",
                 "schedule": {"date": "2026-10-10", "time": "06:30 PM", "category": "Evening Show - Screen 1"}},
                {"id": "R102", "name": "Spider-Man: Brand New Day", "rate": 799.0, "availability": 5, "status": "ACTIVE",
                 "schedule": {"date": "2026-10-10", "time": "09:30 PM", "category": "Night Show - Screen 2"}},
                {"id": "R103", "name": "Naruto", "rate": 199.0, "availability": 20, "status": "ACTIVE",
                 "schedule": {"date": "2026-10-11", "time": "02:00 PM", "category": "Matinee Show - Screen 1"}},
                {"id": "R104", "name": "One Piece", "rate": 1299.0, "availability": 0, "status": "ACTIVE",
                 "schedule": {"date": "2026-10-11", "time": "06:00 PM", "category": "Premium Evening - IMAX 3D"}},
                {"id": "R105", "name": "BLEACH: Thousand-Year Blood War - The Calamity", "rate": 1000.0, "availability": 3, "status": "ACTIVE",
                 "schedule": {"date": "2026-10-11", "time": "09:00 PM", "category": "Special Screening - Screen 3"}},
            ]

            for item in demo_resources:
                res = Resource(
                    id=item["id"],
                    name=item["name"],
                    rate=item["rate"],
                    availability=item["availability"],
                    status=item["status"]
                )
                session.add(res)
                session.flush()

                sch = Schedule(
                    resource_id=res.id,
                    date=item["schedule"]["date"],
                    time=item["schedule"]["time"],
                    category=item["schedule"]["category"]
                )
                session.add(sch)

            session.commit()
    except Exception as e:
        session.rollback()
        raise e
    finally:
        session.close()


if __name__ == '__main__':
    print("Initializing database and seeding demo data...")
    init_db(reseed=True)
    print("Database initialized successfully at:", DB_FILE)
