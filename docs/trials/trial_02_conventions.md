# 트라이얼 #2 구현 규약(확정 · 실데이터 실행 전)

> **확정본** — 이 파일의 SHA256을 적은 레지스트리 행(구현 규약 행)이 번호 1~37을 참조로 포함한다. 그 행이 기록된 뒤 이 파일은 바뀌지 않는다
> (바꾸려면 새 파일 + 새 레지스트리 행).
> 앵커된 사전등록(`trial_02_preregistration.md` · #35)을 **구현**하는 선택만 적는다 — 사전등록 규칙을 바꾸는 것은 정정 문서의 몫이다(#36 정정 01).
> 근거는 `docs/ops_log.md` 2026-09-24~29 단계 2 검토 항목.

1. **청산 수수료 기준** = 수량 × 추정 청산가 × liquidationFee(`SizingLimits.liq_fee_on_liq_price=True`) — §1 46행 문언. 레지스트리 #2는 "명목×fee"로 기준 미지정 · 트라이얼 #1은 진입 명목(엔진 기본 · 불변). 근거: advisor 2b·2c #1 · Codex #1.
2. **P3 SL 자리표시**: `EntryIntent.sl == SlFromFill.anchor(= O_d)` · 실제 SL′ = 2 × 예상 체결가 − O_d(사이징 전 확정). 근거: Codex 2b·2c #3(수용). 공시: 반전 체결가 기준 거울상이라 R_반전 = R_원판 − 2 × 슬리피지(약 4 bps) — "체결가 기준 거울상"(§4 P3)의 뜻 그대로.
3. **고정 사이징 자본**: 체결된 진입마다 실행 지갑 → E_ref 1,000 · Δ지갑 = 청산 후 − E_ref · 거부·0체결은 리셋 없음 · 보고 원장 = net_pnl 누적 · 판정기는 `final_wallet`을 읽지 않는다. 근거: before-pass #1.
4. **레버리지 대역**: `SizingLimits(leverage_range=(10,30))` 명시 · 봇 기본 (50,100) 불변(#30 · §11-3).
5. **23:59 봉 7단계**(재생 루프 훅) + 훅 분 전략 판단 뒤 대기 진입 없음 단언. 근거: before-pass #4 · advisor 2b·2c #2.
6. **P2 대기열**: 원 교차에서 소비·대기열 · i+k 마감 판정 · conflict → position_busy → dropped(체결 ≥ 원래 날 23:59) → 가격 게이트 · 다음 날로 넘기지 않음. 근거: before-pass #5.
7. **동시 교차**: 한 봉에서 **아직 소비되지 않은** 두 방향이 함께 처음 교차할 때만 `conflict_cross`(둘 다 소비) · 한 방향이 이미 소비됐으면 다른 방향의 첫 교차는 정상 셋업(§1 35행 "방향별 첫 교차 하나만 셋업"). 근거: advisor 2d·2e #1.
8. **건너뜀 첫 실패 순서**: conflict_cross → position_busy → late_cross → sl_wrong_side → sl_dist_out_of_range(바닥/천장) → (엔진) sl_crossed_before_fill → sizing_rejected / normalization. 보고용(판정 무관).
9. **펀딩 존재 판정**: 경계 b의 확정 펀딩 = b ≤ funding_ms < b + 60,000(재생 정산과 같은 분 버킷).
10. **P4 추출**: 유효·범위 있는 날마다 `integers(1, ⌊R/tick⌋ + 1)` 1회 · 무범위·무효일은 난수 없음.
11. **Arm B 중앙값**: 정확한 Decimal(20개 · 가운데 둘의 평균) · 엄격 `<`.
12. **워밍업**: 창 시작 전 21일은 R·중앙값만 쌓고 진입·분모 없음 · O_d는 그날 첫 봉이 00:00 봉일 때만(아니면 그날은 이미 무효).
13. **플라시보는 Arm A만**(§4 "원판 = Arm A · IS").
14. **§9 ③ 정적 검사 범위**: `strategies/trial02/*.py` — `.rolling(` · `deque` · donchian/channel 이름 · 봉 창 슬라이스 위 max/min 금지.
15. **부트스트랩 스트림 표**: `SeedSequence((20260924,1)).spawn(8)[k]` · k = 0 gross_A · 1 net_A · 2 gross_B · 3 net_B · 4 A/B 일별 대비.
17. **정확한 mark 격자**(C2): 완전한 날 = 정렬 분 00:00…23:59 각각 봉 하나 · mark 4필드 유한 Decimal · 중복은 준비 단계에서 중단/합침.
18. **범위 이력은 적격성과 무관**(C1): 완전한 mark 날마다 R_d 기록 — 펀딩만 무효인 날도 다음 날 R_{d−1}을 준다 · days.py와 전략의 정의가 같음(테스트).
19. **23:59 봉 고저 미사용**(C4): 교차 판정은 23:58 봉까지 · 23:58 첫 교차 = late_cross(체결 23:59) · §7-3 분모에서 23:59 봉 제외.
20. **데이터 준비**(C14 · K1'): 원시 캡처 하나 → 순수 감사·빌드 → 매니페스트 해시(소비자가 검증) · **mark 계열과 kline 계열은 분마다 독립** — mark: 아카이브 mark 4필드 ok → 아카이브, 아니면 REST markPriceKlines(행이 있는데 비정상 → 중단 · 없음 → 결손 분) · kline: 아카이브 OHLC·거래량·trades ok → 아카이브, 아니면 REST klines(비정상 → 중단 · 없음 → kline 없음) · 재생 봉 = mark가 있는 분(kline이 없으면 kline 필드 빈 값 · trades = −1 · source = mark 출처) · **mark-only 분은 중단이 아니다**(2d·2e C12/C19의 해당 부분 대체 — 사전등록 §1 완결성은 mark 기준) · 트라이얼 #2 소비자는 봉 kline 필드를 읽지 않는다(시험).
21. **펀딩 버킷**(C18·C20): 기록이 있는 분 버킷 단위 · 1개 ok → 이벤트 · 바이트 동일 중복 → 합침 · 그 밖의 2개 이상 · 비정상 값 · 00/08/16 UTC 밖 → 중단 · 재생에는 검증된 이벤트만.
22. **position_busy 구조**: 기본 전략에서는 생기지 않는다 — 반대 띠(D < O_d = 초기 SL · 트레일은 이익 쪽으로만 조임)에 닿는 봉은 엔진 `on_bar`(체결 → 청산 → SL → TP)가 전략 판단 전에 이미 SL 청산 · `has_position`의 대기 진입도 같은 이유로 기본 경로에서 비어 있다 · P2 지연 결정에서만 가능(테스트).
23. **§7-3 결합**(2f 범위): 전략의 `first_cross`(outcome = intent)와 다음 봉 엔진 `EntrySkipped`(sl_crossed_before_fill · sizing_rejected · normalization = {below_min_qty, min_notional})를 run.py가 `on_event`로 이어 한 교차당 사유 하나 · tick·규칙 = #36 스냅샷(SHA256 4개 검증 · 대체 없음).
24. **날 경계 가드**: 새 날 첫 봉에서 포지션·대기 진입이 있으면 중단(주입 집합 오류 방지).
25. **데이터 핀 행 형식**: 레지스트리에 `strategies/trial02/data_pins.json`을 적은 행이 **정확히 하나** · 그 행에 원시·산출물 파일마다 `파일=SHA256` · 핀과 같은(푸시된) 커밋에 들어 있어야 한다(`t2_provenance.load_pins`).
26. **판정 문자열 형식**: 분류가 붙으면 `REJECT(§7-2: <검정력 부족|효과 부재|결론 보류형 REJECT>)` · 그 밖은 §7 라벨 그대로 · 표준출력 = 이 문자열 하나.
27. **매수보유 = kline 일 종가**(K2): 준비 출력 `kline_close_daily.json` — kline 계열에서 UTC 날마다 23:59 kline 종가, 없으면 그날 마지막 kline 분 종가 · IS 창 날만 · kline이 없는 날은 건너뛰고 다음 수익률이 잇는다 · mark 계열·유효일과 무관(사전등록 §3-1).
28. **판정기 수치 규칙**: 입력 Decimal → float64 한 번 · 유한하지 않은 값 → 판정 거부 · 보고서 JSON 엄격(NaN → null) · 모든 트라이얼 #2 손익 프로세스(run · p1_t2_run · evaluate_t2)는 시작 때 파이썬 기본 10진 문맥.
29. **산술 무결성(값 기준 거부 없음 · K3')**: 판정기 입력은 유한한 Decimal(아니면 거부) · float64 계산이 실제로 넘치거나 비유한 결과를 내면 판정 거부(판정 없음 · 아무것도 쓰지 않음) · 크기만으로 거부하는 한도는 없다 · 가격 필터(#36 max/min ≈ 8,135)로 가격 항은 ~8.2×10⁷ bps 이내라 넘침에는 펀딩율 ~10¹⁴⁰ 같은 비현실 값이 필요하다 · 진짜 정의되지 않는 통계(n < 2 · 분산 0 등)는 사전등록 §3-1대로(실패·비교 불가).
16. **§11-8 산출물 스키마·격리 CLI·증거**: 실행 기록 `var/backtest/t2/IS/_records/<이름>.json`(명령·모듈·인자·출력 SHA256·git HEAD·출처) ·
   준비 출력(정확한 집합) = manifest.json · bars_1m.parquet · funding.json · source_audit.json · kline_close_daily.json ·
   원시(raw/ · 정확한 집합) = archive_rows.jsonl · fill_ranges.json · rest_klines.jsonl · rest_mark.jsonl · funding.jsonl ·
   전략 실행(정확한 집합) = trades.jsonl · crosses.jsonl · days.jsonl · validity.json · meta.json · P1 조각·병합 = p1_draws.json · p1_null.jsonl
   (원판 0건이면 + p1_not_computable.json) · 곁파일 = verify_receipt.json · p1_merge_expect.json · 판정 = evaluation/{report.json, verdict.txt,
   record.json} · CLI = `python -m backtest.t2_stages --evaluator-commit H --stage {prepare|verify|A|base|p1|p1-merge|p4}` → 격리 하위 프로세스
   `backtest.prepare_t2` · `strategies.trial02.run` · `backtest.p1_t2_run` · 판정 `python -m backtest.evaluate_t2`(한 번) ·
   커밋/푸시 증거(판정기 커밋 H · 원격/참조 · 포함 확인)는 푸시 뒤 레지스트리 #38.
30. **변형 화이트리스트**(G4): A · B · P2_delay1 · P2_delay5 · P3_invert · P4_draw000..199만 · 조합 금지 · 이름 ↔ 변형 고정 표(실행·판정기 양쪽 · 시험으로 교차 대조).
31. **P1 계산 불가**(G5): 원판 A 0건이면 귀무분포를 만들지 않는다(p1_not_computable.json) · 판정은 §7 우선순위 1(트레이드 0)이 먼저 · 계산 가능 여부 ≠ (n_A > 0)이면 판정 거부.
32. **P1 시간 청산 사유**(G6): P1 실행의 청산 사유 = TIME_EXIT · 추출마다 time_exit/liquidation 개수 보고.
33. **출처 사슬**(G1·G3·G10~G13·H2·H13~H15·K4): 모든 단계 전 판정기 커밋 H 푸시·동결(지문 at H = HEAD) · 깨끗한 트리 · 핀은 커밋·푸시된 파일 + 레지스트리 핀 행 · verify 영수증은 성공한 verify 기록과 함께 · 기록 종류별 출처 · 정확한 출력 집합 · 검증된 이어 하기 · 하위 프로세스마다 지문 재확인 · 판정기는 결과 파일을 열기 전에 독립 기대 목록 전체를 대조.
34. **전략 산술 문맥**: 띠·sl_dist·중앙값 = Context(prec 34 · HALF_EVEN) · 엔진 = EXEC_CTX(#22) · 프로세스 기본 문맥 = 파이썬 기본(28 · HALF_EVEN).
35. **처분 구분**(H3): 준비 중단(SourceStop) → 판정 없음 · 정정 문서로 사용자에게 · "데이터 구할 수 없음" 폐기는 사용자 승인 레지스트리 행으로만 · 검증된 준비 입력에서 V_A 빈 경우 → 우선순위 0 폐기 · 산출물 누락·변조·불일치 → 판정 거부.
36. **B 비수축 진단**: 수축일 = B `days.jsonl`의 status = trading · C = V_B 비수축일 A 트레이드 · B 날 상태는 V_B와 일대일(판정기가 검사).
37. **판정 순수 핵심과 사전확약 함수**: `backtest/verdict_t2.py` — IS 판정(§7 IS 행)과 OOS·전진 판정 함수(§7 OOS·전진 행)를 IS 결과 전에 확정 · OOS·전진 입력 적재는 각각 사용자 승인 단계·활성화 레지스트리 행.

