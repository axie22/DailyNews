"""SQLite state: items, Jev features, deliveries, feedback, source health.

The DB file lives on an (optionally encrypted) orphan `data` branch between GitHub
Actions runs, so everything here must be safe to resume after a crash mid-run.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from dailynews.sources.base import RawItem

SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
  id INTEGER PRIMARY KEY,
  url TEXT NOT NULL,
  url_hash TEXT NOT NULL UNIQUE,
  title TEXT NOT NULL,
  title_key TEXT NOT NULL,
  content TEXT NOT NULL DEFAULT '',
  source TEXT NOT NULL,
  source_group TEXT NOT NULL,
  lab TEXT,
  arxiv_id TEXT,
  family TEXT,
  published_at TEXT NOT NULL,
  first_seen TEXT NOT NULL,
  meta TEXT NOT NULL DEFAULT '{}',
  cluster_id INTEGER,              -- NULL = canonical; else id of the canonical item
  status TEXT NOT NULL DEFAULT 'new'   -- new | seed | sent
);
CREATE INDEX IF NOT EXISTS ix_items_arxiv ON items(arxiv_id);
CREATE INDEX IF NOT EXISTS ix_items_family ON items(family);
CREATE INDEX IF NOT EXISTS ix_items_first_seen ON items(first_seen);

CREATE TABLE IF NOT EXISTS features (
  item_id INTEGER PRIMARY KEY REFERENCES items(id) ON DELETE CASCADE,
  qset TEXT NOT NULL,
  model TEXT NOT NULL,
  answers TEXT NOT NULL,
  classified_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS deliveries (
  id INTEGER PRIMARY KEY,
  item_id INTEGER NOT NULL,
  kind TEXT NOT NULL,               -- digest | breaking
  message_id INTEGER,
  score REAL,
  sent_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS feedback (
  item_id INTEGER PRIMARY KEY,
  label INTEGER NOT NULL,           -- +1 / -1 (latest tap wins)
  at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS source_runs (
  id INTEGER PRIMARY KEY,
  source TEXT NOT NULL,
  run_at TEXT NOT NULL,
  fetched INTEGER NOT NULL,
  new_items INTEGER NOT NULL DEFAULT 0,
  error TEXT
);
CREATE INDEX IF NOT EXISTS ix_source_runs ON source_runs(source, run_at);

CREATE TABLE IF NOT EXISTS usage (
  id INTEGER PRIMARY KEY,
  run_at TEXT NOT NULL,
  calls INTEGER NOT NULL,
  input_tokens INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""

_STOP = set("a an and the of for to in on with by from at is are via as its it this that new".split())


def normalize_url(url: str) -> str:
    p = urlparse(url.strip())
    q = [(k, v) for k, v in parse_qsl(p.query) if not k.lower().startswith(("utm_", "ref", "fbclid", "gclid"))]
    return urlunparse((p.scheme.lower() or "https", p.netloc.lower().removeprefix("www."),
                       p.path.rstrip("/"), "", urlencode(q), ""))


def url_hash(url: str) -> str:
    return hashlib.sha256(normalize_url(url).encode()).hexdigest()


def title_key(title: str) -> str:
    toks = [t for t in re.findall(r"[a-z0-9]+(?:\.[0-9]+)*", title.lower()) if t not in _STOP]
    return " ".join(sorted(set(toks)))


def jaccard(a: str, b: str) -> float:
    sa, sb = set(a.split()), set(b.split())
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds")


def from_iso(s: str) -> datetime:
    return datetime.fromisoformat(s)


class Store:
    TITLE_SIM = 0.8          # near-duplicate headline threshold
    TITLE_MIN_TOKENS = 4     # don't cluster on very short titles ("Introducing Claude")
    CLUSTER_LOOKBACK = timedelta(days=4)

    def __init__(self, path: Path | str):
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(path))
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys = ON")
        self.db.executescript(SCHEMA)

    def close(self):
        self.db.commit()
        self.db.close()

    # ── kv ───────────────────────────────────────────────────────────────────
    def kv_get(self, key: str, default: str | None = None) -> str | None:
        row = self.db.execute("SELECT value FROM kv WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default

    def kv_set(self, key: str, value: str):
        self.db.execute("INSERT INTO kv(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                        (key, value))
        self.db.commit()

    # ── source bookkeeping ───────────────────────────────────────────────────
    def last_success(self, source: str) -> datetime | None:
        row = self.db.execute(
            "SELECT max(run_at) AS t FROM source_runs WHERE source=? AND error IS NULL", (source,)).fetchone()
        return from_iso(row["t"]) if row and row["t"] else None

    def source_due(self, source: str, min_interval_hours: float, now: datetime) -> bool:
        last = self.last_success(source)
        return last is None or now - last >= timedelta(hours=min_interval_hours) - timedelta(minutes=10)

    def record_source_run(self, source: str, now: datetime, fetched: int, new_items: int = 0,
                          error: str | None = None):
        self.db.execute("INSERT INTO source_runs(source, run_at, fetched, new_items, error) VALUES(?,?,?,?,?)",
                        (source, iso(now), fetched, new_items, error[:500] if error else None))
        self.db.commit()

    def source_health(self, now: datetime, lookback_runs: int = 3) -> list[str]:
        """Sources whose last N attempts all failed or returned nothing."""
        warnings = []
        sources = [r["source"] for r in self.db.execute("SELECT DISTINCT source FROM source_runs")]
        for s in sources:
            rows = self.db.execute(
                "SELECT fetched, error FROM source_runs WHERE source=? ORDER BY run_at DESC LIMIT ?",
                (s, lookback_runs)).fetchall()
            if len(rows) < lookback_runs:
                if rows and rows[0]["error"]:
                    warnings.append(f"{s}: {rows[0]['error'][:120]}")
                continue
            if all(r["error"] or r["fetched"] == 0 for r in rows):
                err = next((r["error"] for r in rows if r["error"]), "returned 0 items")
                warnings.append(f"{s}: {err[:120]}")
        return warnings

    # ── ingest + clustering ──────────────────────────────────────────────────
    def ingest(self, raws: list[RawItem], now: datetime, seed: bool = False) -> int:
        """Insert unseen items; attach duplicates to their cluster's canonical item.

        seed=True (first successful run of a source) stores its *undated* items as already
        seen. Dated items are naturally bounded by max_age_days, but an undated back catalogue
        (e.g. the scraped Anthropic research page) would otherwise all look brand new.
        Returns the number of new canonical items.
        """
        new_canonical = 0
        recent = self._recent_canonicals(now)
        for raw in raws:
            h = url_hash(raw.url)
            existing = self.db.execute("SELECT id, cluster_id FROM items WHERE url_hash=?", (h,)).fetchone()
            if existing:
                canon_id = existing["cluster_id"] or existing["id"]
                self._merge_into(canon_id, raw)
                continue

            family = raw.meta.get("family")
            tkey = title_key(raw.title)
            canon = self._find_cluster(raw, family, tkey, recent)
            published = raw.published_at or now
            status = "seed" if (seed and raw.published_at is None) else "new"
            cur = self.db.execute(
                """INSERT INTO items(url, url_hash, title, title_key, content, source, source_group, lab,
                       arxiv_id, family, published_at, first_seen, meta, cluster_id, status)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (raw.url, h, raw.title, tkey, raw.content or "", raw.source, raw.group, raw.lab,
                 raw.arxiv_id, family, iso(published), iso(now), json.dumps(raw.meta),
                 canon["id"] if canon else None, status))
            if canon:
                self._merge_into(canon["id"], raw)
            else:
                new_canonical += status == "new"
                recent.append({"id": cur.lastrowid, "arxiv_id": raw.arxiv_id, "family": family,
                               "title_key": tkey, "source": raw.source})
        self.db.commit()
        return new_canonical

    def _recent_canonicals(self, now: datetime) -> list[dict]:
        rows = self.db.execute(
            "SELECT id, arxiv_id, family, title_key, source FROM items WHERE cluster_id IS NULL AND first_seen >= ?",
            (iso(now - self.CLUSTER_LOOKBACK),)).fetchall()
        return [dict(r) for r in rows]

    def _find_cluster(self, raw: RawItem, family: str | None, tkey: str, recent: list[dict]) -> dict | None:
        if raw.arxiv_id:
            row = self.db.execute("SELECT id FROM items WHERE arxiv_id=? AND cluster_id IS NULL LIMIT 1",
                                  (raw.arxiv_id,)).fetchone()
            if row:
                return dict(row)
        for c in recent:
            if family and c["family"] == family:
                return c
        if len(tkey.split()) >= self.TITLE_MIN_TOKENS:
            for c in recent:
                # Same-source near-duplicates are usually distinct posts (e.g. "Part 1/Part 2").
                if c["source"] != raw.source and jaccard(c["title_key"], tkey) >= self.TITLE_SIM:
                    return c
        return None

    def _merge_into(self, canon_id: int, raw: RawItem):
        row = self.db.execute("SELECT meta, lab, content, url FROM items WHERE id=?", (canon_id,)).fetchone()
        if not row:
            return
        meta = json.loads(row["meta"])
        if raw.url != row["url"]:
            also = meta.setdefault("also_on", [])
            entry = {"source": raw.source, "url": raw.url}
            if entry not in also:
                also.append(entry)
        if "hf_upvotes" in raw.meta:
            meta["hf_upvotes"] = max(int(meta.get("hf_upvotes", 0)), int(raw.meta["hf_upvotes"]))
            meta.setdefault("hf_url", raw.meta.get("hf_url"))
        if raw.group == "hf_models":
            meta["variants"] = sorted(set(meta.get("variants", [])) | {raw.url.rsplit("/", 1)[-1]})[:12]
            # Traction accumulates after first sight; keep the best seen across the family's repos.
            meta["likes"] = max(int(meta.get("likes") or 0), int(raw.meta.get("likes") or 0))
            meta["downloads"] = max(int(meta.get("downloads") or 0), int(raw.meta.get("downloads") or 0))
        # A lab-attributed duplicate (e.g. an HF paper from google) upgrades the canonical item.
        lab = row["lab"] or raw.lab
        content = row["content"] if len(row["content"]) >= len(raw.content or "") else raw.content
        self.db.execute("UPDATE items SET meta=?, lab=?, content=? WHERE id=?",
                        (json.dumps(meta), lab, content, canon_id))

    # ── queries ──────────────────────────────────────────────────────────────
    @staticmethod
    def _row(r: sqlite3.Row) -> dict:
        d = dict(r)
        d["meta"] = json.loads(d.get("meta") or "{}")
        if d.get("answers"):
            d["answers"] = json.loads(d["answers"])
        return d

    def candidates(self, now: datetime, window_hours: float, max_age_days: float) -> list[dict]:
        rows = self.db.execute(
            """SELECT i.*, f.answers, f.qset, f.model FROM items i LEFT JOIN features f ON f.item_id = i.id
               WHERE i.cluster_id IS NULL AND i.status='new' AND i.first_seen >= ? AND i.published_at >= ?""",
            (iso(now - timedelta(hours=window_hours)), iso(now - timedelta(days=max_age_days)))).fetchall()
        return [self._row(r) for r in rows]

    def needing_features(self, now: datetime, qset: str, window_hours: float, max_age_days: float,
                         include_heuristic: bool) -> list[dict]:
        """Candidates without current-qset features, plus rated items (so retraining stays consistent)."""
        out = {}
        for c in self.candidates(now, window_hours, max_age_days):
            if c.get("qset") != qset or (include_heuristic and c.get("model") == "heuristic"):
                out[c["id"]] = c
        rows = self.db.execute(
            """SELECT i.*, f.answers, f.qset, f.model FROM feedback fb JOIN items i ON i.id = fb.item_id
               LEFT JOIN features f ON f.item_id = i.id WHERE f.qset IS NULL OR f.qset != ?""", (qset,)).fetchall()
        for r in rows:
            out.setdefault(r["id"], self._row(r))
        return list(out.values())

    def save_features(self, item_id: int, qset: str, model: str, answers: dict, now: datetime):
        self.db.execute(
            """INSERT INTO features(item_id, qset, model, answers, classified_at) VALUES(?,?,?,?,?)
               ON CONFLICT(item_id) DO UPDATE SET qset=excluded.qset, model=excluded.model,
               answers=excluded.answers, classified_at=excluded.classified_at""",
            (item_id, qset, model, json.dumps(answers), iso(now)))
        self.db.commit()

    def item(self, item_id: int) -> dict | None:
        r = self.db.execute("""SELECT i.*, f.answers, f.qset, f.model FROM items i
                               LEFT JOIN features f ON f.item_id=i.id WHERE i.id=?""", (item_id,)).fetchone()
        return self._row(r) if r else None

    def mark_sent(self, item_id: int, kind: str, message_id: int | None, score: float | None, now: datetime):
        self.db.execute("UPDATE items SET status='sent' WHERE id=?", (item_id,))
        self.db.execute("INSERT INTO deliveries(item_id, kind, message_id, score, sent_at) VALUES(?,?,?,?,?)",
                        (item_id, kind, message_id, score, iso(now)))
        self.db.commit()

    def set_feedback(self, item_id: int, label: int, now: datetime) -> bool:
        if not self.db.execute("SELECT 1 FROM items WHERE id=?", (item_id,)).fetchone():
            return False
        self.db.execute("""INSERT INTO feedback(item_id, label, at) VALUES(?,?,?)
                           ON CONFLICT(item_id) DO UPDATE SET label=excluded.label, at=excluded.at""",
                        (item_id, label, iso(now)))
        self.db.commit()
        return True

    def labeled(self, qset: str) -> list[tuple[dict, int]]:
        rows = self.db.execute(
            """SELECT i.*, f.answers, f.qset, f.model, fb.label FROM feedback fb
               JOIN items i ON i.id=fb.item_id JOIN features f ON f.item_id=i.id
               WHERE f.qset=? AND f.model != 'heuristic'""", (qset,)).fetchall()
        return [(self._row(r), int(r["label"])) for r in rows]

    def record_usage(self, now: datetime, calls: int, input_tokens: int):
        if calls:
            self.db.execute("INSERT INTO usage(run_at, calls, input_tokens) VALUES(?,?,?)",
                            (iso(now), calls, input_tokens))
            self.db.commit()

    def usage_since(self, since: datetime) -> tuple[int, int]:
        r = self.db.execute("SELECT coalesce(sum(calls),0) c, coalesce(sum(input_tokens),0) t FROM usage WHERE run_at>=?",
                            (iso(since),)).fetchone()
        return int(r["c"]), int(r["t"])

    def count_new_since(self, since: datetime) -> int:
        return self.db.execute("SELECT count(*) FROM items WHERE cluster_id IS NULL AND status!='seed' AND first_seen>=?",
                               (iso(since),)).fetchone()[0]

    # ── maintenance ──────────────────────────────────────────────────────────
    def prune(self, now: datetime, keep_days: int = 45):
        """Drop old unrated items to keep the committed DB small. Rated items are kept forever
        (they're the training set); cluster children of kept items are kept too."""
        cutoff = iso(now - timedelta(days=keep_days))
        self.db.execute(
            """DELETE FROM items WHERE first_seen < ? AND id NOT IN (SELECT item_id FROM feedback)
               AND coalesce(cluster_id, -1) NOT IN (SELECT item_id FROM feedback)""", (cutoff,))
        self.db.execute("DELETE FROM features WHERE item_id NOT IN (SELECT id FROM items)")
        self.db.execute("DELETE FROM deliveries WHERE sent_at < ? AND item_id NOT IN (SELECT id FROM items)", (cutoff,))
        self.db.execute("DELETE FROM source_runs WHERE run_at < ?", (iso(now - timedelta(days=14)),))
        self.db.execute("DELETE FROM usage WHERE run_at < ?", (iso(now - timedelta(days=90)),))
        self.db.commit()
        self.db.execute("VACUUM")
