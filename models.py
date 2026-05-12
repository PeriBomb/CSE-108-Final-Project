# Import database tools and Flask login features
from extensions import db
from flask_login import UserMixin
import random
import string

# USER MODEL - represents a person (student, teacher, or admin) in the system
class User(UserMixin, db.Model):
    __tablename__ = "users"  # Database table name
    id = db.Column(db.Integer, primary_key=True)  # Unique ID for each user
    username = db.Column(db.String(80), unique=True, nullable=False)  # Username (must be unique)
    email = db.Column(db.String(120), nullable=True)  # Email address
    password = db.Column(db.String(200), nullable=False)  # Encrypted password
    role = db.Column(db.String(20), nullable=False, default="student")  # student | teacher | admin
    points = db.Column(db.Integer, nullable=False, default=0)  # Points earned from studying
    first_name = db.Column(db.String(80), nullable=False)  # User's first name
    last_name = db.Column(db.String(80), nullable=False)  # User's last name
    
    # Encrypt the password for security
    def set_password(self, password):
        from werkzeug.security import generate_password_hash
        self.password = generate_password_hash(password)

    # Check if entered password matches stored encrypted password
    def check_password(self, password):
        from werkzeug.security import check_password_hash
        return check_password_hash(self.password, password)
    
    # Display user as "First Last" instead of raw object
    def __repr__(self):
        return f"{self.first_name} {self.last_name}"


# CLASS MODEL - represents a course taught by a teacher
class Class(db.Model):
    __tablename__ = "classes"  # Database table name
 
    id          = db.Column(db.Integer, primary_key=True)  # Unique ID for each class
    name        = db.Column(db.String(120), unique=True, nullable=False)  # Class name (e.g., "Biology 101")
    join_code   = db.Column(db.String(10), unique=True, nullable=False)  # Unique code students use to join
    teacher_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)  # Which teacher owns this class
    
    # Link to the teacher who created this class
    teacher = db.relationship("User", backref=db.backref("taught_classes", passive_deletes=True))
    
    # Links to related data: questions, collectibles, and student enrollments
    questions    = db.relationship("Question",        backref="class_ref", lazy=True, cascade="all, delete-orphan")
    collectibles = db.relationship("Collectible",     backref="class_ref", lazy=True, cascade="all, delete-orphan")
    enrollments  = db.relationship("ClassEnrollment", backref="class_ref", lazy=True, cascade="all, delete-orphan")
 
    # Get list of students currently in this class
    @property
    def students(self):
        return [enrollment.student for enrollment in self.enrollments if enrollment.status == "active"]
 
    # Generate a unique 6-character code that students can use to join this class
    @staticmethod
    def generate_join_code():
        """Generate a unique 6-character alphanumeric join code."""
        while True:
            code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
            if not Class.query.filter_by(join_code=code).first():
                return code
 
    # Count how many active students are in this class
    @property
    def active_student_count(self):
        return ClassEnrollment.query.filter_by(class_id=self.id, status="active").count()
 
    # Display class as "ClassName (JOINCODE)" instead of raw object
    def __repr__(self):
        return f"{self.name} ({self.join_code})"


# CLASS ENROLLMENT MODEL - represents a student being enrolled in a class
class ClassEnrollment(db.Model):
    __tablename__ = "class_enrollments"  # Database table name
 
    id         = db.Column(db.Integer, primary_key=True)  # Unique ID for each enrollment
    student_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)  # Which student
    class_id   = db.Column(db.Integer, db.ForeignKey("classes.id", ondelete="CASCADE"), nullable=False)  # Which class
    status     = db.Column(db.String(20), nullable=False, default="active")  # active | removed (for tracking if removed from class)
 
    # Link to the student enrolled
    student = db.relationship("User", backref=db.backref("class_enrollments", passive_deletes=True))
 
    # Display enrollment in readable format
    def __repr__(self):
        return f"Enrollment(student={self.student_id}, class={self.class_id}, status={self.status})"


