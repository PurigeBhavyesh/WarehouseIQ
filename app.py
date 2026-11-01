import os
from pathlib import Path

from dotenv import load_dotenv
from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
)
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import URL, or_
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from werkzeug.security import (
    generate_password_hash,
    check_password_hash,
)


# --------------------------------------------------
# 1. Load environment variables
# --------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent

# Load settings from the .env file beside app.py.
# override=True ensures this project's values take priority.
load_dotenv(BASE_DIR / ".env", override=True)

required_vars = [
    "DB_USER",
    "DB_PASSWORD",
    "DB_HOST",
    "DB_NAME",
    "SECRET_KEY",
]

missing_vars = [
    name for name in required_vars
    if not os.getenv(name)
]

if missing_vars:
    raise RuntimeError(
        f"Missing environment variables: {', '.join(missing_vars)}"
    )


# --------------------------------------------------
# 2. Initialize Flask
# --------------------------------------------------

app = Flask(__name__)

app.config["SECRET_KEY"] = os.getenv("SECRET_KEY")

app.config["SQLALCHEMY_DATABASE_URI"] = URL.create(
    "mysql+pymysql",
    username=os.getenv("DB_USER"),
    password=os.getenv("DB_PASSWORD"),
    host=os.getenv("DB_HOST"),
    port=int(os.getenv("DB_PORT", "3306")),
    database=os.getenv("DB_NAME"),
)

app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

# Set COOKIE_SECURE=true only when using HTTPS.
app.config["SESSION_COOKIE_SECURE"] = (
    os.getenv("COOKIE_SECURE", "false").lower() == "true"
)


# --------------------------------------------------
# 3. Initialize SQLAlchemy
# --------------------------------------------------

db = SQLAlchemy(app)


# --------------------------------------------------
# 4. User model
# Define this model only once in this file.
# --------------------------------------------------

class User(db.Model):
    __tablename__ = "users"

    id = db.Column(
        db.Integer,
        primary_key=True,
    )

    username = db.Column(
        db.String(80),
        unique=True,
        nullable=False,
    )

    email = db.Column(
        db.String(120),
        unique=True,
        nullable=False,
    )

    password_hash = db.Column(
        db.String(255),
        nullable=False,
    )


# --------------------------------------------------
# 5. Create missing database tables
# This must run after all models have been defined.
# --------------------------------------------------

with app.app_context():
    db.create_all()
    app.logger.info("Database tables checked successfully.")


# --------------------------------------------------
# 6. Home route
# --------------------------------------------------

@app.route("/")
def home():
    if session.get("user_id"):
        return redirect(url_for("dashboard"))

    return redirect(url_for("login"))


# --------------------------------------------------
# 7. Registration route
# --------------------------------------------------

@app.route("/register", methods=["GET", "POST"])
def register():

    if session.get("user_id"):
        return redirect(url_for("dashboard"))

    if request.method == "POST":

        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        # Validate required fields.
        if not username or not email or not password:
            return "All fields are required.", 400

        # Validate field lengths.
        if len(username) > 80 or len(email) > 120:
            return "Username or email is too long.", 400

        if len(password) < 8:
            return "Password must contain at least 8 characters.", 400

        # Basic email validation.
        if (
            "@" not in email
            or email.startswith("@")
            or email.endswith("@")
            or "." not in email.rsplit("@", 1)[-1]
        ):
            return "Enter a valid email address.", 400

        try:
            # Check whether the username or email already exists.
            existing_user = db.session.execute(
                db.select(User).where(
                    or_(
                        User.username == username,
                        User.email == email,
                    )
                )
            ).scalar_one_or_none()

            if existing_user:
                return "Username or email already exists.", 409

            # Hash the password before storing it.
            user = User(
                username=username,
                email=email,
                password_hash=generate_password_hash(password),
            )

            db.session.add(user)
            db.session.commit()

        except IntegrityError:
            # Handles duplicate entries submitted concurrently.
            db.session.rollback()
            return "Username or email already exists.", 409

        except SQLAlchemyError:
            db.session.rollback()
            app.logger.exception(
                "Database error during registration."
            )
            return "Registration failed. Please try again.", 500

        return redirect(url_for("login"))

    return render_template("registration.html")


# --------------------------------------------------
# 8. Login route
# --------------------------------------------------

@app.route("/login", methods=["GET", "POST"])
def login():

    if session.get("user_id"):
        return redirect(url_for("dashboard"))

    if request.method == "POST":

        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if not email or not password:
            return "Email and password are required.", 400

        try:
            user = db.session.execute(
                db.select(User).where(User.email == email)
            ).scalar_one_or_none()

        except SQLAlchemyError:
            db.session.rollback()
            app.logger.exception("Database error during login.")
            return "Login failed. Please try again.", 500

        if user and check_password_hash(
            user.password_hash,
            password,
        ):
            # Remove any old session values before logging in.
            session.clear()
            session["user_id"] = user.id

            return redirect(url_for("dashboard"))

        return "Invalid email or password.", 401

    return render_template("login.html")


# --------------------------------------------------
# 9. Dashboard route
# --------------------------------------------------

@app.route("/dashboard")
def dashboard():

    user_id = session.get("user_id")

    if user_id is None:
        return redirect(url_for("login"))

    try:
        user = db.session.get(User, user_id)

    except SQLAlchemyError:
        db.session.rollback()
        app.logger.exception("Database error loading dashboard.")
        return "Unable to load dashboard. Please try again.", 500

    if user is None:
        session.clear()
        return redirect(url_for("login"))

    return render_template(
        "dashboard.html",
        username=user.username,
    )


# --------------------------------------------------
# 10. Logout route
# --------------------------------------------------

@app.route("/logout", methods=["POST"])
def logout():

    session.clear()

    return redirect(url_for("login"))


# --------------------------------------------------
# 11. Run the application
# --------------------------------------------------

if __name__ == "__main__":
    app.run(debug=True)
