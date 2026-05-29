"""create ingest job tables

Revision ID: 9c518adb7515
Revises: 546fdb1e642a
Create Date: 2026-05-29 00:00:00.000000

"""
from __future__ import annotations

from collections.abc import Sequence
from typing import Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9c518adb7515'
down_revision: Union[str, Sequence[str], None] = '546fdb1e642a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'ingest_jobs',
        sa.Column('ingest_job_uuid', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('project_uuid', sa.Uuid(), nullable=False),
        sa.Column('project_document_uuid', sa.Uuid(), nullable=False),
        sa.Column('status', sa.Text(), server_default=sa.text("'queued'"), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint("status IN ('queued', 'running', 'done', 'failed')", name=op.f('ck_ingest_jobs_status')),
        sa.ForeignKeyConstraint(['project_document_uuid'], ['project_documents.project_document_uuid'], name=op.f('fk_ingest_jobs_project_document_uuid_project_documents'), ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['project_uuid'], ['projects.project_uuid'], name=op.f('fk_ingest_jobs_project_uuid_projects'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('ingest_job_uuid', name=op.f('pk_ingest_jobs')),
    )
    op.create_index(op.f('ix_ingest_jobs_project_document_uuid'), 'ingest_jobs', ['project_document_uuid'], unique=False)
    op.create_index(op.f('ix_ingest_jobs_project_uuid'), 'ingest_jobs', ['project_uuid'], unique=False)
    op.create_table(
        'ingest_job_events',
        sa.Column('ingest_job_event_uuid', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('ingest_job_uuid', sa.Uuid(), nullable=False),
        sa.Column('event', sa.Text(), nullable=False),
        sa.Column('phase', sa.Text(), nullable=True),
        sa.Column('message', sa.Text(), nullable=True),
        sa.Column('ts', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint("event IN ('ingest_started', 'ingest_progress', 'ingest_completed', 'ingest_error')", name=op.f('ck_ingest_job_events_event')),
        sa.ForeignKeyConstraint(['ingest_job_uuid'], ['ingest_jobs.ingest_job_uuid'], name=op.f('fk_ingest_job_events_ingest_job_uuid_ingest_jobs'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('ingest_job_event_uuid', name=op.f('pk_ingest_job_events')),
    )
    op.create_index(op.f('ix_ingest_job_events_ingest_job_uuid'), 'ingest_job_events', ['ingest_job_uuid'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_ingest_job_events_ingest_job_uuid'), table_name='ingest_job_events')
    op.drop_table('ingest_job_events')
    op.drop_index(op.f('ix_ingest_jobs_project_uuid'), table_name='ingest_jobs')
    op.drop_index(op.f('ix_ingest_jobs_project_document_uuid'), table_name='ingest_jobs')
    op.drop_table('ingest_jobs')
