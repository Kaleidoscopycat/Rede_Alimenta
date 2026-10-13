"""expiração opcional de token de usuário (Fase 3 Parte 2 · Etapa B)

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-13

`users.expires_at` é NULL para os usuários existentes (sem expiração, comportamento anterior). `scripts/create_user.py --expires-in-hours N` grava a data-limite;
depois dela o token deixa de autenticar (401 genérico). Reversível: o downgrade apenas remove a coluna.
"""
from alembic import op
import sqlalchemy as sa

revision = '0005'
down_revision = '0004'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('users', sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'expires_at')
