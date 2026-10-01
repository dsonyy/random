import json
from pathlib import Path

from . import openfoam_client
from . import workflow

# None of these may run while a failed check has not reached the user. Enforced at the
# dispatch point, where the tool name is already known.
SET_TOOLS = frozenset({
    "set_block_mesh_dict",
    "set_control_dict",
    "set_transport_properties",
    "set_turbulence_properties",
    "set_field",
})

MUST_ASK = (
    "Check {name} has failed and you have not asked the user yet. Call ask_user first: say what was "
    "measured, what it means for the physics, and what the options are. Then change the case."
)

def schema(tool_name: str, description: str, /, **properties) -> dict:
    return {
        "name": tool_name,
        "description": description,
        "input_schema": {
            "type": "object",
            "properties": {k: v if isinstance(v, dict) else {"enum": list(v)}
                           for k, v in properties.items()},
            "required": list(properties),
        },
    }


TEXT = {"type": "string"}
NUMBER = {"type": "number"}
COUNT = {"type": "integer"}
MAPPING = {"type": "object"}

SCHEMAS = [
    schema(
        "set_block_mesh_dict",
        "The mesh. 'cells' is the cell count per side of the square cavity. 'grading' is an "
        "OpenFOAM simpleGrading triple written in brackets, '(1 1 1)' for uniform cells and for "
        "example '(2 2 1)' to cluster them towards one side.",
        cells=COUNT, grading=TEXT,
    ),
    schema(
        "set_control_dict",
        "Which solver runs and for how long. icoFoam is transient laminar incompressible; "
        "pisoFoam is transient and takes a turbulence model.",
        application=("icoFoam", "pisoFoam"), delta_t=NUMBER, end_time=NUMBER,
        write_interval=COUNT,
    ),
    schema(
        "set_transport_properties",
        "Kinematic viscosity in m^2/s.",
        nu=NUMBER,
    ),
    schema(
        "set_turbulence_properties",
        "RAS switches on Reynolds averaging and then k, epsilon and nut must exist in 0/.",
        simulation_type=("laminar", "RAS"), ras_model=("kEpsilon", "kOmegaSST"),
    ),
    schema(
        "set_field",
        "One field file in 0/. 'internal_value' is a bare value with no 'uniform' in front of "
        "it, so 0.00375 or (0 0 0). boundary_conditions maps each patch to its entries, for "
        "example "
        '{"movingWall": {"type": "kqRWallFunction", "value": "uniform 0.00375"}}. The square '
        "cavity's patches are movingWall, fixedWalls and frontAndBack, and frontAndBack is "
        "always type empty.",
        name=("U", "p", "k", "epsilon", "nut"), dimensions=TEXT, internal_value=TEXT,
        boundary_conditions=MAPPING,
    ),
    schema(
        "run",
        "Mesh the case, solve it, refine the mesh, solve again, and compare the two centre line "
        "profiles. 'plan' is one sentence saying what is about to be computed: it is shown to "
        "the user, who has to agree before anything starts. Returns what every check measured, "
        "stopping at the first one that failed.",
        plan=TEXT,
    ),
    schema(
        "read_file",
        "Read a file from the case the person brought, to discuss or explain it. Paths are "
        "relative to the case, for example system/controlDict or 0/U.",
        path=TEXT,
    ),
    schema(
        "read_log",
        "Tail of an OpenFOAM log. Only useful after a run, so after a check has failed.",
        utility=TEXT, mesh=("coarse", "fine"), lines=COUNT,
    ),
    schema(
        "ask_user",
        "Stop and ask the person running this. Required whenever a check fails: the write "
        "tools refuse until you have asked.",
        question=TEXT, options={"type": "array", "items": TEXT},
    ),
    schema(
        "done",
        "End the run, once there are results. Report only what the checks measured.",
        summary=TEXT,
    ),
]


def tool_set_block_mesh_dict(session, cells, grading):
    session.params.update(cells=cells, grading=grading)
    return f"mesh set to {cells} cells per side, grading {grading}"


def tool_set_control_dict(session, application, delta_t, end_time, write_interval):
    session.params.update(application=application, delta_t=delta_t, end_time=end_time,
                          write_interval=write_interval)
    return (f"controlDict: {application}, deltaT {delta_t}, endTime {end_time}, "
            f"writeInterval {write_interval}")


