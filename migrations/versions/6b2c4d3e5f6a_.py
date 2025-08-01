"""Add utility account type

Revision ID: 6b2c4d3e5f6a
Revises: 5a1b3c2d4e5f
Create Date: 2025-07-16 13:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '6b2c4d3e5f6a'
down_revision = '5a1b3c2d4e5f'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.alter_column('account', 'type',
               existing_type=sa.VARCHAR(length=64),
               type=sa.String(length=64),
               existing_nullable=True)
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.alter_column('account', 'type',
               existing_type=sa.String(length=64),
               type=sa.VARCHAR(length=64),
               existing_nullable=True)
    # ### end Alembic commands ###
