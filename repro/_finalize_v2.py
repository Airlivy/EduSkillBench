#!/usr/bin/env python3
"""_finalize_v2.py -- 用 v2 批次（统一 ark 口径）重算排行榜。

与旧脚本的关键区别（修掉那些数据漏洞）：
  1. 只认【有效运行】：reward 有值 且 无 verifier_error 且 无 error。
     评委崩溃绝不当 0 分，缺分数的格绝不手工填数。
  2. 【满格硬校验】：每个模型必须 84/84 格（14 技能 × 3 题 × 2 条件）齐全，
     任何一格缺失就报错退出，不出榜。杜绝"各列在不同题目集合上算均值"。
  3. 取数规则【全模型统一】：干净优先，其次最新（不再有"GLM 取最大值"这类特例）。
  4. 输出写到 results_v2/，不覆盖已发布的 results/。

用法：
  python jobs/_finalize_v2.py                     # 默认前缀 v2，5 个模型自动发现
  python jobs/_finalize_v2.py --root v2 --models glm-5.3 kimi-k2.7-code
  python jobs/_finalize_v2.py --allow-incomplete   # 只做预览、不强制满格（会标注）
"""
import argparse, csv, json, pathlib, re, sys, collections

REPO = pathlib.Path(__file__).resolve().parent.parent
JOBS = REPO / "jobs"
RUN_RE = re.compile(r"skill-eval/(?P<skill>[^/]+)/opencode/(?P<cond>baseline|with-skill)/"
                    r"(?P<ts>[^/]+)/(?P<skill2>[^/]+)__(?P<case>\d+)__[0-9a-f]+$")
CELLS = 84


def collect(root: pathlib.Path):
    """-> {(skill, cond, case): [runs]}"""
    cells = collections.defaultdict(list)
    for rj in root.rglob("result.json"):
        m = RUN_RE.search(str(rj.parent).replace("\\", "/"))
        if not m:
            continue
        try:
            d = json.loads(rj.read_text(encoding="utf-8"))
        except Exception:
            continue
        reward = (d.get("rewards") or {}).get("reward")
        valid = (reward is not None and not d.get("verifier_error") and not d.get("error"))
        cells[(m["skill"], m["cond"], m["case"])].append(
            {"reward": reward, "valid": valid, "ts": m["ts"]})
    return cells


def pick(runs):
    clean = [r for r in runs if r["valid"]]
    pool = clean or runs
    return sorted(pool, key=lambda r: r["ts"])[-1]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="v2", help="运行目录前缀（v2 / formal）")
    ap.add_argument("--models", nargs="*")
    ap.add_argument("--out", default="results_v2")
    ap.add_argument("--allow-incomplete", action="store_true")
    a = ap.parse_args()

    models = a.models or sorted(p.name[len(a.root) + 1:] for p in JOBS.glob(f"{a.root}-*")
                                if p.is_dir())
    if not models:
        print(f"✗ 没有 jobs/{a.root}-* 目录"); return 2

    per_model, skill_rows, overall_rows = {}, [], []
    bad = []
    for m in models:
        cells = collect(JOBS / f"{a.root}-{m}")
        if not cells:
            print(f"  {m}: 没有运行"); bad.append(m); continue
        picked = {k: pick(v) for k, v in cells.items()}
        valid = {k: r for k, r in picked.items() if r["valid"]}
        miss = CELLS - len(valid)
        if miss > 0:
            bad.append(m)
            print(f"  {m:22s} ✗ 有效格 {len(valid)}/{CELLS}（缺 {miss}）")
        else:
            print(f"  {m:22s} ✓ {len(valid)}/{CELLS}")
        per_model[m] = valid
        skills = sorted({k[0] for k in valid})
        for s in skills:
            ws = [r["reward"] for k, r in valid.items() if k[0] == s and k[1] == "with-skill"]
            bs = [r["reward"] for k, r in valid.items() if k[0] == s and k[1] == "baseline"]
            skill_rows.append({"model": m, "skill": s,
                               "with_skill": round(sum(ws) / len(ws), 3) if ws else "",
                               "baseline": round(sum(bs) / len(bs), 3) if bs else "",
                               "lift": round(sum(ws) / len(ws) - sum(bs) / len(bs), 3)
                                       if ws and bs else ""})
        ws = [r["reward"] for k, r in valid.items() if k[1] == "with-skill"]
        bs = [r["reward"] for k, r in valid.items() if k[1] == "baseline"]
        if ws and bs:
            wm, bm = sum(ws) / len(ws), sum(bs) / len(bs)
            overall_rows.append({"model": m, "cells": len(valid),
                                 "with_skill_avg_reward": round(wm, 3),
                                 "baseline_avg_reward": round(bm, 3),
                                 "reward_lift": round(wm - bm, 3)})

    print()
    if bad and not a.allow_incomplete:
        print(f"❌ {len(bad)} 个模型不完整：{', '.join(bad)}")
        print("   先跑： bash jobs/_retry_failed.sh <模型>   再跑： python jobs/_validity_check.py --root " + a.root)
        print("   （如需只看预览，加 --allow-incomplete）")
        return 1

    out = REPO / a.out
    out.mkdir(exist_ok=True)
    if overall_rows:
        with open(out / "model_overall_summary.csv", "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(overall_rows[0].keys())); w.writeheader(); w.writerows(overall_rows)
        (out / "model_overall_summary.json").write_text(
            json.dumps({"cells_per_model": CELLS, "rows": overall_rows}, ensure_ascii=False, indent=1))
    with open(out / "model_skill_summary.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["model", "skill", "with_skill", "baseline", "lift"])
        w.writeheader(); w.writerows(skill_rows)

    print("模型总览：")
    for r in overall_rows:
        print(f"  {r['model']:22s} with {r['with_skill_avg_reward']:.3f} · "
              f"base {r['baseline_avg_reward']:.3f} · lift {r['reward_lift']:+.3f}")
    print(f"\n已写入 {a.out}/（未改动已发布的 results/）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
