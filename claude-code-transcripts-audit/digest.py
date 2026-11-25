#!/usr/bin/env python3
"""Reduce Claude Code session transcripts (JSONL) to readable digests plus CSV tables.

usage: digest.py OUT_DIR TRANSCRIPT_DIR [TRANSCRIPT_DIR ...]
"""
import csv
import json
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

USER_LIMIT = 3000
ASSISTANT_LIMIT = 700
RESULT_LIMIT = 300
COMMAND_LIMIT = 500

TEST_PATTERN = re.compile(
    r"\b(gradlew?|just|pnpm|npm|yarn|vitest|jest|playwright|pytest|bru|biome|tsc|ktlint|detekt|mise)\b"
)


def parse_time(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00")) if value else None


def clip(text, limit):
    text = text if isinstance(text, str) else json.dumps(text, ensure_ascii=False)
    text = text.strip()
    return text if len(text) <= limit else f"{text[:limit]} ...[+{len(text) - limit} chars]"


def result_text(content):
    if isinstance(content, str):
        return content
    parts = []
    for block in content or []:
        if block.get("type") == "text":
            parts.append(block.get("text", ""))
        else:
            parts.append(f"[{block.get('type')}]")
    return "\n".join(parts)


def describe_tool(name, tool_input):
    if name == "Bash":
        return clip(tool_input.get("command", ""), COMMAND_LIMIT)
    if name in ("Edit", "Write", "Read", "NotebookEdit"):
        path = tool_input.get("file_path", "")
        if name == "Edit":
            return f"{path} (-{len(tool_input.get('old_string', ''))} +{len(tool_input.get('new_string', ''))} chars)"
        if name == "Write":
            return f"{path} ({len(tool_input.get('content', ''))} chars)"
        return path
    if name == "Agent":
        return (
            f"[{tool_input.get('subagent_type', 'default')}/{tool_input.get('model', 'inherit')}] "
            f"{tool_input.get('description', '')}: {clip(tool_input.get('prompt', ''), 400)}"
        )
    if name == "Skill":
        return f"{tool_input.get('skill', '')} {clip(tool_input.get('args', '') or '', 200)}"
    return clip(tool_input, 300)


def user_text_kind(text):
    if text.startswith("Base directory for this skill:"):
        return "skill-body"
    if text.startswith("<local-command") or text.startswith("<command-name>"):
        return "local-command"
    if text.startswith("<system-reminder>") or text.startswith("<task-notification>"):
        return "system"
    return "human"


def digest_session(path, out_dir, session_rows, bash_rows):
    events = []
    pending = {}
    meta = {
        "title": "",
        "cwds": Counter(),
        "branches": Counter(),
        "models": Counter(),
        "skills": Counter(),
        "tools": Counter(),
        "prs": set(),
        "cost": None,
    }
    first = last = None
    human_messages = 0
    human_chars = 0
    interruptions = 0

    for line in path.open(errors="replace"):
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        kind = record.get("type")
        if kind == "custom-title":
            meta["title"] = record.get("customTitle", "")
        elif kind == "pr-link":
            meta["prs"].add(record.get("prNumber"))
        elif kind == "cost-state":
            meta["cost"] = record.get("totalCostUSD")
        if kind not in ("user", "assistant"):
            continue

        when = parse_time(record.get("timestamp"))
        if when:
            first = first or when
            last = when
        if record.get("cwd"):
            meta["cwds"][record["cwd"]] += 1
        if record.get("gitBranch"):
            meta["branches"][record["gitBranch"]] += 1
        message = record.get("message") or {}
        content = message.get("content")
        stamp = when.strftime("%m-%d %H:%M:%S") if when else "?"

        if kind == "assistant":
            if message.get("model"):
                meta["models"][message["model"]] += 1
            for block in content if isinstance(content, list) else []:
                if block.get("type") == "text" and block.get("text", "").strip():
                    events.append(f"[{stamp}] ASSISTANT: {clip(block['text'], ASSISTANT_LIMIT)}")
                elif block.get("type") == "tool_use":
                    name = block.get("name", "")
                    tool_input = block.get("input") or {}
                    meta["tools"][name] += 1
                    if name == "Skill":
                        meta["skills"][tool_input.get("skill", "")] += 1
                    pending[block.get("id")] = (len(events), name, tool_input, when)
                    events.append(f"[{stamp}] TOOL {name}: {describe_tool(name, tool_input)}")
            continue

        blocks = content if isinstance(content, list) else [{"type": "text", "text": content or ""}]
        for block in blocks:
            block_type = block.get("type")
            if block_type == "tool_result":
                call = pending.pop(block.get("tool_use_id"), None)
                if not call:
                    continue
                index, name, tool_input, started = call
                seconds = (when - started).total_seconds() if when and started else 0
                text = result_text(block.get("content"))
                failed = bool(block.get("is_error"))
                events[index] += (
                    f"\n    -> {seconds:.0f}s{' ERROR' if failed else ''}: {clip(text, RESULT_LIMIT)}"
                )
                if name == "Bash":
                    command = tool_input.get("command", "")
                    bash_rows.append(
                        {
                            "session": path.stem,
                            "started": started.isoformat() if started else "",
                            "seconds": round(seconds),
                            "background": bool(tool_input.get("run_in_background")),
                            "error": failed,
                            "looks_like_build_or_test": bool(TEST_PATTERN.search(command)),
                            "command": command[:1500],
                        }
                    )
            elif block_type == "text":
                text = block.get("text", "")
                text_kind = user_text_kind(text)
                if text_kind == "skill-body":
                    events.append(f"[{stamp}] SKILL BODY LOADED: {text.splitlines()[0]}")
                elif text_kind == "local-command":
                    events.append(f"[{stamp}] LOCAL COMMAND: {clip(text, 200)}")
                elif text_kind == "system":
                    events.append(f"[{stamp}] SYSTEM NOTE: {clip(text, 200)}")
                elif text.strip():
                    if "[Request interrupted" in text:
                        interruptions += 1
                    if not record.get("isMeta"):
                        human_messages += 1
                        human_chars += len(text)
                    events.append(f"[{stamp}] USER: {clip(text, USER_LIMIT)}")
            elif block_type == "image":
                events.append(f"[{stamp}] USER: [image]")

    if not first:
        return
    minutes = (last - first).total_seconds() / 60
    header = [
        f"# session {path.stem}",
        f"file: {path}",
        f"title: {meta['title']}",
        f"start: {first.isoformat()}  end: {last.isoformat()}  wall: {minutes:.0f} min",
        f"cwd: {dict(meta['cwds'].most_common(4))}",
        f"branches: {dict(meta['branches'].most_common(6))}",
        f"models: {dict(meta['models'])}",
        f"skills: {dict(meta['skills'])}",
        f"tools: {dict(meta['tools'].most_common())}",
        f"prs: {sorted(p for p in meta['prs'] if p)}",
        f"human messages: {human_messages} ({human_chars} chars), interruptions: {interruptions}",
        f"cost usd: {meta['cost']}",
        "",
    ]
    (out_dir / f"{first.strftime('%m%d-%H%M')}_{path.stem[:8]}.md").write_text(
        "\n".join(header + events) + "\n"
    )
    session_rows.append(
        {
            "session": path.stem,
            "source": str(path.parent),
            "title": meta["title"],
            "start": first.isoformat(),
            "end": last.isoformat(),
            "wall_min": round(minutes),
            "top_cwd": meta["cwds"].most_common(1)[0][0] if meta["cwds"] else "",
            "branches": "|".join(meta["branches"]),
            "models": "|".join(meta["models"]),
            "skills": "|".join(f"{k}:{v}" for k, v in meta["skills"].items()),
            "tool_calls": sum(meta["tools"].values()),
            "bash": meta["tools"]["Bash"],
            "edits": meta["tools"]["Edit"] + meta["tools"]["Write"],
            "agents": meta["tools"]["Agent"],
            "human_messages": human_messages,
            "human_chars": human_chars,
            "interruptions": interruptions,
            "prs": "|".join(str(p) for p in sorted(p for p in meta["prs"] if p)),
            "cost_usd": meta["cost"],
            "digest_chars": sum(len(e) for e in events),
        }
    )


def write_csv(path, rows):
    if not rows:
        return
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main():
    out_dir = Path(sys.argv[1])
    session_rows, bash_rows = [], []
    for source in sys.argv[2:]:
        source = Path(source)
        for group, pattern in (("sessions", "*.jsonl"), ("subagents", "*/subagents/*.jsonl")):
            target = out_dir / group
            target.mkdir(parents=True, exist_ok=True)
            for path in sorted(source.glob(pattern)):
                digest_session(path, target, session_rows if group == "sessions" else [], bash_rows)
    write_csv(out_dir / "sessions.csv", sorted(session_rows, key=lambda row: row["start"]))
    write_csv(out_dir / "bash.csv", sorted(bash_rows, key=lambda row: row["started"]))
    print(f"{len(session_rows)} sessions, {len(bash_rows)} bash calls -> {out_dir}")


if __name__ == "__main__":
    main()
