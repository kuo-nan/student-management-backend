"""rename student score to personal score

Revision ID: e7f8a9b0c1d2
Revises: 610f54cbe012
Create Date: 2026-11-08 17:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "e7f8a9b0c1d2"
down_revision: Union[str, Sequence[str], None] = "610f54cbe012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "student",
        "score",
        new_column_name="personal_score",
        existing_type=sa.Integer(),
        nullable=False,
        comment="学生个人评分，与课程和考试无关",
    )


def downgrade() -> None:
    op.alter_column(
        "student",
        "personal_score",
        new_column_name="score",
        existing_type=sa.Integer(),
        nullable=False,
        comment=None,
    )
