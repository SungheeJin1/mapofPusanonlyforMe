"""Export the map as data for the web app (web/index.html).

Writes web/map-data.json with everything in the same pixel space as
busan_map.svg (WIDTH x HEIGHT):
  land       SVG path of land (sea and rivers are the gaps)
  subway     {"1": {d, samples, ends}, ...}
  buses      [{no, d, samples, from, turn, stops: [stop index...], km}]
  stops      [{n: name, x, y, r: [route numbers], p: priority 1-3}]
"""
import json
import math
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import build_map as bm  # noqa: E402
from shapely.geometry import LineString  # noqa: E402
from shapely.ops import linemerge  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUT = ROOT / "web" / "map-data.json"

ORDER = ["금정7", "77", "100-1", "80", "31", "189", "10", "144", "111-1"]
LANDMARK = re.compile(r"(역$|역[.\s(]|시장|병원|대학교|구청|시청|터미널|해수욕장|차고지|종점|백화점|부산대)")


def r1(v):
    return round(v, 1)


def line_d(geom):
    return bm.path_d(geom, False)


def samples(line: LineString, step=40.0):
    """Points every `step` px along the line, for placing route-number badges."""
    out = []
    d = step / 2
    while d < line.length:
        p = line.interpolate(d)
        q = line.interpolate(min(d + 4, line.length))
        ang = math.degrees(math.atan2(q.y - p.y, q.x - p.x))
        out.append([r1(p.x), r1(p.y), round(ang)])
        d += step
    return out


def main():
    print("land ...")
    land = bm.build_land()
    land = land.buffer(2.5, join_style="mitre").buffer(-2.5, join_style="mitre")
    land = land.simplify(0.35, preserve_topology=True)

    print("subway ...")
    subway, _ = bm.build_routes()
    ends = {"1": "다대포해수욕장 ↔ 노포", "2": "장산 ↔ 양산", "3": "수영 ↔ 대저"}
    sub = {}
    for k, v in subway.items():
        if not v:
            continue
        g = linemerge(list(v.values())).simplify(0.4)
        parts = list(g.geoms) if g.geom_type == "MultiLineString" else [g]
        sub[k] = {"d": line_d(g), "samples": [s for p in parts for s in samples(p)], "ends": ends[k]}

    print("bus stops ...")
    stop_data = json.loads((DATA / "bus_stops.json").read_text())
    routed = json.loads((DATA / "bus_routes.json").read_text())

    # one stop entry per name (both directions' poles merged), split if far apart
    stops, index = [], {}
    seq = {}
    for no in ORDER:
        seq[no] = []
        for line in stop_data.get(no, []):
            for s in line["stops"]:
                x, y = bm.proj(s["lon"], s["lat"])
                cand = [i for i in index.get(s["name"], []) if math.dist((stops[i]["x"], stops[i]["y"]), (x, y)) < 40]
                if cand:
                    i = cand[0]
                    st = stops[i]
                    k = st["_k"]
                    st["x"], st["y"], st["_k"] = (st["x"] * k + x) / (k + 1), (st["y"] * k + y) / (k + 1), k + 1
                else:
                    i = len(stops)
                    stops.append({"n": s["name"], "x": x, "y": y, "r": [], "p": 1, "_k": 1})
                    index.setdefault(s["name"], []).append(i)
                st = stops[i]
                if no not in st["r"]:
                    st["r"].append(no)
                if s["idx"] == 1 or s.get("rpoint"):
                    st["p"] = 3
                if not seq[no] or seq[no][-1] != i:
                    seq[no].append(i)
    for st in stops:
        if st["p"] < 3 and (len(st["r"]) >= 2 or LANDMARK.search(st["n"])):
            st["p"] = 2
        st["x"], st["y"] = r1(st["x"]), r1(st["y"])
        del st["_k"]

    buses = []
    for no in ORDER:
        lines = [LineString([bm.proj(lon, lat) for lon, lat in ln]) for ln in routed.get(no, []) if len(ln) > 1]
        if not lines:
            continue
        geom = lines[0] if len(lines) == 1 else linemerge(lines)
        geom = geom.simplify(0.5)
        first = stop_data[no][0]["stops"]
        turn = next((s["name"] for s in first if s.get("rpoint")), first[len(first) // 2]["name"])
        km = sum(l.length for l in lines) / bm.SCALE * 6371.0 * math.cos(math.radians(35.17))
        parts = list(geom.geoms) if geom.geom_type == "MultiLineString" else [geom]
        buses.append({
            "no": no,
            "d": line_d(geom),
            "samples": [s for p in parts for s in samples(p)],
            "from": first[0]["name"],
            "turn": turn,
            "stops": seq[no],
            "km": round(km, 1),
        })
        print(f"  {no}: {len(seq[no])} stops, {km:.1f} km")

    OUT.parent.mkdir(exist_ok=True)
    data = {"w": bm.WIDTH, "h": bm.HEIGHT, "land": bm.path_d(land, True), "subway": sub, "buses": buses, "stops": stops}
    OUT.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")))
    print(f"wrote {OUT} ({OUT.stat().st_size / 1e3:.0f} KB): {len(stops)} stops, "
          f"{sum(s['p'] >= 2 for s in stops)} major")


if __name__ == "__main__":
    main()
