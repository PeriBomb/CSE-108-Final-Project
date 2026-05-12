# Import libraries for Flask web framework, database management, user authentication, and admin tools
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from flask import Flask, render_template, redirect, url_for, request, flash
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_required, current_user, login_user, logout_user
from flask_admin import Admin, AdminIndexView
from flask_admin.contrib.sqla import ModelView
from flask_socketio import SocketIO, join_room, emit, leave_room
from flask import jsonify
from wtforms import PasswordField
from extensions import db
from models import User, Class, ClassEnrollment, Question, Collectible, StudentCollectible, TradeRequest, RARITY_LEVELS, RARITY_WEIGHTS
import random
import os
from werkzeug.utils import secure_filename

# Create Flask app and configure database settings
app = Flask(__name__)
UPLOAD_FOLDER = "static/uploads/collectibles"
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif"}
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///data.db"  # Use SQLite database file
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SECRET_KEY"] = "dev-secret-key"  # Secret key for sessions\
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok =True)
socketio = SocketIO(app)  # Initialize SocketIO for real-time features (not used yet)
# Initialize the database with the app

db.init_app(app)
def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS
# Set up user login system - manages user sessions and authentication
login_manager = LoginManager(app)
login_manager.login_view = "login"  # Redirect to login page if user not authenticated

# Load user from database when needed for login/session management
@app.before_request
def before_request():
    db.session.execute(text("PRAGMA foreign_keys=ON"))

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

class AdminView(AdminIndexView):
    pass

# Admin panel configuration - controls what admin can see and edit for users
class UserAdminView(ModelView):
    column_exclude_list = ["password"]  # Hide password column in list view
    form_excluded_columns = ["password"]  # Hide password in form (use password_input instead)
    form_columns = ["first_name", "last_name", "username", "password_input", "email", "role", "points"]  # Fields admin can edit
    form_extra_fields = {
        "password_input": PasswordField("Password")  # Special password field for admin to enter
    }
    def on_model_change(self, form, model, is_created):
        # When admin saves, encrypt the password
        if form.password_input.data:
            model.set_password(form.password_input.data)
    def is_accessible(self):
        # Only admin users can access this panel
        return current_user.is_authenticated and current_user.role == "admin"
    def inaccessible_callback(self, name, **kwargs):
        # If not admin, redirect to login
        return redirect(url_for("login"))


# Create admin interface at /admin for managing all data in the system
admin = Admin(app, name="ClassPack Admin View", index_view=AdminView())

admin.add_view(UserAdminView(User, db.session))  # Admin can manage users
admin.add_view(ModelView(Class, db.session))  # Admin can manage classes
admin.add_view(ModelView(ClassEnrollment, db.session))  # Admin can manage student enrollments
admin.add_view(ModelView(Question, db.session))  # Admin can manage questions
admin.add_view(ModelView(Collectible, db.session))  # Admin can manage collectible items
admin.add_view(ModelView(StudentCollectible, db.session))  # Admin can manage what students have collected
admin.add_view(ModelView(TradeRequest, db.session))  # Admin can manage trade requests between students

# Home page - just redirects to login
@app.route("/")
def index():
    return redirect(url_for("login"))

# Login page - handles user authentication and directs them to their dashboard
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        # User submitted login form
        username = request.form.get("username")
        password = request.form.get("password")
        
        # Find user in database
        user = User.query.filter_by(username=username).first()
        
        # Check if user exists and password is correct
        if user and user.check_password(password):
            login_user(user)  # Log them in
            # Redirect to appropriate dashboard based on user role
            if user.role == "admin":
                return redirect("/admin")
            elif user.role == "teacher":
                return redirect(url_for("teacher_dashboard"))
            else:
                return redirect(url_for("student_dashboard"))
        else:
            flash("Invalid username or password")  # Show error message

    return render_template("login.html")

