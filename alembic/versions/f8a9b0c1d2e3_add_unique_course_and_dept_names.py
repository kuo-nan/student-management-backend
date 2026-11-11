"""add unique course and dept names

Revision ID: f8a9b0c1d2e3
Revises: e7f8a9b0c1d2
Create Date: 2026-11-11
"""

from typing import Sequence, Union

from sqlalchemy import inspect, text

from alembic import op

revision: str = "f8a9b0c1d2e3"
down_revision: Union[str, Sequence[str], None] = "e7f8a9b0c1d2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

DEPT_CONSTRAINT = "uk_dept_name"
COURSE_CONSTRAINT = "uk_course_name"


def _unique_constraint_exists(
    connection,
    table_name: str,
    column_name: str,
) -> bool:
    inspector = inspect(connection)
    constraints = inspector.get_unique_constraints(table_name)
    if any(
        item.get("column_names") == [column_name] for item in constraints
    ):
        return True
    indexes = inspector.get_indexes(table_name)
    return any(
        item.get("unique") and item.get("column_names") == [column_name]
        for item in indexes
    )


def _assert_names_are_unique(
    connection,
    table_name: str,
    column_name: str,
) -> None:
    duplicate_count = connection.execute(
        text(
            f"""
            SELECT COUNT(*)
            FROM (
                SELECT {column_name}
                FROM {table_name}
                GROUP BY {column_name}
                HAVING COUNT(*) > 1
            ) AS duplicated_names
            """
        )
    ).scalar_one()
    if duplicate_count:
        raise RuntimeError(
            f"{table_name}.{column_name} contains duplicate values; "
            "resolve them before applying this migration"
        )


def upgrade() -> None:
    connection = op.get_bind()

    _assert_names_are_unique(connection, "dept", "dept_name")
    _assert_names_are_unique(connection, "course", "course_name")

    if not _unique_constraint_exists(connection, "dept", "dept_name"):
        op.create_unique_constraint(DEPT_CONSTRAINT, "dept", ["dept_name"])
    if not _unique_constraint_exists(connection, "course", "course_name"):
        op.create_unique_constraint(COURSE_CONSTRAINT, "course", ["course_name"])


def downgrade() -> None:
    connection = op.get_bind()

    if _unique_constraint_exists(connection, "course", "course_name"):
        op.drop_constraint(COURSE_CONSTRAINT, "course", type_="unique")
    if _unique_constraint_exists(connection, "dept", "dept_name"):
        op.drop_constraint(DEPT_CONSTRAINT, "dept", type_="unique")