def tool_set_transport_properties(session, nu):
    session.params["nu"] = nu
    return f"nu set to {nu}"


def tool_set_turbulence_properties(session, simulation_type, ras_model):
    session.params.update(simulation_type=simulation_type, ras_model=ras_model)
    if simulation_type == "RAS":
        return (f"turbulence set to RAS {ras_model}. The fields k, epsilon and nut must exist "
                "in 0/ or the solver will refuse to start.")
    return "turbulence set to laminar"


def tool_set_field(session, name, dimensions, internal_value, boundary_conditions):
    internal_value = internal_value.removeprefix("uniform ").strip()
    dimensions = dimensions.strip()
    if not dimensions.startswith("["):
        dimensions = f"[{dimensions}]"
    session.params.setdefault("fields", {})[name] = {
        "dimensions": dimensions,
        "internal_value": internal_value,
        "boundary_conditions": boundary_conditions,
    }
    return f"field {name} staged, internalField uniform {internal_value}, dimensions {dimensions}"


def tool_run(session, plan):
    print(f"\n  ? {plan}\n    Enter to run, anything else to stop.")
    answer = input("  > ").strip()
    print()
    if answer:
        return f"the user did not agree and said: {answer}"

    # Not a bare number: OpenFOAM would read 001 in a case directory as a time.
    existing = len(list(session.case_dir.glob("run-*")))
    session.root = session.case_dir / f"run-{existing + 1:03d}"
    session.root.mkdir()
    session.verdicts.clear()
    try:
        results = workflow.run_tutorial_once(session)
    except workflow.CheckFailed as failure:
        session.failed_check = failure.verdict
        session.user_was_asked = False
        verdict = failure.verdict
        return (f"check {verdict.name} FAILED: measured {verdict.measured:.6g} against a limit "
                f"of {verdict.threshold:.6g}. {verdict.message} Nothing after this check ran. "
                "Ask the user before changing anything.")
    session.failed_check = None
    return ("every check passed. " + json.dumps(
        {k: v for k, v in results.items() if "profile" not in k}, default=str))


def tool_read_file(session, path):
    if session.case_dir is None:
        return "no case was given to read; the bundled template is being used instead"
    target = session.case_dir / path
    if not target.is_file():
        listing = ", ".join(sorted(str(f.relative_to(session.case_dir))
                                   for f in session.case_dir.rglob("*") if f.is_file()))
        return f"{path} is not in the case. It holds: {listing}"
    return target.read_text()[:4000]


def tool_read_log(session, utility, mesh, lines):
    path = session.root / mesh / f"log.{utility}"
    if not path.exists():
        return (f"no log.{utility} in the {mesh} case: nothing has run yet. Finish configuring "
                "and stop calling tools, and the workflow will run.")
    return "\n".join(path.read_text().splitlines()[-lines:])


def tool_ask_user(session, question, options):
    session.user_was_asked = True
    print(f"\n  ? {question}")
    for number, option in enumerate(options, 1):
        print(f"    {number}. {option}")
    answer = input("  > ").strip()
    if answer.isdigit() and 1 <= int(answer) <= len(options):
        answer = options[int(answer) - 1]
    print(f"[ask] {question} -> {answer}")
    return answer


def tool_done(session, summary):
    if not session.verdicts:
        session.finished = True
        print(f"[summary] {summary}")
        return "run ended. Nothing was measured, because the workflow never ran."

    session.finished = True
    print(f"[summary] {summary}")
    # The last verdict per check is the current state. A check that failed and then passed on a
    # retry is not still failing.
    latest = {v.name: v for v in session.verdicts}
    failed = sorted(name for name, v in latest.items() if not v.ok)
    return ("run ended. Measured state at the end: "
            + (f"still failing: {', '.join(failed)}" if failed else "all checks green"))


TOOL_FUNCTIONS = {
    "set_block_mesh_dict": tool_set_block_mesh_dict,
    "set_control_dict": tool_set_control_dict,
    "set_transport_properties": tool_set_transport_properties,
    "set_turbulence_properties": tool_set_turbulence_properties,
    "set_field": tool_set_field,
    "run": tool_run,
    "read_file": tool_read_file,
    "read_log": tool_read_log,
    "ask_user": tool_ask_user,
    "done": tool_done,
}
