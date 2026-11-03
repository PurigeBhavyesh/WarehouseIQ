
import os
from pathlib import Path
from decimal import Decimal, InvalidOperation

from dotenv import load_dotenv
from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    flash,
)
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import URL, or_
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from werkzeug.security import (
    generate_password_hash,
    check_password_hash,
)


# ==================================================
# 1. LOAD ENVIRONMENT VARIABLES
# ==================================================

BASE_DIR = Path(__file__).resolve().parent
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


# ==================================================
# 2. INITIALIZE FLASK
# ==================================================

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
app.config["SESSION_COOKIE_SECURE"] = (
    os.getenv("COOKIE_SECURE", "false").lower() == "true"
)


# ==================================================
# 3. INITIALIZE DATABASE
# ==================================================

db = SQLAlchemy(app)


# ==================================================
# 4. USER MODEL
# ==================================================

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


# ==================================================
# 5. PRODUCT MODEL
# ==================================================

class Product(db.Model):
    __tablename__ = "products"

    id = db.Column(
        db.Integer,
        primary_key=True,
    )

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=False,
        index=True,
    )

    sku = db.Column(
        db.String(50),
        nullable=False,
    )

    name = db.Column(
        db.String(120),
        nullable=False,
    )

    category = db.Column(
        db.String(80),
        nullable=False,
    )

    unit = db.Column(
        db.String(20),
        nullable=False,
        default="piece",
    )

    purchase_price = db.Column(
        db.Numeric(10, 2),
        nullable=False,
    )

    selling_price = db.Column(
        db.Numeric(10, 2),
        nullable=False,
    )

    quantity = db.Column(
        db.Integer,
        nullable=False,
        default=0,
    )

    reorder_level = db.Column(
        db.Integer,
        nullable=False,
        default=10,
    )

    is_active = db.Column(
        db.Boolean,
        nullable=False,
        default=True,
    )

    created_at = db.Column(
        db.DateTime,
        nullable=False,
        server_default=db.func.current_timestamp(),
    )

    __table_args__ = (
        db.UniqueConstraint(
            "user_id",
            "sku",
            name="uq_product_user_sku",
        ),
        db.CheckConstraint(
            "purchase_price >= 0",
            name="ck_product_purchase_price_nonnegative",
        ),
        db.CheckConstraint(
            "selling_price >= 0",
            name="ck_product_selling_price_nonnegative",
        ),
        db.CheckConstraint(
            "quantity >= 0",
            name="ck_product_quantity_nonnegative",
        ),
        db.CheckConstraint(
            "reorder_level >= 0",
            name="ck_product_reorder_level_nonnegative",
        ),
    )


# ==================================================
# 6. CREATE MISSING TABLES
# Keep this AFTER every model definition.
# ==================================================

with app.app_context():
    db.create_all()
    app.logger.info("Database tables checked successfully.")


# ==================================================
# 7. SHARED HELPER FUNCTIONS
# ==================================================

def get_logged_in_user():
    """Return the logged-in user, or None."""

    user_id = session.get("user_id")

    if user_id is None:
        return None

    try:
        user = db.session.get(User, user_id)
    except SQLAlchemyError:
        db.session.rollback()
        app.logger.exception("Could not retrieve logged-in user.")
        return None

    if user is None:
        session.clear()

    return user


def parse_product_form():
    """Validate and return product fields from a submitted form."""

    sku = request.form.get("sku", "").strip().upper()
    name = request.form.get("name", "").strip()
    category = request.form.get("category", "").strip()
    unit = request.form.get("unit", "").strip()

    if not all([sku, name, category, unit]):
        raise ValueError("All text fields are required.")

    if len(sku) > 50:
        raise ValueError("SKU must not exceed 50 characters.")

    if len(name) > 120:
        raise ValueError("Product name must not exceed 120 characters.")

    if len(category) > 80:
        raise ValueError("Category must not exceed 80 characters.")

    if len(unit) > 20:
        raise ValueError("Unit must not exceed 20 characters.")

    purchase_price = Decimal(
        request.form.get("purchase_price", "").strip()
    )

    selling_price = Decimal(
        request.form.get("selling_price", "").strip()
    )

    quantity = int(request.form.get("quantity", "").strip())
    reorder_level = int(
        request.form.get("reorder_level", "").strip()
    )

    if not purchase_price.is_finite() or not selling_price.is_finite():
        raise ValueError("Prices must be valid finite numbers.")

    maximum_price = Decimal("99999999.99")

    if not (
        Decimal("0") <= purchase_price <= maximum_price
        and Decimal("0") <= selling_price <= maximum_price
    ):
        raise ValueError("Prices are outside the permitted range.")

    if quantity < 0 or reorder_level < 0:
        raise ValueError("Quantity and reorder level cannot be negative.")

    return {
        "sku": sku,
        "name": name,
        "category": category,
        "unit": unit,
        "purchase_price": purchase_price,
        "selling_price": selling_price,
        "quantity": quantity,
        "reorder_level": reorder_level,
    }


# ==================================================
# 8. HOME
# ==================================================

@app.route("/")
def home():
    if session.get("user_id"):
        return redirect(url_for("dashboard"))

    return redirect(url_for("login"))


# ==================================================
# 9. REGISTRATION
# ==================================================

