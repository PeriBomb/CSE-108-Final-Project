from flask import Flask, render_template, redirect, url_for, request, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_required, current_user, login_user, logout_user
from flask_admin import Admin
from flask_admin.contrib.sqla import ModelView
from wtforms import PasswordField
from extensions import db
from models import User, Class, ClassEnrollment, Question, Collectible, StudentCollectible, TradeRequest

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///data.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SECRET_KEY"] = "dev-secret-key"

db.init_app(app)

login_manager = LoginManager(app)
login_manager.login_view = "login"

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

class UserAdminView(ModelView):
    column_exclude_list = ["password"]
    form_excluded_columns = ["password"]
    form_columns = ["first_name", "last_name", "username", "password_input", "email", "role"]
    form_extra_fields = {
        "password_input": PasswordField("Password")
    }
    def on_model_change(self, form, model, is_created):
        if form.password_input.data:
            model.set_password(form.password_input.data)
    def is_accessible(self):
        return current_user.is_authenticated and current_user.role == "admin"
    def inaccessible_callback(self, name, **kwargs):
        return redirect(url_for("login"))



admin = Admin(app, name="ClassPack Admin View")
admin.add_view(UserAdminView(User, db.session))
admin.add_view(ModelView(Class, db.session))
admin.add_view(ModelView(ClassEnrollment, db.session))
admin.add_view(ModelView(Question, db.session))
admin.add_view(ModelView(Collectible, db.session))
admin.add_view(ModelView(StudentCollectible, db.session))
admin.add_view(ModelView(TradeRequest, db.session))



@app.route("/")
def index():
    return redirect(url_for("login"))

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        
        user = User.query.filter_by(username=username).first()
        
        if user and user.check_password(password):
            login_user(user)
            if user.role == "admin":
                return redirect("/admin")
            elif user.role == "teacher":
                return redirect(url_for("teacher_dashboard"))
            else:
                return redirect(url_for("student_dashboard"))
        else:
            flash("Invalid username or password")

    return render_template("login.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username   = request.form.get("username", "").strip()
        password   = request.form.get("password", "")
        first_name = request.form.get("first_name", "").strip()
        last_name  = request.form.get("last_name", "").strip()
        role       = request.form.get("role", "student")
        join_code  = request.form.get("join_code", "").strip().upper()

        if User.query.filter_by(username=username).first():
            flash("Username already taken.")
            return render_template("register.html")

        user = User(
            username=username,
            first_name=first_name,
            last_name=last_name,
            role=role,
            points=0
        )
        user.set_password(password)
        db.session.add(user)
        db.session.flush()

        if role == "student":
            cls = Class.query.filter_by(join_code=join_code).first()
            if not cls:
                flash("Invalid class join code.")
                db.session.rollback()
                return render_template("register.html")
            enrollment = ClassEnrollment(student_id=user.id, class_id=cls.id)
            db.session.add(enrollment)
        elif role == "teacher":
            class_name = request.form.get("class_name", "").strip()
            if class_name:
                new_class = Class(
                    name=class_name,
                    join_code=Class.generate_join_code(),
                    teacher_id=user.id
                )
                db.session.add(new_class)
#
        print("role:", role)
        print("class_name:", request.form.get("class_name"))

        db.session.commit()
        flash("Account created! Please log in.")
        return redirect(url_for("login"))

    return render_template("register.html")

@app.route("/logout")
def logout():
    logout_user()
    return redirect(url_for("login"))

if __name__ == "__main__":
    app.run(debug=True)