"""Extract the 评价准则 (rubric) section from each task description under raw/.

Walks every .md / .docx file beneath raw/, locates the rubric subsection
regardless of which numbering style the author used, and writes one JSONL
row per source to rubrics.jsonl alongside this script.
"""
from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path

from docx import Document
from docx.document import Document as _DocxDoc
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph

RAW = Path(__file__).parent / "raw"
OUT = Path(__file__).parent / "rubrics.jsonl"
OUT_CSV = Path(__file__).parent / "rubrics.csv"

# Section heading that begins the rubric. Covers:
#   "### 5、评价准则", "5. 评价准则", "5．评价标准", "评价标准：" / "评价准则：".
RUBRIC_HEAD = re.compile(
    r"^\s*#*\s*[（(]?\s*[\d五六七八]+\s*[）)、.．]\s*评价\s*(?:准则|标准)"
    r"|^\s*评价\s*(?:准则|标准)\s*[:：]?\s*$"
)

# Section heading that ends the rubric. Matches a numbered heading whose
# title starts with one of the well-known follow-on keywords. Tolerates
# half/full-width digits, separators, and markdown / paren prefixes.
_STOP_WORDS = "案例|规范|测试|测评|参考|附录|常见|结语|教学建议|落地"
_BARE_STOPS = "测试主题|测试问题|测评问题|测试情景|测评情景|案例对比|规范依据|参考文献"
NEXT_HEAD = re.compile(
    rf"^\s*#*\s*[（(]?\s*[\d一二三四五六七八九十]+\s*[）)、.．]\s*(?:{_STOP_WORDS})"
    rf"|^\s*(?:{_BARE_STOPS})\s*[:：]?\s*$"
)


def _iter_blocks(doc: _DocxDoc):
    """Yield Paragraph / Table objects in true document order."""
    for child in doc.element.body.iterchildren():
        if child.tag == qn("w:p"):
            yield Paragraph(child, doc)
        elif child.tag == qn("w:tbl"):
            yield Table(child, doc)


def _table_to_markdown(tbl: Table) -> str:
    rows = [
        [c.text.strip().replace("\n", " ") for c in row.cells]
        for row in tbl.rows
    ]
    if not rows:
        return ""
    width = max(len(r) for r in rows)
    rows = [r + [""] * (width - len(r)) for r in rows]
    head = "| " + " | ".join(rows[0]) + " |"
    sep = "|" + "|".join(["---"] * width) + "|"
    body = ["| " + " | ".join(r) + " |" for r in rows[1:]]
    return "\n".join([head, sep, *body])


def _extract_md(path: Path) -> str | None:
    lines = path.read_text(encoding="utf-8").splitlines()
    start: int | None = None
    end: int | None = None
    for i, line in enumerate(lines):
        if start is None:
            if RUBRIC_HEAD.search(line):
                start = i + 1
        elif NEXT_HEAD.search(line):
            end = i
            break
    if start is None:
        return None
    return "\n".join(lines[start:end]).strip() or None


def _extract_docx(path: Path) -> str | None:
    doc = Document(str(path))
    pieces: list[str] = []
    in_section = False
    for block in _iter_blocks(doc):
        if isinstance(block, Paragraph):
            txt = block.text.strip()
            if not in_section:
                if txt and RUBRIC_HEAD.search(txt):
                    in_section = True
                continue
            if txt and NEXT_HEAD.search(txt):
                break
            if txt:
                pieces.append(txt)
        else:  # Table
            if in_section:
                md = _table_to_markdown(block)
                if md:
                    pieces.append(md)
    if not in_section:
        return None
    return "\n\n".join(pieces).strip() or None


def main() -> None:
    rows: list[dict] = []
    misses: list[str] = []
    for path in sorted(RAW.rglob("*")):
        if not path.is_file() or path.name.startswith((".", "~$")):
            continue
        if path.suffix == ".md":
            rubric = _extract_md(path)
        elif path.suffix == ".docx":
            rubric = _extract_docx(path)
        else:
            continue
        rel = path.relative_to(RAW).as_posix()
        if rubric:
            rows.append(
                {
                    "source": rel,
                    "author": path.parent.name,
                    "task": path.stem,
                    "rubric": rubric,
                }
            )
        else:
            misses.append(rel)

    OUT.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
        encoding="utf-8",
    )
    with OUT_CSV.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["source", "author", "task", "rubric"])
        writer.writeheader()
        writer.writerows(rows)
    print(f"extracted {len(rows)} rubrics -> {OUT}, {OUT_CSV}")
    if misses:
        print(f"no rubric found in {len(misses)} file(s):", file=sys.stderr)
        for m in misses:
            print(f"  {m}", file=sys.stderr)


if __name__ == "__main__":
    main()
