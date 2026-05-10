# Import the Flask app and database setup
from app import app
from extensions import db
from models import User

# Create an admin user in the database when this script runs
with app.app_context():
    admin = User(
        username="admin",  # Username to log in with
        email="adminmail@gmail.com",
        first_name="Admin",
        last_name="Person",
        role="admin"  # Mark as admin so they can access admin panel
    )
    admin.set_password("password")  # Encrypt and set password
    db.session.add(admin)  # Add to database
    db.session.commit()  # Save to database
    print("Admin created!")  # Print confirmation message