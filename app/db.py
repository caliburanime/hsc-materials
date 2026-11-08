"""Database access layer. Every function takes an open sqlite3 connection."""
import json
import random
import sqlite3
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "hsc-questions.db"
DATA_DIR = ROOT / "data"


def connect():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def now():
    return datetime.now().isoformat(timespec="seconds")


# ---------------------------------------------------------------- catalogue

def subject_folders():
    """{subject_id: data/<Folder>} — folder names are cased ('ICT'), ids are not ('ict')."""
    out = {}
    for meta in DATA_DIR.glob("*/meta.json"):
        sid = json.loads(meta.read_text(encoding="utf-8"))["subject_id"]
        out[sid] = meta.parent
    return out


def board_names():
    names = {}
    for meta in DATA_DIR.glob("*/meta.json"):
        for b in json.loads(meta.read_text(encoding="utf-8")).get("boards", []):
            names[b["code"]] = b["name"]
    return names


def subjects(con):
    """Subjects with per-type question counts and their chapters."""
    out = []
    for s in con.execute("SELECT * FROM subjects ORDER BY name_en"):
        s = dict(s)
        s["counts"] = {r["type"]: r["n"] for r in con.execute(
            "SELECT q.type, COUNT(*) n FROM questions q JOIN chapters c ON c.id=q.chapter_id "
            "WHERE c.subject_id=? GROUP BY q.type", (s["id"],))}
        s["chapters"] = []
        for c in con.execute("SELECT * FROM chapters WHERE subject_id=? ORDER BY number", (s["id"],)):
            c = dict(c)
            c["counts"] = {r["type"]: r["n"] for r in con.execute(
                "SELECT type, COUNT(*) n FROM questions WHERE chapter_id=? GROUP BY type", (c["id"],))}
            s["chapters"].append(c)
        out.append(s)
    return out


def filter_options(con, subject):
    """Boards and years that actually occur in the data (for filter dropdowns)."""
    base = "FROM questions q JOIN chapters c ON c.id=q.chapter_id WHERE c.subject_id=?"
    boards = [r[0] for r in con.execute(f"SELECT DISTINCT q.board {base} AND q.board IS NOT NULL ORDER BY 1", (subject,))]
    years = [r[0] for r in con.execute(f"SELECT DISTINCT q.year {base} AND q.year IS NOT NULL ORDER BY 1 DESC", (subject,))]
    return boards, years


# ---------------------------------------------------------------- questions

def _where(subject=None, chapters=None, qtype=None, board=None, year=None, ids=None, q=None, flagged=False):
    cond, args = [], []
    if subject:
        cond.append("c.subject_id=?"); args.append(subject)
    if chapters:
        cond.append(f"c.number IN ({','.join('?' * len(chapters))})"); args += list(chapters)
    if qtype:
        cond.append("q.type=?"); args.append(qtype)
    if board:
        cond.append("q.board=?"); args.append(board)
    if year:
        cond.append("q.year=?"); args.append(year)
    if ids is not None:
        cond.append(f"q.id IN ({','.join('?' * len(ids))})"); args += list(ids)
    if flagged:
        cond.append("q.review_note IS NOT NULL")
    if q:
        # Phrase-quote the term so FTS5 syntax characters in user input can't break the query.
        term = '"' + q.replace('"', '""') + '"'
        cond.append("q.rowid IN (SELECT rowid FROM questions_fts WHERE questions_fts MATCH ?)"); args.append(term)
    return (" WHERE " + " AND ".join(cond)) if cond else "", args


_FROM = "FROM questions q JOIN chapters c ON c.id=q.chapter_id"


def count_questions(con, **f):
    where, args = _where(**f)
    return con.execute(f"SELECT COUNT(*) {_FROM}{where}", args).fetchone()[0]


def pick_ids(con, count, shuffle=True, **f):
    where, args = _where(**f)
    ids = [r[0] for r in con.execute(f"SELECT q.id {_FROM}{where} ORDER BY q.id", args)]
    if shuffle:
        random.shuffle(ids)
    return ids[:count] if count else ids


def media_url(question_id, path):
    """Question images are stored relative to the subject folder; serve them via /media/."""
    return f"/media/{question_id.split('-', 1)[0]}/{path}" if path else None


