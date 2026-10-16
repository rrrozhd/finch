"""Typed, time-aware facts in SurrealDB. Writing a key again supersedes (never overwrites) the old fact."""
import os
import threading

from surrealdb import Surreal

_db = None
_lock = threading.RLock()  # FastAPI runs sync endpoints in a threadpool; the embedded connection is not thread-safe


def db():
    global _db
    if _db is None:
        _db = Surreal(os.getenv("SURREAL_URL") or "mem://")
        if os.getenv("SURREAL_USER"):
            _db.signin({"username": os.environ["SURREAL_USER"], "password": os.environ["SURREAL_PASS"]})
        _db.use(os.getenv("SURREAL_NS", "taxagent"), os.getenv("SURREAL_DB", "demo"))
    return _db


def _q(sql, params):
    with _lock:
        return db().query(sql, params)


def put(session: str, key: str, value, source: str, by: str, reason: str = "") -> dict:
    """by: which agent/stage wrote it (intake, categorizer, ocr, vision, user)."""
    _q("UPDATE fact SET current = false, superseded_at = time::now() "
               "WHERE session = $s AND key = $k AND current = true", {"s": session, "k": key})
    return _q("CREATE fact SET session = $s, key = $k, data = $v, source = $src, by = $by, reason = $r, "
                      "at = time::now(), current = true RETURN AFTER",
                      {"s": session, "k": key, "v": value, "src": source, "by": by, "r": reason})[0]


def current(session: str, prefix: str = "") -> dict:
    rows = _q("SELECT key, data, source, by, at FROM fact WHERE session = $s AND current = true "
                      "AND string::starts_with(key, $p)", {"s": session, "p": prefix})
    return {r["key"]: _v(r) for r in rows}


def history(session: str, key: str) -> list:
    return [_v(r) for r in _q("SELECT data, source, by, reason, at, superseded_at, current FROM fact "
                                      "WHERE session = $s AND key = $k ORDER BY at", {"s": session, "k": key})]


def _v(row: dict) -> dict:
    row["value"] = row.pop("data")  # `value` is reserved in SurrealQL, so it is stored as `data`
    return row
