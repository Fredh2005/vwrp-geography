# Where VWRP actually invests

The geographic reality of a fund called "All-World": **61% of it is one country**,
and 70% is three.

Live at **https://fredh2005.github.io/vwrp-geography/**

## What it shows

- A **world choropleth** shaded by each country's real share of the fund, with a
  hover readout giving weight, holding count, dominant sector and largest companies.
- **Every country ranked** by weight, because a map flatters large empty countries
  and hides small dense ones — Hong Kong and Taiwan being the obvious cases.
- **Concentration measures**, including *effective countries*: the weight-adjusted
  count of how many equally-sized countries would produce the same concentration.
  VWRP holds 49 and behaves like **2.6**.

## Where the numbers come from

Vanguard's own published holdings export — 3,792 holdings with their real weights,
as at 31 July 2026. Not estimates. 49 countries map to a shape, covering **99.03%**
of the fund by weight.

## How the map is built

`build.py` does everything ahead of time so the published page needs no mapping
library, no CDN and no network:

1. Reads Natural Earth 50m TopoJSON (the 110m file omits Hong Kong and Singapore,
   which between them are 3% of the fund).
2. Decodes the quantised, delta-encoded arcs.
3. Projects to 2D with d3's `naturalEarth1` formula, implemented in Python.
4. Simplifies each ring with Ramer-Douglas-Peucker — 1 MB of raw paths down to 82 KB.
5. Drops Antarctica and crops the frame to the inhabited world.
6. Emits plain SVG path strings, inlined into `index.html`.

Rebuild after a new holdings export:

```bash
python build.py
```

It needs `pandas` and `openpyxl`, and the world topology at `/tmp/world50m.json`:

```bash
curl -Lo /tmp/world50m.json https://cdn.jsdelivr.net/npm/world-atlas@2/countries-50m.json
```

Three details worth knowing if you change it. Russia and Fiji cross the **180th
meridian**, so their rings jump from +179 to -179 longitude; projected naively that
draws a straight line back across the entire map, which is exactly what it did the
first time. `split_antimeridian()` cuts each ring at the crossing and closes both
halves along the meridian. Russia legitimately appears on both edges of the map as
a result, the same as on any world map centred on Greenwich. Simplifying a **closed ring** with plain
RDP collapses it to two points — first and last are the same, so the baseline has
zero length and every perpendicular distance computes as zero; `simplify()` splits
each ring at its farthest point instead. And city-states project to **under a pixel**
at this width, so any country whose shape is smaller than 6px gets drawn as a
circular marker at its projected centre rather than being invisible.

## The caveat that matters

**Country here means where a company is listed, not where it earns.** Shell is
British-listed but sells oil worldwide; TSMC is Taiwanese-listed and sells to
everyone. So "61% United States" describes where the shares trade, not where the
economic exposure sits — the true geographic spread is wider than this map shows,
and no holdings file can tell you by how much.

Not investment advice.
