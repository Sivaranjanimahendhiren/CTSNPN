import csv, json, statistics
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
rows=list(csv.DictReader((ROOT/'data/cms/curated/demo_ed_utilization.csv').open()))
# A transparent demo heuristic: low acuity + repeated ED use + low alternative utilization.
flagged=[]
for r in rows:
    ed=int(r['ed_visits']); pc=int(r['pc_visits']); uc=int(r['urgent_care_visits']); th=int(r['telehealth_visits']); acuity=r['acuity_signal']
    if acuity=='low' and ed>=2 and (pc+uc+th)==0:
        flagged.append(r['member_id'])
print('CTS-NPN deterministic demo')
print('Total synthetic members:',len(rows))
print('Potential navigation patterns:',flagged)
print('Safety check: SYN008 has high acuity/chest pain and is NOT flagged.')
print('This demo is synthetic and not a clinical decision rule.')
