import re
import shutil
import subprocess
from pathlib import Path

RESOURCES = Path(__file__).parent.parent / "resources"

# A case with no turbulenceProperties is laminar.
DEFAULTS = {
    "simulation_type": "laminar",
    "fields": {},
}

SKIP_WHEN_COPYING = ("postProcessing",)


def run_command(case_dir: Path, command: str, keep_log: bool = True) -> tuple[int, str]:
    finished = subprocess.run(command, shell=True, cwd=case_dir, capture_output=True, text=True)
    log = finished.stdout + finished.stderr
    if keep_log:
        (case_dir / f"log.{command.split()[0]}").write_text(log)
    return finished.returncode, log


def case_params(params: dict) -> dict:
    return {**DEFAULTS, **params}


def set_entry(case_dir: Path, dictionary: str, entry: str, value) -> None:
    run_command(case_dir, f"foamDictionary {dictionary} -entry {entry} -set '{value}'",
                keep_log=False)


def read_entry(case_dir: Path, dictionary: str, entry: str) -> str | None:
    code, out = run_command(case_dir, f"foamDictionary {dictionary} -entry {entry} -value",
                            keep_log=False)
    return out.strip() if code == 0 else None


def copy_case(source: Path, dest: Path) -> None:
    """The person's case, minus anything a previous run left behind."""
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    for item in source.iterdir():
        if (item.name in SKIP_WHEN_COPYING or item.name.startswith("log.")
                or item.name.startswith("run-")):
            continue
        if item.is_dir() and item.name != "0" and _is_a_time(item.name):
            continue
        (shutil.copytree if item.is_dir() else shutil.copy)(item, dest / item.name)


def _is_a_time(name: str) -> bool:
    try:
        float(name)
    except ValueError:
        return False
    return True


def write_case(source: Path, dest: Path, params: dict) -> None:
    """Copy the person's case and apply what the model changed. Their case is never touched."""
    params = case_params(params)
    copy_case(source, dest)
    shutil.copy(RESOURCES / "centreline", dest / "system" / "centreline")

    control = {"application": "application", "delta_t": "deltaT", "end_time": "endTime",
               "write_interval": "writeInterval", "start_from": "startFrom"}
    for name, entry in control.items():
        if name in params:
            set_entry(dest, "system/controlDict", entry, params[name])
    if "nu" in params:
        set_entry(dest, "constant/transportProperties", "nu", params["nu"])
    if "cells" in params:
        set_entry(dest, "system/blockMeshDict", "blocks",
                  with_cell_count(read_entry(dest, "system/blockMeshDict", "blocks"),
                                  params["cells"]))

    turbulence = dest / "constant" / "turbulenceProperties"
    if params.get("simulation_type") == "RAS":
        # A laminar case has no discretisation entries for k and epsilon, so the solver refuses
        # to start. These come from OpenFOAM's own turbulent cavity tutorial.
        for name in ("fvSchemes", "fvSolution"):
            shutil.copy(RESOURCES / name, dest / "system" / name)
        turbulence.write_text(
            "FoamFile\n{\n    version 2.0;\n    format ascii;\n    class dictionary;\n"
            "    object turbulenceProperties;\n}\n\nsimulationType RAS;\n\nRAS\n{\n"
            f"    RASModel {params.get('ras_model', 'kEpsilon')};\n"
            "    turbulence on;\n    printCoeffs on;\n}\n")
        set_entry(dest, "constant/transportProperties", "transportModel", "Newtonian")
    elif params.get("simulation_type") == "laminar" and turbulence.exists():
        set_entry(dest, "constant/turbulenceProperties", "simulationType", "laminar")

    for name, spec in params["fields"].items():
        write_field(dest, name, **spec)


def with_cell_count(blocks: str | None, cells: int) -> str:
    """Replace the cell counts inside a block definition, keeping everything else."""
    if not blocks:
        return f"( hex (0 1 2 3 4 5 6 7) ({cells} {cells} 1) simpleGrading (1 1 1) )"
    return re.sub(r"\(\s*\d+\s+\d+\s+(\d+)\s*\)",
                  lambda m: f"({cells} {cells} {m.group(1)})", blocks, count=1)


