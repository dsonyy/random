import json
import os
import sys
from pathlib import Path

import anthropic

from . import checks
from . import openfoam_client
from . import workflow
from . import tools

MODEL = "claude-sonnet-5"

SYSTEM = """You set up OpenFOAM cases and supervise the runs, for someone sitting at a terminal
inside their own case.

Write plain sentences. No markdown.

Talk normally and answer questions about the case. Calling no tools is a fine turn. When they
ask for something to be computed, set what their request implies and nothing else, then call run
with one sentence saying what is about to be computed. Run shows that sentence to them and waits
for their agreement, so do not ask separately.

The set tools record what the case should be. Nothing is written to disk and nothing is
solved until you call run. The case already has its fields, so set one only to change it or to
add k, epsilon and nut for a turbulence model.

A run reports what every check measured and stops at the first one that failed. Work out what a
failure means, then ask them what to do before changing anything.

The limits are mine, so you cannot guess them: Courant at most 1 before and below 1 during the
run, Reynolds under 1000 unless a turbulence model is on, the largest initial residual at the
final step below 1e-5, and the two centre line profiles within 2 percent of the lid speed.

Report only what the checks measured. Every verdict so far is listed in each message you get."""


def anthropic_client() -> anthropic.Anthropic:
    for env in (Path.cwd() / ".env", Path(__file__).parent.parent / ".env"):
        if not env.exists():
            continue
        for line in env.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip().strip("\"'"))
    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("ANTHROPIC_API_KEY is not set.")
    return anthropic.Anthropic()


def current_state_message(session) -> str:
    set_so_far = {k: v for k, v in session.params.items() if k != "fields"}
    if fields := sorted(session.params.get("fields", {})):
        set_so_far["fields_written"] = fields
    if not set_so_far:
        block = "Nothing is configured yet and no case exists on disk."
    else:
        block = "What you have set so far:\n" + json.dumps(set_so_far, indent=2)
        if "nu" in session.params:
            block += f"\n\nRe = {checks.reynolds_number(openfoam_client.case_params(session.params)):.4g}"
    if session.verdicts:
        measured = "\n".join(
            f"  {'passed' if v.ok else 'FAILED'} {v.name} = {v.measured:.6g} (limit {v.threshold:.6g})"
            for v in session.verdicts
        )
        block += ("\n\nEvery check measured so far, in order. This is the whole record: "
                  "anything not listed here did not run.\n" + measured)
    return block


def run_model_turn(api, session: workflow.Session, messages: list) -> None:
    while True:
        print()
        with api.messages.stream(
            model=MODEL,
            max_tokens=8000,
            system=SYSTEM,
            tools=tools.SCHEMAS,
            messages=messages,
        ) as stream:
            for piece in stream.text_stream:
                print(piece, end="", flush=True)
            reply = stream.get_final_message()
        print()
        messages.append({"role": "assistant", "content": reply.content})

        # A truncated reply has no complete tool call in it, which is indistinguishable from the
        # model having finished unless the stop reason is checked.
        if reply.stop_reason == "max_tokens":
            print("[warn] reply hit max_tokens and was truncated")
            print("  · reply truncated at max_tokens, asking it to be brief")
            messages.append({"role": "user", "content": (
                "Your reply was cut off by the token limit. Be brief: call the tools you need "
                "with no explanation, one at a time if the arguments are long."
            )})
            continue

        calls = [b for b in reply.content if b.type == "tool_use"]
        if not calls:
            return

        results = []
        for call in calls:
            writes = call.name in tools.SET_TOOLS
            if writes and session.failed_check is not None and not session.user_was_asked:
                output = tools.MUST_ASK.format(name=session.failed_check.name)
            else:
                try:
                    output = tools.TOOL_FUNCTIONS[call.name](session, **call.input)
                except Exception as exc:
                    output = f"{type(exc).__name__}: {exc}"
            summary = output.splitlines()[0] if output else ""
            print(f"[tool] {call.name}" if len(output) > 110 or "\n" in output
                  else f"[tool] {summary}")
            results.append(
                {"type": "tool_result", "tool_use_id": call.id, "content": str(output)}
            )
        messages.append({"role": "user", "content": results})
        if session.finished:
            return


def talk(api, session: workflow.Session, messages: list, question: str) -> None:
    messages.append({"role": "user",
                     "content": f"{question}\n\n{current_state_message(session)}"})
    run_model_turn(api, session, messages)

