"""Compare tiny and full-rubric requests, with one call per sample and safe traces."""
import argparse
import hashlib
import json
import os
from pathlib import Path
from repro import judge
from repro.credentials import load_env_file
from repro.calibration.smoke_ready import fixtures

ROOT = Path(__file__).resolve().parents[2]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--env-file', type=Path, required=True)
    ap.add_argument('--base-url', required=True)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--execute', action='store_true')
    ap.add_argument('--thinking-budget', type=int, default=8000)
    ap.add_argument('--effort', choices=['low','high','max'])
    args = ap.parse_args()
    samples = [('tiny', {'question':'What is 2 + 2?', 'ground_truth':'4', 'score_metric':'weighted',
                        'rubric':[{'id':'C1','description':'The answer states 4.', 'points':100}]}, '4')]
    cases = {c['id']: c for c in json.loads((ROOT/'data/releases/run-ready-20260930/evals.json').read_text())['cases']}
    for fixture in fixtures():
        if fixture['task_id']=='self-explanation-prompt-designer__03' and fixture['variant'] in ('positive','factual_error'):
            samples.append((fixture['variant'], {**cases[fixture['task_id']], 'score_metric':'weighted'}, fixture['answer']))
    model = 'glm-5.3-flash'
    plan = {'model':model,'maximum_calls':len(samples), 'thinking_budget':args.thinking_budget, 'effort':args.effort,
            'timeouts_seconds':judge.DEFAULT_TIMEOUTS,
            'judge_sha256':hashlib.sha256(Path(judge.__file__).read_bytes()).hexdigest(),
            'samples':[{'name':n,'rubric_items':len(c['rubric']), 'prompt_chars':len(judge.build_prompt(c,t)),
                        'prompt_sha256':hashlib.sha256(judge.build_prompt(c,t).encode()).hexdigest()} for n,c,t in samples]}
    if args.out.exists():
        raise ValueError('Use a new output directory; diagnostic evidence is immutable')
    args.out.mkdir(parents=True)
    judge.atomic_json(args.out/'plan.json', plan)
    if not args.execute:
        print(json.dumps(plan));return
    load_env_file(args.env_file)
    os.environ['ANTHROPIC_BASE_URL'] = args.base_url
    results=[]
    for name, case, answer in samples:
        try:
            text, meta = judge.call_judge(judge.build_prompt(case,answer), model,
                                         telemetry_path=args.out/f'{name}.trace.json', thinking_budget=args.thinking_budget, effort=args.effort)
            judge.atomic_json(args.out/f'{name}.response.json', meta)
            (args.out/f'{name}.text.txt').write_text(text, encoding='utf-8')
            if meta.get('stop_reason') in ('max_tokens','stream_incomplete'):
                raise judge.JudgeError(meta['stop_reason'], metadata=meta)
            verdict = judge.score_items(judge.decode_verdict(text), case['rubric'], 'weighted')
            judge.atomic_json(args.out/f'{name}.verdict.json', verdict)
            result={'sample':name,'status':'scored','score':verdict['score'], 'critical_pass':verdict['critical_pass'], 'elapsed_seconds':meta['elapsed_seconds']}
        except judge.JudgeError as exc:
            judge.atomic_json(args.out/f'{name}.error.json', {'category':exc.category,'metadata':exc.metadata})
            result={'sample':name,'status':'failed','category':exc.category}
            if exc.category in ('authentication','missing_credentials'):
                results.append(result);judge.atomic_json(args.out/'summary.json',results);raise
        except (ValueError, KeyError, TypeError) as exc:
            result={'sample':name,'status':'invalid_verdict','exception_type':type(exc).__name__}
        results.append(result)
        judge.atomic_json(args.out/'summary.json',results)
        print(json.dumps(result),flush=True)


if __name__=='__main__':main()
