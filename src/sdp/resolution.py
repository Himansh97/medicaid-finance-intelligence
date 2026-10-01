"""Conservative filename-based version selection, not verified legal lineage.

Resolve before filtering amounts. Suffixes identify distinct arrangements.
Unknown review types or tied versions cannot establish a current amount.
"""
import re
import pandas as pd

ARRANGEMENT_KEY = ['state_code', 'payment_type_normalised', 'provider_class',
                   'rating_period_start', 'rating_period_end', 'identifier_suffix']
RESOLUTION_VERSION = '0.6.0'


def version_rank(value):
    value = str(value).strip().lower()
    if value == 'new':
        return 0
    if value == 'renewal':
        return 1
    match = re.fullmatch(r'amend(?:ment)?(\d*)', value)
    return 1 + int(match[1] or 1) if match else None


def resolve(frame):
    """One row per candidate family, with unknown amounts preserved as null.

    The retained row in an ambiguous family is only a metadata representative;
    candidate_identifiers lists every input, and no financial value is exposed.
    """
    data = frame.copy()
    data['identifier_suffix'] = data['identifier_suffix'].fillna('')
    data['_rank'] = data['review_type'].map(version_rank)
    rows = []
    for _, group in data.groupby(ARRANGEMENT_KEY, dropna=False, sort=False):
        top = group[group['_rank'] == group['_rank'].max()]
        ambiguous = group['_rank'].isna().any() or len(top) != 1
        selected = (group if ambiguous else top).sort_values('sdp_identifier').iloc[0].copy()
        selected['lineage_status'] = ('AMBIGUOUS' if ambiguous else
                                      'SINGLE_FILING' if len(group) == 1 else 'INFERRED_FROM_IDENTIFIER')
        selected['candidate_identifiers'] = ' | '.join(sorted(group.sdp_identifier))
        selected['resolution_version'] = RESOLUTION_VERSION
        usable = not ambiguous and selected['amount_is_publishable'] == True
        selected['amount_status'] = 'KNOWN' if usable else 'UNRESOLVED_LINEAGE' if ambiguous else 'MISSING_LATEST_AMOUNT'
        if not usable:
            for field in ('amount_usd', 'amount_cents', 'federal_share_cents', 'amount_source'):
                selected[field] = None
        selected['amount_is_publishable'] = usable
        rows.append(selected)
    if not rows:
        return data.drop(columns='_rank').assign(lineage_status='', candidate_identifiers='',
                                                 resolution_version='', amount_status='')
    return pd.DataFrame(rows).drop(columns='_rank').reset_index(drop=True)
