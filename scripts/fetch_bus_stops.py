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
            for s in items(raw):
                lat, lon = pick(s, "lat", "gpsy", "y"), pick(s, "lin", "lng", "gpsx", "x")
                if lat and lon:
                    stops.append({"idx": int(pick(s, "bstopidx", "idx") or len(stops) + 1),
                                  "name": pick(s, "bstopnm", "nodenm") or "",
                                  "lat": float(lat), "lon": float(lon)})
            stops.sort(key=lambda s: s["idx"])
            out[lineno].append({"lineid": lineid, "name": pick(line, "buslinenum", "lineno"), "stops": stops})
        print(f"{lineno}: " + ", ".join(f"{l['lineid']} ({len(l['stops'])} stops)" for l in out[lineno]) or f"{lineno}: not found")
    (DATA / "bus_stops.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
