#!/usr/bin/env python3
"""_validity_check.py -- 出榜前的完整性闸门：确保每个模型每个格都有【有效分数】。

规则（这是"不许有数据漏洞"的硬约束）：
  * 一个格 = (技能, 题号, 条件)，全表应有 14 × 3 × 2 = 84 格。
  * 一次运行只有同时满足下面三条才算【有效】：
        rewards.reward 有值（不是 None）
        没有 verifier_error（评委崩溃/判不了分 → 绝不当 0 分）
        没有 error（超时等运行级错误）
  * 一个格只要**有任意一次有效运行**就算齐；取数规则沿用官方：
    优先干净的，其次最新的。
  * 只要有任何格不齐 → 退出码 1 并打印缺失清单（防止带着窟窿出榜）。

用法：
  python jobs/_validity_check.py --all
  python jobs/_validity_check.py glm-5.3 kimi-k2.7-code
  python jobs/_validity_check.py --all --csv jobs/missing_cells.csv
"""
import argparse, csv, json, pathlib, re, sys, collections

REPO = pathlib.Path(__file__).resolve().parent.parent
JOBS = REPO / "jobs"
RUN_RE = re.compile(r"skill-eval/(?P<skill>[^/]+)/opencode/(?P<cond>baseline|with-skill)/"
                    r"(?P<ts>[^/]+)/(?P<skill2>[^/]+)__(?P<case>\d+)__[0-9a-f]+$")

def scan(model, prefix="formal"):
    """-> {(skill, case, cond): [ {valid, reward, why, ts} ]}"""
    cells = collections.defaultdict(list)
    root = JOBS / f"{prefix}-{model}"
    if not root.is_dir():
        return None
    for rj in root.rglob("result.json"):
        m = RUN_RE.search(str(rj.parent).replace("\\", "/"))
        if not m:
            continue
        try:
            d = json.loads(rj.read_text(encoding="utf-8"))
        except Exception:
            continue
        reward = (d.get("rewards") or {}).get("reward")
        why = None
        if reward is None:
            why = ("verifier_error" if d.get("verifier_error")
                   else (d.get("error_category") or "no_reward"))
        cells[(m["skill"], m["case"], m["cond"])].append({
            "valid": reward is not None and not d.get("verifier_error") and not d.get("error"),
            "reward": reward, "why": why, "ts": m["ts"],
        })
    return cells

def pick(runs):
    """官方取数：干净优先，其次最新"""
    clean = [r for r in runs if r["valid"]]
    pool = clean or runs
    return sorted(pool, key=lambda r: r["ts"])[-1]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("models", nargs="*")
    ap.add_argument("--all", action="store_true", help="扫 jobs/formal-* 全部")
    ap.add_argument("--expect", type=int, default=84, help="每模型应有的格数")
    ap.add_argument("--csv", default=None, help="把缺失格写到 CSV")
    ap.add_argument("--root", default="formal", help="运行目录前缀，如 formal / v2")
    a = ap.parse_args()

    models = a.models
    if a.all or not models:
        models = sorted(p.name[len(a.root) + 1:] for p in JOBS.glob(f"{a.root}-*") if p.is_dir())

    missing_rows, bad = [], 0
    print(f"== 完整性检查（目录前缀 {a.root}-，每模型应有 {a.expect} 格）==")
    for m in models:
        cells = scan(m, a.root)
        if cells is None:
            print(f"  {m:22s} ✗ 没有运行目录")
            bad += 1
            continue
        valid_cells = [k for k, v in cells.items() if pick(v)["valid"]]
        # 期望的完整格集合：以该模型出现过的技能 × 题号 01-03 × 2 条件
        allskills = sorted({k[0] for k in cells})
        expect = {(s, f"{c:02d}", cond) for s in allskills for c in (1, 2, 3)
                  for cond in ("baseline", "with-skill")}
        miss = sorted(expect - set(valid_cells))
        flag = "✓" if not miss else "✗"
        print(f"  {m:22s} {flag} 有效格 {len(valid_cells)}/{len(expect)}"
              + ("" if not miss else f"  缺 {len(miss)} 格"))
        if miss:
            bad += 1
            for k in miss:
                runs = cells.get(k, [])
                why = pick(runs)["why"] if runs else "从未跑"
                print(f"       缺: {k[0]} case{k[1]} {k[2]}  （{why}）")
                missing_rows.append({"model": m, "skill": k[0], "case": k[1],
                                     "cond": k[2], "reason": why})

    if a.csv and missing_rows:
        with open(a.csv, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["model", "skill", "case", "cond", "reason"])
            w.writeheader(); w.writerows(missing_rows)
        print(f"\n缺失清单已写入 {a.csv}")

    print()
    if bad:
        print(f"❌ 有 {bad} 个模型不完整 —— 先重跑缺失格，别出榜")
        print("   重跑： bash jobs/_retry_failed.sh <模型>")
        return 1
    print("✅ 所有模型满格，可以出榜")
    return 0

if __name__ == "__main__":
    sys.exit(main())
