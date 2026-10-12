"""itens da doação: validade, refrigeração e peso por item; agregados no lote; rascunho (Fase 3 Parte 1)

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-12

* `donation_items`: novos campos OPCIONAIS (nulos nos itens históricos simulados, que NÃO são alterados nem preenchidos com valores inventados).
* `donation_items.data_origin` passa a ser garantido igual ao da doação por FOREIGN KEY COMPOSTA (donation_id, data_origin) → donations(id, data_origin).
* `donations`: agregados do lote misto (categories, is_mixed_batch, aggregated_at, updated_at) e novo estado 'DRAFT' (rascunho).
* Reversível: o downgrade devolve os rascunhos ao estado 'PENDING_CONFIRMATION' (nenhuma doação é apagada) e remove apenas as colunas/constraints desta revisão.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None

STATUS_NOVO = "status IN ('DRAFT','PENDING_CONFIRMATION','READY','BLOCKED_EXPIRED','BLOCKED_NO_VALIDITY','MATCHING','MATCHED','NO_MATCH','HISTORICAL')"
STATUS_ANTIGO = "status IN ('PENDING_CONFIRMATION','READY','BLOCKED_EXPIRED','BLOCKED_NO_VALIDITY','MATCHING','MATCHED','NO_MATCH','HISTORICAL')"


def upgrade() -> None:
    # ---- donations: cabeçalho com agregados
    op.add_column('donations', sa.Column('categories', postgresql.ARRAY(sa.String(length=30)), nullable=True))
    op.add_column('donations', sa.Column('is_mixed_batch', sa.Boolean(), server_default=sa.text('false'), nullable=False))
    op.add_column('donations', sa.Column('aggregated_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('donations', sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True))
    op.drop_constraint('ck_donation_status', 'donations', type_='check')
    op.create_check_constraint('ck_donation_status', 'donations', STATUS_NOVO)
    op.create_unique_constraint('uq_donation_id_origin', 'donations', ['id', 'data_origin'])
    # ---- donation_items: novos campos (todos opcionais)
    op.add_column('donation_items', sa.Column('description', sa.String(length=160), nullable=True))
    op.add_column('donation_items', sa.Column('perecibilidade', sa.String(length=40), nullable=True))
    op.add_column('donation_items', sa.Column('exige_refrigeracao', sa.Boolean(), nullable=True))
    op.add_column('donation_items', sa.Column('validity_days', sa.Integer(), nullable=True))
    op.add_column('donation_items', sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('donation_items', sa.Column('validity_source', sa.String(length=32), nullable=True))
    op.add_column('donation_items', sa.Column('validity_precision', sa.String(length=10), nullable=True))
    op.add_column('donation_items', sa.Column('unit_weight', sa.Float(), nullable=True))
    op.add_column('donation_items', sa.Column('unit_weight_unit', sa.String(length=4), nullable=True))
    op.add_column('donation_items', sa.Column('weight_basis', sa.String(length=24), nullable=True))
    op.add_column('donation_items', sa.Column('entry_source', sa.String(length=20), nullable=True))
    op.add_column('donation_items', sa.Column('pending_fields', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column('donation_items', sa.Column('parser_suggestion', postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column('donation_items', sa.Column('created_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('donation_items', sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True))
    op.create_check_constraint('ck_ditem_uw_unit', 'donation_items', "unit_weight_unit IS NULL OR unit_weight_unit IN ('kg','g','l','ml')")
    op.create_check_constraint('ck_ditem_uw_pos', 'donation_items', "unit_weight IS NULL OR unit_weight > 0")
    op.create_check_constraint('ck_ditem_uw_pair', 'donation_items', "(unit_weight IS NULL) = (unit_weight_unit IS NULL)")
    op.create_check_constraint('ck_ditem_wbasis', 'donation_items', "weight_basis IS NULL OR weight_basis IN ('MASSA_INFORMADA','VOLUME_CONVERTIDO','MASSA_UNITARIA_CATEGORIA')")
    op.create_check_constraint('ck_ditem_vprec', 'donation_items', "validity_precision IS NULL OR validity_precision IN ('DAY','MONTH')")
    op.create_check_constraint('ck_ditem_source', 'donation_items', "entry_source IS NULL OR entry_source IN ('MANUAL','TEXTO_SUGERIDO')")
    # ---- data_origin do item == data_origin da doação (FK composta substitui a FK simples; falha aqui se algum item histórico divergisse)
    op.drop_constraint('donation_items_donation_id_fkey', 'donation_items', type_='foreignkey')
    op.create_foreign_key('fk_ditem_donation_origin', 'donation_items', 'donations', ['donation_id', 'data_origin'], ['id', 'data_origin'])


def downgrade() -> None:
    op.drop_constraint('fk_ditem_donation_origin', 'donation_items', type_='foreignkey')
    op.create_foreign_key('donation_items_donation_id_fkey', 'donation_items', 'donations', ['donation_id'], ['id'])
    for ck in ('ck_ditem_source', 'ck_ditem_vprec', 'ck_ditem_wbasis', 'ck_ditem_uw_pair', 'ck_ditem_uw_pos', 'ck_ditem_uw_unit'):
        op.drop_constraint(ck, 'donation_items', type_='check')
    for col in ('updated_at', 'created_at', 'parser_suggestion', 'pending_fields', 'entry_source', 'weight_basis', 'unit_weight_unit', 'unit_weight', 'validity_precision',
                'validity_source', 'expires_at', 'validity_days', 'exige_refrigeracao', 'perecibilidade', 'description'):
        op.drop_column('donation_items', col)
    op.drop_constraint('uq_donation_id_origin', 'donations', type_='unique')
    # rascunhos voltam a "pendente de confirmação": nenhuma doação é apagada
    op.execute("UPDATE donations SET status = 'PENDING_CONFIRMATION' WHERE status = 'DRAFT'")
    op.drop_constraint('ck_donation_status', 'donations', type_='check')
    op.create_check_constraint('ck_donation_status', 'donations', STATUS_ANTIGO)
    for col in ('updated_at', 'aggregated_at', 'is_mixed_batch', 'categories'):
        op.drop_column('donations', col)
