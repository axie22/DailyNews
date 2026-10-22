"""One-off: export recently delivered items, encrypted to scripts/review.pub, as annotations.

The repo is public, so nothing readable is printed: a random AES key encrypts the gzipped
JSON, and only the holder of the private key (not in this repo) can read it.
"""
import base64, gzip, json, os, sqlite3, subprocess, sys
from datetime import datetime, timedelta, timezone

db = sqlite3.connect(os.environ.get("DAILYNEWS_DB", "state/dailynews.db"))
db.row_factory = sqlite3.Row
since = (datetime.now(timezone.utc) - timedelta(days=int(sys.argv[1]) if len(sys.argv) > 1 else 8)).isoformat()
rows = db.execute("""
  SELECT d.kind, d.sent_at, d.score, i.id, i.title, i.url, i.source, i.lab, i.published_at,
         substr(i.content, 1, 600) AS content, i.meta, f.answers, fb.label
  FROM deliveries d JOIN items i ON i.id = d.item_id
  LEFT JOIN features f ON f.item_id = i.id LEFT JOIN feedback fb ON fb.item_id = i.id
  WHERE d.sent_at >= ? ORDER BY d.sent_at""", (since,)).fetchall()
out = []
for r in rows:
    a = json.loads(r["answers"] or "{}")
    meta = json.loads(r["meta"] or "{}")
    out.append({"kind": r["kind"], "sent": r["sent_at"], "score": round(r["score"] or 0, 2), "id": r["id"],
                "title": r["title"], "url": r["url"], "source": r["source"], "lab": r["lab"],
                "published": r["published_at"], "content": r["content"], "label": r["label"],
                "hf_upvotes": meta.get("hf_upvotes"), "also_on": [o["source"] for o in meta.get("also_on", [])],
                "jev": {"kind": a.get("kind", {}).get("label"), "topic": a.get("topic", {}).get("label"),
                        "sig": round(a.get("significance", {}).get("score", 0), 2),
                        "subst": round(a.get("substantive", {}).get("p", 0), 2)}})
stats = {"labels": dict(db.execute("SELECT label, count(*) FROM feedback GROUP BY label").fetchall()),
         "candidates_7d": db.execute("SELECT count(*) FROM items WHERE cluster_id IS NULL AND first_seen >= ?",
                                     ((datetime.now(timezone.utc) - timedelta(days=7)).isoformat(),)).fetchone()[0],
         "by_source_7d": dict(db.execute("""SELECT source, count(*) FROM items WHERE cluster_id IS NULL
                                AND first_seen >= ? GROUP BY source""",
                                ((datetime.now(timezone.utc) - timedelta(days=7)).isoformat(),)).fetchall())}
blob = gzip.compress(json.dumps({"items": out, "stats": stats}).encode())
key = os.urandom(32); iv = os.urandom(16)
enc = subprocess.run(["openssl", "enc", "-aes-256-cbc", "-K", key.hex(), "-iv", iv.hex()], input=blob,
                     capture_output=True, check=True).stdout
wrapped = subprocess.run(["openssl", "pkeyutl", "-encrypt", "-pubin", "-inkey", "scripts/review.pub",
                          "-pkeyopt", "rsa_padding_mode:oaep", "-pkeyopt", "rsa_oaep_md:sha256"],
                         input=key + iv, capture_output=True, check=True).stdout
payload = base64.b64encode(len(wrapped).to_bytes(2, "big") + wrapped + enc).decode()
chunks = [payload[i:i + 3500] for i in range(0, len(payload), 3500)]
print(f"{len(out)} items, {len(payload)} b64 chars, {len(chunks)} chunks")
for n, c in enumerate(chunks):
    print(f"::notice title=review {n + 1}/{len(chunks)}::{c}")
