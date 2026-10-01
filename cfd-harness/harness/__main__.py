import shutil
import sys
from pathlib import Path

from . import openfoam_client, workflow
from .harness import anthropic_client, talk


def main() -> None:
    if shutil.which("blockMesh") is None:
        sys.exit("OpenFOAM is not on PATH. Source its bashrc first, for example:\n"
                 "  source /usr/lib/openfoam/openfoam2412/etc/bashrc")

    case_dir = Path.cwd()
    if not (case_dir / "system").is_dir():
        sys.exit(f"{case_dir} is not an OpenFOAM case: no system directory. "
                 "Run this from inside the case you want to work on.")

    api = anthropic_client()
    params = openfoam_client.read_parameters_from_case(case_dir)
    described = ", ".join(f"{name} {value}" for name, value in params.items())
    print(f"case: {case_dir}\n{described}")
    session = workflow.Session(root=Path(), params=params, case_dir=case_dir)
    messages = []

    print("OpenFOAM cavity harness. Describe what you want computed, or 'q' to quit.")
    while True:
        try:
            question = input("\n> ").strip()
        except EOFError:
            return
        if question in {"q", "quit", "exit"}:
            return
        if not question:
            continue

        talk(api, session, messages, question)


if __name__ == "__main__":
    main()
