"""`backtest/evaluate_t2.py` — 합성 전체 파이프라인(실제 `Stages` + 실제 출력 형식을 쓰는 가짜 러너) 위에서 판정·거부.

세계: 날 D0−22 … D0+39 평평한 봉 + 00/08/16 펀딩 → V_A = D0…D0+39(40일) · V_B = 같음. 트레이드는 변형마다 시나리오로 준다.
"""
from __future__ import annotations

import ast
import hashlib
import json
from decimal import Decimal
from pathlib import Path

import pytest

from backtest import days as DY
from backtest import evaluate_t2 as E
from backtest import p1_t2_run as R
from backtest import t2_provenance as PV
from backtest import t2_stages as T
from backtest.data import Bar1m, Funding
from backtest.replay import RunRecord
from strategies.trial02 import anchor as A

ROOT = Path(__file__).resolve().parent.parent
DAY, MIN, H = 86_400_000, 60_000, 3_600_000
D0 = 19_723
FIRST, LAST = D0, D0 + 39
PINS = {"raw": {"archive_rows.jsonl": "r"}, "prepared": {"bars_1m.parquet": "b", "funding.json": "f", "source_audit.json": "s"}}


def world_bars() -> tuple[list[Bar1m], list[Funding]]:
    bars, fs = [], []
    for d in range(D0 - 22, LAST + 1):
        p = str(60000 + (d - D0) * 10)
        bars += [Bar1m(d * DAY + m * MIN, p, p, p, p, "1", "1", 1, "0", "0", p, p, p, p, "archive") for m in range(1440)]
        fs += [Funding(d * DAY + h * H, "0.0001", p) for h in (0, 8, 16)]
    return bars, fs


BARS, FUNDS = world_bars()
VALIDITY = DY.validity(BARS, FUNDS, FIRST, LAST)