@app.route("/register", methods=["GET", "POST"])
def register():

    if session.get("user_id"):
        return redirect(url_for("dashboard"))

    if request.method == "POST":

        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        if not username or not email or not password:
            return "All fields are required.", 400

        if len(username) > 80 or len(email) > 120:
            return "Username or email is too long.", 400

        if len(password) < 8:
            return "Password must contain at least 8 characters.", 400

        if (
            "@" not in email
            or email.startswith("@")
            or email.endswith("@")
            or "." not in email.rsplit("@", 1)[-1]
        ):
            return "Enter a valid email address.", 400

        try:
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

            user = User(
                username=username,
                email=email,
                password_hash=generate_password_hash(password),
            )

            db.session.add(user)
            db.session.commit()

        except IntegrityError:
            db.session.rollback()
            return "Username or email already exists.", 409

        except SQLAlchemyError:
            db.session.rollback()
            app.logger.exception("Database error during registration.")
            return "Registration failed. Please try again.", 500

        return redirect(url_for("login"))

    return render_template("registration.html")


# ==================================================
# 10. LOGIN
# ==================================================

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
            session.clear()
            session["user_id"] = user.id

            return redirect(url_for("dashboard"))

        return "Invalid email or password.", 401

    return render_template("login.html")


# ==================================================
# 11. DASHBOARD
# ==================================================

@app.route("/dashboard")
def dashboard():
    user_id = session.get("user_id")

    # Redirect users who are not signed in.
    if user_id is None:
        return redirect(url_for("login"))

    try:
        user = db.session.get(User, user_id)

        # Handle a session referring to a deleted user.
        if user is None:
            session.clear()
            return redirect(url_for("login"))

        product_count = Product.query.filter_by(
            user_id=user.id,
            is_active=True,
        ).count()

        low_stock_count = Product.query.filter(
            Product.user_id == user.id,
            Product.is_active.is_(True),
            Product.quantity <= Product.reorder_level,
        ).count()

        return render_template(
            "dashboard.html",
            username=user.username,
            product_count=product_count,
            low_stock_count=low_stock_count,
        )

    except SQLAlchemyError:
        db.session.rollback()
        app.logger.exception("Database error loading dashboard.")
        return "Unable to load dashboard. Please try again.", 500


# ==================================================
# 12. LIST PRODUCTS
# ==================================================

@app.route("/products")
def products():

    user = get_logged_in_user()

    if user is None:
        return redirect(url_for("login"))

    try:
        product_list = (
            Product.query
            .filter_by(
                user_id=user.id,
                is_active=True,
            )
            .order_by(Product.name.asc())
            .all()
        )

    except SQLAlchemyError:
        db.session.rollback()
        app.logger.exception("Could not load products.")
        return "Unable to load products. Please try again.", 500

    return render_template(
        "products.html",
        products=product_list,
    )


# ==================================================
# 13. ADD PRODUCT
# ==================================================

@app.route("/products/add", methods=["GET", "POST"])
def add_product():

    user = get_logged_in_user()

    if user is None:
        return redirect(url_for("login"))

    if request.method == "POST":

        try:
            data = parse_product_form()

            product = Product(
                user_id=user.id,
                **data,
            )

            db.session.add(product)
            db.session.commit()

            flash("Product added successfully.", "success")
            return redirect(url_for("products"))

        except (ValueError, InvalidOperation):
            db.session.rollback()
            flash(
                "Invalid product details. Check every field.",
                "error",
            )

        except IntegrityError:
            db.session.rollback()
            flash(
                "This SKU already exists in your inventory.",
                "error",
            )

        except SQLAlchemyError:
            db.session.rollback()
            app.logger.exception("Failed to add product.")
            flash("A database error occurred.", "error")

    return render_template("add_product.html")


# ==================================================
# 14. EDIT PRODUCT
# ==================================================

@app.route(
    "/products/<int:product_id>/edit",
    methods=["GET", "POST"],
)
def edit_product(product_id):

    user = get_logged_in_user()

    if user is None:
        return redirect(url_for("login"))

    product = Product.query.filter_by(
        id=product_id,
        user_id=user.id,
        is_active=True,
    ).first_or_404()

    if request.method == "POST":

        try:
            data = parse_product_form()

            for field, value in data.items():
                setattr(product, field, value)

            db.session.commit()

            flash("Product updated successfully.", "success")
            return redirect(url_for("products"))

        except (ValueError, InvalidOperation):
            db.session.rollback()
            flash(
                "Invalid product details. Check every field.",
                "error",
            )

        except IntegrityError:
            db.session.rollback()
            flash(
                "This SKU already exists in your inventory.",
                "error",
            )

        except SQLAlchemyError:
            db.session.rollback()
            app.logger.exception("Failed to update product.")
            flash("A database error occurred.", "error")

    return render_template(
        "edit_product.html",
        product=product,
    )


# ==================================================
# 15. DEACTIVATE PRODUCT
# ==================================================

@app.route(
    "/products/<int:product_id>/deactivate",
    methods=["POST"],
)
def deactivate_product(product_id):

    user = get_logged_in_user()

    if user is None:
        return redirect(url_for("login"))

    product = Product.query.filter_by(
        id=product_id,
        user_id=user.id,
        is_active=True,
    ).first_or_404()

    try:
        product.is_active = False
        db.session.commit()

        flash("Product deactivated successfully.", "success")

    except SQLAlchemyError:
        db.session.rollback()
        app.logger.exception("Failed to deactivate product.")
        flash("Unable to deactivate the product.", "error")

    return redirect(url_for("products"))


# ==================================================
# 16. LOGOUT
# ==================================================

@app.route("/logout", methods=["POST"])
def logout():

    session.clear()

    return redirect(url_for("login"))


# ==================================================
# 17. RUN APPLICATION
# ==================================================

if __name__ == "__main__":
    app.run(debug=True)
