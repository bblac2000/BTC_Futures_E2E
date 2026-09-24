# 트라이얼 #2 정정 문서 01 — 런타임 규칙 스냅샷의 출처(레지스트리 #36)

> 앵커된 사전등록(`trial_02_preregistration.md` · SHA256 `d353f586…` · createdTime 2026-09-24T10:22:54.426Z)은 **바꾸지 않는다**.
> 이 문서는 §1 사이징 행 · §11-6의 "규칙 = 앵커 시점 캡처 런타임 스냅샷"을 구현 가능한 하나의 출처로 고정한다. 실데이터 손익 계산 전.

## 문제
- 앵커 시점에 캡처된 스냅샷이 없었다(Codex 단계 2 before-pass #7). 가진 것은 2026-09-02 fixture(앵커 전 22일)뿐.
- 지금 캡처도 앵커 **뒤**라 문언("앵커 시점")과 정확히 같지 않다 — 어느 쪽이든 정정이 필요하다.

## 결정(사용자 2026-09-24 · (a))
- **출처 = 2026-09-24 UTC 앵커 뒤 같은 날 캡처 하나** · **대체 경로 없음**(fixture로 되돌아가지 않는다).
- 캡처: `scripts/capture_trial02_rules.py` · read-only 키(권한 실측 — 읽기 외 권한 꺼짐) · GET만 · 2026-09-24T11:01:04Z.
- 파일(`docs/trials/trial_02_rules_snapshot/` · `_meta` 포함 파일 전체의 SHA256):

| 파일 | 엔드포인트 | captured_at_utc | SHA256 |
|---|---|---|---|
| exchangeInfo.json | GET /fapi/v1/exchangeInfo | 2026-09-24T11:01:04.595Z | `e549134cdf804ad3b8554656a4ac9fa61c1ce66cb9f28a1e3e39883f997bf5c5` |
| leverageBracket.json | GET /fapi/v1/leverageBracket?symbol=BTCUSDT (서명) | 2026-09-24T11:01:04.714Z | `65aa79460e4347c4ad71420018e8671389b409072da119249bb7e7d096067636` |
| commissionRate.json | GET /fapi/v1/commissionRate?symbol=BTCUSDT (서명) | 2026-09-24T11:01:04.759Z | `b8a89d16882d74d7520b305114d56cb58aea7a50cd09e1137b3f2068d1b3cdad` |
| fundingInfo.json | GET /fapi/v1/fundingInfo (공개) | 2026-09-24T11:01:04.813Z | `9db101c8ed362f5803aa170330da0dd037ac93b091fcd7fcb773daccc1149187` |

- fundingInfo는 사용자가 적은 세 파일 밖이다: 규칙 파서(`exchange/loader.build_rules`)의 필수 입력이라 **다른 출처와 섞지 않으려고 같은 캡처에서** 받았다(백테스트 펀딩은 §2대로 REST 확정 펀딩율 — fundingInfo 값은 판정에 쓰이지 않는다).
- **taker = 0.0005(5 bps) 단언 통과** — 사전등록 §2와 같다(§2 정정 불필요) · maker 0.0002.
- 참고(보고): 파싱된 BTCUSDT 심볼 필터·레버리지 브라켓·수수료는 2026-09-02 fixture와 **값이 같다**.
