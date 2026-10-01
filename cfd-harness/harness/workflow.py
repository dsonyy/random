from dataclasses import asdict, dataclass, field
from pathlib import Path

from . import checks
from . import openfoam_client


@dataclass
class Session:
    root: Path
    params: dict
    case_dir: Path | None = None
    results: dict = field(default_factory=dict)
    verdicts: list[checks.Verdict] = field(default_factory=list)
    failed_check: checks.Verdict | None = None
    user_was_asked: bool = False
    finished: bool = False


class CheckFailed(Exception):
    def __init__(self, verdict):
        super().__init__(verdict.message)
        self.verdict = verdict


def checks_before_solving(params: dict) -> list[checks.Verdict]:
    return [checks.check_courant_pre(params), checks.check_regime(params)]


def checks_after_solving(log: str) -> list[checks.Verdict]:
    return [
        checks.check_courant_post(openfoam_client.parse_courant_numbers(log)),
        checks.check_steady(openfoam_client.parse_residuals_at_final_step(log)),
    ]


def stop_if_any_check_failed(session: Session, verdicts, stage: str) -> None:
    for verdict in verdicts:
        session.verdicts.append(verdict)
        print(f"[{stage}] {verdict.name}={verdict.measured:.4g} "
              f"limit={verdict.threshold:.4g} {'ok' if verdict.ok else 'FAILED'}")
    for verdict in verdicts:
        if not verdict.ok:
            raise CheckFailed(verdict)


def run_openfoam(session: Session, case_dir: Path, command: str, stage: str) -> str:
    code, log = openfoam_client.run_command(case_dir, command)
    print(f"[{stage}] {command.split()[0]} exit={code}")
    if code != 0:
        message = openfoam_client.find_fatal_error(log) or log[-400:]
        stop_if_any_check_failed(session, [checks.check_case_loads(code, message)], stage)
    return log


def solve(session: Session, case_dir: Path, solver: str, stage: str) -> None:
    log = run_openfoam(session, case_dir, solver, stage)
    stop_if_any_check_failed(session, checks_after_solving(log), stage)


def sample_centreline(session: Session, case_dir: Path, stage: str):
    run_openfoam(session, case_dir, "postProcess -func centreline -latestTime", stage)
    samples = sorted(case_dir.glob("postProcessing/centreline/*/line_U.xy"))
    return openfoam_client.read_sampled_profile(samples[-1]) if samples else None


def twice_the_mesh(params: dict) -> dict:
    """Half the time step needs twice the steps to cover the same span."""
    finer = dict(params, cells=params["cells"] * 2, delta_t=params["delta_t"] / 2)
    for name in ("end_time", "write_interval"):
        if name in params:
            finer[name] = params[name] * 2
    return finer


def run_tutorial_once(session: Session) -> dict:
    params = openfoam_client.case_params(session.params)
    stop_if_any_check_failed(session, checks_before_solving(params), "pre")

    coarse_dir = session.root / "coarse"
    openfoam_client.write_case(session.case_dir, coarse_dir, params)
    run_openfoam(session, coarse_dir, "blockMesh", "coarse")
    solve(session, coarse_dir, params["application"], "coarse")

    fine_params = twice_the_mesh(params)
    fine_dir = session.root / "fine"
    openfoam_client.write_case(session.case_dir, fine_dir, fine_params)
    run_openfoam(session, fine_dir, "blockMesh", "fine")
    run_openfoam(session, fine_dir,
                 "mapFields ../coarse -consistent -sourceTime latestTime", "fine")
    solve(session, fine_dir, fine_params["application"], "fine")

    coarse_profile = sample_centreline(session, coarse_dir, "coarse")
    fine_profile = sample_centreline(session, fine_dir, "fine")
    mesh_verdict = checks.check_mesh_independent(coarse_profile, fine_profile,
                                                 params["lid_speed"])
    session.results = {
        "params": dict(params),
        "reynolds": checks.reynolds_number(params),
        "coarse_profile": coarse_profile,
        "fine_profile": fine_profile,
        "mesh_independent": asdict(mesh_verdict),
    }
    stop_if_any_check_failed(session, [mesh_verdict], "compare")
    print("[done] all checks passed")
    return session.results
