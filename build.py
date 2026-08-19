#!/usr/bin/env python3
"""Turn TopoJSON + Vanguard holdings into a self-contained geography page.

Decodes the topology and projects it here rather than in the browser, so the
published page carries plain SVG paths and needs no mapping library at all.
"""
import json, math, os, sys

TOPO = "/tmp/world50m.json"
SRC = "/Users/freddiehewer/Desktop/Holdings details - Vanguard FTSE All-World UCITS ETF (USD) Accumulating - 18_08_2026.xlsx"
OUT = os.path.expanduser("~/Documents/GitHub/vwrp-geography/mapdata.json")

A2N = {
 "US":"840","JP":"392","GB":"826","TW":"158","CA":"124","HK":"344","KR":"410",
 "CH":"756","FR":"250","DE":"276","IN":"356","AU":"036","NL":"528","ES":"724",
 "SE":"752","IT":"380","DK":"208","SG":"702","BR":"076","ZA":"710","SA":"682",
 "MX":"484","TH":"764","MY":"458","ID":"360","IL":"376","BE":"056","FI":"246",
 "NO":"578","AE":"784","QA":"634","PL":"616","TR":"792","PH":"608","CL":"152",
 "AT":"040","IE":"372","PT":"620","NZ":"554","GR":"300","CN":"156","KW":"414",
 "HU":"348","CZ":"203","RO":"642","CO":"170","EG":"818","IS":"352","RU":"643",
}

W, H = 900, 460


def natural_earth(lon, lat):
    """d3's naturalEarth1 raw projection, in radians."""
    l = math.radians(lon); p = math.radians(lat)
    p2 = p * p; p4 = p2 * p2
    x = l * (0.8707 - 0.131979 * p2 + p4 * (-0.013791 + p4 * (0.003971 * p2 - 0.001529 * p4)))
    y = p * (1.007226 + p2 * (0.015085 + p4 * (-0.044475 + 0.028874 * p2 - 0.005916 * p4)))
    return x, y


# Projection bounds, so the drawing fills the viewBox
X0, _ = natural_earth(-180, 0); X1, _ = natural_earth(180, 0)
_, Y0 = natural_earth(0, 90);   _, Y1 = natural_earth(0, -90)
SCALE = min(W / (X1 - X0), H / (Y0 - Y1))
CX, CY = W / 2, H / 2


def project(lon, lat):
    x, y = natural_earth(lon, lat)
    return (CX + x * SCALE, CY - y * SCALE)


def decode_arcs(topo):
    """TopoJSON arcs are quantised and delta-encoded; undo both."""
    tr = topo.get("transform")
    out = []
    for arc in topo["arcs"]:
        pts = []
        x = y = 0
        for dx, dy in arc:
            if tr:
                x += dx; y += dy
                lon = x * tr["scale"][0] + tr["translate"][0]
                lat = y * tr["scale"][1] + tr["translate"][1]
            else:
                lon, lat = dx, dy
            pts.append((lon, lat))
        out.append(pts)
    return out


def ring_points(arcs, idxs):
    pts = []
    for i in idxs:
        a = arcs[~i][::-1] if i < 0 else arcs[i]
        pts.extend(a[1:] if pts else a)
    return pts


def _rdp(pts, tol):
    """Ramer-Douglas-Peucker on an OPEN polyline."""
    if len(pts) < 3:
        return pts
    keep = [False] * len(pts)
    keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        lo, hi = stack.pop()
        if hi <= lo + 1:
            continue
        x0, y0 = pts[lo]; x1, y1 = pts[hi]
        dx, dy = x1 - x0, y1 - y0
        norm = math.hypot(dx, dy) or 1e-9
        worst, wi = -1.0, lo
        for i in range(lo + 1, hi):
            px, py = pts[i]
            d = abs(dy * px - dx * py + x1 * y0 - y1 * x0) / norm
            if d > worst:
                worst, wi = d, i
        if worst > tol:
            keep[wi] = True
            stack.append((lo, wi)); stack.append((wi, hi))
    return [p for p, k in zip(pts, keep) if k]


def simplify(pts, tol):
    """Simplify a CLOSED ring.

    Running RDP straight over a ring collapses it: first and last point are the
    same, so the baseline has zero length and every perpendicular distance comes
    out as zero. Split the ring at its farthest point from the start and treat
    the two halves as open polylines instead.
    """
    if len(pts) < 4:
        return pts
    ring = pts[:-1] if pts[0] == pts[-1] else pts[:]
    if len(ring) < 4:
        return pts
    x0, y0 = ring[0]
    far = max(range(len(ring)), key=lambda i: (ring[i][0]-x0)**2 + (ring[i][1]-y0)**2)
    if far < 2 or far > len(ring) - 2:
        out = _rdp(ring + [ring[0]], tol)
    else:
        out = _rdp(ring[:far+1], tol)[:-1] + _rdp(ring[far:] + [ring[0]], tol)
    if out and out[0] != out[-1]:
        out.append(out[0])
    return out