# Registration page - creates new student or teacher accounts
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        # Get form data from registration form
        username   = request.form.get("username", "").strip()
        password   = request.form.get("password", "")
        first_name = request.form.get("first_name", "").strip()
        last_name  = request.form.get("last_name", "").strip()
        role       = request.form.get("role", "student")
        join_code  = request.form.get("join_code", "").strip().upper()

        # Check if username already exists
        if User.query.filter_by(username=username).first():
            flash("Username already taken.")
            return render_template("register.html")

        # Create new user
        user = User(
            username=username,
            first_name=first_name,
            last_name=last_name,
            role=role,
            points=0  # Start with 0 points
        )
        user.set_password(password)  # Encrypt password
        db.session.add(user)
        db.session.flush()  # Save user to database temporarily

        # If registering as student, enroll them in a class
        if role == "student":
            cls = Class.query.filter_by(join_code=join_code).first()
            if not cls:
                flash("Invalid class join code.")
                db.session.rollback()  # Undo user creation
                return render_template("register.html")
            enrollment = ClassEnrollment(student_id=user.id, class_id=cls.id)
            db.session.add(enrollment)
        # If registering as teacher, create their first class
        elif role == "teacher":
            class_name = request.form.get("class_name", "").strip()
            if class_name:
                existing = Class.query.filter_by(name=class_name).first()
                if existing:
                    flash("Class Already Exists", "error")
                    db.session.rollback()
                    return render_template("register.html")
                new_class = Class(
                    name=class_name,
                    join_code=Class.generate_join_code(),  # Generate unique code for students to join
                    teacher_id=user.id
                )
                db.session.add(new_class)

        # Debug logging
        print("role:", role)
        print("class_name:", request.form.get("class_name"))

        db.session.commit()  # Save everything to database
        flash("Account created! Please log in.")
        return redirect(url_for("login"))

    return render_template("register.html")

@socketio.on("join_class")
def join_class(data):
    class_id = data.get("join_code")
    room = f"class_{join_code}"
    join_room(room)

# Student home page - shows their classes and allows joining new classes
@app.route("/student/dashboard", methods=["POST", "GET"])
@login_required  # Must be logged in to access
def student_dashboard():
    # Make sure user is actually a student (not a teacher or admin)
    if current_user.role != "student":
        return redirect(url_for("login"))

    if request.method == "POST":
        # Student is trying to join a new class with a join code
        join_code = request.form.get("join_code", "").strip().upper()
        cls = Class.query.filter_by(join_code=join_code).first()
        if not cls:
            flash("Invalid class join code.")
            db.session.rollback()
            return render_template("student_dashboard.html")
        # Add student to the class
        enrollment = ClassEnrollment(student_id=current_user.id, class_id=cls.id)
        active = ClassEnrollment.query.filter_by(student_id=current_user.id, class_id=cls.id, status="active").first()
        if active:
            flash("You are already enrolled in this class.")
            return render_template("student_dashboard.html")
        else:
            db.session.add(enrollment)
            db.session.commit()
        flash(f"Joined class: {cls.name}")
        return redirect("/student/dashboard")
    
    return render_template("student_dashboard.html", classes=current_user.class_enrollments)

@app.route("/class/chat/<join_code>")
@login_required
def class_chat(join_code):
    cls = Class.query.filter_by(join_code=join_code).first_or_404()
    return render_template("class_chat.html", cls=cls, join_code=join_code)

@socketio.on("join_class")
def join_class(data):
    join_code = data.get("join_code")
    room = f"class_{join_code}"
    join_room(room)
@socketio.on("send_message")
def handle_send_message(data):
    join_code = data.get("join_code")
    username = data.get("username")
    message = data.get("message")

    room = f"class_{join_code}"

    emit("chat_message", {
        "username": username,
        "message":message
        }, room = room)
    
def push_trade_update(join_code, sender_name, reciever_name, item_name):
    room = f"class_{join_code}"

    socketio.emit(
        "trade_update",
        {"message": f" Trade completed: {sender_name} traded '{item_name}' to '{reciever_name}'"},
        room=room
    )
def send_trade_update(join_code, text):
    room = f"class_{join_code}"
    socketio.emit("trade_update", {"message": text}, room=room)


@app.route("/trade/complete/<int:trade_id>", methods=["POST"])
@login_required
def complete_trade(trade_id):
    trade = TradeRequest.query.get_or_404(trade_id)

    item = Collectible.query.get(trade.item_id)
    sender = User.query.get(trade.sender_id)
    reciever = User.query.get(trade.reciever_id)

    item.owner_id = reciever.id
    db.session.commit()

    push_trade_update(
        join_code=trade.class_id,
        sender_name=sender.username,
        reciever_name=reciever.username,
        item_name=item.name
    
    )

    return jsonify({"status" : "success", "message" : "Trade completed"})

@app.route("/student/leave_class/<int:enrollment_id>", methods=["POST"])
@login_required
def student_leave_class(enrollment_id):
    if current_user.role != "student":
        return redirect(url_for("login"))
    
    enrollment = ClassEnrollment.query.filter_by(id=enrollment_id, student_id=current_user.id).first_or_404()

    try:
        db.session.delete(enrollment)
        db.session.commit()
        flash("You have successfully left the class.")
    except Exception as e:
        db.session.rollback()
        flash("An error occurred while trying to leave the class.")
        print(f"Error: {e}")
    return redirect("/student/dashboard")