def trades(means: list[float], per_day: int = 2, liq: int = 0) -> list[dict]:
    out = []
    for i, m in enumerate(means):
        d = FIRST + (i // per_day) % 40
        e = d * DAY + (60 + 300 * (i % per_day)) * MIN
        out.append({"trade_id": i, "entry_ms": e, "exit_ms": e + 120 * MIN, "direction": "LONG" if i % 2 else "SHORT",
                    "net_bps": str(m), "gross_bps": str(m + 14), "sl_dist": "0.01",
                    "exit_reason": "liquidation" if i < liq else "time_exit", "wallet_before": "1000", "final_wallet": "x"})
    return out


def alt(n: int, center: float, spread: float = 30.0) -> list[float]:
    return [center + (spread if i % 2 else -spread) + (i % 7) for i in range(n)]


def good_scenario() -> dict:
    s = {"A": alt(80, 40.0), "B": alt(80, 40.0), "P2_delay1": alt(60, 5.0), "P2_delay5": alt(60, -5.0),
         "P3_invert": alt(80, -60.0)}
    s |= {f"P4_draw{d:03d}": alt(20, -10.0 + (d % 10)) for d in range(200)}
    s["p1_null"] = [-10.0 + (d % 20) for d in range(1000)]
    return s


class World:
    def __init__(self, base: Path, scen: dict, liq_a: int = 0, p1_fail: int = 0, validity: DY.Validity | None = None,
                 extra_prep: bool = False, contraction: set[int] | None = None, force_nc: bool = False):
        self.base, self.scen, self.liq_a, self.p1_fail = base, scen, liq_a, p1_fail
        self.validity = validity or VALIDITY
        self.extra_prep, self.contraction, self.force_nc = extra_prep, contraction, force_nc
        self.meta_override: dict = {}

    def __call__(self, module, args, out, timeout_s=0, env=None):
        out.mkdir(parents=True, exist_ok=True)
        prov = {"evaluator_commit": "EV", "pins_commit": "PC", "fingerprint": "FP"}
        if module == T.PREP_MODULE:
            for f in T.PREP_OUTPUTS + (("extra.txt",) if self.extra_prep else ()):
                if not (out / f).exists():
                    (out / f).write_text(f"{f}\n")
        elif module == T.STRATEGY:
            name = args[1]
            ts = trades(self.scen[name], liq=self.liq_a if name == "A" else 0)
            if name == "B":
                keep = self.contraction if self.contraction is not None else self.validity.v_b
                ts = [t for t in ts if int(t["entry_ms"]) // DAY in keep]
            _w(out / "trades.jsonl", ts)
            _w(out / "crosses.jsonl", [{"final_reason": None, "direction": t["direction"]} for t in ts])
            dd = [] if name != "B" else [{"event": "day", "day": d, "status": "trading" if self.contraction is None
                                          or d in self.contraction else "not_contraction"} for d in sorted(self.validity.v_b)]
            _w(out / "days.jsonl", dd)
            (out / "validity.json").write_text(json.dumps(self.validity.as_dict(), sort_keys=True) + "\n")
            manifest = hashlib.sha256((self.base / "prepared" / "manifest.json").read_bytes()).hexdigest()
            meta = {"variant_name": name, "variant": E.VARIANTS[name], "pins": PINS, "pins_commit": "PC",
                    "manifest_sha256": manifest, "bo_v1_sha256": A.BO_V1_SHA256, "rules_snapshot_sha256": A.RULES_SNAPSHOT_SHA256,
                    "git_head": "HEAD", "gate": prov | {"manifest_sha256": manifest}, "n_trades": len(ts), "n_first_cross": len(ts)}
            meta |= self.meta_override.get(name, {})
            (out / "meta.json").write_text(json.dumps(meta, sort_keys=True) + "\n")
        elif args[0] == "--merge":
            R.merge(Path(args[2]), json.loads(Path(args[4]).read_text()), out)
        else:
            lo, hi = (int(x) for x in args[args.index("--draws") + 1].split("-"))
            if not self.scen["A"] or self.force_nc:
                (out / E.NOT_COMPUTABLE).write_text('{"computable": false, "reason": "n_A=0"}\n')
                (out / "p1_draws.json").write_text("[]")
                _w(out / "p1_null.jsonl", [])
            else:
                ds = [{"draw": d, "ok": d >= self.p1_fail, "failed_slot": None if d >= self.p1_fail else 0, "placed": []}
                      for d in range(lo, hi + 1)]
                (out / "p1_draws.json").write_text(json.dumps(ds, sort_keys=True, separators=(",", ":")))
                _w(out / "p1_null.jsonl", [{"draw": d["draw"], "n": 3, "mean_net_bps": str(self.scen["p1_null"][d["draw"]]),
                                            "exits": {"time_exit": 3, "liquidation": 0}} for d in ds if d["ok"]])
        outs = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(out.iterdir()) if p.is_file()}
        return RunRecord(module, list(args), 0, "ok", "", "t0", "t1", "HEAD", "3.12", "2", outs)


def _w(p: Path, rows: list[dict]) -> None:
    p.write_text("".join(json.dumps(r, sort_keys=True, separators=(",", ":")) + "\n" for r in rows))


@pytest.fixture
def patched(monkeypatch):
    monkeypatch.setattr(PV, "require_evaluator_frozen", lambda repo, h, fetch=True: None)
    monkeypatch.setattr(PV, "fingerprint", lambda repo: "FP")
    monkeypatch.setattr(PV, "load_pins", lambda repo, fetch=True: (PINS, "PC"))
    monkeypatch.setattr(PV, "head", lambda repo: "HEAD")


def build(tmp_path, scen=None, **kw) -> World:
    w = World(tmp_path, scen or good_scenario(), **kw)
    st = T.Stages("EV", base=tmp_path, repo=tmp_path, runner=w, fetch=False)
    st.prep.mkdir(parents=True)
    (st.prep / "manifest.json").write_text(json.dumps({"raw": PINS["raw"], **PINS["prepared"]}))
    st.prepare()
    st.verify()
    st.arm(["A"], 1)
    st.arm(list(T.BASE_NAMES), 1)
    st.arm(T.p4_names(), 1)
    st.p1(4, 1)
    st.p1_merge()
    return w


def run_eval(tmp_path, bars=None, days=(FIRST, LAST)):
    b = bars if bars is not None else BARS
    return E.evaluate(tmp_path, tmp_path, fetch=False, load_prepared=lambda o, p, r: (b, FUNDS),
                      rebuild=lambda o, r: None, window=(0, 1), days=days)


def test_is_pass_and_single_call(tmp_path, patched):
    build(tmp_path)
    verdict, report, record = run_eval(tmp_path)
    assert verdict == "IS PASS", report["gates"]
    assert (tmp_path / "evaluation" / "verdict.txt").read_text() == "IS PASS\n"
    assert record["report_sha256"] == hashlib.sha256((tmp_path / "evaluation" / "report.json").read_bytes()).hexdigest()
    assert report["P4"]["defined"] == 200 and report["P1"]["failed_draws"] == 0
    with pytest.raises(E.Refusal):
        run_eval(tmp_path)                                                   # 한 번만


def test_placebo_rejection_p3(tmp_path, patched):
    s = good_scenario()
    s["P3_invert"] = alt(80, 60.0)
    build(tmp_path, s)
    verdict, report, _ = run_eval(tmp_path)
    assert verdict.startswith("REJECT") and report["priority"] == 5 and report["placebo_rejects"]["P3"]


def test_zero_trades_a(tmp_path, patched):
    s = good_scenario()
    s["A"], s["B"] = [], []
    build(tmp_path, s)
    verdict, report, _ = run_eval(tmp_path)
    assert verdict == "REJECT(FAIL — 트레이드 0)" and report["P1"]["computable"] is False


def test_survival(tmp_path, patched):
    build(tmp_path, liq_a=1)
    assert run_eval(tmp_path)[0] == "REJECT(생존)"


def test_p1_harness_defect(tmp_path, patched):
    build(tmp_path, p1_fail=11)
    v, report, _ = run_eval(tmp_path)
    assert v == "폐기" and report["priority"] == 4


def test_p4_zero_trade_draws_counted_and_discard(tmp_path, patched):
    s = good_scenario()
    for d in range(11):
        s[f"P4_draw{d:03d}"] = []
    build(tmp_path, s)
    v, report, _ = run_eval(tmp_path)
    assert v == "폐기" and report["P4"]["defined"] == 189


def test_refuses_extra_record(tmp_path, patched):
    build(tmp_path)
    (tmp_path / "_records" / "stray.json").write_text("{}")
    with pytest.raises(E.Refusal):
        run_eval(tmp_path)
    assert not (tmp_path / "evaluation").exists()


def test_refuses_missing_run(tmp_path, patched):
    build(tmp_path)
    (tmp_path / "_records" / "P4_draw150.json").unlink()
    with pytest.raises(E.Refusal):
        run_eval(tmp_path)


def test_refuses_wrong_meta_variant(tmp_path, patched):
    w = World(tmp_path, good_scenario())
    w.meta_override = {"P2_delay5": {"variant": E.VARIANTS["P2_delay1"]}}
    st = T.Stages("EV", base=tmp_path, repo=tmp_path, runner=w, fetch=False)
    st.prep.mkdir(parents=True)
    (st.prep / "manifest.json").write_text(json.dumps({"raw": PINS["raw"], **PINS["prepared"]}))
    for step in (st.prepare, st.verify, lambda: st.arm(["A"], 1), lambda: st.arm(list(T.BASE_NAMES), 1),
                 lambda: st.arm(T.p4_names(), 1), lambda: st.p1(2, 1), st.p1_merge):
        step()
    with pytest.raises(E.Refusal):
        run_eval(tmp_path)


def test_refuses_dirty_git_head(tmp_path, patched):
    build(tmp_path)
    f = tmp_path / "_records" / "B.json"
    rec = json.loads(f.read_text())
    rec["run"]["git_head"] = "HEAD+dirty"
    f.write_text(json.dumps(rec))
    with pytest.raises(E.Refusal):
        run_eval(tmp_path)


def test_refuses_merge_content_mismatch(tmp_path, patched):
    build(tmp_path)
    m = tmp_path / "runs" / "P1_merged" / "p1_null.jsonl"
    rows = m.read_text().splitlines()
    rows[0] = rows[0].replace('"mean_net_bps":"', '"mean_net_bps":"9')
    m.write_text("\n".join(rows) + "\n")
    rec_f = tmp_path / "_records" / "P1_merge.json"
    rec = json.loads(rec_f.read_text())
    rec["run"]["outputs"]["p1_null.jsonl"] = hashlib.sha256(m.read_bytes()).hexdigest()   # 기록까지 고쳐도
    rec_f.write_text(json.dumps(rec))
    with pytest.raises(E.Refusal):
        run_eval(tmp_path)


def test_refuses_trade_outside_valid_days(tmp_path, patched):
    s = good_scenario()
    build(tmp_path, s)
    d = tmp_path / "runs" / "P2_delay1"
    rows = [json.loads(x) for x in (d / "trades.jsonl").read_text().splitlines()]
    rows[0]["entry_ms"] = (FIRST - 5) * DAY + MIN
    _w(d / "trades.jsonl", rows)
    rec_f = tmp_path / "_records" / "P2_delay1.json"
    rec = json.loads(rec_f.read_text())
    rec["run"]["outputs"]["trades.jsonl"] = hashlib.sha256((d / "trades.jsonl").read_bytes()).hexdigest()
    rec_f.write_text(json.dumps(rec))
    with pytest.raises(E.Refusal):
        run_eval(tmp_path)


def test_bh_series_bridges_missing_days_and_uses_last_bar():
    p = lambda d, m, c: Bar1m(d * DAY + m * MIN, c, c, c, c, "1", "1", 1, "0", "0", c, c, c, c, "archive")  # noqa: E731
    bars = [p(1, 1439, "100"), p(1, 100, "90"), p(2, 500, "110"), p(4, 1439, "121")]        # 3일 없음 · 2일은 23:59 없음
    bh = E.bh_series(bars, 1, 4)
    assert bh["days"] == 3 and bh["window_return"] == pytest.approx(0.21)
    from backtest.stats_t2 import sharpe_or_none
    assert bh["daily_sharpe"] == sharpe_or_none([0.1, 0.1])


def test_evaluator_imports_no_strategy_and_never_reads_final_wallet():
    src = (ROOT / "backtest" / "evaluate_t2.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    mods = [n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
    assert not any(m and m.startswith("strategies") and m != "strategies.trial02" for m in mods)
    names = [a.name for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module == "strategies.trial02" for a in n.names]
    assert names == ["anchor"]
    body = src.split('"""', 2)[2]
    assert "final_wallet" not in body


def test_decimal_values_are_converted_once():
    assert E._f("12.5") == 12.5 and isinstance(E._f(Decimal("1")), float)


def test_refuses_consistently_dirty_head(tmp_path, patched):
    build(tmp_path)
    f = tmp_path / "_records" / "B.json"
    rec = json.loads(f.read_text())
    rec["run"]["git_head"] = rec["provenance"]["head"] = "HEAD+dirty"
    mf = tmp_path / "runs" / "B" / "meta.json"
    meta = json.loads(mf.read_text())
    meta["git_head"] = "HEAD+dirty"                                           # 메타까지 일관되게 — 더러운 트리 검사만 남긴다
    mf.write_text(json.dumps(meta, sort_keys=True) + "\n")
    rec["run"]["outputs"]["meta.json"] = hashlib.sha256(mf.read_bytes()).hexdigest()
    f.write_text(json.dumps(rec))
    with pytest.raises(E.Refusal, match="더러운"):
        run_eval(tmp_path)


def test_nonfinite_value_is_refused_not_passed(tmp_path, patched):
    s = good_scenario()
    s["P4_draw007"] = [float("nan")] * 3
    build(tmp_path, s)
    with pytest.raises(E.Refusal, match="유한"):
        run_eval(tmp_path)
    assert not (tmp_path / "evaluation").exists()


def test_extra_prepare_output_is_refused(tmp_path, patched):
    build(tmp_path, extra_prep=True)
    with pytest.raises(E.Refusal):
        run_eval(tmp_path)


def test_noncontraction_diagnostic_uses_b_day_status(tmp_path, patched):
    contraction = set(range(FIRST, FIRST + 10))
    build(tmp_path, contraction=contraction)
    _, report, _ = run_eval(tmp_path)
    d = report["B_vs_noncontraction_A"]
    a_on_vb = [t for t in trades(good_scenario()["A"]) if int(t["entry_ms"]) // DAY in VALIDITY.v_b]
    assert d["contraction_days"] == 10 and d["n_B"] + d["n_C"] == len(a_on_vb) and d["n_B"] == 20
    assert report["skips_A"]["invalid_days_A"] == 0 and report["trades_A"]["trades_per_valid_day"] == 2.0


def test_priority3_verdict_string_format(tmp_path, patched):
    s = good_scenario()
    s["A"] = alt(80, -40.0)
    build(tmp_path, s)
    verdict, report, _ = run_eval(tmp_path)
    assert report["priority"] == 3 and verdict == f"REJECT(§7-2: {report['classification']})"
    assert (tmp_path / "evaluation" / "verdict.txt").read_text() == verdict + "\n"
    json.loads((tmp_path / "evaluation" / "report.json").read_text())                  # 엄격 JSON(NaN 없음)
    assert "NaN" not in (tmp_path / "evaluation" / "report.json").read_text()


def test_bh_uncomparable_label(tmp_path, patched):
    build(tmp_path)
    flat = [Bar1m(b.open_ms, "60000", "60000", "60000", "60000", "1", "1", 1, "0", "0", b.mark_open, b.mark_high, b.mark_low,
                  b.mark_close, "archive") for b in BARS]
    _, report, _ = run_eval(tmp_path, bars=flat)
    assert report["buy_and_hold"]["is_label"] == "비교 불가"


@pytest.mark.parametrize("override", [{"n_trades": 1}, {"pins": {"raw": {}, "prepared": {}}}, {"pins_commit": "OTHER"},
                                      {"bo_v1_sha256": "0" * 64}])
def test_meta_mismatch_refused(tmp_path, patched, override):
    w = World(tmp_path, good_scenario())
    w.meta_override = {"P3_invert": override}
    st = T.Stages("EV", base=tmp_path, repo=tmp_path, runner=w, fetch=False)
    st.prep.mkdir(parents=True)
    (st.prep / "manifest.json").write_text(json.dumps({"raw": PINS["raw"], **PINS["prepared"]}))
    for step in (st.prepare, st.verify, lambda: st.arm(["A"], 1), lambda: st.arm(list(T.BASE_NAMES), 1),
                 lambda: st.arm(T.p4_names(), 1), lambda: st.p1(2, 1), st.p1_merge):
        step()
    with pytest.raises(E.Refusal):
        run_eval(tmp_path)


def test_p1_not_computable_with_trades_is_refused(tmp_path, patched):
    build(tmp_path, force_nc=True)
    with pytest.raises(E.Refusal):
        run_eval(tmp_path)


def test_empty_v_a_is_priority0(tmp_path, patched):
    empty_days = (LAST + 100, LAST + 110)
    v = DY.validity(BARS, FUNDS, *empty_days)
    s = good_scenario()
    s["A"], s["B"], s["P2_delay1"], s["P2_delay5"], s["P3_invert"] = [], [], [], [], []
    for d in range(200):
        s[f"P4_draw{d:03d}"] = []
    build(tmp_path, s, validity=v)
    verdict, report, _ = run_eval(tmp_path, days=empty_days)
    assert verdict == "폐기" and report["priority"] == 0


def test_evaluator_variant_table_matches_run_table():
    from strategies.trial02.run import variant_for, variant_meta
    for n in E.STRATEGY_RUNS:
        assert E.VARIANTS[n] == variant_meta(variant_for(n)), n


def test_overflowing_value_is_refused(tmp_path, patched):
    s = good_scenario()
    build(tmp_path, s)
    d = tmp_path / "runs" / "P4_draw011"
    rows = [json.loads(x) for x in (d / "trades.jsonl").read_text().splitlines()]
    rows[0]["net_bps"] = "1e400"
    _w(d / "trades.jsonl", rows)
    rec_f = tmp_path / "_records" / "P4_draw011.json"
    rec = json.loads(rec_f.read_text())
    rec["run"]["outputs"]["trades.jsonl"] = hashlib.sha256((d / "trades.jsonl").read_bytes()).hexdigest()
    rec_f.write_text(json.dumps(rec))
    with pytest.raises(E.Refusal, match="범위"):
        run_eval(tmp_path)


def _rewrite(tmp_path, name, fname, rows):
    d = tmp_path / "runs" / name
    _w(d / fname, rows)
    rec_f = tmp_path / "_records" / f"{name}.json"
    rec = json.loads(rec_f.read_text())
    rec["run"]["outputs"][fname] = hashlib.sha256((d / fname).read_bytes()).hexdigest()
    rec_f.write_text(json.dumps(rec))


def test_b_day_status_file_must_cover_v_b(tmp_path, patched):
    build(tmp_path, contraction=set(range(FIRST, FIRST + 10)))
    rows = [json.loads(x) for x in (tmp_path / "runs" / "B" / "days.jsonl").read_text().splitlines()][1:]   # 한 날 빠짐
    _rewrite(tmp_path, "B", "days.jsonl", rows)
    with pytest.raises(E.Refusal):
        run_eval(tmp_path)


def test_b_trade_on_non_trading_day_refused(tmp_path, patched):
    build(tmp_path, contraction=set(range(FIRST, FIRST + 10)))
    rows = [json.loads(x) for x in (tmp_path / "runs" / "B" / "days.jsonl").read_text().splitlines()]
    for r in rows:
        if r["day"] == FIRST:
            r["status"] = "not_contraction"                       # B 트레이드가 있는 날을 쉬는 날로
    _rewrite(tmp_path, "B", "days.jsonl", rows)
    with pytest.raises(E.Refusal):
        run_eval(tmp_path)


def test_malformed_receipt_is_a_refusal(tmp_path, patched):
    build(tmp_path)
    (tmp_path / "_records" / "verify_receipt.json").write_text("{not json")
    with pytest.raises(E.Refusal):
        run_eval(tmp_path)


def test_overflowing_mean_of_finite_values_is_refused(tmp_path, patched):
    build(tmp_path)
    d = tmp_path / "runs" / "P4_draw033"
    rows = [json.loads(x) for x in (d / "trades.jsonl").read_text().splitlines()]
    for r in rows[:3]:
        r["net_bps"] = "1e308"                                    # 각각 유한 · 평균은 inf
    _rewrite(tmp_path, "P4_draw033", "trades.jsonl", rows)
    with pytest.raises(E.Refusal):
        run_eval(tmp_path)


def test_sanity_bound_refuses_absurd_bps(tmp_path, patched):
    build(tmp_path)
    rows = [json.loads(x) for x in (tmp_path / "runs" / "B" / "trades.jsonl").read_text().splitlines()]
    rows[0]["net_bps"], rows[1]["net_bps"] = "1e200", "2e200"                   # 유한하지만 넘침 유발
    _rewrite(tmp_path, "B", "trades.jsonl", rows)
    with pytest.raises(E.Refusal, match="건전성"):
        run_eval(tmp_path)