def to_path(geom, arcs, min_area=0.6, tol=0.45):
    polys = []
    if geom["type"] == "Polygon":
        polys = [geom["arcs"]]
    elif geom["type"] == "MultiPolygon":
        polys = geom["arcs"]
    else:
        return ""

    d = []
    for poly in polys:
        for ring in poly:
            pts = [project(lon, lat) for lon, lat in ring_points(arcs, ring)]
            if len(pts) < 4:
                continue
            pts = simplify(pts, tol)
            if len(pts) < 4:
                continue
            # Drop slivers that only add bytes at this size.
            area = abs(sum(pts[i][0]*pts[i-1][1] - pts[i-1][0]*pts[i][1]
                           for i in range(len(pts)))) / 2
            if area < min_area:
                continue
            d.append("M" + "L".join(f"{round(x)},{round(y)}" for x, y in pts) + "Z")
    return "".join(d)


def main():
    import pandas as pd
    topo = json.load(open(TOPO))
    arcs = decode_arcs(topo)
    geoms = topo["objects"]["countries"]["geometries"]

    # Small territories still need to be visible, so keep their slivers.
    KEEP_SMALL = {"344", "702", "376", "634", "414"}
    SKIP = {"010"}          # Antarctica: a fifth of the frame, nothing held there
    paths, names = {}, {}
    for g in geoms:
        cid = g.get("id")
        if not cid or cid in SKIP:
            continue
        small = cid in KEEP_SMALL
        p = to_path(g, arcs,
                    min_area=0.05 if small else 1.5,
                    tol=0.15 if small else 0.5)
        if p:
            paths[cid] = p
            names[cid] = (g.get("properties") or {}).get("name", cid)

    df = pd.read_excel(SRC, header=6).dropna(subset=["Ticker"])
    df["wt"] = df["% of market value"].astype(str).str.rstrip("%").astype(float)
    df["mv"] = (df["Market value"].astype(str)
                .str.replace(r"[US$,]", "", regex=True).astype(float))

    # Natural Earth's formal names overflow the ranked list.
    SHORT = {"840": "United States", "784": "UAE"}

    countries = {}
    for region, grp in df.groupby("Region"):
        cid = A2N.get(str(region).strip())
        if not cid:
            continue
        top = grp.nlargest(3, "wt")[["Holding name", "wt"]].values.tolist()
        sec = grp.groupby("Sector")["wt"].sum().sort_values(ascending=False)
        countries[cid] = {
            "code": region,
            "name": SHORT.get(cid, names.get(cid, region)),
            "weight": round(float(grp["wt"].sum()), 4),
            "holdings": int(len(grp)),
            "topSector": sec.index[0] if len(sec) else None,
            "topSectorPct": round(float(sec.iloc[0] / grp["wt"].sum() * 100), 1) if len(sec) else None,
            "top": [[str(n)[:40], round(float(w), 4)] for n, w in top],
        }

    # Concentration measures worth stating plainly.
    ws = sorted((c["weight"] for c in countries.values()), reverse=True)
    total = sum(ws)
    shares = [w / total for w in ws]
    hhi = sum(x * x for x in shares)

    # Crop the viewBox to the drawn world rather than the whole projection.
    import re as _re
    coords = [tuple(map(float, pair.split(",")))
              for d in paths.values()
              for pair in _re.findall(r"(-?\d+(?:\.\d+)?,-?\d+(?:\.\d+)?)", d)]
    min_y = min(c[1] for c in coords); max_y = max(c[1] for c in coords)
    pad = 6
    vb_y = max(0, min_y - pad)
    vb_h = min(H, max_y + pad) - vb_y

    payload = {
        "concentration": {
            "top1": round(ws[0], 2),
            "top3": round(sum(ws[:3]), 2),
            "top5": round(sum(ws[:5]), 2),
            "top10": round(sum(ws[:10]), 2),
            "countries": len(ws),
            "effectiveCountries": round(1 / hhi, 1),
        },
        "viewBox": f"0 {vb_y:.0f} {W} {vb_h:.0f}",
        "paths": paths,
        "names": names,
        "countries": countries,
        "asOf": "31 July 2026",
        "totalHoldings": int(len(df)),
        "mappedWeight": round(float(sum(c["weight"] for c in countries.values())), 2),
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(payload, open(OUT, "w"), separators=(",", ":"))

    print(f"countries with holdings : {len(countries)}")
    print(f"shapes drawn            : {len(paths)}")
    print(f"fund weight on the map  : {payload['mappedWeight']}%")
    print(f"file size               : {os.path.getsize(OUT)/1024:.0f} KB")
    miss = sorted({str(r).strip() for r in df['Region'].dropna()} - {c['code'] for c in countries.values()})
    print(f"unmapped regions        : {miss or 'none'}")
    c = payload["concentration"]
    print(f"top 1 / 3 / 10          : {c['top1']}% / {c['top3']}% / {c['top10']}%")
    print(f"effective countries     : {c['effectiveCountries']} (of {c['countries']})")

    tpl = os.path.join(os.path.dirname(OUT), "template.html")
    if os.path.exists(tpl):
        html = open(tpl).read().replace("__MAPDATA__", json.dumps(payload, separators=(",", ":")))
        idx = os.path.join(os.path.dirname(OUT), "index.html")
        open(idx, "w").write(html)
        print(f"index.html              : {os.path.getsize(idx)/1024:.0f} KB")


if __name__ == "__main__":
    main()
