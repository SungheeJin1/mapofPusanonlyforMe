"""Shrink an Overpass roads export to data/roads.json.gz:
[[highway, oneway, [[lon, lat], ...]], ...] with coordinates rounded to ~10 cm."""
import gzip
import json
import sys

src, dst = sys.argv[1], sys.argv[2]
ways = []
for el in json.load(open(src))["elements"]:
    if el["type"] != "way" or "geometry" not in el:
        continue
    t = el.get("tags", {})
    oneway = t.get("oneway", "no")
    if t.get("junction") == "roundabout" and oneway == "no":
        oneway = "yes"
    if t.get("busway") or t.get("oneway:bus") == "no":
        oneway = "no"
    ways.append([t["highway"], oneway, [[round(p["lon"], 6), round(p["lat"], 6)] for p in el["geometry"]]])
with gzip.open(dst, "wt") as f:
    json.dump(ways, f, separators=(",", ":"))
print(len(ways), "roads")
