"""Run logging for this kit's scripts: a logger per module, a run id on every line, and
an optional JSON-lines format.

    import runlog
    log = runlog.get_logger(__name__)
    runlog.setup()                      # once per run, in main(); returns the run id
    runlog.run(main)                    # at the bottom of a script: one place for crashes

Settings (environment variables):
    LOG_LEVEL   DEBUG, INFO, WARNING (default) or ERROR
    LOG_FORMAT  text (default) or json: one JSON object per line
    LOG_FILE    append log lines to this file instead of standard error
    RUN_ID      reuse a run id handed down by a caller (default: a new one per run)

Log lines go to standard error or LOG_FILE, never to standard output, so what a script
prints is unchanged. The scripts log counts, paths and ids. An error is logged with its
message and traceback, which can quote the text the failing step was reading, so treat
a LOG_FILE like the files the kit works on. Standard library only; works on Python 3.9
and later.
"""

from __future__ import annotations

import datetime
import json
import logging
import os
import sys
import uuid

_HANDLER_FLAG = "_runlog_handler"
_state = {"run_id": "-"}


def new_run_id() -> str:
    """A sortable id: UTC time plus 8 random hex characters."""
    now = datetime.datetime.now(datetime.timezone.utc)
    return now.strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]


def run_id() -> str:
    return _state["run_id"]


class _RunId(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.run_id = _state["run_id"]
        return True


class _Json(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        ts = datetime.datetime.fromtimestamp(record.created, datetime.timezone.utc)
        doc = {
            "ts": ts.isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "run_id": getattr(record, "run_id", "-"),
            "msg": record.getMessage(),
        }
        if record.exc_info:
            doc["exc"] = self.formatException(record.exc_info)
        return json.dumps(doc, ensure_ascii=False)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def setup(run_id: str | None = None) -> str:
    """Configure the root logger from the environment; safe to call more than once."""
    _state["run_id"] = run_id or os.environ.get("RUN_ID") or new_run_id()
    root = logging.getLogger()
    for h in [h for h in root.handlers if getattr(h, _HANDLER_FLAG, False)]:
        root.removeHandler(h)
        h.close()
    path = os.environ.get("LOG_FILE")
    handler = (
        logging.FileHandler(path, encoding="utf-8") if path else logging.StreamHandler()
    )
    setattr(handler, _HANDLER_FLAG, True)
    handler.addFilter(_RunId())
    if os.environ.get("LOG_FORMAT", "text").strip().lower() == "json":
        handler.setFormatter(_Json())
    else:
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s %(levelname)s %(name)s [run %(run_id)s] %(message)s"
            )
        )
    root.addHandler(handler)
    level = os.environ.get("LOG_LEVEL", "WARNING").strip().upper()
    root.setLevel(
        level if level in ("DEBUG", "INFO", "WARNING", "ERROR") else "WARNING"
    )
    return _state["run_id"]


def run(main) -> None:
    """Call main() and exit with its code; an unexpected error is logged once, with the
    run id, and becomes a one-line message and exit code 1."""
    try:
        code = main()
    # the one top-level catch; SystemExit and Ctrl-C pass through untouched
    except Exception as exc:
        if _state["run_id"] == "-":
            setup()
        logging.getLogger("runlog").exception("unexpected error")
        sys.stderr.write(f"error: {exc.__class__.__name__}: {exc} (run {run_id()})\n")
        code = 1
    sys.exit(code)
