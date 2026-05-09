from flask import Flask, render_template, redirect, url_for, request, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_required, current_user, login_user, logout_user
from flask_admin import Admin
from flask_admin.contrib.sqla import ModelView
from wtforms import PasswordField
from extensions import db
from models import User, Class, ClassEnrollment, Question, Collectible, StudentCollectible, TradeRequest, RARITY_LEVELS, RARITY_WEIGHTS
import random

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
    form_columns = ["first_name", "last_name", "username", "password_input", "email", "role", "points"]
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

@app.route("/student/dashboard")
@login_required
def student_dashboard():
    if current_user.role != "student":
        return redirect(url_for("login"))
    return render_template("student_dashboard.html")

@app.route("/student/shop/buy", methods=["POST"])
@login_required
def student_buy_card():
    if current_user.role != "student":
        return redirect(url_for("login"))

    if current_user.points < 50:
        flash("Not enough points.")
        return redirect(url_for("student_shop"))

    enrollment = ClassEnrollment.query.filter_by(
        student_id=current_user.id, status="active"
    ).first()
    if not enrollment:
        flash("You are not enrolled in a class.")
        return redirect(url_for("student_shop"))

    pool = Collectible.query.filter_by(class_id=enrollment.class_id).all()
    if not pool:
        flash("No collectibles available yet.")
        return redirect(url_for("student_shop"))

    weights = []
    for c in pool:
        idx = RARITY_LEVELS.index(c.rarity) if c.rarity in RARITY_LEVELS else 0
        weights.append(RARITY_WEIGHTS[idx])

    chosen = random.choices(pool, weights=weights, k=1)[0]
    sc = StudentCollectible(student_id=current_user.id, collectible_id=chosen.id)
    current_user.points -= 50
    db.session.add(sc)
    db.session.commit()

    flash(f"You got: {chosen.emoji} {chosen.name} ({chosen.rarity})")
    return redirect(url_for("student_shop"))


@app.route("/student/shop")
@login_required
def student_shop():
    if current_user.role != "student":
        return redirect(url_for("login"))
    return render_template("student_shop.html", points=current_user.points)

@app.route("/student/study")
@login_required
def student_study():
    if current_user.role != "student":
        return redirect(url_for("login"))

    enrollment = ClassEnrollment.query.filter_by(
        student_id=current_user.id, status="active"
    ).first()
    if not enrollment:
        flash("You are not enrolled in a class.")
        return redirect(url_for("student_dashboard"))

    questions = Question.query.filter_by(
        class_id=enrollment.class_id, is_active=True
    ).all()
    if not questions:
        flash("No questions available yet.")
        return redirect(url_for("student_dashboard"))

    question = random.choice(questions)
    return render_template("student_study.html", question=question)


@app.route("/student/study/answer", methods=["POST"])
@login_required
def student_study_answer():
    question_id = request.form.get("question_id", type=int)
    chosen = request.form.get("answer", "").lower()

    question = Question.query.get_or_404(question_id)
    correct = chosen.lower() == question.correct_option.lower()
    if correct:
        current_user.points += question.point_value
        db.session.commit()

    return render_template("student_study.html", question=question, chosen=chosen, correct=correct, answered=True)

@app.route("/teacher/dashboard")
@login_required
def teacher_dashboard():
    if current_user.role != "teacher":
        return redirect(url_for("login"))
    # For each class, get the classes for the active user
    classes = Class.query.filter_by(teacher_id=current_user.id).all()
    class_data = []
    #for each class, get the data for that class and pass to the template as a list of dicts with keys "name", "join_code", and "students"
    for cls in classes:
        students = [enrollment.student for enrollment in cls.enrollments if enrollment.status == "active"]
        class_data.append({
            "name": cls.name,
            "join_code": cls.join_code,
            "students": students
        })
    return render_template("teacher_dashboard.html", Classes=class_data)

@app.route("/teacher/question/add", methods=["GET", "POST"])
@login_required
def teacher_add_question():
    if current_user.role != "teacher":
        return redirect(url_for("login"))

    classes = Class.query.filter_by(teacher_id=current_user.id).all()

    if request.method == "POST":
        q = Question(
            class_id=classes[0].id,
            text=request.form.get("text", "").strip(),
            option_a=request.form.get("option_a", "").strip(),
            option_b=request.form.get("option_b", "").strip(),
            option_c=request.form.get("option_c", "").strip(),
            option_d=request.form.get("option_d", "").strip(),
            correct_option=request.form.get("correct_option", "a").lower(),
            point_value=int(request.form.get("point_value", 10)),
            is_active=True
        )
        db.session.add(q)
        db.session.commit()
        flash("Question created!")
        return redirect(url_for("teacher_add_question"))

    return render_template("teacher_add_question.html", classes=classes)

@app.route("/teacher/questions")
@login_required
def teacher_questions():
    if current_user.role != "teacher":
        return redirect(url_for("login"))
    classes = Class.query.filter_by(teacher_id=current_user.id).all()
    if not classes:
        flash("You have no classes yet.")
        return redirect(url_for("teacher_dashboard"))
    questions = Question.query.filter_by(class_id=classes[0].id).all()
    return render_template("teacher_questions.html", questions=questions)


@app.route("/teacher/question/<int:question_id>/toggle", methods=["POST"])
@login_required
def teacher_toggle_question(question_id):
    if current_user.role != "teacher":
        return redirect(url_for("login"))
    q = Question.query.get_or_404(question_id)
    q.is_active = not q.is_active
    db.session.commit()
    flash(f"Question marked as {'active' if q.is_active else 'inactive'}.")
    return redirect(url_for("teacher_questions"))


@app.route("/teacher/question/<int:question_id>/delete", methods=["POST"])
@login_required
def teacher_delete_question(question_id):
    if current_user.role != "teacher":
        return redirect(url_for("login"))
    q = Question.query.get_or_404(question_id)
    db.session.delete(q)
    db.session.commit()
    flash("Question deleted.")
    return redirect(url_for("teacher_questions"))

@app.route("/logout")
def logout():
    logout_user()
    return redirect(url_for("login"))

with app.app_context():
    db.create_all()
if __name__ == "__main__":
    app.run(debug=True)