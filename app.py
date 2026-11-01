import os
from flask import Flask,render_template,request
from flask_sqlalchemy import SQLAlchemy
from dotenv import load_dotenv
from sqlalchemy import URL
from werkzeug.security import generate_password_hash,check_password_hash


load_dotenv()

app = Flask(__name__)


app.config["SQLALCHEMY_DATABASE_URI"] = (
    f"mysql+pymysql://"
    f"{os.getenv('DB_USER')}:"
    f"{os.getenv('DB_PASSWORD')}@"
    f"{os.getenv('DB_HOST')}:"
    f"{os.getenv('DB_PORT')}/"
    f"{os.getenv('DB_NAME')}"
)

app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

class User(db.Model):
    __tablename__="users"
    id=db.Column(
        db.Integer,
        primary_key=True
    )

    username=db.Column(
        db.String(80),
        unique=True,
        nullable=False
    )

    email=db.Column(
        db.String(120),
        unique=True,
        nullable=False
    )

    password_hash=db.Column(
        db.String(225),
        nullable=False
    )


@app.route("/")
def home():
    return render_template('login.html')

@app.route("/register",methods=["GET","POST"])
def register():
    if request.method=="POST":
        username=request.form.get("username").strip()
        email=request.form.get("email").strip().lower()
        password=request.form.get("password","")

        if not username or not email or not password:
            return "All fields are required.", 400

        if len(username)>80 or len(email)>120:
            return "Username or Email is too long.", 400

        if len(password)<8:
            return "Password is too short.", 400

        existing_user=db.session.execute(
            db.select(User).where(
                db.or_(
                    User.username==username,
                    User.email==email
                )
            )
        ).scalar_one_or_none()

        if existing_user:
            return "Username or Email already exists.", 409

        hashed_password=generate_password_hash(password)

        user=User(
            username=username,
            email=email,
            password_hash=hashed_password
        )

        try:
            db.session.add(user)
            db.session.commit()
        except Exception:
            db.session.rollback()
            app.logger.exception("Registration Failed")
            return "Registration failed. Please try again.", 500

        return render_template("login.html"), 201

    return render_template("registration.html")

@app.route("/login",methods=["GET","POST"])
def login():
    if request.method=="POST":
        email=request.form.get("email","").strip().lower()
        password=request.form.get("password","")

        user=db.session.execute(
            db.select(User).where(User.email==email)
        ).scalar_one_or_none()

        if user and check_password_hash(user.password_hash,password):
            return render_template("dashboard.html")

        return "Invalid email or password.", 401
    return render_template("login.html")

with app.app_context():
    db.create_all()


if __name__ == "__main__":
    app.run(debug=True)