FIELD = """FoamFile
{{
    version     2.0;
    format      ascii;
    class       {cls};
    object      {name};
}}

dimensions      {dimensions};

internalField   uniform {internal_value};

boundaryField
{{
{boundary_conditions}
}}
"""


def write_field(case_dir: Path, name: str, dimensions: str, internal_value: str,
                boundary_conditions: dict) -> None:
    patches = ""
    for patch, entries in boundary_conditions.items():
        patches += f"    {patch}\n    {{\n"
        for key, value in entries.items():
            patches += f"        {key} {value};\n"
        patches += "    }\n"
    (case_dir / "0" / name).write_text(FIELD.format(
        cls="volVectorField" if internal_value.startswith("(") else "volScalarField",
        name=name,
        dimensions=dimensions,
        internal_value=internal_value,
        boundary_conditions=patches.rstrip(),
    ))


def find_fatal_error(log: str) -> str | None:
    lines = log.splitlines()
    for index, line in enumerate(lines):
        if "FOAM FATAL" in line:
            return " ".join(lines[index:index + 4]).strip()
    return None


def parse_courant_numbers(log: str) -> list[float]:
    return [float(v) for v in re.findall(r"Courant Number mean: \S+ max: ([\d.eE+-]+)", log)]


def parse_residuals_at_final_step(log: str) -> dict[str, float]:
    blocks = re.split(r"^Time = ", log, flags=re.MULTILINE)
    residuals = {}
    for field, value in re.findall(
        r"Solving for (\w+), Initial residual = ([\d.eE+-]+)", blocks[-1]
    ):
        residuals.setdefault(field, float(value))
    return residuals


def measure_box(case_dir: Path) -> float | None:
    """The longest side of the mesh, in metres."""
    scale = read_entry(case_dir, "system/blockMeshDict", "scale")
    vertices = read_entry(case_dir, "system/blockMeshDict", "vertices")
    if not vertices:
        return None
    points = [tuple(float(v) for v in point.split())
              for point in re.findall(r"\(([^()]+)\)", vertices)]
    if not points:
        return None
    spans = [max(p[axis] for p in points) - min(p[axis] for p in points) for axis in (0, 1)]
    return max(spans) * (float(scale) if scale else 1.0)


def measure_lid_speed(case_dir: Path) -> float | None:
    """The fastest velocity any boundary is held at."""
    boundary = read_entry(case_dir, "0/U", "boundaryField")
    if not boundary:
        return None
    speeds = []
    for vector in re.findall(r"uniform\s*\(([^()]+)\)", boundary):
        components = [float(v) for v in vector.split()]
        speeds.append(sum(c * c for c in components) ** 0.5)
    return max(speeds) if speeds else None


def read_parameters_from_case(case_dir: Path) -> dict:
    blocks = read_entry(case_dir, "system/blockMeshDict", "blocks")
    cells = re.search(r"\(\s*(\d+)\s+\d+\s+\d+\s*\)", blocks or "")
    numbers = {"nu": read_entry(case_dir, "constant/transportProperties", "nu"),
               "delta_t": read_entry(case_dir, "system/controlDict", "deltaT"),
               "end_time": read_entry(case_dir, "system/controlDict", "endTime"),
               "write_interval": read_entry(case_dir, "system/controlDict", "writeInterval")}
    found = {name: float(value) for name, value in numbers.items() if value}
    if "write_interval" in found:
        found["write_interval"] = int(found["write_interval"])
    if cells:
        found["cells"] = int(cells.group(1))
    if application := read_entry(case_dir, "system/controlDict", "application"):
        found["application"] = application
    if simulation := read_entry(case_dir, "constant/turbulenceProperties", "simulationType"):
        found["simulation_type"] = simulation
    # Both of these are read from the case rather than assumed: every check that involves a
    # speed or a length is wrong by exactly as much as these are.
    if (box := measure_box(case_dir)) is not None:
        found["box_size"] = box
    if (lid := measure_lid_speed(case_dir)) is not None:
        found["lid_speed"] = lid
    return found


def read_sampled_profile(path: Path) -> list[tuple[float, ...]]:
    rows = []
    for line in path.read_text().splitlines():
        if line.strip() and not line.startswith("#"):
            rows.append(tuple(float(v) for v in line.split()))
    return rows
