#!/usr/bin/env python3
"""HSC question bank — local Flask app.   python app/server.py  →  http://localhost:5000"""
import sys
from pathlib import Path

from flask import Flask, abort, g, jsonify, redirect, render_template, request, send_from_directory, url_for

sys.path.insert(0, str(Path(__file__).parent))
import db  # noqa: E402

app = Flask(__name__)
app.json.ensure_ascii = False

MODE_LABELS = {"mcq": "বহুনির্বাচনি (MCQ)", "cq_short": "সৃজনশীল — ছোট (১/২ নম্বর)", "cq_analytical": "সৃজনশীল — বিশ্লেষণধর্মী"}
BN_DIGITS = str.maketrans("0123456789", "০১২৩৪৫৬৭৮৯")
PAGE_SIZE = 25


def con():
    if "db" not in g:
        g.db = db.connect()
    return g.db


@app.teardown_appcontext
def close_db(_exc):
    c = g.pop("db", None)
    if c is not None:
        c.close()


@app.context_processor
def inject():
    return {"MODE_LABELS": MODE_LABELS, "board_names": db.board_names()}


@app.template_filter("bn")
def bn(value):
    return str(value).translate(BN_DIGITS)


@app.template_filter("dt")
def fmt_dt(value):
    return value.replace("T", " ")[:16] if value else ""


@app.template_filter("mmss")
def mmss(seconds):
    seconds = int(seconds or 0)
    return f"{seconds // 60}:{seconds % 60:02d}"


# ------------------------------------------------------------------ pages

@app.route("/")
def index():
    return render_template("index.html", subjects=db.subjects(con()), stats=db.stats(con()),
                           recent=db.history(con(), limit=5))


@app.route("/quiz/setup")
def quiz_setup():
    subjects = db.subjects(con())
    for s in subjects:
        s["boards"], s["years"] = db.filter_options(con(), s["id"])
    return render_template("quiz-setup.html", subjects=subjects, preselect=request.args.get("subject"))


@app.route("/quiz/mcq/<int:sid>")
def quiz_mcq(sid):
    return _quiz_page(sid, "mcq", "quiz-mcq.html")


@app.route("/quiz/cq/<int:sid>")
def quiz_cq(sid):
    return _quiz_page(sid, "cq", "quiz-cq.html")


def _quiz_page(sid, kind, template):
    session = db.get_session(con(), sid)
    if not session or (kind == "mcq") != (session["mode"] == "mcq"):
        abort(404)
    if session["finished_at"]:
        return redirect(url_for("quiz_results", sid=sid))
    questions = db.fetch(con(), ordered_ids=session["config"]["question_ids"], reveal=(kind == "cq"))
    return render_template(template, session=session, questions=questions)


@app.route("/quiz/results/<int:sid>")
def quiz_results(sid):
    session = db.get_session(con(), sid)
    if not session or not session["finished_at"]:
        abort(404)
    questions = db.fetch(con(), ordered_ids=session["config"]["question_ids"], reveal=True)
    answers = db.session_answers(con(), sid)
    return render_template("results.html", session=session, questions=questions, answers=answers)


