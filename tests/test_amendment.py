from app.pipeline import execute
from app.modules.contract.service import normalize
from app.modules.contract.versions import instant

HEADER='specimen,project,department,received,released,urgent\n'
BASE=('000100,BIO,门诊,2026-11-02T09:00:00+08:00,2026-11-02T11:00:00+08:00,0\n',
      '000101,HEM,住院,2026-11-02T09:00:00+08:00,2026-11-02T10:00:00+08:00,1\n')

def _rows(csv_text):
    from app.modules.intake.reader import read
    return read(csv_text.encode('utf-8'))['rows']

def _versions():
    from app.config import SAMPLES
    import json
    return json.loads((SAMPLES/'versions.json').read_text())

def test_amendment_becomes_current_record():
    csv=HEADER+BASE[0]+'000100,BIO,门诊,2026-11-02T09:00:00+08:00,2026-11-02T12:00:00+08:00,0\n'
    r=normalize(_rows(csv),_versions())
    assert len(r['rows'])==1
    current=r['rows'][0]
    assert current['released']=='2026-11-02T04:00:00+00:00'
    assert current['amended'] is True and current['replaces_line']==2
    retired=[i for i in r['issues'] if i['code']=='AMENDED']
    assert len(retired)==1 and retired[0]['line']==2 and retired[0]['superseded_by']==3
    assert retired[0]['raw']['released']=='2026-11-02T11:00:00+08:00'

def test_amendment_enters_sla_calculation():
    csv=HEADER+BASE[0]+'000100,BIO,门诊,2026-11-02T09:00:00+08:00,2026-11-02T14:00:00+08:00,0\n'
    bundle=execute(csv.encode('utf-8'))
    calc=next(r for r in bundle['calculate']['rows'] if r['specimen']=='000100')
    # 09:00 -> 14:00 working minutes are 240 (lunch excluded), over the BIO 180 limit; the old 120-minute version would pass.
    assert calc['elapsed_minutes']=='240.0' and calc['state']=='超时'
    assert bundle['reconcile']['balanced']

def test_identical_retry_does_not_add_record():
    csv=HEADER+BASE[0]+BASE[0]+BASE[0]
    r=normalize(_rows(csv),_versions())
    assert len(r['rows'])==1
    assert sum(i['code']=='DUPLICATE' for i in r['issues'])==2
    assert r['revisions']==[]

def test_identical_retry_of_amendment_does_not_add_record():
    amended='000100,BIO,门诊,2026-11-02T09:00:00+08:00,2026-11-02T12:00:00+08:00,0\n'
    csv=HEADER+BASE[0]+amended+amended
    r=normalize(_rows(csv),_versions())
    assert len(r['rows'])==1
    assert r['rows'][0]['line']==3
    assert sum(i['code']=='DUPLICATE' for i in r['issues'])==1
    assert len(r['revisions'])==1 and r['revisions'][0]['applied']

def test_failed_amendment_restores_old_version():
    bad='000100,BIO,门诊,2026-11-02T09:00:00+08:00,2026-11-02T08:00:00+08:00,0\n'
    csv=HEADER+BASE[0]+bad+bad
    r=normalize(_rows(csv),_versions())
    assert len(r['rows'])==1
    current=r['rows'][0]
    assert current['line']==2 and 'amended' not in current
    assert sum(i['code']=='REVERSED' for i in r['issues'])==2
    rejected=[v for v in r['revisions'] if not v['applied']]
    assert len(rejected)==2
    assert rejected[0]['rejected_code']=='REVERSED'
    assert rejected[0]['previous_line']==2 and rejected[0]['current_line']==2

def test_failed_amendment_then_successful_one():
    bad='000100,BIO,门诊,2026-11-02T09:00:00+08:00,2026-11-02T08:00:00+08:00,0\n'
    good='000100,BIO,门诊,2026-11-02T09:00:00+08:00,2026-11-02T12:00:00+08:00,0\n'
    csv=HEADER+BASE[0]+bad+good
    r=normalize(_rows(csv),_versions())
    assert len(r['rows'])==1 and r['rows'][0]['line']==4 and r['rows'][0]['amended']
    statuses=sorted((v['applied'],v['current_line']) for v in r['revisions'])
    assert statuses==[(False,2),(True,4)]

def test_chained_amendments_keep_full_history():
    second='000100,BIO,门诊,2026-11-02T09:00:00+08:00,2026-11-02T12:00:00+08:00,0\n'
    third='000100,BIO,住院,2026-11-02T09:00:00+08:00,2026-11-02T12:00:00+08:00,0\n'
    csv=HEADER+BASE[0]+second+third
    r=normalize(_rows(csv),_versions())
    current=r['rows'][0]
    assert current['line']==4 and current['department']=='住院' and current['replaces_line']==3
    assert [i['line'] for i in r['issues'] if i['code']=='AMENDED']==[2,3]
    assert [v['previous_line'] for v in r['revisions']]==[2,3]
    assert r['revisions'][1]['changes']==[{'field':'department','old':'门诊','new':'住院'}]

def test_original_record_and_source_retained():
    csv=HEADER+BASE[0]+'000100,BIO,门诊,2026-11-02T09:00:00+08:00,2026-11-02T12:00:00+08:00,0\n'
    r=normalize(_rows(csv),_versions())
    revision=r['revisions'][0]
    assert revision['previous_raw']['line']==2
    assert revision['previous_raw']['released']=='2026-11-02T11:00:00+08:00'
    assert revision['current_raw']['line']==3
    assert {c['field'] for c in revision['changes']}=={'released'}

def test_input_conservation_through_pipeline():
    bad='000100,BIO,门诊,2026-11-02T09:00:00+08:00,2026-11-02T08:00:00+08:00,0\n'
    good='000100,BIO,门诊,2026-11-02T09:00:00+08:00,2026-11-02T12:00:00+08:00,0\n'
    csv=HEADER+BASE[0]+BASE[1]+bad+good
    bundle=execute(csv.encode('utf-8'))
    rec=bundle['reconcile']
    assert rec['input']==rec['output']+rec['isolated']+rec['blank']
    assert rec['balanced']
    # Every physical row is either the current record or one quarantine issue.
    intake_rows=len(bundle['intake']['rows'])
    assert rec['output']+sum(1 for i in bundle['quarantine']['rows'] if i['code']!='COLUMN_COUNT')==intake_rows

def test_dirty_sample_amendment_flow():
    bundle=execute((__import__('app.config',fromlist=['SAMPLES']).SAMPLES/'dirty.csv').read_bytes())
    current=next(r for r in bundle['contract']['rows'] if r['specimen']=='000002')
    # The latest retransmission (line 55, 13:00) wins; earlier 12:30 amendment was itself superseded.
    assert current['line']==55 and current['amended']
    assert current['released']=='2026-11-02T05:00:00+00:00'
    # Specimen 000003's bad amendment leaves the original computable.
    specimen3=next(r for r in bundle['contract']['rows'] if r['specimen']=='000003')
    assert specimen3['line']==4 and 'amended' not in specimen3
    revoked=next(v for v in bundle['contract']['revisions'] if v['specimen']=='000003')
    assert revoked['applied'] is False and revoked['rejected_code']=='REVERSED'
    assert bundle['reconcile']['balanced']
