#!/usr/bin/env -S uv run -q --script
# /// script
# dependencies = ["rookie-cookies"]
# ///
import csv
import json
import sys
import urllib.request

import rookie_cookies

COLUMNS = ["kind", "title", "places", "url"]

HELP = f"""List all Google Maps saved lists of the account signed in to your browser as CSV to stdout.

Usage: google-maps-lists.py > lists.csv
Feed each url to google-maps-list-export.py to export its places.

Columns: {", ".join(COLUMNS)}"""

COOKIE_HELP = "Sign in at https://www.google.com/maps in your browser and rerun."

# Response index -> kind. The pb sections 23, 24 and 12+38 request own, followed and shared lists.
SECTIONS = {29: "own", 30: "followed", 43: "shared"}
URL = (
    "https://www.google.com/locationhistory/preview/mas?authuser=0&hl=en&gl=gb"
    "&pb=!2m1!7e81!12m1!1i1000!23m2!1i1000!3b1!24m2!1i1000!3b1!38m2!1i1000!3b1"
)
STARRED_URL = "https://www.google.com/maps/@0,0,3z/data=!4m2!11m1!3e4"


def at(node, *path):
    for i in path:
        if not isinstance(node, list) or len(node) <= i:
            return None
        node = node[i]
    return node


def google_cookie():
    cookies = rookie_cookies.load(["google.com"])
    return "; ".join(f"{c['name']}={c['value']}" for c in cookies if c["domain"] in (".google.com", "www.google.com"))


def main():
    if len(sys.argv) != 1:
        sys.exit(HELP)
    cookie = google_cookie()
    if not cookie:
        sys.exit("No Google session in any browser. " + COOKIE_HELP)

    headers = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/128.0 Safari/537.36", "Cookie": cookie}
    with urllib.request.urlopen(urllib.request.Request(URL, headers=headers), timeout=30) as res:
        data = json.loads(res.read().decode("utf-8").split("\n", 1)[1])
    if not any(at(data, i, 3) for i in SECTIONS):
        sys.exit("No lists returned. The Google session may be expired. " + COOKIE_HELP)

    writer = csv.DictWriter(sys.stdout, fieldnames=COLUMNS)
    writer.writeheader()
    writer.writerow({"kind": "starred", "title": "Starred places", "places": "", "url": STARRED_URL})
    for index, kind in SECTIONS.items():
        for lst in at(data, index, 3) or []:
            writer.writerow({
                "kind": kind,
                "title": at(lst, 4),
                "places": at(lst, 12),
                "url": f"https://www.google.com/maps/placelists/list/{at(lst, 0, 0)}",
            })
        if at(data, index, 1):
            print(f"Warning: more {kind} lists exist than were returned", file=sys.stderr)


if __name__ == "__main__":
    main()
