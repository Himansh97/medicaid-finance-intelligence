"""Durable local synthetic fixture jobs."""
from alembic import op
revision = '0001_jobs'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.execute('CREATE SCHEMA operations')
    op.execute('''CREATE TABLE operations.jobs (
        id uuid PRIMARY KEY,
        idempotency_key varchar(128) NOT NULL UNIQUE,
        scenario text NOT NULL CHECK (scenario IN ('clean', 'defective')),
        status text NOT NULL DEFAULT 'QUEUED'
            CHECK (status IN ('QUEUED','RUNNING','SUCCEEDED','FAILED')),
        attempts integer NOT NULL DEFAULT 0 CHECK (attempts >= 0),
        max_attempts integer NOT NULL DEFAULT 3 CHECK (max_attempts BETWEEN 1 AND 5),
        lease_token uuid,
        lease_expires_at timestamptz,
        created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
        updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
        result jsonb,
        error_code text,
        CHECK ((status = 'RUNNING') = (lease_token IS NOT NULL AND lease_expires_at IS NOT NULL)),
        CHECK ((status = 'SUCCEEDED') = (result IS NOT NULL))
    )''')
    op.execute('CREATE INDEX jobs_claim ON operations.jobs (status, created_at)')


def downgrade():
    op.execute('DROP TABLE operations.jobs')
    op.execute('DROP SCHEMA operations')