def _looks_like_code(s):
    return bool(s) and ("{" in s or ";" in s) and "\n" in s


def fetch(con, ids=None, reveal=False, ordered_ids=None, limit=None, offset=0, **f):
    """Return fully-assembled question dicts. Answers are only included when reveal=True."""
    if ordered_ids is not None:
        ids = ordered_ids
    if ids is not None and not ids:
        return []
    where, args = _where(ids=ids, **f)
    sql = f"SELECT q.*, c.number AS chapter, c.name AS chapter_name {_FROM}{where} ORDER BY q.id"
    if limit:
        sql += " LIMIT ? OFFSET ?"; args += [limit, offset]
    rows = [dict(r) for r in con.execute(sql, args)]
    if not rows:
        return []
    qids = [r["id"] for r in rows]
    marks = ",".join("?" * len(qids))
    opts, parts = {}, {}
    for o in con.execute(f"SELECT * FROM mcq_options WHERE question_id IN ({marks}) ORDER BY id", qids):
        opts.setdefault(o["question_id"], []).append(o)
    for p in con.execute(f"SELECT * FROM cq_parts WHERE question_id IN ({marks}) ORDER BY id", qids):
        parts.setdefault(p["question_id"], []).append(p)

    out = []
    for r in rows:
        extra = json.loads(r["extra_json"]) if r["extra_json"] else {}
        qid = r["id"]
        q = {
            "id": qid, "type": r["type"], "chapter": r["chapter"], "chapter_name": r["chapter_name"],
            "text": r["text"], "text_en": r["text_en"], "image": media_url(qid, r["image"]),
            "stem": extra.get("stem"), "stem_image": media_url(qid, extra.get("stem_image")),
            "statements": extra.get("statements", []), "group": extra.get("group"),
            "board": r["board"], "year": r["year"], "qno": extra.get("source_qno"),
            "tags": json.loads(r["tags"] or "[]"), "marks": r["marks"], "review_note": r["review_note"],
        }
        q["stem_is_code"] = _looks_like_code(q["stem"])
        if r["type"] == "mcq":
            q["options"] = []
            for o in opts.get(qid, []):
                d = {"label": o["label"], "text": o["text"], "image": media_url(qid, o["image"])}
                if reveal:
                    d["is_correct"] = bool(o["is_correct"])
                q["options"].append(d)
            if reveal:
                q["answer"] = next((o["label"] for o in opts.get(qid, []) if o["is_correct"]), None)
                q["explanation"] = extra.get("explanation")
        else:
            q["answer"] = extra.get("answer") if reveal or r["type"] == "cq_short" else None
            q["answer_image"] = media_url(qid, extra.get("answer_image"))
            q["parts"] = [{"label": p["label"], "text": p["text"], "marks": p["marks"], "bloom_level": p["bloom_level"],
                           "answer": p["answer"], "answer_image": media_url(qid, p["answer_image"])}
                          for p in parts.get(qid, [])]
        out.append(q)
    if ordered_ids is not None:
        pos = {i: n for n, i in enumerate(ordered_ids)}
        out.sort(key=lambda q: pos[q["id"]])
    return out


# ---------------------------------------------------------------- sessions

def create_session(con, subject, mode, chapters, question_ids, config):
    cfg = dict(config, question_ids=question_ids)
    cur = con.execute(
        "INSERT INTO test_sessions (started_at, subject_id, mode, chapters, total_questions, config_json) "
        "VALUES (?,?,?,?,?,?)",
        (now(), subject, mode, json.dumps(chapters), len(question_ids), json.dumps(cfg)))
    con.commit()
    return cur.lastrowid


def get_session(con, sid):
    row = con.execute("SELECT * FROM test_sessions WHERE id=?", (sid,)).fetchone()
    if not row:
        return None
    s = dict(row)
    s["config"] = json.loads(s["config_json"] or "{}")
    s["chapters"] = json.loads(s["chapters"] or "[]")
    return s


