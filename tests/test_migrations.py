import os
import sqlite3
import subprocess
import sys


def test_sqlite_upgrade_from_0008_removes_legacy_and_adds_semantic_cache(tmp_path):
    database = tmp_path / "migration.db"
    env = {**os.environ, "DATABASE_URL": f"sqlite+aiosqlite:///{database}"}
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "0008_hybrid_recommendations"],
        check=True,
        env=env,
        capture_output=True,
        text=True,
    )
    with sqlite3.connect(database) as connection:
        before = {row[1] for row in connection.execute("PRAGMA table_info(opportunities)")}
    assert "prefilter_score" in before
    assert "final_score" in before

    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        check=True,
        env=env,
        capture_output=True,
        text=True,
    )
    with sqlite3.connect(database) as connection:
        after = {row[1] for row in connection.execute("PRAGMA table_info(opportunities)")}
        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }

    assert "prefilter_score" not in after
    assert "final_score" not in after
    assert "semantic_representations" in tables