# QUESTION MODEL - represents a multiple choice study question
class Question(db.Model):
    __tablename__ = "questions"  # Database table name
 
    id             = db.Column(db.Integer, primary_key=True)  # Unique ID for each question
    class_id       = db.Column(db.Integer, db.ForeignKey("classes.id"), nullable=False)  # Which class this question belongs to
    text           = db.Column(db.Text, nullable=False)  # The question text
    option_a       = db.Column(db.String(300), nullable=False)  # Answer choice A
    option_b       = db.Column(db.String(300), nullable=False)  # Answer choice B
    option_c       = db.Column(db.String(300), nullable=False)  # Answer choice C
    option_d       = db.Column(db.String(300), nullable=False)  # Answer choice D
    correct_option = db.Column(db.String(1), nullable=False)   # Which choice is correct: 'a' | 'b' | 'c' | 'd'
    point_value    = db.Column(db.Integer, nullable=False, default=10)  # Points awarded for answering correctly
    is_active      = db.Column(db.Boolean, nullable=False, default=True)  # Whether students can see/answer this question
 
    # Display question with first 50 characters instead of raw object
    def __repr__(self):
        return f"Question({self.id}: {self.text[:50]})"


# RARITY LEVELS - defines how common/rare collectible cards are
RARITY_LEVELS  = ["common", "rare", "legendary"]  # Types of rarity
RARITY_WEIGHTS = [60, 35, 5]  # Odds of getting each: 60% common, 35% rare, 5% legendary
 
 
# COLLECTIBLE MODEL - template for a type of collectible card (like a Pokemon species)
class Collectible(db.Model):
    """Template defined by a teacher — the 'species' of a collectible."""
    __tablename__ = "collectibles"  # Database table name
 
    id          = db.Column(db.Integer, primary_key=True)  # Unique ID for each collectible type
    class_id    = db.Column(db.Integer, db.ForeignKey("classes.id"), nullable=False)  # Which class this belongs to
    name        = db.Column(db.String(120), nullable=False)  # Name of the collectible
    description = db.Column(db.String(300), nullable=True)  # Description of the collectible
    rarity      = db.Column(db.String(20), nullable=False, default="common")  # How rare it is
    emoji       = db.Column(db.String(10), nullable=True, default="🦂")  # Icon/emoji to display
    image_path = db.Column(db.String(255), nullable=True)
    is_base        = db.Column(db.Boolean, nullable=False, default=False)  # True for the custom art set

    
    # Display collectible type instead of raw object
    def __repr__(self):
        return f"Collectible({self.name}, {self.rarity})"
 
 
# STUDENT COLLECTIBLE MODEL - represents one actual copy of a collectible card that a student owns
class StudentCollectible(db.Model):
    """One owned instance of a Collectible template."""
    __tablename__ = "student_collectibles"  # Database table name
 
    id             = db.Column(db.Integer, primary_key=True)  # Unique ID for each owned card
    student_id     = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)  # Which student owns it
    collectible_id = db.Column(db.Integer, db.ForeignKey("collectibles.id"), nullable=False)  # Which type of collectible
    is_locked      = db.Column(db.Boolean, nullable=False, default=False)  # Locked while in a pending trade
 
    # Links to the student owner and the collectible type
    student     = db.relationship("User",        backref="owned_collectibles")
    collectible = db.relationship("Collectible", backref="instances")
 
    # Display owned card instead of raw object
    def __repr__(self):
        return f"StudentCollectible(student={self.student_id}, item={self.collectible_id})"


# TRADE REQUEST MODEL - represents a student wanting to trade collectible cards with another student
class TradeRequest(db.Model):
    __tablename__ = "trade_requests"  # Database table name
 
    id                = db.Column(db.Integer, primary_key=True)  # Unique ID for each trade request
    sender_id         = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)  # Student initiating the trade
    receiver_id       = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)  # Student receiving the request
    offered_item_id   = db.Column(db.Integer, db.ForeignKey("student_collectibles.id"), nullable=False)  # What the sender is offering
    requested_item_id = db.Column(db.Integer, db.ForeignKey("student_collectibles.id"), nullable=False)  # What the sender wants
    status            = db.Column(db.String(20), nullable=False, default="pending")  # pending | accepted | declined | countered | cancelled
    
    # For counter offers - if someone makes a different offer instead of accepting
    parent_trade_id = db.Column(db.Integer, db.ForeignKey("trade_requests.id"), nullable=True)
 
    # Links to the students and items involved in the trade
    sender         = db.relationship("User", foreign_keys=[sender_id],   backref="sent_trades")
    receiver       = db.relationship("User", foreign_keys=[receiver_id], backref="received_trades")
    offered_item   = db.relationship("StudentCollectible", foreign_keys=[offered_item_id])
    requested_item = db.relationship("StudentCollectible", foreign_keys=[requested_item_id])
 
    # Link to parent trade if this is a counter offer
    parent_trade = db.relationship("TradeRequest", remote_side=[id], backref="counter_offers")
 
    # Display trade request in readable format
    def __repr__(self):
        return f"Trade({self.sender_id} → {self.receiver_id}, status={self.status})"
    
