# mapofPusanonlyforMe

부산 지도. 표시하는 것은 아래뿐이고, 지명·도로·범례는 넣지 않았습니다.

- 육지: 연한 미색, 아래쪽에 그림자를 깔아 살짝 떠 보이게
- 바다·강: 연한 하늘색
- 도시철도 1·2·3호선: 각 노선 고유색 (주황 / 초록 / 갈색)
- 버스 금정7, 77, 100-1, 80, 31, 189번: 연두색

![부산 지도](busan_map.png)

결과물: `busan_map.svg` (벡터), `busan_map.png` (2400px)

## 웹앱

`web/index.html` + `web/map-data.json`. 확대·이동이 되는 지도에 노선 번호와 버스정류장 이름을 표시합니다.

- 노선 번호: 버스 노선을 따라 번호 배지, 지하철은 호선 번호 원
- 정류장: 기점·회차, 여러 노선이 서는 정류장, 역·시장·병원·대학 등 주요 정류장은 처음부터 이름 표시.
  나머지는 확대하면 보입니다.
- 노선(아래 칩이나 지도 위 선)을 누르면 그 노선만 강조되고 정류장 순서 목록이 나옵니다.

로컬에서 보기: `cd web && python3 -m http.server` 후 http://localhost:8000
(데이터를 `fetch`로 읽어서 파일을 바로 열면 안 됩니다.)

## 데이터

- 해안선, 강, 지하철 선로, 도로망: © OpenStreetMap contributors (ODbL), Overpass API
- 버스 정류장 순서와 좌표: 부산광역시_부산버스정보시스템 (공공데이터포털)

OpenStreetMap에는 6개 버스 노선 중 100-1번만 있어서, 버스는 공공데이터의 정류장 순서를
OSM 도로망 위에서 정류장 사이 최단 경로(일방통행 반영, 큰길 우선)로 이어 그렸습니다.

## 다시 만들기

1. 데이터: `.github/workflows/fetch-osm.yml`이 GitHub Actions에서 받아 `data/`에 커밋합니다.
   버스 정류장은 저장소 Secret `BUSAN_BIMS_KEY`(공공데이터포털 일반 인증키, Decoding)가 필요합니다.
2. 버스 노선: `python3 scripts/route_buses.py` → `data/bus_routes.json`
3. 지도: `python3 scripts/build_map.py` → `busan_map.svg`
4. PNG: `node scripts/render_png.js` → `busan_map.png` (Playwright 필요)
5. 웹앱 데이터: `python3 scripts/build_webapp.py` → `web/map-data.json`
