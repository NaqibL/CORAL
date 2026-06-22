"""pr1002 TSP — nearest-neighbour baseline.

run() returns a tour as a list of 1002 city indices (0-indexed), each appearing exactly once.
The tour is implicitly closed: the last city connects back to city 0.
Distances are TSPLIB EUC_2D: nint(sqrt((x1-x2)^2 + (y1-y2)^2)).
"""

import math
import urllib.request
from pathlib import Path

DATA_URL = "http://comopt.ifi.uni-heidelberg.de/software/TSPLIB95/tsp/pr1002.tsp"
DATA_FILE = Path(__file__).parent / "data" / "pr1002.tsp"


def _ensure_data():
    DATA_FILE.parent.mkdir(exist_ok=True)
    if not DATA_FILE.exists():
        urllib.request.urlretrieve(DATA_URL, DATA_FILE)


def _parse_tsp(path: Path) -> list[tuple[float, float]]:
    cities = []
    reading = False
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line == "NODE_COORD_SECTION":
                reading = True
                continue
            if line == "EOF":
                break
            if reading and line:
                parts = line.split()
                if len(parts) >= 3:
                    cities.append((float(parts[1]), float(parts[2])))
    return cities


def _dist_sq(cities: list, a: int, b: int) -> float:
    ax, ay = cities[a]
    bx, by = cities[b]
    return (ax - bx) ** 2 + (ay - by) ** 2


def _nearest_neighbour(cities: list, start: int = 0) -> list[int]:
    n = len(cities)
    unvisited = set(range(n))
    tour = [start]
    unvisited.remove(start)
    while unvisited:
        last = tour[-1]
        nearest = min(unvisited, key=lambda c: _dist_sq(cities, last, c))
        tour.append(nearest)
        unvisited.remove(nearest)
    return tour


def run() -> list[int]:
    _ensure_data()
    cities = _parse_tsp(DATA_FILE)
    return _nearest_neighbour(cities, start=0)
