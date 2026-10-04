"""Restore selected source cases without translating or inventing assessment rules.

DOCX is retained byte-for-byte. Text views are exports, not replacements for
Word layout, automatic numbering or equation objects; those objects are saved.
"""
import csv
import hashlib
import json
import re
import shutil
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OLD = ROOT / 'data/releases/run-ready-20260930'
OUT = ROOT / 'data/releases/source-faithful-20261001'
W = '{http://schemas.openxmlformats.org/wordprocessingml/2006/main}'
M = '{http://schemas.openxmlformats.org/officeDocument/2006/math}'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def doc_text(path):
    if path.suffix == '.md':
        return path.read_bytes().decode('utf-8-sig'), []
    with zipfile.ZipFile(path) as archive:
        body = ET.fromstring(archive.read('word/document.xml')).find(W + 'body')
    equations = [ET.tostring(x, encoding='unicode') for x in body.iter(M + 'oMath')]
    def paragraph(node):
        return ''.join((x.text or '') if x.tag in (W+'t', M+'t') else
                       '\t' if x.tag == W+'tab' else
                       '\n' if x.tag in (W+'br', W+'cr') else '' for x in node.iter())
    output = []
    for node in body:
        if node.tag == W+'p':
            output.append(paragraph(node))
        elif node.tag == W+'tbl':
            for row in node.findall(W+'tr'):
                output.append('\t'.join('\n'.join(paragraph(p) for p in cell.findall(W+'p'))
                                        for cell in row.findall(W+'tc')))
    return '\n'.join(output), equations


def category(line):
    if '\t' in line or line.lstrip().startswith('|'):
        return None
    value = re.sub(r'^\s*#{1,6}\s*', '', line).strip()
    value = re.sub(r'^[（(]?\s*[0-9一二三四五六七八九十]+\s*[）)、.．]\s*', '', value)
    for kind, pattern in [
        ('title', r'^任务名称'), ('context', r'^(触发情景|Context\b)'),
        ('problem', r'^(核心问题|Problem\b)'), ('solution', r'^(解决方案|Solution\b)'),
        ('rubric', r'^评价(?:准则|标准)(?:\s|：|:|（|\(|$)'),
        ('examples', r'^案例对比'), ('references', r'^规范依据'),
        ('questions', r'^(?:测试|测评)(?:情景|场景|问题|主题)')]:
        if re.match(pattern, value, re.I):
            return kind
    if re.match(r'^\s*#{1,6}\s*[0-9一二三四五六七八九十]+(?:\s*$|[、.．])', line):
        return 'other'
    return None


def sections(text):
    starts = []
    offset = 0
    for line in text.splitlines(keepends=True):
        kind = category(line)
        if kind == 'other' and re.match(r'^[、\s]*案例对比', text[offset+len(line):]):
            kind = 'examples'
        if kind:
            starts.append((offset, kind))
        offset += len(line)
    return [{'kind': kind, 'start': start,
             'end': starts[i+1][0] if i+1 < len(starts) else len(text),
             'text': text[start:starts[i+1][0] if i+1 < len(starts) else len(text)]}
            for i, (start, kind) in enumerate(starts)]


def locate(text, quote):
    # Whitespace-insensitive matching is ONLY for locating a historical binding.
    # The exported question is the exact original slice, including its spacing.
    positions = [i for i, c in enumerate(text) if not c.isspace()]
    compact = ''.join(text[i] for i in positions)
    needle = ''.join(c for c in quote if not c.isspace())
    matches = [m.start() for m in re.finditer(re.escape(needle), compact)]
    if len(matches) != 1:
        raise ValueError(('Ambiguous/missing source question', quote, len(matches)))
    start = positions[matches[0]]
    end = positions[matches[0]+len(needle)-1]+1
    return start, end


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n')