# redirect to the respective class
@app.route("/student/class/<int:class_id>")
@login_required
def student_view_class(class_id):
    if current_user.role != "student":
        return redirect(url_for("login"))
    
    cls = Class.query.filter_by(id=class_id).first_or_404()
    return render_template("student_class.html", cls=cls)

# Process student purchasing collectible card from shop - costs 50 points
@app.route("/student/shop/buy", methods=["POST"])
@login_required  # Must be logged in
def student_buy_card():
    if current_user.role != "student":
        return redirect(url_for("login"))

    # Check if student has enough points
    if current_user.points < 50:
        flash("Not enough points.")
        return redirect(url_for("student_shop"))

    # Make sure student is enrolled in at least one class
    enrollment = ClassEnrollment.query.filter_by(
        student_id=current_user.id, status="active"
    ).first()
    if not enrollment:
        flash("You are not enrolled in a class.")
        return redirect(url_for("student_shop"))

    # Get all collectible cards available in their class
    pool = Collectible.query.filter_by(class_id=enrollment.class_id).all()
    if not pool:
        flash("No collectibles available yet.")
        return redirect(url_for("student_shop"))

    # Calculate odds for each card based on rarity (rarer cards less likely)
    weights = []
    for c in pool:
        idx = RARITY_LEVELS.index(c.rarity) if c.rarity in RARITY_LEVELS else 0
        weights.append(RARITY_WEIGHTS[idx])

    # Randomly select a card based on rarity odds
    chosen = random.choices(pool, weights=weights, k=1)[0]
    # Add card to student's collection
    sc = StudentCollectible(student_id=current_user.id, collectible_id=chosen.id)
    current_user.points -= 50  # Deduct 50 points
    db.session.add(sc)
    db.session.commit()

    flash(f"You got: {chosen.emoji} {chosen.name} ({chosen.rarity})")
    return redirect(url_for("student_shop"))


# Shop page - students can spend points to buy collectible cards
@app.route("/student/shop")
@login_required  # Must be logged in
def student_shop():
    if current_user.role != "student":
        return redirect(url_for("login"))
    return render_template("student_shop.html", points=current_user.points)

# Study page - shows random question for student to answer
@app.route("/student/study")
@login_required  # Must be logged in
def student_study():
    if current_user.role != "student":
        return redirect(url_for("login"))

    # Get student's enrolled class
    enrollment = ClassEnrollment.query.filter_by(
        student_id=current_user.id, status="active"
    ).first()
    if not enrollment:
        flash("You are not enrolled in a class.")
        return redirect(url_for("student_dashboard"))

    # Get all active questions for their class
    questions = Question.query.filter_by(
        class_id=enrollment.class_id, is_active=True
    ).all()
    if not questions:
        flash("No questions available yet.")
        return redirect(url_for("student_dashboard"))

    # Pick a random question
    question = random.choice(questions)
    return render_template("student_study.html", question=question)


# Process student's answer to a question - awards points if correct
@app.route("/student/study/answer", methods=["POST"])
@login_required  # Must be logged in
def student_study_answer():
    question_id = request.form.get("question_id", type=int)
    chosen = request.form.get("answer", "").lower()  # Get student's answer

    question = Question.query.get_or_404(question_id)
    # Check if answer is correct
    correct = chosen.lower() == question.correct_option.lower()
    if correct:
        # Award points to student
        current_user.points += question.point_value
        db.session.commit()

    # Return the same question with results (showing if correct/incorrect)
    return render_template("student_study.html", question=question, chosen=chosen, correct=correct, answered=True)

# Shows only the current student's collection
@app.route("/student/collection")
@login_required
def student_collection():
    if current_user.role != "student":
        return redirect(url_for("login"))
    # create an array containing students collection to be passed into render_template
    # query student collectibles for collectibles with current student id
    collection = StudentCollectible.query.filter_by(student_id=current_user.id).all()
    return render_template("student_collection.html", collection=collection)

