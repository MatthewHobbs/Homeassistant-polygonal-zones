"""Architecture smoke check for the shapely native dependency.

Run inside a per-architecture container by .github/workflows/multi-arch.yml to
prove that shapely (the integration's only non-pure-Python runtime requirement,
a C extension over GEOS) resolves an installable wheel and that its geometry
operations actually work on the target architecture.

Kept deliberately free of any ``homeassistant`` import so it stays fast under
QEMU emulation — the pure-Python integration code is architecture-independent;
shapely's compiled wheel is the only thing that can differ across arches.
"""

import shapely
from shapely.geometry import Point, Polygon

square = Polygon([(0, 0), (0, 2), (2, 2), (2, 0)])
assert square.contains(Point(1, 1)), "point inside the polygon should be contained"
assert not square.contains(Point(3, 3)), "point outside the polygon should not be contained"

print(f"shapely {shapely.__version__} import + geometry OK")
