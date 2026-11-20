"""Turn each bus route's ordered stop list into a line that follows real roads.

Input:  data/bus_stops.json (fetch_bus_stops.py), data/roads.json.gz (compact_roads.py)
Output: data/bus_routes.json  {lineno: [[[lon, lat], ...], ...]}  (one line per API route id)

Between consecutive stops the bus takes the cheapest path on the OSM road
graph (respecting one-way streets; main roads are preferred over side
streets). Each stop is snapped onto the nearest road segment: buses stop on
the right-hand kerb, so the nearest carriageway is normally the one the bus
drives on. Service roads (e.g. inside the Pusan National University campus,
which 금정7 loops through) are used only when no ordinary road is near.
"""
import gzip
import heapq
import json
import math
import pathlib
import sys

from shapely import STRtree
from shapely.geometry import LineString, Point

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

LAT0 = 35.17
KX = 111320 * math.cos(math.radians(LAT0))  # metres per degree lon
KY = 110540                                  # metres per degree lat

# cost multiplier per road type: buses keep to the main roads
COST = {
    "motorway": 1.0, "trunk": 1.0, "primary": 1.0, "secondary": 1.0, "busway": 0.9,
    "motorway_link": 1.1, "trunk_link": 1.1, "primary_link": 1.1, "secondary_link": 1.1,
    "tertiary": 1.15, "tertiary_link": 1.15, "unclassified": 1.4, "residential": 1.6,
    "living_street": 2.5, "service": 2.5,
}


def m(lon, lat):
    return ((lon - 129.0) * KX, (lat - LAT0) * KY)


def ll(x, y):
    return (x / KX + 129.0, y / KY + LAT0)


class Graph:
    def __init__(self, roads):
        self.adj = {}       # node -> list of (cost, node)
        self.xy = {}        # node -> (x, y) metres
        ids = {}
        segs, self.seg_info, self.seg_penalty = [], [], []
        for hw, oneway, coords in roads:
            k = COST.get(hw, 2.0)
            pts = [m(*c) for c in coords]
            nodes = []
            for c, p in zip(coords, pts):
                key = (c[0], c[1])
                if key not in ids:
                    ids[key] = len(ids)
                    self.xy[ids[key]] = p
                nodes.append(ids[key])
            for a, b in zip(nodes, nodes[1:]):
                d = math.dist(self.xy[a], self.xy[b]) * k
                if oneway != "-1":
                    self.adj.setdefault(a, []).append((d, b))
                if oneway in ("no", "-1", "false", "0"):
                    self.adj.setdefault(b, []).append((d, a))
                segs.append(LineString([self.xy[a], self.xy[b]]))
                self.seg_info.append((a, b, k, oneway))
                # minor roads (campus/estate driveways) only win a stop when no real road is close
                self.seg_penalty.append(30.0 if hw in ("service", "living_street") else 0.0)
        self.tree = STRtree(segs)
        self.segs = segs
        self.next_id = len(ids)

    def snap(self, x, y, skip=0):
        """Insert a node on the (skip+1)-th nearest road segment to (x, y)."""
        p = Point(x, y)
        cand = self.tree.query(p.buffer(150))
        cand = sorted(cand, key=lambda i: self.segs[i].distance(p) + self.seg_penalty[i])
        if len(cand) <= skip:
            return None
        i = cand[skip]
        seg = self.segs[i]
        a, b, k, oneway = self.seg_info[i]
        q = seg.interpolate(seg.project(p))
        n = self.next_id
        self.next_id += 1
        self.xy[n] = (q.x, q.y)
        da, db = math.dist(self.xy[a], self.xy[n]) * k, math.dist(self.xy[n], self.xy[b]) * k
        if oneway != "-1":
            self.adj.setdefault(a, []).append((da, n))
            self.adj.setdefault(n, []).append((db, b))
        if oneway in ("no", "-1", "false", "0"):
            self.adj.setdefault(b, []).append((db, n))
            self.adj.setdefault(n, []).append((da, a))
        return n

    def path(self, s, t, limit):
        """A* from s to t; gives up beyond `limit` cost."""
        tx, ty = self.xy[t]
        h = lambda n: math.dist(self.xy[n], (tx, ty)) * 0.9
        best = {s: 0.0}
        prev = {}
        pq = [(h(s), 0.0, s)]
        while pq:
            _, g, n = heapq.heappop(pq)
            if n == t:
                out = [t]
                while out[-1] != s:
                    out.append(prev[out[-1]])
                return out[::-1]
            if g > best.get(n, math.inf) or g > limit:
                continue
            for c, nb in self.adj.get(n, ()):
                ng = g + c
                if ng < best.get(nb, math.inf):
                    best[nb] = ng
                    prev[nb] = n
                    heapq.heappush(pq, (ng + h(nb), ng, nb))
        return None


def route_line(g, stops):
    pts = [m(s["lon"], s["lat"]) for s in stops]
    out = []
    fallbacks = 0
    for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
        straight = math.dist((x1, y1), (x2, y2))
        if straight < 1:
            continue
        found = None
        # try the nearest segment first, then the next ones (other carriageway etc.)
        for s_skip, t_skip in ((0, 0), (1, 0), (0, 1), (1, 1), (2, 0), (0, 2)):
            a, b = g.snap(x1, y1, s_skip), g.snap(x2, y2, t_skip)
            if a is None or b is None:
                continue
            p = g.path(a, b, limit=max(straight * 6, 1500))
            if p:
                found = [g.xy[n] for n in p]
                break
        if not found:
            fallbacks += 1
            found = [(x1, y1), (x2, y2)]
        out.extend(found if not out else found[1:])
    out = drop_spurs(out)
    return [list(map(lambda v: round(v, 6), ll(x, y))) for x, y in out], fallbacks


def drop_spurs(pts, max_len=150.0, tol=5.0):
    """Remove short out-and-back spikes: where a stop was snapped onto a side
    street or the far carriageway, the path runs in and straight back out.

    A spike is a U-turn whose retraced part is shorter than max_len. Longer
    out-and-back sections (real turnarounds, e.g. 금정7's campus loop) stay."""
    pts = list(pts)
    i = 1
    while i < len(pts) - 1:
        a, b = i - 1, i + 1
        length = 0.0
        while a >= 0 and b < len(pts) and math.dist(pts[a], pts[b]) < tol:
            length += math.dist(pts[a], pts[a + 1])
            a -= 1
            b += 1
        if a < i - 1 and length < max_len:
            # pts[a+1] and pts[b-1] coincide; drop everything between
            del pts[a + 2:b]
            i = max(a + 1, 1)
        else:
            i += 1
    return pts


def main():
    roads = json.load(gzip.open(DATA / "roads.json.gz", "rt"))
    stops = json.loads((DATA / "bus_stops.json").read_text())
    print(f"{len(roads)} roads; building graph ...")
    g = Graph(roads)
    result = {}
    for lineno, lines in stops.items():
        result[lineno] = []
        for line in lines:
            if len(line["stops"]) < 2:
                continue
            coords, fb = route_line(g, line["stops"])
            result[lineno].append(coords)
            print(f"  {lineno} ({line['lineid']}): {len(line['stops'])} stops, {fb} straight-line fallbacks")
    (DATA / "bus_routes.json").write_text(json.dumps(result, ensure_ascii=False, separators=(",", ":")))


if __name__ == "__main__":
    sys.exit(main())
