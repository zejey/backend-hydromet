"""initial_baseline

Revision ID: 0001
Revises: 
Create Date: 2026-04-16 13:24:34.992052

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0001'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Baseline schema — mirrors existing tables."""
    op.create_table(
        "admin",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("email", sa.String(255), unique=True, nullable=False),
        sa.Column("role", sa.String(50), server_default="admin"),
        sa.Column("username", sa.String(100), unique=True, nullable=False),
        sa.Column("uid", sa.String(255)),
        sa.Column("password_hash", sa.Text, nullable=False),
    )

    op.create_table(
        "users",
        sa.Column("id", sa.String(255), primary_key=True),
        sa.Column("first_name", sa.String(64), nullable=False),
        sa.Column("middle_name", sa.String(64)),
        sa.Column("last_name", sa.String(64), nullable=False),
        sa.Column("suffix", sa.String(16)),
        sa.Column("house_address", sa.Text, nullable=False),
        sa.Column("barangay", sa.String(64), nullable=False),
        sa.Column("phone_number", sa.String(11), unique=True, nullable=False),
        sa.Column("role", sa.String(32), server_default="resident"),
        sa.Column("is_verified", sa.Boolean, server_default="false"),
        sa.Column("password_hash", sa.Text),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )

    op.create_table(
        "barangays",
        sa.Column("id", sa.String(255), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("is_active", sa.Boolean, server_default="true"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )

    op.create_table(
        "emergency_hotlines",
        sa.Column("id", sa.String(255), primary_key=True),
        sa.Column("service_name", sa.String(255), nullable=False),
        sa.Column("phone_number", sa.String(50), nullable=False),
        sa.Column("category", sa.String(50), nullable=False),
        sa.Column("icon_color", sa.String(50)),
        sa.Column("icon_type", sa.String(50)),
        sa.Column("is_active", sa.Boolean, server_default="true"),
        sa.Column("priority", sa.Integer, server_default="0"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )

    op.create_table(
        "notifications",
        sa.Column("id", sa.String(255), primary_key=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("message", sa.Text),
        sa.Column("type", sa.String(50)),
        sa.Column("sent_to", sa.String(255)),
        sa.Column("status", sa.String(50)),
        sa.Column("date_time", sa.DateTime, server_default=sa.func.now()),
    )

    op.create_table(
        "user_notification_reads",
        sa.Column("user_id", sa.Text, nullable=False),
        sa.Column("notification_id", sa.Text, nullable=False),
        sa.Column("read_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("user_id", "notification_id"),
    )

    op.create_table(
        "safety_categories",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.Text),
        sa.Column("order_num", sa.Integer, server_default="1"),
        sa.Column("icon", sa.String(100)),
        sa.Column("gradient_colors", sa.Text),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("is_active", sa.Boolean, server_default="true"),
    )

    op.create_table(
        "safety_tips",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("category_id", sa.Integer, sa.ForeignKey("safety_categories.id", ondelete="CASCADE")),
        sa.Column("range_label", sa.String(100)),
        sa.Column("level", sa.String(50)),
        sa.Column("color", sa.String(50)),
        sa.Column("order_num", sa.Integer, server_default="1"),
        sa.Column("is_active", sa.Boolean, server_default="true"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )

    op.create_table(
        "safety_tip_details",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("tip_id", sa.Integer, sa.ForeignKey("safety_tips.id", ondelete="CASCADE")),
        sa.Column("description", sa.Text, nullable=False),
        sa.Column("order_num", sa.Integer, server_default="1"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )

    op.create_table(
        "government_agencies",
        sa.Column("id", sa.String(255), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("location_latitude", sa.Float),
        sa.Column("location_longitude", sa.Float),
        sa.Column("type", sa.String(100)),
        sa.Column("contact", sa.String(100)),
        sa.Column("facilities", sa.Text),
        sa.Column("description", sa.Text),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )

    op.create_table(
        "system_settings",
        sa.Column("key", sa.String(100), primary_key=True),
        sa.Column("value", sa.JSON, nullable=False),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
    )

    op.create_table(
        "system_logs",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("user_id", sa.Integer),
        sa.Column("user_label", sa.String(120)),
        sa.Column("role", sa.String(50)),
        sa.Column("action", sa.String(120), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("details", sa.Text, nullable=False),
        sa.Column("ip_address", sa.String(64)),
        sa.Column("user_agent", sa.Text),
    )

    op.create_table(
        "user_emails",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.String(255), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("is_verified", sa.Boolean, server_default="false"),
        sa.Column("is_primary", sa.Boolean, server_default="true"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )


def downgrade() -> None:
    """Drop all tables in reverse order."""
    op.drop_table("user_emails")
    op.drop_table("system_logs")
    op.drop_table("system_settings")
    op.drop_table("government_agencies")
    op.drop_table("safety_tip_details")
    op.drop_table("safety_tips")
    op.drop_table("safety_categories")
    op.drop_table("user_notification_reads")
    op.drop_table("notifications")
    op.drop_table("emergency_hotlines")
    op.drop_table("barangays")
    op.drop_table("users")
    op.drop_table("admin")
