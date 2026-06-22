"""TSP pr1002 grader.

Evaluates programs that solve the pr1002 TSP instance.
The program file must define a run() function returning a list of 1002 integers —
a permutation of [0..1001] representing the order cities are visited.
Distances are TSPLIB EUC_2D: nint(sqrt((x1-x2)^2 + (y1-y2)^2)).
Score = 259045 / tour_length (higher is better; 1.0 matches the known optimum).
"""

from __future__ import annotations

import json
import math
import subprocess
import textwrap
import urllib.request
from pathlib import Path

from coral.grader import TaskGrader
from coral.types import ScoreBundle

OPTIMAL = 259045
N = 1002
DATA_URL = "http://comopt.ifi.uni-heidelberg.de/software/TSPLIB95/tsp/pr1002.tsp"
_TASKDATA = Path(__file__).parent / "taskdata"
_DATA_FILE = _TASKDATA / "pr1002.tsp"


def _ensure_data() -> None:
    _TASKDATA.mkdir(exist_ok=True)
    if not _DATA_FILE.exists():
        urllib.request.urlretrieve(DATA_URL, _DATA_FILE)


def _parse_tsp(path: Path) -> list[tuple[float, float]]:
    cities: list[tuple[float, float]] = []
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


class Grader(TaskGrader):
    def evaluate(self) -> ScoreBundle:
        try:
            _ensure_data()
            cities = _parse_tsp(_DATA_FILE)
        except Exception as e:
            return self.fail(f"Failed to load pr1002 data: {e}")

        program_file = self.args.get("program_file", "solution.py")
        import os
        program_path = os.path.join(self.codebase_path, program_file)

        if not os.path.exists(program_path):
            return self.fail(f"Program file not found: {program_file}")

        cities_repr = repr(cities)
        script = textwrap.dedent(f"""\
            import json, sys, os, math, urllib.request
            from pathlib import Path

            N = {N}
            OPTIMAL = {OPTIMAL}

            # Ensure data file exists in codebase for the solution to use
            data_dir = Path({str(self.codebase_path)!r}) / "data"
            data_dir.mkdir(exist_ok=True)
            data_file = data_dir / "pr1002.tsp"
            if not data_file.exists():
                urllib.request.urlretrieve({DATA_URL!r}, data_file)

            sys.path.insert(0, os.path.dirname({os.path.abspath(program_path)!r}))
            module_name = {os.path.splitext(os.path.basename(program_path))[0]!r}
            program = __import__(module_name)

            try:
                tour = program.run()
            except Exception as e:
                print(json.dumps({{"error": f"run() raised: {{e}}"}}))
                sys.exit(0)

            if not isinstance(tour, (list, tuple)) or len(tour) != N:
                print(json.dumps({{"error": f"run() must return a list of {{N}} ints, got length {{len(tour) if hasattr(tour, '__len__') else '?'}}"}}))
                sys.exit(0)

            tour = [int(c) for c in tour]
            if sorted(tour) != list(range(N)):
                missing = sorted(set(range(N)) - set(tour))
                duplicates = [c for c in set(tour) if tour.count(c) > 1]
                print(json.dumps({{"error": f"Invalid tour. Missing: {{missing[:5]}}. Duplicates: {{duplicates[:5]}}"}}))
                sys.exit(0)

            CITIES = {cities_repr}

            def dist(a, b):
                ax, ay = CITIES[a]
                bx, by = CITIES[b]
                return round(math.sqrt((ax - bx)**2 + (ay - by)**2))

            length = sum(dist(tour[i], tour[(i + 1) % N]) for i in range(N))
            print(json.dumps({{"tour_length": length}}))
        """)

        try:
            result = subprocess.run(
                [*self.get_python_command(), "-c", script],
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )
        except subprocess.TimeoutExpired:
            return self.fail(f"Evaluation timed out after {self.timeout}s")
        except Exception as e:
            return self.fail(f"Evaluation failed: {e}")

        if result.returncode != 0:
            return self.fail(result.stderr.strip()[-2000:])

        stdout = result.stdout.strip()
        if not stdout:
            return self.fail(f"Script produced no output.\nstderr: {result.stderr.strip()[-1000:]}")

        try:
            data = json.loads(stdout)
        except json.JSONDecodeError:
            for line in reversed(stdout.splitlines()):
                line = line.strip()
                if line.startswith("{"):
                    try:
                        data = json.loads(line)
                        break
                    except json.JSONDecodeError:
                        continue
            else:
                return self.fail(f"No valid JSON in output.\nstdout: {stdout[-500:]}")

        if "error" in data:
            return self.fail(data["error"])

        tour_length = data["tour_length"]
        score = OPTIMAL / tour_length
        explanation = (
            f"Tour length: {tour_length} | "
            f"Score: {score:.6f} | "
            f"Optimal: {OPTIMAL}"
        )
        return self.score(score, explanation)