# Teacher home page - manage their classes and students
@app.route("/teacher/dashboard", methods=["POST", "GET"])
@login_required  # Must be logged in
def teacher_dashboard():
    if current_user.role != "teacher":
        return redirect(url_for("login"))
    
    # Get all classes taught by this teacher
    classes = Class.query.filter_by(teacher_id=current_user.id).all()
    class_data = []  # Prepare data for template
    
    # Build data for each class including enrolled students
    for cls in classes:
        students = [enrollment.student for enrollment in cls.enrollments if enrollment.status == "active"]
        class_data.append({
            "name": cls.name,
            "join_code": cls.join_code,
            "students": students
        })
    
    if request.method == "POST":
        # Check if this is a delete request
        if request.form.get("_method") == "DELETE":
            join_code = request.form.get("join_code", "").strip()
            cls = Class.query.filter_by(join_code=join_code, teacher_id=current_user.id).first()
            if cls:
                db.session.delete(cls)  # Delete the class
                db.session.commit()
                flash("Class deleted.")
            else:
                flash("Class not found or you do not have permission to delete it.")
            return redirect(url_for("teacher_dashboard"))

        # Create a new class
        class_name = request.form.get("class_name", "").strip()
        if class_name:
            existing = Class.query.filter_by(name=class_name).first()
            if existing:
                flash("Class Already Exists", "error")
                db.session.rollback()
                return render_template("teacher_dashboard.html")
            new_class = Class(
                name=class_name,
                join_code=Class.generate_join_code(),  # Generate unique join code
                teacher_id=current_user.id
            )
            db.session.add(new_class)
            db.session.commit()
            flash("Class created!")
            return redirect(url_for("teacher_dashboard"))    
    return render_template("teacher_dashboard.html", Classes=class_data)

# Add a new question to a class - for teachers to create study questions
@app.route("/teacher/question/add", methods=["GET", "POST"])
@app.route("/teacher/question/add/<string:join_code>", methods=["GET", "POST"])  # Can come from class page
@login_required  # Must be logged in
def teacher_add_question(join_code=None):
    if current_user.role != "teacher":
        return redirect(url_for("login"))

    # Get all teacher's classes
    classes = Class.query.filter_by(teacher_id=current_user.id).all()
    selected_class_id = None

    # If coming from a specific class, pre-select it
    if join_code:
        selected_class = Class.query.filter_by(join_code=join_code, teacher_id=current_user.id).first()
        if selected_class:
            selected_class_id = selected_class.id

    if request.method == "POST":
        # Get form data from question creation form
        selected_class_id = request.form.get("class_id", type=int)
        cls = Class.query.filter_by(id=selected_class_id, teacher_id=current_user.id).first()
        if not cls:
            flash("Please select a valid class.")
            return redirect(url_for("teacher_add_question", join_code=join_code) if join_code else url_for("teacher_add_question"))

        # Create new question
        q = Question(
            class_id=cls.id,
            text=request.form.get("text", "").strip(),
            option_a=request.form.get("option_a", "").strip(),
            option_b=request.form.get("option_b", "").strip(),
            option_c=request.form.get("option_c", "").strip(),
            option_d=request.form.get("option_d", "").strip(),
            correct_option=request.form.get("correct_option", "a").lower(),  # Which answer is correct
            point_value=int(request.form.get("point_value", 10)),  # Points awarded for correct answer
            is_active=True
        )
        db.session.add(q)
        db.session.commit()
        flash("Question created!")
        return redirect(url_for("teacher_add_question", join_code=join_code) if join_code else url_for("teacher_add_question"))

    return render_template("teacher_add_question.html", classes=classes, selected_class_id=selected_class_id, join_code=join_code)

# View all questions - shows questions from teacher's first class
@app.route("/teacher/questions")
@login_required  # Must be logged in
def teacher_questions():
    if current_user.role != "teacher":
        return redirect(url_for("login"))
    # Get all teacher's classes
    classes = Class.query.filter_by(teacher_id=current_user.id).all()
    if not classes:
        flash("You have no classes yet.")
        return redirect(url_for("teacher_dashboard"))
    # Get questions from their first class
    questions = Question.query.filter_by(class_id=classes[0].id).all()
    return render_template("teacher_questions.html", questions=questions)


# View questions for a specific class - accessed from class page
@app.route("/teacher/questions/<string:join_code>")
@login_required  # Must be logged in
def teacher_class_questions(join_code):
    if current_user.role != "teacher":
        return redirect(url_for("login"))
    # Get the class by join code (must be teacher's own class)
    cls = Class.query.filter_by(join_code=join_code, teacher_id=current_user.id).first_or_404()
    # Get all questions in this class
    questions = Question.query.filter_by(class_id=cls.id).all()
    return render_template("teacher_questions.html", questions=questions, current_class=cls)


