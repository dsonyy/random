#!/usr/bin/env python3
"""Replace the Clawd mascot in the Claude Code welcome header with the Conduct logo.

Usage:
  patch_logo.py [BINARY]            patch (default: the binary ~/.local/bin/claude points to)
  patch_logo.py --restore [BINARY]  put Clawd back

Run it again after every Claude Code update.
"""

import json
import os
import platform
import re
import struct
import subprocess
import sys
from pathlib import Path

BLANK = "⠀"

LOGO = {
    " ▐": BLANK + "▄",
    "▛███▛█": "▄███▀▀",
    "▝▜": "▀█",
    "█████": "███▄" + BLANK,
    "█▀": BLANK + BLANK,
    " ▝▝   ▝▝ ": BLANK * 3 + "▀▀▀▀▀" + BLANK,
}


# Bun's bytecode keeps string constants as [u32 length][u32 hash][UTF-16LE data].
def entry_pattern(text):
    return re.compile(
        re.escape(struct.pack("<I", len(text))) + b".{4}" + re.escape(text.encode("utf-16-le")),
        re.DOTALL,
    )


def swap(data, old, new):
    matches = list(entry_pattern(old).finditer(data))
    if len(matches) != 1:
        sys.exit(f"Expected one entry for {old!r}, found {len(matches)}. This Claude Code version is not supported.")
    start = matches[0].start() + 8
    encoded = new.encode("utf-16-le")
    data[start : start + len(encoded)] = encoded

def binary_version(binary):
    output = subprocess.run([str(binary), "--version"], capture_output=True, text=True, check=True).stdout
    return output.split()[0]


def skip_entrance_animation(version):
    config_dir = os.environ.get("CLAUDE_CONFIG_DIR")
    config = Path(config_dir) / ".claude.json" if config_dir else Path.home() / ".claude.json"
    if not config.exists():
        return
    settings = json.loads(config.read_text())
    if settings.get("lastClawdEntranceVersion") == version:
        return
    settings["lastClawdEntranceVersion"] = version
    temporary = config.with_suffix(".json.logo-tmp")
    temporary.write_text(json.dumps(settings, indent=2, ensure_ascii=False))
    os.replace(temporary, config)


def main():
    args = sys.argv[1:]
    restore = "--restore" in args
    args = [arg for arg in args if arg != "--restore"]
    binary = Path(args[0] if args else Path.home() / ".local/bin/claude").resolve()
    mapping = {new: old for old, new in LOGO.items()} if restore else LOGO

    data = bytearray(binary.read_bytes())
    if all(entry_pattern(new).search(data) for new in mapping.values()):
        print(f"{binary} is already {'restored' if restore else 'patched'}.")
    else:
        for old, new in mapping.items():
            swap(data, old, new)
        patched = binary.with_name(binary.name + ".logo-tmp")
        patched.write_bytes(data)
        patched.chmod(binary.stat().st_mode)
        if platform.system() == "Darwin":
            subprocess.run(["codesign", "--force", "--sign", "-", str(patched)], check=True, capture_output=True)
        binary_version(patched)
        os.replace(patched, binary)
        print(f"{'Restored' if restore else 'Patched'} {binary}.")

    if not restore:
        skip_entrance_animation(binary_version(binary))


if __name__ == "__main__":
    main()
