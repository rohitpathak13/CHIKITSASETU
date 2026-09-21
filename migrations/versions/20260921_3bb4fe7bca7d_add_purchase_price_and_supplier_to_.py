"""add_purchase_price_and_supplier_to_medicines

Revision ID: 3bb4fe7bca7d
Revises: c7363561e48f
Create Date: 2026-09-21 10:41:51.804711

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3bb4fe7bca7d'
down_revision: Union[str, None] = 'c7363561e48f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('medicines', schema=None) as batch_op:
        batch_op.add_column(sa.Column('purchase_price', sa.Numeric(precision=10, scale=2), nullable=True, server_default='0.00'))
        batch_op.add_column(sa.Column('supplier', sa.String(length=150), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('medicines', schema=None) as batch_op:
        batch_op.drop_column('supplier')
        batch_op.drop_column('purchase_price')
