# HSC Question Bank

Local quiz app for Bangladesh HSC board questions. Design: see [system-design.md](system-design.md).

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python scripts/validate.py     # check data/
.venv/bin/python scripts/build_db.py     # JSON -> hsc-questions.db (test history is preserved)
.venv/bin/python app/server.py           # http://localhost:5000
```

Questions live in `data/<Subject>/chapter-N/{mcq,cq-short,cq-analytical}.json`; images in `data/<Subject>/assets/`.
Questions marked ⚠ have a `review_note` (doubt about transcription or the printed answer key).