@app.route("/browse")
def browse():
    f = _browse_filters()
    page = max(1, request.args.get("page", 1, type=int))
    total = db.count_questions(con(), **f["query"])
    questions = db.fetch(con(), reveal=True, limit=PAGE_SIZE, offset=(page - 1) * PAGE_SIZE, **f["query"])
    subjects = db.subjects(con())
    boards, years = db.filter_options(con(), f["form"]["subject"]) if f["form"]["subject"] else ([], [])
    args = {k: v for k, v in request.args.items() if k != "page" and v}
    return render_template("browse.html", questions=questions, total=total, page=page, pages=-(-total // PAGE_SIZE),
                           f=f["form"], subjects=subjects, boards=boards, years=years, args=args)


def _browse_filters():
    a = request.args
    subjects = db.subjects(con())
    subject = a.get("subject") or (subjects[0]["id"] if len(subjects) == 1 else "")
    chapter = a.get("chapter", type=int)
    form = {"subject": subject, "chapter": chapter, "type": a.get("type", ""), "board": a.get("board", ""),
            "year": a.get("year", ""), "q": a.get("q", "").strip(), "flagged": a.get("flagged") == "1"}
    query = dict(subject=subject or None, chapters=[chapter] if chapter else None, qtype=form["type"] or None,
                 board=form["board"] or None, year=form["year"] or None, q=form["q"] or None, flagged=form["flagged"])
    return {"form": form, "query": query}


@app.route("/history")
def history():
    return render_template("history.html", sessions=db.history(con()), stats=db.stats(con()),
                           subjects={s["id"]: s for s in db.subjects(con())})


@app.route("/media/<subject>/<path:path>")
def media(subject, path):
    folder = db.subject_folders().get(subject)
    if not folder:
        abort(404)
    return send_from_directory(folder, path)


# ------------------------------------------------------------------ API

@app.route("/api/questions")
def api_questions():
    a = request.args
    chapters = [int(x) for x in a.get("chapter", "").split(",") if x.strip().isdigit()]
    f = dict(subject=a.get("subject") or None, chapters=chapters or None, qtype=a.get("type") or None,
             board=a.get("board") or None, year=a.get("year") or None, q=a.get("q") or None)
    limit = min(a.get("limit", 25, type=int), 200)
    if a.get("random") == "true":
        ids = db.pick_ids(con(), limit, shuffle=True, **f)
        questions = db.fetch(con(), ordered_ids=ids, reveal=False)
    else:
        questions = db.fetch(con(), reveal=False, limit=limit, offset=a.get("offset", 0, type=int), **f)
    return jsonify({"count": len(questions), "questions": questions})


@app.route("/api/stats")
def api_stats():
    return jsonify(db.stats(con(), request.args.get("subject") or None))


@app.route("/api/quiz/start", methods=["POST"])
def api_quiz_start():
    b = request.get_json(silent=True) or {}
    mode = b.get("type", "mcq")
    if mode not in MODE_LABELS:
        return jsonify(error="Unknown quiz type"), 400
    subject = b.get("subject")
    chapters = [int(c) for c in b.get("chapters", [])]
    if not subject or not chapters:
        return jsonify(error="Pick a subject and at least one chapter"), 400
    f = dict(subject=subject, chapters=chapters, qtype=mode, board=b.get("board") or None, year=b.get("year") or None)
    ids = db.pick_ids(con(), int(b.get("count") or 0) or 25, shuffle=b.get("random", True), **f)
    if not ids:
        return jsonify(error="No questions match these filters"), 404
    minutes = int(b.get("time_minutes") or 0) if b.get("timed") else 0
    config = {"timed": bool(minutes), "time_minutes": minutes, "random": bool(b.get("random", True)),
              "board": f["board"], "year": f["year"]}
    sid = db.create_session(con(), subject, mode, chapters, ids, config)
    page = "quiz_mcq" if mode == "mcq" else "quiz_cq"
    return jsonify(session_id=sid, total=len(ids), url=url_for(page, sid=sid))


@app.route("/api/quiz/submit", methods=["POST"])
def api_quiz_submit():
    b = request.get_json(silent=True) or {}
    session = db.get_session(con(), b.get("session_id"))
    if not session:
        return jsonify(error="Unknown session"), 404
    if session["finished_at"]:
        return jsonify(error="Already submitted", url=url_for("quiz_results", sid=session["id"])), 409
    answers = b.get("answers", [])
    if session["mode"] == "mcq":
        got, total = db.finish_mcq(con(), session, answers)
    else:
        got, total = db.finish_cq(con(), session, answers)
    return jsonify(score=got, total=total, percentage=round(100 * got / total, 1) if total else 0,
                   url=url_for("quiz_results", sid=session["id"]))


if __name__ == "__main__":
    if not db.DB_PATH.exists():
        sys.exit("hsc-questions.db not found. Build it first:  python scripts/build_db.py")
    app.run(host="127.0.0.1", port=5000, debug="--debug" in sys.argv)
