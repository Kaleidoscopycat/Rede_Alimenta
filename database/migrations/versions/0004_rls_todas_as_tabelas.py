"""RLS em todas as tabelas do schema da aplicação + revogação dos papéis anon/authenticated (Fase 3 Parte 2 · Etapa B)

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-13

Contexto: o Supabase expõe uma API REST automática (PostgREST) sobre as tabelas do schema `public`. A ÚNICA porta de entrada dos dados da Rede Alimenta IA é a nossa API,
que conecta com o papel dono das tabelas (o dono ignora RLS; não usamos FORCE). Com RLS habilitado e SEM nenhuma policy, os papéis `anon` e `authenticated` não leem nem gravam nada,
e os privilégios deles são revogados (defesa em profundidade).

* Roda também no PostgreSQL local/Compose, onde `anon` e `authenticated` NÃO existem (a revogação só ocorre para papéis existentes).
* Cobre TODAS as tabelas existentes do schema, inclusive `alembic_version`. Tabelas criadas por migrations futuras precisam habilitar RLS (o teste `test_rls_em_todas_as_tabelas` falha se alguma ficar sem).
* Reversível: o downgrade desabilita RLS em todas as tabelas. Os privilégios revogados NÃO são devolvidos aos papéis do Supabase (escolha deliberada: o estado seguro é manter o acesso fechado).
"""
from alembic import op

revision = '0004'
down_revision = '0003'
branch_labels = None
depends_on = None

_ENABLE = """
DO $$
DECLARE t record;
BEGIN
  FOR t IN SELECT tablename FROM pg_tables WHERE schemaname = current_schema() LOOP
    EXECUTE format('ALTER TABLE %I.%I ENABLE ROW LEVEL SECURITY', current_schema(), t.tablename);
  END LOOP;
END $$;
"""

_REVOKE = """
DO $$
DECLARE r text;
BEGIN
  FOREACH r IN ARRAY ARRAY['anon', 'authenticated'] LOOP
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r) THEN
      EXECUTE format('REVOKE ALL ON ALL TABLES IN SCHEMA %I FROM %I', current_schema(), r);
      EXECUTE format('REVOKE ALL ON ALL SEQUENCES IN SCHEMA %I FROM %I', current_schema(), r);
      EXECUTE format('ALTER DEFAULT PRIVILEGES IN SCHEMA %I REVOKE ALL ON TABLES FROM %I', current_schema(), r);
      EXECUTE format('ALTER DEFAULT PRIVILEGES IN SCHEMA %I REVOKE ALL ON SEQUENCES FROM %I', current_schema(), r);
    END IF;
  END LOOP;
END $$;
"""

_DISABLE = """
DO $$
DECLARE t record;
BEGIN
  FOR t IN SELECT tablename FROM pg_tables WHERE schemaname = current_schema() LOOP
    EXECUTE format('ALTER TABLE %I.%I DISABLE ROW LEVEL SECURITY', current_schema(), t.tablename);
  END LOOP;
END $$;
"""


def upgrade() -> None:
    op.execute(_ENABLE)
    op.execute(_REVOKE)


def downgrade() -> None:
    op.execute(_DISABLE)
