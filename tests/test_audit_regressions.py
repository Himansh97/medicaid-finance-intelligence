"""Hand-checked counterexamples for the September reporting audit."""
from pathlib import Path
import json
import pandas as pd
import pytest
from src.sdp import tableau_export as export
from src.sdp import readiness
from src.data_generation.build_fixture import build, connect
from src.validation.run_pipeline import run


def row(review='Renewal', amount=100, **changes):
    r = dict(sdp_identifier=f'VA_Fee_IPH_{review}_20240101-20241231',
             state_code='VA', state_name='Virginia', payment_type_normalised='FEE',
             provider_class='IPH', review_type=review,
             review_type_normalised='Amendment' if review.startswith('Amend') else review,
             rating_period_start='2024-01-01', rating_period_end='2024-12-31',
             identifier_suffix=None, amount_usd=amount,
             amount_cents=None if amount is None else amount*100,
             amount_is_publishable=amount is not None, federal_share_cents=None,
             amount_source='form_field', document_type='approval', description='test',
             grandfathered_cap_usd=500, grandfathered_cap_cents=50000,
             identifier_mismatch=None, source_url='https://example.org/test.pdf',
             source_sha256='test-only', retrieved_at='2026-09-30', extraction_version='test')
    r.update(changes)
    return r


@pytest.fixture
def source(tmp_path, monkeypatch):
    path = tmp_path/'sdp_arrangements.csv'
    monkeypatch.setattr(export, 'ARRANGEMENTS', path)
    ready = tmp_path/'readiness.json'
    ready.write_text(json.dumps({'newest_year': 2020, 'states': [{'state': 'Virginia', 'dq_assessment': 'Low concern', 'reports_usably': True}]}))
    monkeypatch.setattr(export, 'READINESS', ready)
    monkeypatch.setattr(readiness, 'OUT_DIR', tmp_path)
    def write(rows):
        pd.DataFrame(rows).to_csv(path, index=False)
    return write


def test_numeric_amendment_order(source):
    source([row('Amend', 100), row('Amend2', 200)])
    out = export.build()
    assert out.amount_usd.tolist() == [200]


def test_missing_latest_does_not_resurrect_older_amount(source):
    source([row('Amend', 100), row('Amend2', None)])
    out = export.build()
    assert len(out) == 1
    assert out.amount_usd.isna().all()
    assert out.sdp_identifier.iloc[0].endswith('Amend2_20240101-20241231')


def test_suffix_distinguishes_arrangements(source):
    source([row(sdp_identifier='VA_Fee_IPH_Renewal_20240101-20241231 A', identifier_suffix='A'),
            row(sdp_identifier='VA_Fee_IPH_Renewal_20240101-20241231 B', identifier_suffix='B')])
    assert len(export.build()) == 2


def test_same_rank_is_unresolved_not_alphabetical(source):
    source([row('Amend', 100), row('Amend1', 200)])
    out = export.build()
    assert out.amount_usd.isna().all()
    assert set(out.lineage_status) == {'AMBIGUOUS'}


def test_optional_readiness_remains_unknown(source):
    export.READINESS.unlink()
    source([row()])
    out = export.build()
    assert out.dq_assessment_year.isna().all()
    assert out.reports_usably.isna().all()


def test_state_cap_not_repeated_in_arrangement_table(source):
    source([row(), row(provider_class='OPH', sdp_identifier='VA_Fee_OPH_Renewal_20240101-20241231')])
    assert 'state_grandfathered_cap_usd' not in export.build().columns


def test_readiness_selects_one_year_and_latest_amount(source):
    source([row('Renewal', 100), row('Amend2', 200),
            row('Renewal', 900, rating_period_start='2023-01-01', rating_period_end='2023-12-31',
                sdp_identifier='VA_Fee_IPH_Renewal_20230101-20231231')])
    assert readiness.sdp_dollars_by_state(2024) == {'Virginia': 200}


@pytest.mark.parametrize('market,plan', [('SYN_MKT_B', 'SYN_PLAN_B_FFS'),
                                        ('SYN_MKT_A', 'SYN_PLAN_A1')])
def test_claim_assignment_mismatch_blocks_and_excludes(tmp_path, market, plan):
    db = tmp_path/'fixture.db'
    build(db)
    with connect(db) as conn:
        family = conn.execute("SELECT claim_family_id FROM raw_claim_header WHERE market_id='SYN_MKT_A' AND record_type='FFS' AND status='ACCEPTED' LIMIT 1").fetchone()[0]
        conn.execute('UPDATE raw_claim_header SET market_id=?, plan_id=? WHERE claim_family_id=?', (market, plan, family))
    run(db)
    with connect(db) as conn:
        matches = conn.execute('SELECT population_match FROM fact_claim_header_final WHERE claim_family_key LIKE ?', ('%' + family,)).fetchall()
        assert matches and all(m[0] == 'CONFLICTING_EXPOSURE' for m in matches)
        assert conn.execute("SELECT disposition FROM dq_result WHERE rule_id='DQ_CLAIM_POPULATION_MATCH'").fetchone()[0] == 'FAIL'


def test_caps_have_one_state_row_and_document_basis(source):
    source([row(), row(provider_class='OPH', sdp_identifier='second')])
    caps = export.build_caps()
    assert len(caps) == 1
    assert caps.cap_document_sum_usd.tolist() == [1000]
    assert caps.cap_document_count.tolist() == [2]


def test_all_unknown_state_is_not_zero(source):
    source([row('Renewal', 100), row('Amend2', None)])
    result = readiness.attach_sdp_amounts({'states': [{'state': 'Virginia'}]}, 2024)
    assert result['states'][0]['sdp_amount_usd'] is None
    assert result['states'][0]['sdp_unknown_arrangements'] == 1


def test_unknown_review_type_cannot_be_assumed_superseded(source):
    source([row('Renewal', 100), row('Unknown', None)])
    out = export.build()
    assert out.amount_usd.isna().all()
    assert set(out.lineage_status) == {'AMBIGUOUS'}


def test_no_selected_period_has_no_state_amounts(source):
    source([row()])
    assert readiness.sdp_dollars_by_state(2030) == {}


def test_publisher_preserves_manifest_entries_without_extraction(tmp_path, monkeypatch):
    from src.sdp import publish
    manifest = tmp_path/'manifest.json'
    extract = tmp_path/'extract.json'
    manifest.write_text(json.dumps({'retrieved_at': '2026-09-30', 'preprints': [
        {'sdp_identifier': 'TEST_KNOWN', 'pdf_url': 'https://example.org/a.pdf'},
        {'sdp_identifier': 'TEST_UNREADABLE', 'pdf_url': 'https://example.org/b.pdf'}]}))
    extract.write_text(json.dumps({'records': [{'sdp_identifier': 'TEST_KNOWN',
        'letter_type': 'approval', 'amount_cents': 12345}]}))
    monkeypatch.setattr(publish, 'MANIFEST', manifest)
    monkeypatch.setattr(publish, 'EXTRACT', extract)
    rows = publish.build_rows()
    assert [r['sdp_identifier'] for r in rows] == ['TEST_KNOWN', 'TEST_UNREADABLE']
    assert [r['amount_cents'] for r in rows] == [12345, None]
