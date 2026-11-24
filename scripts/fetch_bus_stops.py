"""Fetch the ordered stop list of each bus route from the Busan Bus Information
System open API (data.go.kr, "부산광역시_부산버스정보시스템").

Runs in GitHub Actions with the API key in the BUSAN_BIMS_KEY secret
(the *Decoding* key from data.go.kr).

Writes:
  data/bus_stops.json         {lineno: [{"lineid", "name", "stops": [{"idx", "name", "lat", "lon"}]}]}
  data/bus_raw/*.xml          raw API responses, for debugging (no key inside)
"""
import json
import os
import pathlib
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
RAW = DATA / "bus_raw"
BASE = "https://apis.data.go.kr/6260000/BusanBIMS"

# route number -> spellings to try in the API (village buses are named by district)
LINES = {
    "금정7": ["금정7", "금정구7", "금정07"],
    "77": ["77"],
    "100-1": ["100-1"],
    "80": ["80"],
    "31": ["31"],
    "189": ["189"],
    "10": ["10"],
    "144": ["144"],
    "111-1": ["111-1"],
    "54": ["54"],
}


def call(op, **params):
    params = {"serviceKey": os.environ["BUSAN_BIMS_KEY"], "numOfRows": "1000", "pageNo": "1", **params}
    url = f"{BASE}/{op}?{urllib.parse.urlencode(params)}"
    for attempt in range(4):
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                return r.read()
        except Exception as e:
            print(f"  {op} {params.get('lineno') or params.get('lineid')}: {e}", file=sys.stderr)
            time.sleep(5 * (attempt + 1))
    return b""


def items(raw):
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return []
    return [{c.tag: (c.text or "").strip() for c in it} for it in root.iter("item")]


def pick(d, *names):
    for n in names:
        if d.get(n):
            return d[n]
    return None


_stop_cache = {}


def stop_position(nodeid, arsno, name):
    """(lat, lon) of a stop, via busStopList searched by ARS number or name."""
    if nodeid in _stop_cache:
        return _stop_cache[nodeid]
    queries = ([{"arsno": arsno}] if arsno else []) + ([{"bstopnm": name}] if name else [])
    for q in queries:
        raw = call("busStopList", **q)
        if not (RAW / "busStopList_sample.xml").exists():
            (RAW / "busStopList_sample.xml").write_bytes(raw)
        for it in items(raw):
            lat, lon = pick(it, "gpsy", "lat", "y"), pick(it, "gpsx", "lin", "lng", "x")
            if lat and lon:
                _stop_cache.setdefault(pick(it, "bstopid", "nodeid"), (float(lat), float(lon)))
        if nodeid in _stop_cache:
            return _stop_cache[nodeid]
    return None


def main():
    RAW.mkdir(parents=True, exist_ok=True)
    out = {}
    for lineno, spellings in LINES.items():
        out[lineno] = []
        for sp in spellings:
            raw = call("busInfo", lineno=sp)
            (RAW / f"busInfo_{sp}.xml").write_bytes(raw)
            found = [i for i in items(raw) if pick(i, "buslinenum", "lineno") in spellings]
            if found:
                break
        for line in found:
            lineid = pick(line, "lineid", "lineId")
            raw = call("busInfoByRouteId", lineid=lineid)
            (RAW / f"busInfoByRouteId_{lineid}.xml").write_bytes(raw)
            stops = []
            # The route list gives stop ids only (its lat/lin are live bus
            # positions), so look each stop's coordinates up separately.
            for s in items(raw):
                pos = stop_position(s.get("nodeid"), s.get("arsno"), s.get("bstopnm"))
                if pos:
                    stops.append({"idx": int(s.get("bstopidx") or len(stops) + 1), "name": s.get("bstopnm", ""),
                                  "nodeid": s.get("nodeid"), "rpoint": s.get("rpoint") == "1",
                                  "lat": pos[0], "lon": pos[1]})
                else:
                    print(f"  no position for stop {s.get('bstopnm')} ({s.get('nodeid')})", file=sys.stderr)
            stops.sort(key=lambda s: s["idx"])
            out[lineno].append({"lineid": lineid, "name": pick(line, "buslinenum", "lineno"), "stops": stops})
        print(f"{lineno}: " + ", ".join(f"{l['lineid']} ({len(l['stops'])} stops)" for l in out[lineno]) or f"{lineno}: not found")
    (DATA / "bus_stops.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