# Toggle a question active/inactive - turns on/off whether students can see it
@app.route("/teacher/question/<int:question_id>/toggle", methods=["POST"])
@login_required  # Must be logged in
def teacher_toggle_question(question_id):
    if current_user.role != "teacher":
        return redirect(url_for("login"))
    q = Question.query.get_or_404(question_id)
    q.is_active = not q.is_active  # Switch between active/inactive
    db.session.commit()
    flash(f"Question marked as {'active' if q.is_active else 'inactive'}.")
    return redirect(url_for("teacher_questions"))


# Delete a question - permanently removes it
@app.route("/teacher/question/<int:question_id>/delete", methods=["POST"])
@login_required  # Must be logged in
def teacher_delete_question(question_id):
    if current_user.role != "teacher":
        return redirect(url_for("login"))
    q = Question.query.get_or_404(question_id)
    db.session.delete(q)  # Remove from database
    db.session.commit()
    flash("Question deleted.")
    return redirect(url_for("teacher_questions"))
# Class management page - teacher can view and manage a specific class
@app.route("/teacher/class/<string:join_code>", methods=["GET", "POST"])
@login_required  # Must be logged in
def teacher_class(join_code):
    if current_user.role != "teacher":
        return redirect(url_for("login"))
    # Get the class by join code
    cls = Class.query.filter_by(join_code=join_code).first_or_404()
    # Make sure teacher owns this class
    if cls.teacher_id != current_user.id:
        flash("You do not have access to this class.")
        return redirect(url_for("teacher_dashboard"))    
    
    if request.method == "POST" and request.form.get("_method") == "DELETE":
        # Remove a student from class
        student_id = request.form.get("student_id", type=int)
        if student_id:
            enrollment = ClassEnrollment.query.filter_by(student_id=student_id, class_id=cls.id).first()
            if enrollment:
                db.session.delete(enrollment)  # Remove student enrollment
                db.session.commit()
                flash("Student removed from class.")
            else:
                flash("Student not found in this class.")
        return redirect(url_for("teacher_class", join_code=join_code))
    
    # Display the class page
    return render_template("teacher_class.html", cls=cls)
# Edit an existing question - teacher can modify questions they created
@app.route("/teacher/question/<int:question_id>/edit", methods=["GET", "POST"])
def teacher_edit_question(question_id):
    if current_user.role != "teacher":
        return redirect(url_for("login"))
    # Get the question
    q = Question.query.get_or_404(question_id)
    cls = Class.query.get(q.class_id)
    # Make sure teacher owns this question's class
    if cls.teacher_id != current_user.id:
        flash("You do not have access to this question.")
        return redirect(url_for("teacher_dashboard"))
    
    if request.method == "POST":
        # Update question fields
        q.text = request.form.get("text", "").strip()
        q.option_a = request.form.get("option_a", "").strip()
        q.option_b = request.form.get("option_b", "").strip()
        q.option_c = request.form.get("option_c", "").strip()
        q.option_d = request.form.get("option_d", "").strip()
        q.correct_option = request.form.get("correct_option", "a").lower()
        q.point_value = int(request.form.get("point_value", 10))
        db.session.commit()  # Save changes
        flash("Question updated!")
        return redirect(url_for("teacher_questions"))
    
    # Show edit form
    return render_template("teacher_edit_question.html", question=q)

@app.route("/upload", methods = ["GET", "POST"])
def upload_collectible():
    if request.method == "POST":
        file = request.files.get("file")
        name = request.form.get("name")
        description = request.form.get("description")
        rarity = request.form.get("rarity")
        class_id = request.form.get("class_id")
        if not file or file.filename == "":
            flash("No file selected.", "error")
            return redirect(request.url)
        if not allowed_file(file.filename):
            flash("Invalid file type. Please choose a PNG, JPG, or GIF", "error")
            return redirect(request.url)
        filename = secure(file.filename)
        save_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
        file.save(save_path)
        collectible = Collectible(
            name=name,
            description=description,
            rarity=rarity,
            class_id=class_id,
            image_path=save_path
        )
        db.session.add(collectible)
        db.session.commit()

        flash("Collectible uploaded!", "succes")
        return redirect(url_for(teacher_dashboard))
    return render_template("upload_collectible.html")
# Logout - ends user session
@app.route("/logout")
def logout():
    logout_user()  # Clear login session
    return redirect(url_for("login"))

# Initialize database tables on startup
with app.app_context():
    db.create_all()  # Create all database tables if they don't exist

# Run the Flask server
if __name__ == "__main__":
    socketio.run(app, debug=True)  # Start development server