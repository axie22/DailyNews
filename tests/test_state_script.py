"""Exercise scripts/state.sh against a real local git remote."""
import os
import shutil
import sqlite3
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "state.sh"
pytestmark = pytest.mark.skipif(not (shutil.which("git") and shutil.which("openssl")), reason="needs git+openssl")


def sh(cwd, *args, env=None, check=True):
    return subprocess.run(args, cwd=cwd, env={**os.environ, **(env or {})}, capture_output=True, text=True, check=check)


@pytest.fixture
def repo(tmp_path):
    remote = tmp_path / "remote.git"
    sh(tmp_path, "git", "init", "-q", "--bare", str(remote))
    work = tmp_path / "work"
    sh(tmp_path, "git", "init", "-q", str(work))
    sh(work, "git", "remote", "add", "origin", str(remote))
    return work, remote


def write_db(path: Path, value: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE IF NOT EXISTS kv(k TEXT PRIMARY KEY, v TEXT)")
    con.execute("INSERT OR REPLACE INTO kv VALUES('x', ?)", (value,))
    con.commit()
    con.close()


def read_db(path: Path) -> str:
    return sqlite3.connect(path).execute("SELECT v FROM kv WHERE k='x'").fetchone()[0]


def test_encrypted_roundtrip_and_no_history(repo, tmp_path):
    work, remote = repo
    env = {"STATE_KEY": "s3cret", "DAILYNEWS_DB": "state/dailynews.db"}
    assert "starting fresh" in sh(work, "bash", str(SCRIPT), "pull", env=env).stdout
    write_db(work / "state/dailynews.db", "v1")
    sh(work, "bash", str(SCRIPT), "push", env=env)
    sh(work, "bash", str(SCRIPT), "pull", env=env)
    write_db(work / "state/dailynews.db", "v2")
    sh(work, "bash", str(SCRIPT), "push", env=env)

    files = sh(remote, "git", "ls-tree", "--name-only", "data").stdout.split()
    assert files == ["dailynews.db.enc"]                          # never stored in plaintext
    assert sh(remote, "git", "rev-list", "--count", "data").stdout.strip() == "1"  # orphan, no bloat

    fresh = tmp_path / "fresh"
    sh(tmp_path, "git", "init", "-q", str(fresh))
    sh(fresh, "git", "remote", "add", "origin", str(remote))
    sh(fresh, "bash", str(SCRIPT), "pull", env=env)
    assert read_db(fresh / "state/dailynews.db") == "v2"


def test_wrong_key_fails_and_push_is_refused(repo, tmp_path):
    work, remote = repo
    env = {"STATE_KEY": "right", "DAILYNEWS_DB": "state/dailynews.db"}
    sh(work, "bash", str(SCRIPT), "pull", env=env)
    write_db(work / "state/dailynews.db", "precious")
    sh(work, "bash", str(SCRIPT), "push", env=env)

    other = tmp_path / "other"
    sh(tmp_path, "git", "init", "-q", str(other))
    sh(other, "git", "remote", "add", "origin", str(remote))
    bad = {"STATE_KEY": "wrong", "DAILYNEWS_DB": "state/dailynews.db"}
    assert sh(other, "bash", str(SCRIPT), "pull", env=bad, check=False).returncode != 0
    # The run step would then create a fresh empty DB; the always() push must NOT clobber state.
    write_db(other / "state/dailynews.db", "empty")
    r = sh(other, "bash", str(SCRIPT), "push", env=bad, check=False)
    assert r.returncode != 0 and "refusing" in r.stderr

    sh(work, "bash", str(SCRIPT), "pull", env=env)
    assert read_db(work / "state/dailynews.db") == "precious"
