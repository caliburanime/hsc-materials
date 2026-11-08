#!/usr/bin/env python3
"""Compile data/**/*.json into hsc-questions.db.

    python scripts/build_db.py          # rebuild the database
    python scripts/build_db.py --check  # dry run, print counts only

Questions are rebuilt from scratch every time. Test history (test_sessions /
test_answers) lives in the same file, so it is copied over from the previous
database instead of being wiped.
"""
import json
import sqlite3
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import DB_PATH, load_json, question_files, subject_dirs  # noqa: E402

SCHEMA = """
CREATE TABLE subjects (
    id TEXT PRIMARY KEY, name TEXT NOT NULL, name_en TEXT, code INTEGER
);
CREATE TABLE chapters (
    id TEXT PRIMARY KEY, subject_id TEXT NOT NULL REFERENCES subjects(id),
    number INTEGER NOT NULL, name TEXT NOT NULL, name_en TEXT
);
CREATE TABLE questions (
    id TEXT PRIMARY KEY,
    chapter_id TEXT NOT NULL REFERENCES chapters(id),
    type TEXT NOT NULL,              -- mcq | cq_short | cq_analytical
    text TEXT, text_en TEXT, image TEXT,
    board TEXT, year TEXT, marks INTEGER, difficulty TEXT,
    tags TEXT,                       -- JSON array
    review_note TEXT,                -- non-NULL = flagged for review
    extra_json TEXT                  -- stem, stem_image, statements, set, qno, group, answer (cq_short) ...
);
CREATE TABLE mcq_options (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    question_id TEXT NOT NULL REFERENCES questions(id),
    label TEXT NOT NULL, text TEXT, image TEXT,
    is_correct BOOLEAN NOT NULL DEFAULT 0
);
CREATE TABLE cq_parts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    question_id TEXT NOT NULL REFERENCES questions(id),
    label TEXT NOT NULL, text TEXT NOT NULL, marks INTEGER NOT NULL,
    bloom_level TEXT, answer TEXT, answer_image TEXT
);
CREATE TABLE test_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL, finished_at TEXT,
    subject_id TEXT REFERENCES subjects(id),
    mode TEXT NOT NULL, chapters TEXT NOT NULL,
    total_questions INTEGER NOT NULL, correct INTEGER, score_pct REAL,
    time_taken INTEGER, config_json TEXT
);
CREATE TABLE test_answers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL REFERENCES test_sessions(id),
    question_id TEXT NOT NULL,        -- no FK: history must survive question edits
    given_answer TEXT, is_correct BOOLEAN, time_spent INTEGER, self_grade INTEGER
);
CREATE INDEX idx_questions_chapter ON questions(chapter_id);
CREATE INDEX idx_questions_type ON questions(type);
CREATE INDEX idx_questions_board_year ON questions(board, year);
CREATE INDEX idx_mcq_options_question ON mcq_options(question_id);
CREATE INDEX idx_cq_parts_question ON cq_parts(question_id);
CREATE INDEX idx_test_answers_session ON test_answers(session_id);
CREATE INDEX idx_test_sessions_subject ON test_sessions(subject_id);
CREATE VIRTUAL TABLE questions_fts USING fts5(
    id, text, text_en, tags, content='questions', content_rowid='rowid'
);
"""

def collect():
    """Read every JSON file; return (subjects, chapters, questions) as plain lists."""
    subjects, chapters, questions = [], [], []
    for sdir in subject_dirs():
        meta = load_json(sdir / "meta.json")
        sid = meta["subject_id"]
        subjects.append((sid, meta["subject_name"], meta.get("subject_name_en"), meta.get("subject_code")))
        for c in meta["chapters"]:
            chapters.append((f"{sid}-ch{c['number']}", sid, c["number"], c["name"], c.get("name_en")))
        for number, _name, path in question_files(sdir):
            doc = load_json(path)
            for q in doc["questions"]:
                questions.append((sid, number, doc["type"], q))
    return subjects, chapters, questions


