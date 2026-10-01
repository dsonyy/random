#!/usr/bin/env python3
import csv
import datetime
import json
import os
import re
import sys
import urllib.request

COLUMNS = [
    "list_title", "list_description", "list_owner", "name", "note", "address", "lat", "lng",
    "cid", "mid", "place_id", "maps_url", "photo_url", "added_by", "added_at", "updated_at",
]

HELP = f"""Export a Google Maps saved list as CSV to stdout.

Usage: google-maps-list-export.py <list-url> > places.csv

<list-url> is a share link (maps.app.goo.gl/...) or the address bar URL of an
open list (google.com/maps/placelists/list/...), including Starred places.
Private lists need GOOGLE_COOKIE.

Columns: {", ".join(COLUMNS)}"""

COOKIE_HELP = """This list is private or does not exist. To read a private list, set GOOGLE_COOKIE:
1. Open https://www.google.com/maps signed in, then DevTools -> Application -> Cookies -> https://www.google.com.
2. Copy the values of __Secure-3PSID and __Secure-3PSIDTS.
3. export GOOGLE_COOKIE='__Secure-3PSID=<value>; __Secure-3PSIDTS=<value>'"""

UINT64 = 1 << 64
BROWSER_UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/128.0 Safari/537.36"


def at(node, *path):
    for i in path:
        if not isinstance(node, list) or len(node) <= i:
            return None
        node = node[i]
    return node


def get(url, user_agent, cookie=None):
    headers = {"User-Agent": user_agent}
    if cookie:
        headers["Cookie"] = cookie
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=30) as res:
        return res.read().decode("utf-8"), res.geturl()


def resolve_list_id(url):
    pattern = r"(?:/placelists/list/|!2s)([\w-]{16,})"
    m = re.search(pattern, url)
    if not m:
        # A full browser UA gets a JS interstitial instead of a redirect from maps.app.goo.gl.
        _, final_url = get(url, "Mozilla/5.0")
        m = re.search(pattern, final_url)
    if not m:
        sys.exit(f"No list id found in {url}")
    return m.group(1)


def get_json(url, cookie=None):
    body, _ = get(url, BROWSER_UA, cookie)
    return json.loads(body.split("\n", 1)[1])


def fetch_list(list_id, cookie=None):
    url = (
        "https://www.google.com/maps/preview/entitylist/getlist?authuser=0&hl=en&gl=gb"
        f"&pb=!1m4!1s{list_id}!2e1!3m1!1e1!2e2!3e2!4i2000"
    )
    return at(get_json(url, cookie), 0)


def fetch_starred(cookie):
    # Starred places have no list id; Maps loads them as a "*" search filtered by !54m2!1e4.
    url = "https://www.google.com/search?tbm=map&authuser=0&hl=en&gl=gb&q=*&pb=!7i200!8i0!34m1!31b1!54m2!1e4!2s"
    return [at(item, 1) for item in at(get_json(url, cookie), 64) or [] if at(item, 1)]


def require_cookie():
    cookie = os.environ.get("GOOGLE_COOKIE")
    if not cookie:
        sys.exit(COOKIE_HELP)
    return cookie


def timestamp(node):
    seconds = at(node, 0)
    return datetime.datetime.fromtimestamp(seconds, datetime.UTC).isoformat() if seconds else ""


def place_row(item, lst):
    cid = at(item, 1, 6, 1)
    return {
        "list_title": at(lst, 4) or "",
        "list_description": at(lst, 5) or "",
        "list_owner": at(lst, 3, 0) or "",
        "name": at(item, 2) or "",
        "note": at(item, 3) or "",
        "address": (at(item, 1, 4) or "").strip(),
        "lat": at(item, 1, 5, 2),
        "lng": at(item, 1, 5, 3),
        "cid": int(cid) % UINT64 if cid else "",
        "mid": at(item, 1, 7) or "",
        "place_id": "",
        "maps_url": f"https://maps.google.com/?cid={int(cid) % UINT64}" if cid else "",
        "photo_url": at(item, 13, 0) or "",
        "added_by": at(item, 12, 0) or "",
        "added_at": timestamp(at(item, 9)),
        "updated_at": timestamp(at(item, 10)),
    }


def starred_row(place):
    cid = int(at(place, 10).split(":")[1], 16) if at(place, 10) else None
    return {
        "list_title": "Starred places",
        "name": at(place, 11) or "",
        "address": at(place, 39) or "",
        "lat": at(place, 9, 2),
        "lng": at(place, 9, 3),
        "cid": cid or "",
        "mid": at(place, 89) or "",
        "place_id": at(place, 78) or "",
        "maps_url": f"https://maps.google.com/?cid={cid}" if cid else "",
    }


def list_rows(url):
    list_id = resolve_list_id(url)
    lst = fetch_list(list_id)
    if lst is None:
        lst = fetch_list(list_id, require_cookie())
        if lst is None:
            sys.exit("List not found with GOOGLE_COOKIE either. The cookie may be expired or the list belongs to another account.")
    items = at(lst, 8) or []
    total = at(lst, 12) or len(items)
    print(f"{at(lst, 4)}: {len(items)}/{total} places", file=sys.stderr)
    if len(items) < total:
        print("Warning: list truncated", file=sys.stderr)
    return [place_row(item, lst) for item in items]


def starred_rows():
    places = fetch_starred(require_cookie())
    if not places:
        sys.exit("No starred places returned. The cookie may be expired.")
    print(f"Starred places: {len(places)} places", file=sys.stderr)
    if len(places) == 200:
        print("Warning: Google returns at most 200 starred places, the same as maps.google.com shows", file=sys.stderr)
    return [starred_row(place) for place in places]


def main():
    if len(sys.argv) != 2:
        sys.exit(HELP)
    url = sys.argv[1]
    rows = starred_rows() if "!11m1!3e4" in url else list_rows(url)
    writer = csv.DictWriter(sys.stdout, fieldnames=COLUMNS, restval="")
    writer.writeheader()
    writer.writerows(rows)


if __name__ == "__main__":
    main()
