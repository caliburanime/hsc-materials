"""Shared helpers for the data scripts."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
DB_PATH = ROOT / "hsc-questions.db"
QUESTION_FILES = {"mcq.json": "mcq", "cq-short.json": "cq_short", "cq-analytical.json": "cq_analytical"}


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def subject_dirs(only=None):
    """Subject folders under data/ that have a meta.json (optionally just `only`)."""
    dirs = sorted(p for p in DATA.iterdir() if p.is_dir() and (p / "meta.json").exists())
    if only:
        only = Path(only).resolve()
        dirs = [d for d in dirs if d.resolve() == only]
    return dirs


def question_files(subject_dir):
    """Yield (chapter_number, file_name, path) for every question file in a subject."""
    for chapter_dir in sorted(subject_dir.glob("chapter-*")):
        try:
            number = int(chapter_dir.name.split("-", 1)[1])
        except ValueError:
            continue
        for name in QUESTION_FILES:
            path = chapter_dir / name
            if path.exists():
                yield number, name, path
