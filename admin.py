from app import app
from extensions import db
from models import User

with app.app_context():
    admin = User(
        username="admin",
        email="adminmail@gmail.com",
        first_name="Admin",
        last_name="Person",
        role="admin"
    )
    admin.set_password("password")
    db.session.add(admin)
    db.session.commit()
    print("Admin created!")