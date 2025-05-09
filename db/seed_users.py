from db.models import User, init_db, SessionLocal
from datetime import datetime, timezone

def seed_users():
    init_db()  # ensure tables exist
    db = SessionLocal()

    users = [
        {"username": "alice", "password": "pass1", "role": "scholar"},
        {"username": "bob", "password": "pass2", "role": "peer"},
        {"username": "carol", "password": "pass3", "role": "scholar"},
        {"username": "dave", "password": "pass4", "role": "peer"},
    ]

    for u in users:
        if not db.query(User).filter_by(username=u["username"]).first():
            db.add(User(
                username=u["username"],
                password_hash=u["password"],
                role=u["role"],
                created_at=datetime.now(timezone.utc),
            ))

    db.commit()
    db.close()
    print("Users seeded.")

if __name__ == "__main__":
    seed_users()
