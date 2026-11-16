from collections import Counter
from app.reasons import REASONS

def classify(issues,code=None):
    rows=[dict(r,reason=REASONS.get(r['code'],r['code']),superseded_by=r.get('superseded_by','')) for r in issues if code is None or r['code']==code]
    return {'rows':rows,'counts':dict(Counter(r['code'] for r in rows)),'total':len(rows)}