def finish_mcq(con, session, answers):
    """Grade MCQ answers [{question_id, answer, time_spent}] and persist. Returns (correct, total)."""
    ids = session["config"]["question_ids"]
    given = {a["question_id"]: a for a in answers if a.get("question_id") in set(ids)}
    key = {r["question_id"]: r["label"] for r in con.execute(
        f"SELECT question_id, label FROM mcq_options WHERE is_correct=1 AND question_id IN ({','.join('?' * len(ids))})", ids)}
    correct = 0
    con.execute("DELETE FROM test_answers WHERE session_id=?", (session["id"],))
    for qid in ids:
        a = given.get(qid, {})
        ans = a.get("answer") or None
        ok = ans is not None and ans == key.get(qid)
        correct += ok
        con.execute("INSERT INTO test_answers (session_id, question_id, given_answer, is_correct, time_spent) VALUES (?,?,?,?,?)",
                    (session["id"], qid, ans, int(ok), int(a.get("time_spent") or 0)))
    _close(con, session, correct, len(ids), max_marks=len(ids))
    return correct, len(ids)


def finish_cq(con, session, answers):
    """Self-graded CQ: answers [{question_id, self_grade, time_spent}]. `correct` = marks obtained."""
    ids = session["config"]["question_ids"]
    max_marks = {r["id"]: r["marks"] or 0 for r in con.execute(
        f"SELECT id, marks FROM questions WHERE id IN ({','.join('?' * len(ids))})", ids)}
    given = {a["question_id"]: a for a in answers if a.get("question_id") in max_marks}
    got = 0
    con.execute("DELETE FROM test_answers WHERE session_id=?", (session["id"],))
    for qid in ids:
        a = given.get(qid, {})
        g = a.get("self_grade")
        g = None if g is None else max(0, min(int(g), max_marks[qid]))
        got += g or 0
        con.execute("INSERT INTO test_answers (session_id, question_id, given_answer, is_correct, time_spent, self_grade) VALUES (?,?,?,?,?,?)",
                    (session["id"], qid, None, None if g is None else int(g == max_marks[qid]), int(a.get("time_spent") or 0), g))
    _close(con, session, got, len(ids), max_marks=sum(max_marks.values()))
    return got, sum(max_marks.values())


def _close(con, session, correct, total, max_marks):
    started = datetime.fromisoformat(session["started_at"])
    taken = int((datetime.now() - started).total_seconds())
    pct = round(100.0 * correct / max_marks, 1) if max_marks else 0.0
    con.execute("UPDATE test_sessions SET finished_at=?, correct=?, score_pct=?, time_taken=? WHERE id=?",
                (now(), correct, pct, taken, session["id"]))
    con.commit()


def session_answers(con, session_id):
    return {r["question_id"]: dict(r) for r in con.execute("SELECT * FROM test_answers WHERE session_id=?", (session_id,))}


def history(con, subject=None, limit=100):
    sql = "SELECT * FROM test_sessions WHERE finished_at IS NOT NULL"
    args = []
    if subject:
        sql += " AND subject_id=?"; args.append(subject)
    sql += " ORDER BY id DESC LIMIT ?"; args.append(limit)
    out = []
    for r in con.execute(sql, args):
        r = dict(r); r["chapters"] = json.loads(r["chapters"] or "[]"); out.append(r)
    return out


def stats(con, subject=None):
    args = [subject] if subject else []
    sub = " AND subject_id=?" if subject else ""
    t = con.execute(f"SELECT COUNT(*) n, AVG(score_pct) avg, MAX(score_pct) best FROM test_sessions "
                    f"WHERE finished_at IS NOT NULL{sub}", args).fetchone()
    by_chapter = []
    sql = ("SELECT c.subject_id, c.number, c.name, COUNT(*) n, SUM(a.is_correct) ok "
           "FROM test_answers a JOIN test_sessions s ON s.id=a.session_id "
           "JOIN questions q ON q.id=a.question_id JOIN chapters c ON c.id=q.chapter_id "
           "WHERE s.finished_at IS NOT NULL AND q.type='mcq'" + (" AND c.subject_id=?" if subject else "") +
           " GROUP BY c.id ORDER BY c.subject_id, c.number")
    for r in con.execute(sql, args):
        by_chapter.append({"subject": r["subject_id"], "chapter": r["number"], "name": r["name"],
                           "answered": r["n"], "correct": r["ok"] or 0, "pct": round(100.0 * (r["ok"] or 0) / r["n"], 1)})
    return {"total_tests": t["n"], "avg_score": round(t["avg"], 1) if t["avg"] is not None else None,
            "best_score": t["best"], "by_chapter": by_chapter,
            "recent": [{"id": s["id"], "finished_at": s["finished_at"], "score_pct": s["score_pct"], "mode": s["mode"]}
                       for s in history(con, subject, 10)]}


