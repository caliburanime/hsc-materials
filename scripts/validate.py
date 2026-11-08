#!/usr/bin/env python3
"""Validate question JSON files.

Checks: JSON Schema, unique IDs, image files exist, answer label is one of the
options, chapter numbers match meta.json / folder / ID, CQ marks add up.

    python scripts/validate.py             # everything
    python scripts/validate.py data/ICT    # one subject
Exit code is 1 when any error is found (warnings do not fail).
"""
import re
import sys
from collections import Counter
from pathlib import Path

from jsonschema import Draft7Validator

sys.path.insert(0, str(Path(__file__).parent))
from common import DATA, QUESTION_FILES, load_json, question_files, subject_dirs  # noqa: E402


def check_images(q, subject_dir, where, errors):
    def chk(p):
        if p and not (subject_dir / p).is_file():
            errors.append(f"{where}: image not found: {p}")
    for key in ("image", "stem_image", "answer_image"):
        chk(q.get(key))
    for o in q.get("options", []):
        chk(o.get("image"))
    for part in q.get("parts", []):
        chk(part.get("answer_image"))


def main():
    only = sys.argv[1] if len(sys.argv) > 1 else None
    schema = Draft7Validator(load_json(DATA / "schema.json"))
    errors, warnings, ids, total = [], [], Counter(), Counter()

    dirs = subject_dirs(only)
    if not dirs:
        print("No subject folders found.")
        return 1
    for sdir in dirs:
        meta = load_json(sdir / "meta.json")
        sid = meta["subject_id"]
        chapters = {c["number"] for c in meta["chapters"]}
        boards = {b["code"] for b in meta.get("boards", [])}
        for ch_dir in sorted(sdir.glob("chapter-*")):
            if int(ch_dir.name.split("-")[1]) not in chapters:
                errors.append(f"{ch_dir.relative_to(DATA)}: chapter not listed in meta.json")
        for number, name, path in question_files(sdir):
            rel = path.relative_to(DATA)
            doc = load_json(path)
            for e in sorted(schema.iter_errors(doc), key=lambda e: list(e.absolute_path)):
                loc = "/".join(map(str, e.absolute_path))
                errors.append(f"{rel}: {loc}: {e.message[:160]}")
            if doc.get("subject") != sid:
                errors.append(f"{rel}: subject '{doc.get('subject')}' != '{sid}'")
            if doc.get("chapter") != number:
                errors.append(f"{rel}: chapter {doc.get('chapter')} != folder chapter {number}")
            if doc.get("type") != QUESTION_FILES[name]:
                errors.append(f"{rel}: type '{doc.get('type')}' does not match file name")
            for q in doc.get("questions", []):
                qid = q.get("id", "<no id>")
                where = f"{rel} [{qid}]"
                ids[qid] += 1
                total[doc.get("type")] += 1
                m = re.match(r"^([a-z0-9_]+)-ch(\d+)-", qid)
                if not m or m.group(1) != sid or int(m.group(2)) != number:
                    errors.append(f"{where}: id does not match subject/chapter")
                check_images(q, sdir, where, errors)
                if q.get("source", {}).get("board") not in boards and q.get("source"):
                    warnings.append(f"{where}: board '{q['source'].get('board')}' not in meta.json boards")
                if doc.get("type") == "mcq":
                    labels = [o.get("label") for o in q.get("options", [])]
                    if len(set(labels)) != len(labels):
                        errors.append(f"{where}: duplicate option labels")
                    if q.get("answer") not in labels:
                        errors.append(f"{where}: answer '{q.get('answer')}' not among options {labels}")
                    for o in q.get("options", []):
                        if not o.get("text") and not o.get("image"):
                            errors.append(f"{where}: option {o.get('label')} has neither text nor image")
                if doc.get("type") == "cq_analytical":
                    s = sum(p.get("marks", 0) for p in q.get("parts", []))
                    if s != q.get("total_marks"):
                        errors.append(f"{where}: parts sum to {s}, total_marks is {q.get('total_marks')}")
                if q.get("review_note"):
                    warnings.append(f"{where}: needs review: {q['review_note'][:110]}")

    for qid, n in ids.items():
        if n > 1:
            errors.append(f"duplicate id: {qid} (x{n})")

    for w in warnings:
        print("WARN ", w)
    for e in errors:
        print("ERROR", e)
    summary = ", ".join(f"{n} {t}" for t, n in sorted(total.items())) or "0 questions"
    print(f"\n{summary} | {len(errors)} error(s), {len(warnings)} warning(s)")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
