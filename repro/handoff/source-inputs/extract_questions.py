"""Extract the 测试问题 / 测试情景 section from each task description under raw/.

Walks every .md / .docx file beneath raw/, locates the test-questions
subsection regardless of which heading style the author used, and writes one
JSONL row per source to questions.jsonl alongside this script.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from docx import Document
from docx.document import Document as _DocxDoc
from docx.text.paragraph import Paragraph
from docx.table import Table

from extract_rubric import _iter_blocks, _table_to_markdown

RAW = Path(__file__).parent / "raw"
OUT = Path(__file__).parent / "questions.jsonl"

# Section heading that begins the test-questions block. Covers:
#   "### 8、测试情景（10个）", "8. 测评问题", "8、 测试问题", "测评问题",
#   "（5）测试主题", "测试主题：". Tolerates half/full-width digits, parens,
#   markdown prefixes, and the optional "（N个）" suffix.
QUESTIONS_HEAD = re.compile(
    r"^\s*#*\s*[（(]?\s*[\d一二三四五六七八九十]+\s*[）)、.．]\s*"
    r"测\s*[评试]\s*(?:问题|情景|场景|主题)"
    r"|^\s*测\s*[评试]\s*(?:问题|情景|场景|主题)\s*[（(]?[^\n]{0,12}[)）]?\s*[:：]?\s*$"
)

# A safety net in case authors slip another numbered section after the
# questions. Matches a numbered heading whose title begins with a known
# follow-on keyword.
_STOP_WORDS = "附录|参考|结语|备注|说明|落地|教学建议"
NEXT_HEAD = re.compile(
    rf"^\s*#*\s*[（(]?\s*[\d一二三四五六七八九十]+\s*[）)、.．]\s*(?:{_STOP_WORDS})"
)


def _extract_md(path: Path) -> str | None:
    lines = path.read_text(encoding="utf-8").splitlines()
    start: int | None = None
    end: int | None = None
    for i, line in enumerate(lines):
        if start is None:
            if QUESTIONS_HEAD.search(line):
                start = i + 1
        elif NEXT_HEAD.search(line):
            end = i
            break
    if start is None:
        return None
    return "\n".join(lines[start:end]).strip() or None


def _extract_docx(path: Path) -> str | None:
    doc: _DocxDoc = Document(str(path))
    pieces: list[str] = []
    in_section = False
    for block in _iter_blocks(doc):
        if isinstance(block, Paragraph):
            txt = block.text.strip()
            if not in_section:
                if txt and QUESTIONS_HEAD.search(txt):
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
            questions = _extract_md(path)
        elif path.suffix == ".docx":
            questions = _extract_docx(path)
        else:
            continue
        rel = path.relative_to(RAW).as_posix()
        if questions:
            rows.append(
                {
                    "source": rel,
                    "author": path.parent.name,
                    "task": path.stem,
                    "questions": questions,
                }
            )
        else:
            misses.append(rel)

    OUT.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
        encoding="utf-8",
    )
    print(f"extracted {len(rows)} question sets -> {OUT}")
    if misses:
        print(f"no questions found in {len(misses)} file(s):", file=sys.stderr)
        for m in misses:
            print(f"  {m}", file=sys.stderr)


if __name__ == "__main__":
    main()
