from dataclasses import dataclass


@dataclass
class Verdict:
    name: str
    ok: bool
    measured: float
    threshold: float
    message: str


COURANT_LIMIT = 1.0
RESIDUAL_LIMIT = 1e-5
MESH_DIFF_LIMIT = 0.02
LAMINAR_RE_LIMIT = 1000.0


def reynolds_number(params) -> float:
    return params["lid_speed"] * params["box_size"] / params["nu"]


def check_case_loads(exit_code: int, message: str) -> Verdict:
    return Verdict("case_loads", False, exit_code, 0, message)


def check_courant_pre(params) -> Verdict:
    dx = params["box_size"] / params["cells"]
    co = params["lid_speed"] * params["delta_t"] / dx
    # Upper bound: it assumes every cell moves at the lid speed, which no cell but the top
    # row ever does. Measured max was 0.852 where this estimate reads 1.0, so <= is the
    # correct comparison and still guarantees the real Courant number stays under the limit.
    return Verdict(
        "courant_pre",
        co <= COURANT_LIMIT,
        co,
        COURANT_LIMIT,
        f"estimated Courant {co:.3g} (upper bound) from U={params['lid_speed']}, "
        f"dt={params['delta_t']}, {params['cells']} cells over {params['box_size']} m"
        + ("" if co <= COURANT_LIMIT else ". Lower deltaT or coarsen the mesh."),
    )


def check_regime(params) -> Verdict:
    reynolds = reynolds_number(params)
    ok = reynolds < LAMINAR_RE_LIMIT or params["simulation_type"] != "laminar"
    return Verdict(
        "regime",
        ok,
        reynolds,
        LAMINAR_RE_LIMIT,
        f"Re = {reynolds:.4g} with simulationType {params['simulation_type']}"
        + ("" if ok else f". Above Re {LAMINAR_RE_LIMIT:.0f} the flow is not laminar, so this "
                         "case models the wrong physics and nothing in the log will say so."),
    )


def check_courant_post(courant_values) -> Verdict:
    worst = max(courant_values) if courant_values else 0.0
    return Verdict(
        "courant_post",
        worst < COURANT_LIMIT,
        worst,
        COURANT_LIMIT,
        f"maximum Courant over the run was {worst:.3g}"
        + ("" if worst < COURANT_LIMIT else ". Above 1 the scheme stays stable but the transient "
                                            "is no longer accurate, and the run still exits 0."),
    )


def check_steady(residuals) -> Verdict:
    worst = max(residuals.values()) if residuals else 1.0
    return Verdict(
        "steady",
        worst < RESIDUAL_LIMIT,
        worst,
        RESIDUAL_LIMIT,
        f"largest initial residual at the final time step was {worst:.3g}"
        + ("" if worst < RESIDUAL_LIMIT else ". The solution is still changing: either the run "
                                             "was too short, or the flow never settles."),
    )


def check_mesh_independent(rows_coarse, rows_fine, lid_speed) -> Verdict:
    def distance_and_ux(rows):
        return [(row[0], row[1]) for row in rows]

    def interpolate_ux_at(profile, distance):
        for (near, u_near), (far, u_far) in zip(profile, profile[1:]):
            if near <= distance <= far:
                if far == near:
                    return u_near
                return u_near + (u_far - u_near) * (distance - near) / (far - near)
        return profile[-1][1]

    coarse = distance_and_ux(rows_coarse)
    fine = distance_and_ux(rows_fine)
    worst = max(abs(interpolate_ux_at(coarse, d) - u) for d, u in fine) / lid_speed
    return Verdict(
        "mesh_independent",
        worst < MESH_DIFF_LIMIT,
        worst,
        MESH_DIFF_LIMIT,
        f"centreline profiles differ by {worst * 100:.1f}% of the lid speed between the two meshes"
        + ("" if worst < MESH_DIFF_LIMIT else ". The answer still moves with the mesh, so it is "
                                              "not converged in space; refine and repeat."),
    )
