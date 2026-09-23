from pathlib import Path
p = Path("main.py")
s = p.read_text(encoding="utf-8")
if 'evidence: str = "impression"' in s:
    raise SystemExit("already patched")
head, sep, tail = s.partition("def label_breakdown(")
assert sep, "label_breakdown not found"
tail = tail.replace("field: str, token: str, platform: str | None):",
    'field: str, token: str, platform: str | None, evidence: str = "impression"):', 1)
tail = tail.replace("AND p.evidence = 'impression'", "AND p.evidence = %s", 1)
tail = tail.replace("(LABEL_VERSION, token, platform, platform),",
    "(LABEL_VERSION, token, evidence, platform, platform),", 1)
tail = tail.replace(
    'def topics(token: str, platform: str | None = None):\n    return label_breakdown("topic", token, platform)',
    'def topics(token: str, platform: str | None = None, evidence: str = "impression"):\n'
    '    if evidence not in ("impression", "engagement"):\n'
    '        evidence = "impression"\n'
    '    return label_breakdown("topic", token, platform, evidence)', 1)
for must in ('evidence: str = "impression"):', "AND p.evidence = %s",
             "(LABEL_VERSION, token, evidence, platform, platform)",
             'label_breakdown("topic", token, platform, evidence)'):
    assert must in tail, "patch step failed: " + must
p.write_text(head + sep + tail, encoding="utf-8")
print("main.py patched: /topics now accepts ?evidence=engagement")
