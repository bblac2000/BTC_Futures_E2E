"""PAPER 재기동 포지션 복원 — 사용자 결정 2026-09-16 (a).

판단 모양은 LIVE 채택(`adopted_from_exchange`)과 같다: **출처를 대조하고, 일치할 때만 채택**, 아니면 flat + 진입 차단 + 알림.
- 출처 ① DB 열린 root 포지션(`positions` — 남은 수량은 부분 청산·수정 행 반영) + 그 이후 정산된 `funding_events`
- 출처 ② 마지막 엔진 스냅샷(`account_snapshots.raw_json.position` — 봉마다·체결/청산/펀딩마다 쓴다)
- (LIVE 배선 때 출처 ③ positionRisk가 같은 자리에 붙는다 — 이 파일은 PAPER만 판단한다)

일치 = 스냅샷이 root open 행 이후(`ts_ms ≥`)이고 방향·수량·진입가·레버리지·SL·TP·진입 시각·누적 펀딩·진입 수수료(open 행 합)가
모두 같고 다음 펀딩 시각이 있다. 트레일링 포지션(기본 꺼짐)은 SL = 마지막 `StopTrailed`의 새 SL(없으면 open 행)이고
트레일 설정·무장·이동 상태도 대조한다(`engine_events` TrailSet·TrailArmed·StopTrailed — Codex 단계 d #3·#4). 추정 청산가는 대조하지 않고 복원 때 **현재 규칙으로 다시 계산**한다(Codex L8b #2) —
계산할 수 없으면 불일치로 처리한다. 그 밖(스냅샷 없음·옛 형식·더 오래됨·값 불일치·한쪽만 포지션)은 전부 불일치:
- 엔진은 flat으로 시작 · `SafetyGate.pause(MISMATCH_PAUSE)`(safety_state에 남아 재기동이 풀지 않는다 · 해제는 사람의 /start)
- DB에 열린 행이 있으면 그 root에 `restart_unrestored` close 행(손익 없음 — 추정하지 않는다). 닫지 않으면 대사 수량 불일치가
  매 봉 다시 sticky로 걸려 /start로도 풀 수 없다.
- 양쪽 값을 모두 알림·운영 이벤트에 남긴다.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING, Any, Literal

from db import record as R
from exchange.decimal_context import ARITH_VERSION, in_exec_context
from exchange.errors import RulesError
from exchange.orders import Direction
from paper.engine import EntryRefused
from paper.types import PositionAbandoned, PositionRestored

if TYPE_CHECKING:
    from ops.runtime import BotRuntime

MISMATCH_PAUSE = "system:restart_position_mismatch"
UNRESTORED_REASON = R.RESTART_UNRESTORED
DECIMAL_FIELDS = ("qty", "entry_price", "sl", "tp", "funding_paid", "entry_commission")


@dataclass(frozen=True)
class RestoreDecision:
    action: Literal["none", "restore", "mismatch"]
    detail: str
    position: dict[str, Any] | None = None        # 복원할 엔진 상태(스냅샷)
    db: dict[str, Any] | None = None              # DB가 본 열린 포지션(불일치 close 행의 원천)
    snapshot_id: int | None = None


def _dec(x: Any) -> Decimal | None:
    if x is None:
        return None
    try:
        return Decimal(str(x))
    except (InvalidOperation, ValueError):
        return None


def _db_open_position(con: sqlite3.Connection, *, mode: str, symbol: str) -> dict[str, Any] | None:
    root = R.open_position_id(con, mode=mode, symbol=symbol)
    if root is None:
        return None
    root_ts = con.execute("SELECT ts_ms FROM positions WHERE id=?", (root,)).fetchone()[0]
    direction, entry_price, leverage, sl, tp = con.execute(
        "SELECT direction, entry_price, leverage, sl, tp FROM positions WHERE position_id=? AND event='open' "
        "ORDER BY id DESC LIMIT 1", (root,)).fetchone()
    state = R.open_position_state(con, mode=mode, symbol=symbol)
    assert state is not None
    commission = sum((Decimal(c) for (c,) in con.execute(
        "SELECT entry_commission_usdt FROM positions WHERE position_id=? AND event='open' AND entry_commission_usdt IS NOT NULL",
        (root,))), Decimal())
    #  소유 = position_id(v3) · 옛 행(NULL)만 시각 경계로(Codex 단계 d 후속 #4)
    funding = sum((Decimal(p) for (p,) in con.execute(
        "SELECT paid_usdt FROM funding_events WHERE mode=? AND symbol=? AND missed=0 AND "
        "(position_id=? OR (position_id IS NULL AND ts_ms>=?))", (mode, symbol, root, root_ts))), Decimal())
    trail, sl = _db_trail(con, mode=mode, symbol=symbol, root_id=int(root), sl=sl)
    return {"root_id": root, "opened_ms": int(root_ts), "direction": direction, "qty": str(state.remaining_qty),
            "entry_price": entry_price, "leverage": leverage, "sl": sl, "tp": tp, "funding_paid": str(funding),
            "entry_commission": str(commission), "trail": trail}


TRAIL_KINDS = ("TrailSet", "TrailArmed", "StopTrailed")


def _db_trail(con: sqlite3.Connection, *, mode: str, symbol: str, root_id: int, sl: Any) -> tuple[dict[str, Any] | None, Any]:
    """트레일링 행(`engine_events` TrailSet·TrailArmed·StopTrailed, **position_id = root**) → (트레일 상태, **유효 SL**).
    트레일링이 없는 포지션(현 봇)은 (None, open 행의 SL) — 기존 대조와 같다(Codex 단계 d #3·#4)."""
    trail: dict[str, Any] | None = None
    for kind, payload in con.execute(
            "SELECT kind, payload_json FROM engine_events WHERE mode=? AND symbol=? AND position_id=? AND kind IN (?,?,?) "
            "ORDER BY id", (mode, symbol, root_id, *TRAIL_KINDS)):
        p = json.loads(payload or "{}")
        if kind == "TrailSet":
            trail = {"arm_r": p["arm_r"], "dist": p["dist"], "r": p["r"], "armed": False, "moved": False}
        elif trail is None:
            continue                                     # 설정 행 없는 무장·이동 = 이 root의 것이 아니다
        elif kind == "TrailArmed":
            trail["armed"] = True
        else:
            trail["armed"] = trail["moved"] = True
            sl = p["new_sl"]
    return trail, sl


def _trail_diffs(snap: Any, db: dict[str, Any] | None) -> list[str]:
    if snap is None and db is None:
        return []
    if not isinstance(snap, dict) or db is None:
        return [f"trail 스냅샷 {snap} ≠ DB {db}"]
    out = [f"trail.{k} 스냅샷 {snap.get(k)} ≠ DB {db[k]}" for k in ("arm_r", "dist", "r") if _dec(snap.get(k)) != _dec(db[k])]
    out += [f"trail.{k} 스냅샷 {snap.get(k)} ≠ DB {db[k]}" for k in ("armed", "moved") if snap.get(k) is not db[k]]
    return out


@in_exec_context                        # DB 합계·대조도 엔진과 같은 EXEC_CTX(호출자 문맥 무관)
def decide_paper_restore(con: sqlite3.Connection, *, mode: str, symbol: str) -> RestoreDecision:
    db = _db_open_position(con, mode=mode, symbol=symbol)
    row = con.execute("SELECT id, ts_ms, raw_json FROM account_snapshots WHERE mode=? AND symbol=? AND source='engine' "
                      "ORDER BY id DESC LIMIT 1", (mode, symbol)).fetchone()
    snap: dict[str, Any] | None = None
    raw: Any = {}
    snap_id = snap_ts = None
    snap_note = "스냅샷 없음"
    if row is not None:
        snap_id, snap_ts = int(row[0]), int(row[1])
        try:
            raw = json.loads(row[2] or "{}")
        except ValueError:
            raw = {}
        if not isinstance(raw, dict) or "position" not in raw:
            snap_note = f"스냅샷 {snap_id}에 포지션 필드 없음(옛 형식)"
        else:
            snap = raw["position"]
            snap_note = f"스냅샷 {snap_id}(ts {snap_ts}) 포지션 {'없음' if snap is None else snap.get('direction')}"
    if db is None and snap is None:
        return RestoreDecision("none", f"DB flat · {snap_note}", snapshot_id=snap_id)
    if db is None:
        return RestoreDecision("mismatch", f"DB flat인데 {snap_note} — 스냅샷 포지션을 버린다", position=snap,
                               snapshot_id=snap_id)
    if snap is None or not isinstance(snap, dict):
        return RestoreDecision("mismatch", f"DB 열린 포지션 root {db['root_id']}인데 {snap_note}", db=db, snapshot_id=snap_id)
    diffs: list[str] = []
    if raw.get("arith") != ARITH_VERSION:
        #  산술 버전 가드(Codex 단계 d 후속 #3): 다른(또는 태그 없는 옛) 산술의 스냅샷은 지금 DB 합계와 정확 대조할 수 없다 —
        #  업그레이드는 flat일 때만(런북 §9.7)이므로 정상 경로에서는 나오지 않는다. 나오면 불일치(flat + 차단 + 알림).
        diffs.append(f"산술 버전 스냅샷 {raw.get('arith')} ≠ 현재 {ARITH_VERSION}")
    if snap_ts is None or snap_ts < db["opened_ms"]:
        diffs.append(f"스냅샷 ts {snap_ts} < 진입 {db['opened_ms']}")
    for k in ("direction", "leverage", "opened_ms"):
        if snap.get(k) != db[k]:
            diffs.append(f"{k} 스냅샷 {snap.get(k)} ≠ DB {db[k]}")
    for k in DECIMAL_FIELDS:
        a, b = _dec(snap.get(k)), _dec(db[k])
        if a != b:
            diffs.append(f"{k} 스냅샷 {snap.get(k)} ≠ DB {db[k]}")
    diffs += _trail_diffs(snap.get("trail"), db["trail"])
    if not isinstance(snap.get("next_funding_ms"), int):
        diffs.append("스냅샷 next_funding_ms 없음")
    if _dec(snap.get("liq_price_est")) is None:
        diffs.append("스냅샷 liq_price_est 해석 불가")
    if diffs:
        return RestoreDecision("mismatch", f"root {db['root_id']} · {snap_note} · " + " · ".join(diffs), position=snap,
                               db=db, snapshot_id=snap_id)
    return RestoreDecision("restore", f"root {db['root_id']} · {snap_note} · 일치", position=snap, db=db,
                           snapshot_id=snap_id)


ACK_KIND = "NoticeAcknowledged"


def _unrestored_notice(root_id: int, direction: str, qty: str, entry_price: str, ts_ms: int) -> dict[str, Any]:
    return {"kind": UNRESTORED_REASON, "id": str(root_id), "since_ms": ts_ms,
            "text": f"재기동 복원 불일치로 DB 포지션 root {root_id} {direction} {qty} @ {entry_price}를 손익 없이 닫았다 — 확인 후 /start"}


def sync_unrestored_notices(rt: BotRuntime) -> int:
    """Codex 배포 전 #1: notice의 원천은 **DB의 `restart_unrestored` close 행**이다 — 확인 이벤트(`NoticeAcknowledged`)가 없는
    close 행마다 notice를 되살린다(close 행 기록 뒤 notice 저장 전에 죽어도 사라지지 않게). 추가한 수를 돌려준다."""
    acked = set()
    for (payload,) in rt.con.execute("SELECT payload_json FROM engine_events WHERE mode=? AND kind=?", (rt.mode.value, ACK_KIND)):
        try:
            p = json.loads(payload or "{}")
        except ValueError:
            continue
        if p.get("kind") == UNRESTORED_REASON:
            acked.add(str(p.get("id")))
    have = {(n.get("kind"), str(n.get("id"))) for n in rt.gate.notices}
    added = 0
    for root, direction, qty, entry_price, ts in rt.con.execute(
            "SELECT position_id, direction, qty, entry_price, ts_ms FROM positions WHERE mode=? AND symbol=? AND event='close' "
            "AND reason=? ORDER BY id", (rt.mode.value, rt.symbol, UNRESTORED_REASON)).fetchall():
        if root is None or str(root) in acked or (UNRESTORED_REASON, str(root)) in have:
            continue
        rt.gate.notices.append(_unrestored_notice(int(root), direction, qty, entry_price, int(ts)))
        have.add((UNRESTORED_REASON, str(root)))
        added += 1
    return added


def apply_restore(rt: BotRuntime, decision: RestoreDecision, ts_ms: int) -> list[str]:
    """판단을 엔진·게이트·DB에 적용한다. 돌려준 문구는 호출자가 텔레그램이 붙은 뒤 알린다(러너 순서)."""
    if sync_unrestored_notices(rt):
        rt.save_state(ts_ms)
    if decision.action == "none":
        return []
    payload = {"action": decision.action, "snapshot_id": decision.snapshot_id, "db": decision.db,
               "snapshot_position": decision.position}
    if decision.action == "restore":
        assert decision.position is not None
        try:
            ev = rt.engine.restore_position(decision.position, ts_ms=ts_ms, detail=decision.detail)
        except (RulesError, ValueError, ArithmeticError, KeyError, TypeError, EntryRefused) as e:
            decision = RestoreDecision("mismatch", f"{decision.detail} · 복원 실패 {type(e).__name__}: {e}",
                                       position=decision.position, db=decision.db, snapshot_id=decision.snapshot_id)
            return apply_restore(rt, decision, ts_ms)
        rt.handle_events(ev, ts_ms)
        rt.record_ops("RestartRestore", decision.detail, ts_ms, payload)
        p = decision.position
        restored = next(e for e in ev if isinstance(e, PositionRestored))
        liq = restored.state["liq_price_est_recomputed"]
        return [f"♻️ 재기동: 포지션 복원 {p['direction']} {p['qty']} @ {p['entry_price']} · {p['leverage']}x · SL {p['sl']}"
                f" · DB와 마지막 엔진 스냅샷 일치({decision.detail}) · 추정 청산가 재계산 {p.get('liq_price_est')} → {liq}"]
    if decision.db is not None:
        d = decision.db
        rt.handle_events([PositionAbandoned(ts_ms, Direction(d["direction"]), Decimal(d["qty"]), Decimal(d["entry_price"]),
                                            f"재기동 복원 불일치 — {decision.detail}")], ts_ms)
    if decision.db is not None:
        d = decision.db
        rt.gate.notices.append(_unrestored_notice(int(d["root_id"]), d["direction"], d["qty"], d["entry_price"], ts_ms))
    rt.gate.pause(MISMATCH_PAUSE)
    rt.record_ops("RestartRestoreMismatch", decision.detail, ts_ms, payload)
    rt.snapshot(ts_ms, "restart_restore_mismatch")                   # 마지막 스냅샷 = flat 시작(다음 재기동이 같은 불일치를 다시 보지 않게)
    rt.save_state(ts_ms)
    db_side = "없음" if decision.db is None else f"{decision.db['direction']} {decision.db['qty']} @ {decision.db['entry_price']}"
    snap_side = "없음" if decision.position is None else \
        f"{decision.position.get('direction')} {decision.position.get('qty')} @ {decision.position.get('entry_price')}"
    return [f"🛑 재기동: 포지션 복원하지 않음 — flat으로 시작 · 신규 진입 일시정지(확인 후 /start)\n"
            f"DB: {db_side} · 스냅샷: {snap_side}\n{decision.detail}"
            + ("" if decision.db is None else f"\nDB 포지션은 '{UNRESTORED_REASON}' close 행으로 닫았다(손익 기록 없음)")]
