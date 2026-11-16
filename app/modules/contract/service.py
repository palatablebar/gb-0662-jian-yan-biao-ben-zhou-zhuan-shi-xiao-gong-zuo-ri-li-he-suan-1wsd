from app.modules.contract.versions import instant,select
from app.errors import RuleError
from app.reasons import SENTINELS

FIELDS=('project','department','received','released','urgent')

def _signature(row):
    return tuple(row[k].strip() for k in FIELDS)

def _validate(row,specimen,versions):
    """Return the normalized computable record, or raise a RuleError carrying the reject reason."""
    if any(row[k].strip() in SENTINELS for k in ('specimen','project','department','received','released')):
        raise RuleError('MISSING','标本必填项缺失')
    a=instant(row['received']);b=instant(row['released'])
    if b<a:raise RuleError('REVERSED','签发早于接收')
    if (b-a).total_seconds()>31*86400:raise RuleError('TOO_LONG','周转跨度超过31天')
    if row['urgent'].strip() not in ('0','1'):raise RuleError('URGENT','急诊标志只能为0或1')
    version=select(row['project'].strip(),a,versions)
    return dict(row,specimen=specimen,received=a.isoformat(),released=b.isoformat(),urgent=row['urgent'].strip()=='1',sla=version['urgent_sla'] if row['urgent'].strip()=='1' else version['sla'],rule_version=version['version'])

def normalize(rows,versions):
    valid=[];issues=[];revisions=[];groups={}
    for row in rows:groups.setdefault(row['specimen'].strip(),[]).append(row)
    # Physical line order decides chronology: later lines are instrument retransmissions.
    for specimen,items in groups.items():
        items.sort(key=lambda r:r['line'])
        current=None;current_raw=None
        for row in items:
            if current is None:
                try:
                    current=_validate(row,specimen,versions);current_raw=row
                except RuleError as e:
                    issues.append({'line':row['line'],'code':e.code,'raw':row})
                continue
            if _signature(row)==_signature(current_raw):
                # Identical retransmission (retry of the same correction): never adds a new record.
                issues.append({'line':row['line'],'code':'DUPLICATE','raw':row});continue
            # A changed retransmission is an amendment: validate it before touching the current record.
            try:
                candidate=_validate(row,specimen,versions)
            except RuleError as e:
                # Amendment failed midway: keep the previous version as the computable record.
                issues.append({'line':row['line'],'code':e.code,'raw':row})
                revisions.append({'specimen':specimen,'applied':False,'rejected_code':e.code,
                    'rejected_line':row['line'],'rejected_raw':dict(row),
                    'previous_line':current_raw['line'],'current_line':current_raw['line'],
                    'changes':[{'field':k,'old':current_raw[k].strip(),'new':row[k].strip()} for k in FIELDS if current_raw[k].strip()!=row[k].strip()]})
                continue
            changes=[{'field':k,'old':current_raw[k].strip(),'new':row[k].strip()} for k in FIELDS if current_raw[k].strip()!=row[k].strip()]
            issues.append({'line':current_raw['line'],'code':'AMENDED','raw':current_raw,'superseded_by':row['line']})
            revisions.append({'specimen':specimen,'applied':True,
                'previous_line':current_raw['line'],'current_line':row['line'],
                'previous_raw':dict(current_raw),'current_raw':dict(row),'changes':changes})
            candidate['amended']=True;candidate['replaces_line']=current_raw['line']
            current=candidate;current_raw=row
        if current is not None:valid.append(current)
    return {'rows':valid,'issues':issues,'revisions':revisions,'versions':versions}
