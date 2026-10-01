#!/usr/bin/env python3
import csv
import json
import os
import sys
import urllib.request

COLUMNS = ["kind", "title", "places", "url"]

HELP = f"""List all Google Maps saved lists of the signed-in account as CSV to stdout.

Usage: google-maps-lists.py > lists.csv
Feed each url to google-maps-list-export.py to export its places.

Columns: {", ".join(COLUMNS)}"""

COOKIE_HELP = """Set GOOGLE_COOKIE to your Google session:
1. Open https://www.google.com/maps signed in, then DevTools -> Application -> Cookies -> https://www.google.com.
2. Copy the values of __Secure-3PSID and __Secure-3PSIDTS.
3. export GOOGLE_COOKIE='__Secure-3PSID=<value>; __Secure-3PSIDTS=<value>'"""

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


def main():
    if len(sys.argv) != 1:
        sys.exit(HELP)
    cookie = os.environ.get("GOOGLE_COOKIE")
    if not cookie:
        sys.exit(f"{HELP}\n\n{COOKIE_HELP}")

    headers = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/128.0 Safari/537.36", "Cookie": cookie}
    with urllib.request.urlopen(urllib.request.Request(URL, headers=headers), timeout=30) as res:
        data = json.loads(res.read().decode("utf-8").split("\n", 1)[1])
    if not any(at(data, i, 3) for i in SECTIONS):
        sys.exit("No lists returned. GOOGLE_COOKIE may be expired.\n\n" + COOKIE_HELP)

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