# ---------------------------------------------------------------- dashboard

WEAK_BELOW_PCT = 60      # chapter accuracy under this is "weak"...
WEAK_MIN_ANSWERS = 5     # ...once at least this many answers back it up
MISSED_MIN_ATTEMPTS = 2  # a question needs this many attempts to be called "often missed"
THIN_BELOW = 5           # fewer MCQs than this in a chapter = thin coverage


def unfinished_sessions(con):
    """Quizzes that were started but never submitted, newest first."""
    out = []
    for r in con.execute("SELECT * FROM test_sessions WHERE finished_at IS NULL ORDER BY id DESC"):
        s = dict(r)
        cfg = json.loads(s["config_json"] or "{}")
        s["chapters"] = json.loads(s["chapters"] or "[]")
        minutes = cfg.get("time_minutes") or 0
        s["timed"] = bool(minutes)
        s["expired"] = bool(minutes) and (datetime.now() - datetime.fromisoformat(s["started_at"])).total_seconds() > minutes * 60
        out.append(s)
    return out


def discard_session(con, sid):
    """Delete an unfinished session. Finished ones are history and are never deleted here."""
    row = con.execute("SELECT finished_at FROM test_sessions WHERE id=?", (sid,)).fetchone()
    if not row or row["finished_at"]:
        return False
    con.execute("DELETE FROM test_answers WHERE session_id=?", (sid,))
    con.execute("DELETE FROM test_sessions WHERE id=?", (sid,))
    con.commit()
    return True


def attention(con):
    """Everything on the dashboard that wants the teacher's eye."""
    by_chapter = {(c["subject"], c["chapter"]): c for c in stats(con)["by_chapter"]}

    weak = sorted((c for c in by_chapter.values() if c["answered"] >= WEAK_MIN_ANSWERS and c["pct"] < WEAK_BELOW_PCT),
                  key=lambda c: c["pct"])

    missed = []
    for r in con.execute(
        "SELECT q.id, q.text, c.subject_id, c.number, COUNT(*) n, SUM(a.is_correct) ok "
        "FROM test_answers a JOIN test_sessions s ON s.id=a.session_id "
        "JOIN questions q ON q.id=a.question_id JOIN chapters c ON c.id=q.chapter_id "
        "WHERE s.finished_at IS NOT NULL AND q.type='mcq' GROUP BY q.id "
        "HAVING n >= ? AND 1.0 * COALESCE(ok, 0) / n < 0.5 ORDER BY 1.0 * COALESCE(ok, 0) / n, n DESC LIMIT 5",
            (MISSED_MIN_ATTEMPTS,)):
        text = " ".join((r["text"] or "").split())
        missed.append({"id": r["id"], "text": text if len(text) <= 90 else text[:87] + "…", "chapter": r["number"],
                       "attempts": r["n"], "wrong": r["n"] - (r["ok"] or 0)})

    untested, thin = [], []
    for s in subjects(con):
        for c in s["chapters"]:
            n = c["counts"].get("mcq", 0)
            if n and (s["id"], c["number"]) not in by_chapter:
                untested.append({"subject": s["id"], "subject_name": s["name_en"], "chapter": c["number"], "name": c["name"], "mcq": n})
            if n < THIN_BELOW:
                thin.append({"subject_name": s["name_en"], "chapter": c["number"], "name": c["name"], "mcq": n})

    flagged = con.execute("SELECT COUNT(*) FROM questions WHERE review_note IS NOT NULL").fetchone()[0]
    return {"weak": weak, "missed": missed, "untested": untested, "thin": thin, "flagged": flagged,
            "unfinished": unfinished_sessions(con)}
