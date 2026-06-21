"""TSP Berlin52 grader.

Evaluates programs that solve the Berlin52 TSP instance.
The program file must define a run() function returning a list of 52 integers —
a permutation of [0..51] representing the order cities are visited.
Score = 7542 / tour_length (higher is better; 1.0 matches the known optimum).
"""

from __future__ import annotations

import json
import os
import subprocess
import textwrap

from coral.grader import TaskGrader
from coral.types import ScoreBundle

OPTIMAL = 7542.0
N = 52

# Berlin52 coordinates (TSPLIB, 0-indexed)
CITIES = [
    (565.0, 575.0), (25.0, 185.0), (345.0, 750.0), (945.0, 685.0),
    (845.0, 655.0), (880.0, 660.0), (25.0, 230.0), (525.0, 1000.0),
    (580.0, 1175.0), (650.0, 1130.0), (1605.0, 620.0), (1220.0, 580.0),
    (1465.0, 200.0), (1530.0, 5.0), (845.0, 680.0), (725.0, 370.0),
    (145.0, 665.0), (415.0, 635.0), (510.0, 875.0), (560.0, 365.0),
    (300.0, 465.0), (520.0, 585.0), (480.0, 415.0), (835.0, 625.0),
    (975.0, 580.0), (1215.0, 245.0), (1320.0, 315.0), (1250.0, 400.0),
    (660.0, 180.0), (410.0, 250.0), (420.0, 555.0), (575.0, 665.0),
    (1150.0, 1160.0), (700.0, 580.0), (685.0, 595.0), (685.0, 610.0),
    (770.0, 610.0), (795.0, 645.0), (720.0, 635.0), (760.0, 650.0),
    (475.0, 960.0), (95.0, 260.0), (875.0, 920.0), (700.0, 500.0),
    (555.0, 815.0), (830.0, 485.0), (1170.0, 65.0), (830.0, 610.0),
    (605.0, 625.0), (595.0, 360.0), (1340.0, 725.0), (1740.0, 245.0),
]


class Grader(TaskGrader):
    def evaluate(self) -> ScoreBundle:
        program_file = self.args.get("program_file", "solution.py")
        program_path = os.path.join(self.codebase_path, program_file)

        if not os.path.exists(program_path):
            return self.fail(f"Program file not found: {program_file}")

        try:
            result = _run_evaluation(program_path, self.timeout, self.get_python_command())
        except subprocess.TimeoutExpired:
            return self.fail(f"Evaluation timed out after {self.timeout}s")
        except Exception as e:
            return self.fail(f"Evaluation failed: {e}")

        if "error" in result:
            return self.fail(result["error"])

        tour_length = result["tour_length"]
        score = OPTIMAL / tour_length
        explanation = (
            f"Tour length: {tour_length:.2f} | "
            f"Score: {score:.6f} | "
            f"Optimal: {OPTIMAL:.0f}"
        )
        return self.score(score, explanation)


def _run_evaluation(program_path: str, timeout: int, python_cmd: list[str]) -> dict:
    cities_repr = repr(CITIES)
    script = textwrap.dedent(f"""\
        import json, sys, os, math

        N = {N}
        OPTIMAL = {OPTIMAL!r}
        CITIES = {cities_repr}

        sys.path.insert(0, os.path.dirname({os.path.abspath(program_path)!r}))
        module_name = {os.path.splitext(os.path.basename(program_path))[0]!r}
        program = __import__(module_name)

        try:
            tour = program.run()
        except Exception as e:
            print(json.dumps({{"error": f"run() raised: {{e}}"}}))
            sys.exit(0)

        # Validate
        if not isinstance(tour, (list, tuple)) or len(tour) != N:
            print(json.dumps({{"error": f"run() must return a list of {{N}} ints, got {{type(tour).__name__}} of length {{len(tour) if hasattr(tour, '__len__') else '?'}}"}}))
            sys.exit(0)

        tour = [int(c) for c in tour]
        if sorted(tour) != list(range(N)):
            missing = sorted(set(range(N)) - set(tour))
            duplicates = [c for c in set(tour) if tour.count(c) > 1]
            print(json.dumps({{"error": f"Invalid tour. Missing: {{missing[:5]}}. Duplicates: {{duplicates[:5]}}"}}))
            sys.exit(0)

        def dist(a, b):
            ax, ay = CITIES[a]
            bx, by = CITIES[b]
            return math.sqrt((ax - bx)**2 + (ay - by)**2)

        length = sum(dist(tour[i], tour[(i + 1) % N]) for i in range(N))
        print(json.dumps({{"tour_length": length}}))
    """)

    result = subprocess.run(
        [*python_cmd, "-c", script],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip()[-2000:])
    stdout = result.stdout.strip()
    if not stdout:
        raise RuntimeError(f"Script produced no output.\nstderr: {result.stderr.strip()[-1000:]}")
    try:
        return json.loads(stdout)
    except json.JSONDecodeError:
        for line in reversed(stdout.splitlines()):
            line = line.strip()
            if line.startswith("{"):
                try:
                    return json.loads(line)
                except json.JSONDecodeError:
                    continue
        raise RuntimeError(f"No valid JSON in output.\nstdout: {stdout[-500:]}")
