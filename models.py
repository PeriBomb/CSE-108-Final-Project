from extensions import db
from flask_login import UserMixin
import random
import string

class User(UserMixin, db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), nullable=True)
    password = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="student")
    points = db.Column(db.Integer, nullable=False, default=0)
    first_name = db.Column(db.String(80), nullable=False)
    last_name = db.Column(db.String(80), nullable=False)
    def set_password(self, password):
        from werkzeug.security import generate_password_hash
        self.password = generate_password_hash(password)

    def check_password(self, password):
        from werkzeug.security import check_password_hash
        return check_password_hash(self.password, password)
    
    def __repr__(self):
        return f"{self.first_name} {self.last_name}"


class Class(db.Model):
    __tablename__ = "classes"
 
    id          = db.Column(db.Integer, primary_key=True)
    name        = db.Column(db.String(120), nullable=False)
    join_code   = db.Column(db.String(10), unique=True, nullable=False)
    teacher_id  = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
 
    teacher      = db.relationship("User",            backref="taught_classes")
    questions    = db.relationship("Question",        backref="class_ref", lazy=True, cascade="all, delete-orphan")
    collectibles = db.relationship("Collectible",     backref="class_ref", lazy=True, cascade="all, delete-orphan")
    enrollments  = db.relationship("ClassEnrollment", backref="class_ref", lazy=True, cascade="all, delete-orphan")
 
    @staticmethod
    def generate_join_code():
        """Generate a unique 6-character alphanumeric join code."""
        while True:
            code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
            if not Class.query.filter_by(join_code=code).first():
                return code
 
    @property
    def active_student_count(self):
        return ClassEnrollment.query.filter_by(class_id=self.id, status="active").count()
 
    def __repr__(self):
        return f"{self.name} ({self.join_code})"


class ClassEnrollment(db.Model):
    __tablename__ = "class_enrollments"
 
    id         = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    class_id   = db.Column(db.Integer, db.ForeignKey("classes.id"), nullable=False)
    status     = db.Column(db.String(20), nullable=False, default="active")  # active | removed
 
    student = db.relationship("User", backref="class_enrollments")
 
    def __repr__(self):
        return f"Enrollment(student={self.student_id}, class={self.class_id}, status={self.status})"


class Question(db.Model):
    __tablename__ = "questions"
 
    id             = db.Column(db.Integer, primary_key=True)
    class_id       = db.Column(db.Integer, db.ForeignKey("classes.id"), nullable=False)
    text           = db.Column(db.Text, nullable=False)
    option_a       = db.Column(db.String(300), nullable=False)
    option_b       = db.Column(db.String(300), nullable=False)
    option_c       = db.Column(db.String(300), nullable=False)
    option_d       = db.Column(db.String(300), nullable=False)
    correct_option = db.Column(db.String(1), nullable=False)   # 'a' | 'b' | 'c' | 'd'
    point_value    = db.Column(db.Integer, nullable=False, default=10)
    is_active      = db.Column(db.Boolean, nullable=False, default=True)
 
    def __repr__(self):
        return f"Question({self.id}: {self.text[:50]})"


RARITY_LEVELS  = ["common", "uncommon", "rare", "legendary"]
RARITY_WEIGHTS = [60, 25, 12, 3]   # drop-rate weights, must match order above
 
 
class Collectible(db.Model):
    """Template defined by a teacher — the 'species' of a collectible."""
    __tablename__ = "collectibles"
 
    id          = db.Column(db.Integer, primary_key=True)
    class_id    = db.Column(db.Integer, db.ForeignKey("classes.id"), nullable=False)
    name        = db.Column(db.String(120), nullable=False)
    description = db.Column(db.String(300), nullable=True)
    rarity      = db.Column(db.String(20), nullable=False, default="common")
    emoji       = db.Column(db.String(10), nullable=False, default="🦂")
 
    def __repr__(self):
        return f"Collectible({self.name}, {self.rarity})"
 
 
class StudentCollectible(db.Model):
    """One owned instance of a Collectible template."""
    __tablename__ = "student_collectibles"
 
    id             = db.Column(db.Integer, primary_key=True)
    student_id     = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    collectible_id = db.Column(db.Integer, db.ForeignKey("collectibles.id"), nullable=False)
    is_locked      = db.Column(db.Boolean, nullable=False, default=False)  # True while in a pending trade
 
    student     = db.relationship("User",        backref="owned_collectibles")
    collectible = db.relationship("Collectible", backref="instances")
 
    def __repr__(self):
        return f"StudentCollectible(student={self.student_id}, item={self.collectible_id})"


class TradeRequest(db.Model):
    __tablename__ = "trade_requests"
 
    id                = db.Column(db.Integer, primary_key=True)
    sender_id         = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    receiver_id       = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    offered_item_id   = db.Column(db.Integer, db.ForeignKey("student_collectibles.id"), nullable=False)
    requested_item_id = db.Column(db.Integer, db.ForeignKey("student_collectibles.id"), nullable=False)
    status            = db.Column(db.String(20), nullable=False, default="pending")
    # pending | accepted | declined | countered | cancelled
 
    # For counter offers
    parent_trade_id = db.Column(db.Integer, db.ForeignKey("trade_requests.id"), nullable=True)
 
    sender         = db.relationship("User", foreign_keys=[sender_id],   backref="sent_trades")
    receiver       = db.relationship("User", foreign_keys=[receiver_id], backref="received_trades")
    offered_item   = db.relationship("StudentCollectible", foreign_keys=[offered_item_id])
    requested_item = db.relationship("StudentCollectible", foreign_keys=[requested_item_id])
 
    parent_trade = db.relationship("TradeRequest", remote_side=[id], backref="counter_offers")
 
    def __repr__(self):
        return f"Trade({self.sender_id} → {self.receiver_id}, status={self.status})"
    