def insert_question(cur, sid, number, qtype, q):
    src = q.get("source", {})
    # Everything that has no column of its own goes into extra_json.
    keys = ["stem", "stem_en", "stem_image", "statements", "group", "explanation"]
    if qtype == "cq_short":
        keys += ["answer", "answer_image"]          # MCQ answers live in mcq_options.is_correct
    extra = {k: q[k] for k in keys if q.get(k) is not None}
    for k in ("qno", "session"):
        if src.get(k) is not None:
            extra["source_" + k] = src[k]

    if qtype == "cq_analytical":
        text, text_en, image, marks = q["stem"], q.get("stem_en"), q.get("stem_image"), q.get("total_marks")
        extra.pop("stem", None); extra.pop("stem_en", None); extra.pop("stem_image", None)
    else:
        text, text_en, image = q["text"], q.get("text_en"), q.get("image")
        marks = 1 if qtype == "mcq" else q.get("marks")

    cur.execute(
        "INSERT INTO questions (id, chapter_id, type, text, text_en, image, board, year, marks,"
        " difficulty, tags, review_note, extra_json) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (q["id"], f"{sid}-ch{number}", qtype, text, text_en, image,
         src.get("board"), src.get("year"), marks, q.get("difficulty"),
         json.dumps(q.get("tags", []), ensure_ascii=False), q.get("review_note"),
         json.dumps(extra, ensure_ascii=False) if extra else None),
    )
    if qtype == "mcq":
        for o in q["options"]:
            cur.execute(
                "INSERT INTO mcq_options (question_id, label, text, image, is_correct) VALUES (?,?,?,?,?)",
                (q["id"], o["label"], o.get("text"), o.get("image"), int(o["label"] == q["answer"])))
    elif qtype == "cq_analytical":
        for p in q["parts"]:
            cur.execute(
                "INSERT INTO cq_parts (question_id, label, text, marks, bloom_level, answer, answer_image)"
                " VALUES (?,?,?,?,?,?,?)",
                (q["id"], p["label"], p["text"], p["marks"], p.get("bloom_level"),
                 p.get("answer"), p.get("answer_image")))


def main():
    check = "--check" in sys.argv
    subjects, chapters, questions = collect()
    counts = Counter(t for _, _, t, _ in questions)
    flagged = sum(1 for *_, q in questions if q.get("review_note"))

    def summary():
        per = ", ".join(f"{n} {t}" for t, n in sorted(counts.items())) or "no questions"
        return (f"{len(subjects)} subject(s), {len(chapters)} chapter(s), "
                f"{len(questions)} question(s) [{per}], {flagged} flagged for review")

    if check:
        print("[dry run]", summary())
        return 0

    tmp = DB_PATH.with_suffix(".db.new")
    tmp.unlink(missing_ok=True)
    con = sqlite3.connect(tmp)
    con.executescript(SCHEMA)
    cur = con.cursor()
    cur.executemany("INSERT INTO subjects VALUES (?,?,?,?)", subjects)
    cur.executemany("INSERT INTO chapters VALUES (?,?,?,?,?)", chapters)
    for sid, number, qtype, q in questions:
        insert_question(cur, sid, number, qtype, q)
    cur.execute("INSERT INTO questions_fts(questions_fts) VALUES('rebuild')")
    con.commit()

    kept = 0
    if DB_PATH.exists():  # carry test history over from the previous build
        con.execute("ATTACH DATABASE ? AS old", (str(DB_PATH),))
        have = {r[0] for r in con.execute("SELECT name FROM old.sqlite_master WHERE type='table'")}
        if {"test_sessions", "test_answers"} <= have:
            con.execute("INSERT INTO test_sessions SELECT * FROM old.test_sessions")
            con.execute("INSERT INTO test_answers SELECT * FROM old.test_answers")
            kept = con.execute("SELECT COUNT(*) FROM test_sessions").fetchone()[0]
            con.commit()
        con.execute("DETACH DATABASE old")
    con.close()
    tmp.replace(DB_PATH)
    print("Built", DB_PATH.name + ":", summary())
    if kept:
        print(f"Kept {kept} test session(s) from the previous database.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
