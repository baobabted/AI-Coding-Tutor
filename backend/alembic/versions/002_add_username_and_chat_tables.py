"""Add username, effective levels, and chat tables

Revision ID: 002
Revises: 001

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add username column to users (NOT NULL, indexed)
    op.add_column(
        "users", sa.Column("username", sa.String(50), nullable=False, server_default="user")
    )
    op.create_index(op.f("ix_users_username"), "users", ["username"], unique=False)

    # Add effective level columns
    op.add_column(
        "users", sa.Column("effective_programming_level", sa.Float(), nullable=True)
    )
    op.add_column(
        "users", sa.Column("effective_maths_level", sa.Float(), nullable=True)
    )

    # Remove the server_default from username after migration
    op.alter_column("users", "username", server_default=None)

    # Create chat_sessions table
    op.create_table(
        "chat_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_type", sa.String(20), nullable=False, server_default="general"),
        sa.Column("module_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(), nullable=True, server_default=sa.text("now()")
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_chat_sessions_user_type", "chat_sessions", ["user_id", "session_type"]
    )

    # Create chat_messages table
    op.create_table(
        "chat_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role", sa.String(10), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("hint_level_used", sa.Integer(), nullable=True),
        sa.Column("problem_difficulty", sa.Integer(), nullable=True),
        sa.Column("maths_difficulty", sa.Integer(), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(), nullable=True, server_default=sa.text("now()")
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["session_id"], ["chat_sessions.id"], ondelete="CASCADE"
        ),
    )
    op.create_index(
        "ix_chat_messages_session_created",
        "chat_messages",
        ["session_id", "created_at"],
    )

    # Create daily_token_usage table
    op.create_table(
        "daily_token_usage",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("input_tokens_used", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("output_tokens_used", sa.Integer(), nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_daily_token_usage_user_date",
        "daily_token_usage",
        ["user_id", "date"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_daily_token_usage_user_date", table_name="daily_token_usage")
    op.drop_table("daily_token_usage")

    op.drop_index("ix_chat_messages_session_created", table_name="chat_messages")
    op.drop_table("chat_messages")

    op.drop_index("ix_chat_sessions_user_type", table_name="chat_sessions")
    op.drop_table("chat_sessions")

    op.drop_column("users", "effective_maths_level")
    op.drop_column("users", "effective_programming_level")
    op.drop_index(op.f("ix_users_username"), table_name="users")
    op.drop_column("users", "username")
