"""Submission readiness must inspect evidence, never trust a status string."""
from pathlib import Path
import sqlite3
import pytest
from src.data_generation.build_fixture import build, connect
from src.data_generation import fixture as fx
from src.validation.run_pipeline import run
from src.releases.preflight import assess


@pytest.fixture
def clean_db(tmp_path, request):
    db = tmp_path / 'clean.db'
    build(db)
    # Repair planted inputs before transformation; never edit outcomes to pass.
    with connect(db) as conn:
        conn.execute("DELETE FROM raw_eligibility_span WHERE source_row_id='ELG_008'")
        conn.execute("UPDATE raw_claim_line SET service_code='SVC_PROF_01' WHERE service_code='SVC_UNMAPPED_99'")
        conn.execute("INSERT INTO source_file VALUES (?,?,?,?,?,?,?,?,?)", (
            'TEST_EMPTY_C_FEB', fx.RUN_ID, 'synthetic', 'claims', 'SYN_MKT_C',
            '2026-02-01', 'test-empty-file-hash', 0, fx.INGESTED_AT))
        if getattr(request, 'param', False):
            conn.execute("UPDATE raw_claim_header SET member_id='SYN_M005' WHERE member_id='SYN_M001'")
    assert run(db)['status'] == 'READY_FOR_REVIEW'
    return db


def test_clean_run_is_eligible_but_not_certified(clean_db):
    before = clean_db.read_bytes()
    result = assess(clean_db, fx.RUN_ID)
    assert result['eligible_for_submission'] is True
    assert result['blockers'] == []
    assert result['expected_checks'] == 14
    assert clean_db.read_bytes() == before


def test_planted_defects_cannot_be_hidden_by_status(tmp_path):
    db = tmp_path/'defective.db'
    build(db)
    run(db)
    with connect(db) as conn:
        conn.execute("UPDATE pipeline_run SET status='READY_FOR_REVIEW'")
    result = assess(db, fx.RUN_ID)
    assert not result['eligible_for_submission']
    assert len([b for b in result['blockers'] if b['code'] == 'RULE_NOT_PASSED']) == 3


@pytest.mark.parametrize('mutation,code', [
    ("DELETE FROM dq_result WHERE rule_id='DQ_HEADER_LINE_BALANCE'", 'MISSING_CHECK'),
    ("UPDATE dq_result SET rule_version='old' WHERE rule_id='DQ_CLAIM_POPULATION_MATCH'", 'MISSING_CHECK'),
    ("UPDATE dq_result SET disposition='NOT_EVALUATED' WHERE rule_id='DQ_HEADER_LINE_BALANCE'", 'RULE_NOT_PASSED'),
    ("UPDATE pipeline_run SET status='CREATED'", 'RUN_NOT_READY'),
    ("DELETE FROM dq_result WHERE rule_id='DQ_MISSING_MARKET_FEED' AND market_id='SYN_MKT_C' AND month_start='2026-02-01'", 'MISSING_CHECK'),
    ("UPDATE dq_result SET severity='WARNING', disposition='ACCEPTED_WITH_REASON' WHERE rule_id='DQ_HEADER_LINE_BALANCE'", 'RULE_NOT_PASSED'),
    ("UPDATE dq_result SET failing_row_count=1 WHERE rule_id='DQ_HEADER_LINE_BALANCE'", 'RULE_NOT_PASSED'),
    ("DELETE FROM expected_partition", 'NO_EXPECTED_PARTITIONS'),
])
def test_incomplete_or_inconsistent_evidence_blocks(clean_db, mutation, code):
    with connect(clean_db) as conn:
        conn.execute(mutation)
    result = assess(clean_db, fx.RUN_ID)
    assert not result['eligible_for_submission']
    assert code in {b['code'] for b in result['blockers']}


def test_unknown_run_is_not_ready(clean_db):
    result = assess(clean_db, 'UNKNOWN')
    assert not result['eligible_for_submission']
    assert result['blockers'][0]['code'] == 'UNKNOWN_RUN'


def test_no_database_is_created_for_wrong_path(tmp_path):
    db = tmp_path/'missing.db'
    with pytest.raises(FileNotFoundError):
        assess(db, fx.RUN_ID)
    assert not db.exists()


@pytest.mark.parametrize('clean_db', [True], indirect=True)
def test_legitimate_cohort_exclusion_is_not_a_quality_failure(clean_db):
    with connect(clean_db) as conn:
        rule = conn.execute("SELECT disposition, failing_row_count, financial_impact_cents FROM dq_result WHERE rule_id='DQ_CLAIM_POPULATION_MATCH'").fetchone()
        assert rule == ('PASS', 0, 0)
        assert conn.execute("SELECT COUNT(*) FROM fact_claim_header_final WHERE population_match='OUT_OF_COHORT'").fetchone()[0] > 0
        assert conn.execute("SELECT SUM(ffs_paid_cents) FROM v_kpi_ffs_month WHERE market_key=1").fetchone()[0] == 0
    assert assess(clean_db, fx.RUN_ID)['eligible_for_submission']
