from app.modules.quarantine.service import evidence_csv
from app.modules.quarantine.diagnose import classify

def test_reason_count(dirty):
    assert dirty['quarantine']['total']==12;assert dirty['quarantine']['counts']['AMENDED']==3

def test_reason_text(dirty):
    assert any(r['reason']=='签发早于接收' for r in dirty['quarantine']['rows'])

def test_filtered(dirty):
    r=classify(dirty['quarantine']['rows'],'AMENDED');assert len(r['rows'])==3
    assert all(row['superseded_by'] for row in r['rows'])

def test_amended_evidence_kept(dirty):
    row=next(r for r in dirty['quarantine']['rows'] if r['code']=='AMENDED' and r['line']==3)
    assert row['raw']['specimen']=='000002';assert row['raw']['released']=='2026-11-02T12:00:00+08:00'
    assert row['superseded_by']==52

def test_revoked_attempt_kept(dirty):
    row=next(r for r in dirty['quarantine']['rows'] if r['line']==53)
    assert row['code']=='REVERSED'

def test_csv_evidence(dirty):
    s=evidence_csv(dirty['quarantine']['rows']);assert s.startswith('\ufeffline,code,reason,raw');assert s.count('\n')==13

def test_clean_no_reject(clean):
    assert clean['quarantine']['total']==0;assert clean['quarantine']['rows']==[]

def test_counts_equal(dirty):
    assert sum(dirty['quarantine']['counts'].values())==len(dirty['quarantine']['rows'])

def test_raw_retained(dirty):
    r=next(i for i in dirty['quarantine']['rows'] if i['code']=='MISSING');assert r['raw']['received']=='N/A'