def write_csv(path, rows, fields):
    with path.open('w', encoding='utf-8-sig', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def build():
    OUT.mkdir(parents=True, exist_ok=True)
    bindings = json.loads((OLD/'source_bindings.json').read_text())
    with (OLD/'advisory.csv').open(encoding='utf-8-sig', newline='') as f:
        old_rows = list(csv.DictReader(f))
    assert [b['task_id'] for b in bindings] == [r['task_id'] for r in old_rows]
    documents = {}
    for b in bindings:
        path = b['local_source_path']
        if path in documents:
            continue
        original = ROOT/path
        assert sha(original) == b['local_source_sha256'], path
        relative = original.relative_to(ROOT/'jobs/new_scenarios/source/raw')
        copied = OUT/'originals'/relative
        copied.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(original, copied)
        assert copied.read_bytes() == original.read_bytes()
        text, equations = doc_text(original)
        ss = sections(text)
        assert any(s['kind']=='rubric' for s in ss), path
        assert any(s['kind']=='questions' for s in ss), path
        assert any(s['kind']=='context' for s in ss), path
        documents[path] = {'source_record': b['source_record'], 'original_path': str(copied.relative_to(OUT)),
            'source_sha256': sha(original), 'text': text, 'sections': ss,
            'equation_objects_xml': equations,
            'text_export_note': ('原始 Word 文件逐字节保留；文本视图的表格用制表符分隔。自动编号、公式上下标与分式版式以原 Word 为准；原始公式 XML 另存，未补写公式。' if original.suffix=='.docx' else '原 Markdown 文件逐字节保留；文本解码时只去除文件头 BOM。')}
    cases = []
    rows = []
    fields = list(old_rows[0]) + ['source_file', 'source_sha256', 'source_scene_index',
        'source_solution', 'source_examples', 'source_references', 'source_document_text', 'source_equation_objects_xml', 'source_format_note']
    issues = []
    for b in bindings:
        d = documents[b['local_source_path']]
        start, end = locate(d['text'], b['source_question_zh'])
        assert any(s['kind']=='questions' and s['start']<=start<end<=s['end'] for s in d['sections']), b['task_id']
        select = lambda kinds: [s for s in d['sections'] if s['kind'] in kinds]
        case = {'task_id': b['task_id'], 'source_record': b['source_record'],
            'source_scene_index': b['original_scene_index'], 'source_file': d['original_path'],
            'source_sha256': d['source_sha256'], 'question_span': [start,end],
            'user_prompt': d['text'][start:end],
            'context_sections': select(('title','context','problem')),
            'rubric_sections': select(('rubric',)), 'solution_sections': select(('solution',)),
            'example_sections': select(('examples',)), 'reference_sections': select(('references',)),
            'expected_output': '', 'reference_policy': '未编写逐题标准答案；源文件中的解决方案、案例原文分别保留，不自动当作每个测试情景的标准答案。',
            'legacy_skill_id': next(r['skill_id'] for r in old_rows if r['task_id']==b['task_id']),
            'execution_status': 'source_restored_not_auto_scoring_protocol'}
        cases.append(case)
        join = lambda name: '\n'.join(s['text'] for s in case[name])
        r = {f:'' for f in fields}
        r.update(task_id=b['task_id'], context=join('context_sections'), user_prompt=case['user_prompt'],
            rubric=join('rubric_sections'), source_file=d['original_path'], source_sha256=d['source_sha256'],
            source_scene_index=b['original_scene_index'], source_solution=join('solution_sections'),
            source_examples=join('example_sections'), source_references=join('reference_sections'),
            source_document_text=d['text'], source_equation_objects_xml=json.dumps(d['equation_objects_xml'], ensure_ascii=False),
            source_format_note=d['text_export_note'])
        rows.append(r)
    for path, d in documents.items():
        issues.append({'source_file':d['original_path'], 'rubric_sections':len([s for s in d['sections'] if s['kind']=='rubric']),
            'equation_objects':len(d['equation_objects_xml']),
            'interpretation_status':'原文统一背景、评价表与各情景的适用关系未擅自裁决；未新增权重、等级转分规则或关键项。'})
    write_csv(OUT/'advisory.csv', rows, fields)
    with (OLD/'core.csv').open(encoding='utf-8-sig',newline='') as f:
        core=list(csv.DictReader(f))
    shutil.copyfile(OLD/'core.csv', OUT/'core.csv')
    write_csv(OUT/'all.csv', [{**{k:'' for k in fields},**r} for r in core]+rows, fields)
    dump(OUT/'cases.json',cases)
    dump(OUT/'source_documents.json',documents)
    dump(OUT/'source_issues.json',issues)
    dump(OUT/'release_gate.json',{'ready':False,'source_fidelity_verified':True,
        'reason':'263题已恢复原文；现有布尔评分器不支持原文多级量规与未指定权重，不能继续使用改写评分规则。',
        'allowed_conditions':{'core':['baseline','with-skill'],'advisory':['baseline'],'all':['baseline']}})
    notes='''# 原文恢复版（2026-10-01）

263 题沿用原先选定的题号和来源对应，不新增、不删题。题目直接从本地源文档提取，不经过翻译或模型改写。背景、原评价表、解决方案、正反案例和依据分别保留；同文档多套量规全部保留，不擅自合并。没有逐题标准答案时留空，不把示例改成强制答案，不新增权重或关键项。

`originals/` 保存 30 份原始文件，逐字节校验。`cases.json` 保存原文片段位置；`source_documents.json` 保存完整文本、章节和原始公式对象 XML。Word 的公式版式、自动编号、表格合并等以原文件为准，CSV/TXT 文本视图不声称复制 Word 排版。Markdown 的换行和字符保留。

`advisory.csv` 是恢复后的 263 题；`all.csv` 的前 42 题内容保持原发布版，本次仅恢复后 263 题。题号保留旧 Skill 前缀仅供追溯，不代表重新确认了 Skill 对应。没有来自原文的学科、难度和 Skill 分类不再沿用推断值。

此版本是原文恢复与人工审核交付，未宣称自动评分可运行。原文可能没有数字权重，或给出多个不同等级量规；不能为了运行旧的逐项通过/不通过评分器而擅自转换。原文矛盾、未证实引用及表述问题原样保留，不能将原文保真校验当作内容正确性认证。

旧改编版保留在 run-ready-20260930，不能再把它称为原 repo 复现版。本次来源是本机保存的 repo 文件快照及既有选题清单，不声称已与远端最新提交独立核对。
'''
    (OUT/'README.md').write_text(notes)
    txt=['EduSkillBench：263题原文恢复版','本文件只增加题号和阅读分区标签，区内内容来自原始文件。不是前次中文翻译版。',
         '没有逐题标准答案时不补写。解决方案、案例与评分标准按原文分别保留。',
         'Word 原文件与公式 XML 一并保留；文本视图不保留公式排版和自动编号，请核对 originals 中的原件。','']
    for i,(c,r) in enumerate(zip(cases,rows),1):
        txt += ['='*70,f'第 {i:03d} / 263 题',f'题号：{c["task_id"]}',f'原文件：{c["source_file"]}',
            '【原文题目】',c['user_prompt'],'【原文统一背景与核心问题（适用关系以原文件为准）】',r['context'],
            '【原文评价标准（各套标准均保留）】',r['rubric'],
            '【原文解决方案（不等同于本题标准答案）】',r['source_solution'],
            '【原文案例】',r['source_examples'],'【原文依据】',r['source_references'],'']
    (OUT/'263题原文核对.txt').write_text('\n'.join(txt),encoding='utf-8-sig')
    dump(OUT/'manifest.json',{'release':OUT.name,'counts':{'core':42,'advisory':263,'all':305,'source_documents':30},
        'builder_sha256':sha(Path(__file__)), 'artifacts':{str(p.relative_to(OUT)):sha(p) for p in sorted(OUT.rglob('*')) if p.is_file() and p.name!='manifest.json'},'skill_files':{}})
    print(json.dumps({'restored':len(cases),'source_documents':len(documents),'out':str(OUT)},ensure_ascii=False))

if __name__=='__main__':build()
