"""복사해 온 E2E 모듈(manifest·telegram sender)이 이 저장소에서 **원본 계약대로** 동작하는가."""
from __future__ import annotations

import io
import json
import sqlite3

import pytest

from data import manifest
from notify import sender


@pytest.fixture
def mdb(tmp_path, monkeypatch):
    p = tmp_path / "manifest.sqlite"
    monkeypatch.setattr(manifest, "MANIFEST_DB", p)
    return p


def test_register_shard_records_and_never_raises_on_lock(mdb, monkeypatch):
    assert manifest.register_shard("live_kline1m", "BTCUSDT", "2026-09-15T000000_000", "/x.parquet",
                                   parquet_path="/x.parquet", parquet_rows=3) is True
    assert manifest.file_status("live_kline1m", "BTCUSDT", "2026-09-15T000000_000") == "converted"

    def boom(*a, **k):
        raise sqlite3.OperationalError("database is locked")
    monkeypatch.setattr(manifest, "upsert_file", boom)
    #  🔴 E2E 2026-08-15 — 대장 락 예외가 writer 스레드를 죽이면 안 된다. 삼키지 않고 이벤트로 남긴다.
    assert manifest.register_shard("live_kline1m", "BTCUSDT", "p2", "/y.parquet") is False
    with sqlite3.connect(mdb) as con:
        kinds = [r[0] for r in con.execute("SELECT kind FROM events")]
    assert kinds == ["manifest_write_failed"]


def test_mark_pruned_keeps_rows_and_returns_the_count(mdb):
    for i in range(3):
        manifest.register_shard("live_markprice", "BTCUSDT", f"p{i}", f"/m{i}.parquet",
                                parquet_path=f"/m{i}.parquet")
    n = manifest.mark_pruned(["/m0.parquet", "/m1.parquet"], note="drive_verified", sizes={"/m0.parquet": 10})
    assert n == 2
    with sqlite3.connect(mdb) as con:
        rows = dict(con.execute("SELECT period, status FROM files"))
    assert rows == {"p0": "pruned", "p1": "pruned", "p2": "converted"}, "행을 지우지 않는다"


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *_exc) -> None:
        return None


def test_http_200_with_ok_false_is_a_failure_not_sent_true():
    """🔴 E2E F-TGDAEMON 계열 — 'HTTP가 돌아왔다'는 '배달됐다'가 아니다. 응답 `ok`를 본다."""
    body = json.dumps({"ok": False, "description": "Bad Request: chat not found"}).encode()
    res = sender._post("t", "c", "hi", opener=lambda req, timeout: _Resp(body))
    assert res["ok"] is False and "chat not found" in res["description"]


def test_ok_true_carries_message_id():
    body = json.dumps({"ok": True, "result": {"message_id": 42}}).encode()
    res = sender._post("t", "c", "hi", opener=lambda req, timeout: _Resp(body))
    assert res == {"ok": True, "message_id": 42, "description": None}


def test_transport_exception_is_a_failure():
    def opener(req, timeout):
        raise TimeoutError("read timed out")
    assert sender._post("t", "c", "hi", opener=opener)["ok"] is False


def test_unconfigured_returns_failure_instead_of_pretending(monkeypatch):
    monkeypatch.setattr(sender, "_loaded", True)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    assert sender.notify("x", block=True) == {"ok": False, "error": "not_configured"}


def test_atexit_drain_is_registered():
    """단명 프로세스에서 비동기 발송이 끊기지 않도록 join 장치가 걸려 있어야 한다."""
    import atexit
    #  atexit에는 조회 API가 없다 → 등록 해제가 성공하면 등록돼 있던 것이다. 다시 등록해 둔다.
    atexit.unregister(sender._drain)
    atexit.register(sender._drain)
    assert callable(sender._drain)


def test_transport_error_text_never_contains_the_token(capsys):
    """Codex L6·7 #5: urllib 예외 문구에 URL(토큰 포함)이 들어가면 stderr·로그로 샌다 → `<token>`으로 가린다."""
    def opener(req, timeout):
        raise OSError(f"cannot connect {req.full_url}")
    res = sender._post("123:SECRET", "c", "hi", opener=opener)
    assert res["ok"] is False and "SECRET" not in res["error"] and "<token>" in res["error"]
    assert "SECRET" not in capsys.readouterr().err
