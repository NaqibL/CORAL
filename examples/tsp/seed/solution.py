"""Berlin52 TSP — nearest-neighbour baseline.

run() returns a tour as a list of 52 city indices (0-indexed), each appearing exactly once.
The tour is implicitly closed: the last city connects back to city 0.
"""

import math

# Berlin52 city coordinates (0-indexed). Source: TSPLIB.
CITIES = [
    (565.0, 575.0),  # 0
    (25.0, 185.0),   # 1
    (345.0, 750.0),  # 2
    (945.0, 685.0),  # 3
    (845.0, 655.0),  # 4
    (880.0, 660.0),  # 5
    (25.0, 230.0),   # 6
    (525.0, 1000.0), # 7
    (580.0, 1175.0), # 8
    (650.0, 1130.0), # 9
    (1605.0, 620.0), # 10
    (1220.0, 580.0), # 11
    (1465.0, 200.0), # 12
    (1530.0, 5.0),   # 13
    (845.0, 680.0),  # 14
    (725.0, 370.0),  # 15
    (145.0, 665.0),  # 16
    (415.0, 635.0),  # 17
    (510.0, 875.0),  # 18
    (560.0, 365.0),  # 19
    (300.0, 465.0),  # 20
    (520.0, 585.0),  # 21
    (480.0, 415.0),  # 22
    (835.0, 625.0),  # 23
    (975.0, 580.0),  # 24
    (1215.0, 245.0), # 25
    (1320.0, 315.0), # 26
    (1250.0, 400.0), # 27
    (660.0, 180.0),  # 28
    (410.0, 250.0),  # 29
    (420.0, 555.0),  # 30
    (575.0, 665.0),  # 31
    (1150.0, 1160.0),# 32
    (700.0, 580.0),  # 33
    (685.0, 595.0),  # 34
    (685.0, 610.0),  # 35
    (770.0, 610.0),  # 36
    (795.0, 645.0),  # 37
    (720.0, 635.0),  # 38
    (760.0, 650.0),  # 39
    (475.0, 960.0),  # 40
    (95.0, 260.0),   # 41
    (875.0, 920.0),  # 42
    (700.0, 500.0),  # 43
    (555.0, 815.0),  # 44
    (830.0, 485.0),  # 45
    (1170.0, 65.0),  # 46
    (830.0, 610.0),  # 47
    (605.0, 625.0),  # 48
    (595.0, 360.0),  # 49
    (1340.0, 725.0), # 50
    (1740.0, 245.0), # 51
]

N = len(CITIES)


def _dist(a: int, b: int) -> float:
    ax, ay = CITIES[a]
    bx, by = CITIES[b]
    return math.sqrt((ax - bx) ** 2 + (ay - by) ** 2)


def _nearest_neighbour(start: int = 0) -> list[int]:
    unvisited = set(range(N))
    tour = [start]
    unvisited.remove(start)
    while unvisited:
        last = tour[-1]
        nearest = min(unvisited, key=lambda c: _dist(last, c))
        tour.append(nearest)
        unvisited.remove(nearest)
    return tour


def run() -> list[int]:
    return _nearest_neighbour(start=0)
