# data/routes/ — 라우트별 추출 CSV 캐시

로그 업로드마다 `extract_log.py`를 다시 돌리는 대신, 이미 추출한 라우트를
gzip CSV + meta.json으로 여기 저장해 세션 간 재사용한다. 폴더명은
라우트 ID(short hash, `--`로 구분된 두 번째 토큰)를 그대로 쓴다.

## 구조

```
data/routes/<route_id>/
  route.csv.gz   # extract_log.py 출력물을 gzip -9 압축한 것
  meta.json       # extract_log.py가 함께 만드는 meta.json (원본 그대로)
```

## 등록된 라우트

| route_id | 별칭 | 세그먼트 | 행 수 | 추출 시 커밋 | 비고 |
|---|---|---|---|---|---|
| `ea5bcc0566` | route1 (x19seg) | 19 (seg0~19) | 22800 | `4fa4a44b9311` (72차 방안I) | seg10에 72차 원 발견 이벤트(정지앞차 레이더락온, t≈683.8~697) 포함 |
| `a5b1ce4e42` | route2 (x7seg) | 7 (seg0~6) | 7859 | `4fa4a44b9311` (72차 방안I) | seg1에 t≈1378.85 레이더락온 이벤트(72차 계속3 교차검증 사례) 포함 |

두 라우트 모두 "boost 윈도우(1.0s) 구조적 부족" 가설 재현에 쓰인
1차 검증 세트(72차 계속2/계속3). 상세 분석은 `FINDINGS.md` "72차"
계열 항목 참고.

| `d2a61d2a73` | 86차 route1 (x18seg) | 18 | 21599 | `284457f38a85` (85차) | c3-ms-curv 실주행, 5항목 스캔 완료(86차) |
| `dfc68039a9` | 86차 route2 (x20seg) | 20 | 24002 | `284457f38a85` (85차) | ttc_danger 3건 포함 |
| `4a32e2c0d3` | 86차 route3 (x20seg) | 20 | 24000 | `284457f38a85` (85차) | 안전지표 전부 클린 |
| `bc4301a25d` | 86차 route4 (x20seg) | 20 | 24000 | `284457f38a85` (85차) | turn_speed_violation 8건 |
| `c0e3054c4a` | 86차 route5 (x20seg) | 20 | 24001 | `284457f38a85` (85차) | turn_speed_violation 28건(최다) |
| `8b55ac185d` | 86차 route6 (x13seg) | 13(마지막 세그 zstd 손상, 스트리밍 폴백 회수) | 15185 | `284457f38a85` (85차) | turn_speed_violation 17건 |
| `1582412718` | 86차 route7 (x20seg) | 20 | 24033 | `284457f38a85` (85차) | stopped_lead/launch_after_stop 각 6건 |
| `e7a09d7ec4` | 86차 route8 (x4seg) | 4 | 4407 | `284457f38a85` (85차) | - |
| `a3fcd91b87` | 86차 route9 (단일세그) | 1 | 1055 | `284457f38a85` (85차) | 짧은 구간, 이상 없음 |
| `6e1e9a8e26` | 86차 route10 (x6seg) | 6 | 6214 | `284457f38a85` (85차) | ttc_danger 9건/harsh_brake 28건(밀집구간 추정) |

위 10개는 86차에서 c3-ms-curv(85차 HEAD) 검증용으로 일괄 업로드된 세트 —
5항목 스캔(`five_item_scan.py`)은 완료, qcamera 프레임 대조는 아직
미실시(원본 zip에 qcamera 미포함, CSV만 재확보됨). 상세는 FINDINGS.md
"86차" 항목 참고.

## 불러오기

`toolkit/data_routes.py`의 `load_route(devnotes_dir, route_id)` 사용.
gzip 압축을 풀어 `analysis_helpers.load_csv()`와 동일한
`list[dict]` 형태로 반환한다 (임시 파일 자동 정리).

```python
from data_routes import load_route
rows, meta = load_route("/home/claude/devnotes", "ea5bcc0566")
```

## 새 라우트 추가 절차

1. `extract_log.py`로 평소대로 추출 (`work/`에)
2. `gzip -k -9 <out.csv>`
3. `mkdir -p data/routes/<route_id>` 후 `route.csv.gz`, `meta.json` 복사
4. 이 표에 한 줄 추가
5. `push_via_api.py`로 `data/routes/<route_id>/*`, `data/routes/README.md`,
   (신규 스크립트면) `toolkit/data_routes.py`, `toolkit/README.md`,
   `toolkit/CHANGELOG.md` 함께 push
