"""Clip geoBoundaries ADM1 (India, Pakistan) to the map window as compact polylines: site/borders.json"""
import json

W, S, E, N = 71.0, 26.0, 81.0, 34.0
out = []
for c in ("IND", "PAK"):
    for f in json.load(open(f"data/geo/{c}.geojson"))["features"]:
        g = f["geometry"]
        polys = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
        for poly in polys:
            for ring in poly:
                if any(W - 1 < x < E + 1 and S - 1 < y < N + 1 for x, y in ring):
                    out.append({"name": f["properties"]["shapeName"], "c": c,
                                "p": [[round(x, 3), round(y, 3)] for x, y in ring[::2]]})
json.dump(out, open("site/borders.json", "w"), separators=(",", ":"))
print(len(out), "rings", sorted({o["name"] for o in out}))
