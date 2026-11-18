"""Render the Busan map (land / sea / subway 1-3 / selected bus routes) to SVG.

Input:  data/coastline.json, data/routes.json  (from fetch_osm.py)
Output: busan_map.svg
"""
import json
import math
import pathlib

from shapely.geometry import LineString, MultiLineString, Point, Polygon, box
from shapely.ops import linemerge, polygonize, unary_union

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

# Area shown on the map: west, south, east, north (degrees)
VIEW = (128.76, 34.99, 129.31, 35.40)
WIDTH = 2400  # px

COLORS = {
    "land": "#F8F3E3",       # 연한 미색
    "land_edge": "#E6DCC2",
    "sea": "#CFE6F3",        # 연한 하늘색
    "bus": "#A6DC4A",        # 연두색
    "1": "#F06A00",          # 부산 도시철도 1호선
    "2": "#81BF48",          # 2호선
    "3": "#BB8C00",          # 3호선
}

BUS_REFS = {"금정7", "77", "100-1", "80", "31", "189"}


# ---------------------------------------------------------------- projection
def merc(lon, lat):
    x = math.radians(lon)
    y = math.log(math.tan(math.pi / 4 + math.radians(lat) / 2))
    return x, y


X0, Y1 = merc(VIEW[0], VIEW[3])
X1, Y0 = merc(VIEW[2], VIEW[1])
SCALE = WIDTH / (X1 - X0)
HEIGHT = round((Y1 - Y0) * SCALE)


def proj(lon, lat):
    x, y = merc(lon, lat)
    return (x - X0) * SCALE, (Y1 - y) * SCALE


def geom_to_line(geom):
    return LineString([proj(p["lon"], p["lat"]) for p in geom])


# ---------------------------------------------------------------- land / sea
def build_land():
    data = json.loads((DATA / "coastline.json").read_text())
    frame = box(0, 0, WIDTH, HEIGHT)

    directed = set()   # directed coastline segments (land lies on the left)
    lines = []
    for el in data["elements"]:
        if el["type"] != "way" or "geometry" not in el:
            continue
        pts = [proj(p["lon"], p["lat"]) for p in el["geometry"]]
        for a, b in zip(pts, pts[1:]):
            directed.add((key(a), key(b)))
        lines.append(LineString(pts))

    merged = linemerge(lines)
    merged = list(merged.geoms) if isinstance(merged, MultiLineString) else [merged]
    clipped = [g for g in (m.intersection(frame) for m in merged) if not g.is_empty]

    noded = unary_union(clipped + [frame.exterior])
    land = []
    for face in polygonize(noded):
        verdict = classify(face, directed)
        if verdict:
            land.append(face)
    return unary_union(land)


def key(p):
    return (round(p[0], 4), round(p[1], 4))


def classify(face: Polygon, directed):
    """True if the face is land, False if sea, None if it touches no coastline.

    OSM coastlines keep land on the left (in north-up geographic terms).  Find
    any coastline segment on the face boundary and probe a point just to its
    left: if that point is inside the face, the face is land.
    """
    ring = list(face.exterior.coords)
    for a, b in zip(ring, ring[1:]):
        ka, kb = key(a), key(b)
        if (ka, kb) in directed:
            (ax, ay), (bx, by) = a, b
        elif (kb, ka) in directed:
            (ax, ay), (bx, by) = b, a
        else:
            continue
        dx, dy = bx - ax, by - ay
        n = math.hypot(dx, dy)
        if n < 1e-6:
            continue
        # left normal in y-down screen space is (dy, -dx)
        probe = Point((ax + bx) / 2 + dy / n * 0.05, (ay + by) / 2 - dx / n * 0.05)
        return face.contains(probe)
    return None


# ---------------------------------------------------------------- routes
def build_routes():
    data = json.loads((DATA / "routes.json").read_text())
    subway = {"1": {}, "2": {}, "3": {}}
    bus = {}
    found = []
    for rel in data["elements"]:
        if rel["type"] != "relation":
            continue
        t = rel.get("tags", {})
        ref = t.get("ref", "")
        if t.get("route") == "subway":
            line = ref if ref in subway else None
            if line is None:
                for n in "123":
                    if f"{n}호선" in t.get("name", ""):
                        line = n
            if line is None:
                continue
            target = subway[line]
        elif t.get("route") == "bus" and ref in BUS_REFS:
            target = bus
        else:
            continue
        found.append((t.get("route"), ref, t.get("name")))
        for m in rel.get("members", []):
            if m["type"] == "way" and m.get("role", "") in ("", "forward", "backward") and "geometry" in m:
                target[m["ref"]] = geom_to_line(m["geometry"])
    for f in sorted(found, key=str):
        print("  route:", *f)
    return subway, bus


