"""Download the raw OpenStreetMap data used by build_map.py.

Writes:
  data/coastline.json  - natural=coastline ways around Busan (Overpass JSON, with geometry)
  data/routes.json     - subway lines 1-3 and the selected bus routes (relations with geometry)
"""
import json
import pathlib
import sys
import time
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
ENDPOINT = "https://overpass-api.de/api/interpreter"

# south, west, north, east
BBOX = (34.95, 128.70, 35.45, 129.36)

BUS_REFS = ["금정7", "77", "100-1", "80", "31", "189"]

QUERIES = {
    "coastline.json": f"""
[out:json][timeout:180];
way["natural"="coastline"]({BBOX[0]},{BBOX[1]},{BBOX[2]},{BBOX[3]});
out geom;
""",
    "routes.json": f"""
[out:json][timeout:180];
area["name"="부산광역시"]["admin_level"="4"]->.busan;
(
  relation["type"="route"]["route"="subway"]["ref"~"^[123]$"](area.busan);
  relation["type"="route"]["route"="subway"]["name"~"부산 ?[123]호선|부산 도시철도 ?[123]호선"](area.busan);
  relation["type"="route"]["route"="bus"]["ref"~"^({'|'.join(BUS_REFS)})$"](area.busan);
);
out geom;
""",
}


def run(query: str) -> bytes:
    body = urllib.parse.urlencode({"data": query}).encode()
    for attempt in range(60):
        try:
            req = urllib.request.Request(ENDPOINT, data=body, headers={"User-Agent": "busan-map-builder/1.0"})
            with urllib.request.urlopen(req, timeout=300) as r:
                return r.read()
        except Exception as e:  # network hiccups / rate limits
            wait = 30
            print(f"  attempt {attempt + 1} failed ({e}); retrying in {wait}s", file=sys.stderr)
            time.sleep(wait)
    raise SystemExit("Overpass request failed")


def main() -> None:
    DATA.mkdir(exist_ok=True)
    for name, q in QUERIES.items():
        print(f"fetching {name} ...")
        raw = run(q)
        json.loads(raw)  # validate
        (DATA / name).write_bytes(raw)
        print(f"  {len(raw) / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
