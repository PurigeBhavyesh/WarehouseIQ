from extensions import db


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