# ---------------------------------------------------------------- svg output
def path_d(geom, closed):
    parts = []
    if geom.is_empty:
        return ""
    if geom.geom_type in ("Polygon", "MultiPolygon"):
        polys = [geom] if geom.geom_type == "Polygon" else list(geom.geoms)
        for p in polys:
            for ring in [p.exterior, *p.interiors]:
                parts.append(coords_d(ring.coords, True))
    else:
        lines = [geom] if geom.geom_type == "LineString" else list(geom.geoms)
        for ln in lines:
            parts.append(coords_d(ln.coords, closed))
    return "".join(parts)


def coords_d(coords, closed):
    pts = [f"{x:.1f} {y:.1f}" for x, y in coords]
    return "M" + "L".join(pts) + ("Z" if closed else "")


def lines_d(lines):
    merged = linemerge(list(lines))
    merged = merged.simplify(0.4)
    return path_d(merged, False)


def main():
    print("building land ...")
    land = build_land().simplify(0.35, preserve_topology=True)
    print("collecting routes ...")
    subway, bus = build_routes()

    land_d = path_d(land, True)
    bus_d = lines_d(bus.values()) if bus else ""
    sub_d = {k: lines_d(v.values()) for k, v in subway.items() if v}

    lw = WIDTH / 1000  # line-width unit
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {WIDTH} {HEIGHT}" width="{WIDTH}" height="{HEIGHT}">
  <defs>
    <filter id="relief" x="-5%" y="-5%" width="110%" height="110%" color-interpolation-filters="sRGB">
      <!-- broad soft shadow cast below/right of the land -->
      <feGaussianBlur in="SourceAlpha" stdDeviation="{6 * lw:.1f}" result="b1"/>
      <feOffset in="b1" dx="{3 * lw:.1f}" dy="{6 * lw:.1f}" result="o1"/>
      <feFlood flood-color="#5E6F7A" flood-opacity="0.30"/>
      <feComposite in2="o1" operator="in" result="s1"/>
      <!-- tight contact shadow right at the shore -->
      <feGaussianBlur in="SourceAlpha" stdDeviation="{1.2 * lw:.1f}" result="b2"/>
      <feOffset in="b2" dx="{1 * lw:.1f}" dy="{2 * lw:.1f}" result="o2"/>
      <feFlood flood-color="#6B6250" flood-opacity="0.35"/>
      <feComposite in2="o2" operator="in" result="s2"/>
      <!-- faint highlight on the upper-left edge for a raised look -->
      <feOffset in="SourceAlpha" dx="{-1.2 * lw:.1f}" dy="{-1.2 * lw:.1f}" result="hl"/>
      <feComposite in="SourceAlpha" in2="hl" operator="out" result="edge"/>
      <feGaussianBlur in="edge" stdDeviation="{0.6 * lw:.1f}" result="edgeb"/>
      <feFlood flood-color="#FFFFFF" flood-opacity="0.9"/>
      <feComposite in2="edgeb" operator="in" result="glint"/>
      <feComposite in="glint" in2="SourceAlpha" operator="in" result="glint2"/>
      <feMerge>
        <feMergeNode in="s1"/>
        <feMergeNode in="s2"/>
        <feMergeNode in="SourceGraphic"/>
        <feMergeNode in="glint2"/>
      </feMerge>
    </filter>
  </defs>
  <rect width="{WIDTH}" height="{HEIGHT}" fill="{COLORS['sea']}"/>
  <path d="{land_d}" fill="{COLORS['land']}" fill-rule="evenodd" stroke="{COLORS['land_edge']}" stroke-width="{0.6 * lw:.2f}" filter="url(#relief)"/>
  <g fill="none" stroke-linecap="round" stroke-linejoin="round">
    <path d="{bus_d}" stroke="{COLORS['bus']}" stroke-width="{2.6 * lw:.2f}"/>
"""
    for n in ("3", "2", "1"):
        if n in sub_d:
            svg += f'    <path d="{sub_d[n]}" stroke="#FFFFFF" stroke-width="{6.4 * lw:.2f}"/>\n'
    for n in ("3", "2", "1"):
        if n in sub_d:
            svg += f'    <path d="{sub_d[n]}" stroke="{COLORS[n]}" stroke-width="{4.4 * lw:.2f}"/>\n'
    svg += "  </g>\n</svg>\n"
    out = ROOT / "busan_map.svg"
    out.write_text(svg)
    print(f"wrote {out} ({len(svg) / 1e6:.2f} MB, {WIDTH}x{HEIGHT})")


if __name__ == "__main__":
    main()
