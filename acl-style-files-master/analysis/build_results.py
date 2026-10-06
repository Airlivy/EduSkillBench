"""Reproduce paper tables from immutable evaluated outputs; failures score zero.
No model calls. Core weights retained; advisory grades are never assigned ordinal numbers.
"""
import argparse,csv,hashlib,json,sys
from pathlib import Path
from collections import Counter,defaultdict
import numpy as np
ROOT=Path(__file__).resolve().parents[2]
PAPER=Path(__file__).resolve().parents[1]
BASE=ROOT/'results_v2/formal-paired-chat-10000-20261002-r2'
FINAL=ROOT/'results_v2/formal-paired-chat-10000-resume-20261005-061018-completion/combined_summary.json'
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def dump(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
def mean(a):return float(np.mean(a))
def main():
 plan=read(BASE/'plan.json');cases=read(BASE/'snapshot/release/cases.json');byid={c['task_id']:c for c in cases}
 source=read(FINAL)['results'];models=plan['models'];rows=[];audit=[]
 assert len(source)==3050 and len({(r['model'],r['condition'],r['task_id']) for r in source})==3050
 for r in source:
  case=byid[r['task_id']];good=r['status']=='evaluated';path=Path(r['result_directory']).resolve()
  x={k:r[k] for k in ['model','condition','task_id','suite','status']};x.update(skill=r['task_id'].split('__')[0],review_flag=bool(r.get('review_required')),failure_zero=not good,score=0.,strict_pass=0.,criterion_top=0.,source_group=case.get('original_source',r['task_id'].split('__')[0]),category=r.get('category',''),result_directory=str(path.relative_to(ROOT)))
  if good:
   if case['suite']=='core':
    f=path/'grading/judge_result.json';v=read(f);items=v['items'];assert len(items)==len(case['rubric'])
    assert all(type(t['pass']) is bool for t in items)
    hits={t['id']:t['pass'] for t in items};assert set(hits)=={f'C{i+1}' for i in range(len(case['rubric']))}
    score=sum(c['points']*hits[f'C{i+1}'] for i,c in enumerate(case['rubric']))/sum(c['points'] for c in case['rubric'])
    assert abs(score-r['score'])<1e-9 and abs(score-v['score'])<1e-9
    bits=list(hits.values())
   else:
    f=path/'grading/result.json';v=read(f);criteria={c['id']:c for c in case['criteria'] if c['id'] in case['applicable_ids']}
    items=v['raw_verdict']['items'];assert len(items)==len(criteria)
    assert {i['id']:i['level'] for i in items}==r['criterion_levels']
    bits=[]
    for item in items:
     c=criteria[item['id']];labels=[l['label'] for l in c['levels']] or ['满足','部分满足','未满足']
     assert item['level'] in labels+['低于原文最低等级']
     bits.append(item['level']==labels[0])
    score=sum(bits)/len(bits)
   x.update(score=score,criterion_top=sum(bits)/len(bits),strict_pass=float(all(bits)))
   audit.append({'path':str(f.relative_to(ROOT)),'sha256':sha(f)})
  rows.append(x)
 assert sum(r['failure_zero'] for r in rows)==28
 fields=list(rows[0])
 with (PAPER/'analysis/paper_scores.csv').open('w',encoding='utf-8-sig',newline='') as f:
  w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows({**r, 'source_group': hashlib.sha256(r['source_group'].encode()).hexdigest()[:16]} for r in rows)
 lookup={(r['model'],r['condition'],r['task_id']):r for r in rows}
 stats={};skillstats=[];rng=np.random.default_rng(20261005)
 for suite in ['core','advisory']:
  subset=[c for c in cases if c['suite']==suite];tids=[c['task_id'] for c in subset];stats[suite]={}
  clusters=sorted({lookup[(models[0],'baseline',t)]['source_group'] for t in tids})
  cluster_indices=[np.array([i for i,t in enumerate(tids) if lookup[(models[0],'baseline',t)]['source_group']==g]) for g in clusters]
  for model in models:
   b=[lookup[model,'baseline',t] for t in tids];w=[lookup[model,'with-skill',t] for t in tids]
   bv=np.array([r['score'] for r in b]);wv=np.array([r['score'] for r in w]);delta=wv-bv
   boot=[]
   for _ in range(5000):
    ix=np.concatenate([cluster_indices[i] for i in rng.integers(0,len(clusters),len(clusters))]);boot.append(mean(delta[ix]))
   paired=[i for i in range(len(tids)) if not b[i]['failure_zero'] and not w[i]['failure_zero']]
   noflag=[i for i in paired if not b[i]['review_flag'] and not w[i]['review_flag']]
   result={'n':len(tids),'baseline':mean(bv),'with_skill':mean(wv),'delta':mean(delta),'gain':mean(delta)/(1-mean(bv)) if mean(bv)<1 else None,'ci':list(map(float,np.quantile(boot,[.025,.975]))),'failures':[sum(r['failure_zero'] for r in a) for a in [b,w]],'strict':[mean([r['strict_pass'] for r in a]) for a in [b,w]],'wins_ties_losses':[int(np.sum(delta>1e-9)),int(np.sum(np.abs(delta)<=1e-9)),int(np.sum(delta< -1e-9))],'complete_pair_n':len(paired),'complete_pair_delta':mean(delta[paired]),'unflagged_pair_n':len(noflag),'unflagged_pair_delta':mean(delta[noflag]),'cluster_count':len(clusters)}
   stats[suite][model]=result
   for skill in sorted({r['skill'] for r in b}):
    ix=[i for i,r in enumerate(b) if r['skill']==skill]
    skillstats.append({'suite':suite,'model':model,'skill':skill,'n':len(ix),'baseline':mean(bv[ix]),'with_skill':mean(wv[ix]),'delta':mean(delta[ix])})
 total={'suite_results':stats,'skill_results':skillstats,'failures':dict(Counter(r['category'] for r in rows if r['failure_zero'])),'review_flags':sum(r['review_flag'] for r in rows),'dataset':{'n':305,'core':42,'advisory':263,'skills':14,'source_documents':len({c['original_source'] for c in cases if c['suite']=='advisory'})},'metric':'Core: original weighted binary reward. Advisory: fraction of applicable dimensions at their highest native label (new reporting statistic, not ordinal-to-score conversion). Both macro-average by task; never pool suite scores.','policy':'Remaining failures count as zero; statuses unchanged. Retain first successful score in historical recovery selection, not best score.','bootstrap':'5000 paired source-cluster resamples, core clusters=14 skills, advisory clusters=30 source documents; seed 20261005. Conditional on retained outcomes, not inference randomness.'}
 dump(PAPER/'analysis/results.json',total)
 dump(PAPER/'analysis/provenance.json',{'base':str(BASE.relative_to(ROOT)),'summary':str(FINAL.relative_to(ROOT)),'summary_sha256':sha(FINAL),'cases_sha256':sha(BASE/'snapshot/release/cases.json'),'reference_pdf_sha256':sha(ROOT/'skillbench.pdf'),'source_results':audit,'build_script_sha256':sha(Path(__file__))})
 short={'glm-5.3':'GLM-5.3','glm-5.3-flash':'GLM-5.3 Flash','deepseek-v4-pro':'DeepSeek V4 Pro','deepseek-v4-flash':'DeepSeek V4 Flash','kimi-k2.7-code':'Kimi K2.7 Code'}
 for suite in stats:
  lines=[]
  for model,s in sorted(stats[suite].items(),key=lambda kv:kv[1]['with_skill'],reverse=True):
   lines.append(f"{short[model]} & {100*s['baseline']:.1f} & {100*s['with_skill']:.1f} & {100*s['delta']:+.1f} & [{100*s['ci'][0]:+.1f}, {100*s['ci'][1]:+.1f}] & {s['failures'][0]}/{s['failures'][1]} \\\\")
  lines.append('\\midrule')
  b=mean([x['baseline'] for x in stats[suite].values()]);w=mean([x['with_skill'] for x in stats[suite].values()]);lines.append(f"Model mean & {100*b:.1f} & {100*w:.1f} & {100*(w-b):+.1f} & --- & --- \\\\")
  (PAPER/f'tables/{suite}_main.tex').write_text('\n'.join(lines)+'\n')
 lines=[]
 for m in models:
  v=stats['advisory'][m];ss=[x for x in skillstats if x['suite']=='advisory' and x['model']==m]
  lines.append(f"{short[m]} & {100*v['delta']:+.1f} & {100*v['complete_pair_delta']:+.1f} ({v['complete_pair_n']}) & {100*v['unflagged_pair_delta']:+.1f} ({v['unflagged_pair_n']}) & {100*mean([x['delta'] for x in ss]):+.1f} "+chr(92)*2)
 (PAPER/'tables/sensitivity.tex').write_text('\n'.join(lines)+'\n')
 lines=[]
 for m in models:
  values=[]
  for suite in ['core','advisory']:
   b,w=stats[suite][m]['strict'];values.extend([f'{b*100:.1f}',f'{w*100:.1f}',f'{(w-b)*100:+.1f}'])
  lines.append(short[m]+' & '+' & '.join(values)+' '+chr(92)*2)
 (PAPER/'tables/strict.tex').write_text('\n'.join(lines)+'\n')
 print(json.dumps({k:{m:{f:v[f] for f in ['baseline','with_skill','delta','ci','failures','strict','complete_pair_delta','unflagged_pair_delta']} for m,v in a.items()} for k,a in stats.items()},indent=2))
if __name__=='__main__':main()
