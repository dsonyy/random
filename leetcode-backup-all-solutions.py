#!/usr/bin/env python3
"""
Backup all your Accepted LeetCode solutions as local files, one per problem.
1. Log into leetcode.com in your browser.
2. Open devtools -> Application/Storage -> Cookies -> leetcode.com.
3. Copy the values of "LEETCODE_SESSION" and "csrftoken".
4. export LEETCODE_SESSION=...
    export LEETCODE_CSRFTOKEN=...
5. python3 leetcode-backup-all-solutions.py [output_dir]
"""
import os
import sys

import requests

GRAPHQL_URL = "https://leetcode.com/graphql"

LANG_EXT = {
    "python": "py", "python3": "py", "java": "java", "c": "c", "cpp": "cpp",
    "csharp": "cs", "javascript": "js", "typescript": "ts", "php": "php",
    "swift": "swift", "kotlin": "kt", "dart": "dart", "golang": "go",
    "ruby": "rb", "scala": "scala", "rust": "rs", "racket": "rkt",
    "erlang": "erl", "elixir": "ex", "mysql": "sql", "mssql": "sql",
    "oraclesql": "sql", "postgresql": "sql", "bash": "sh",
}


def get_extension(lang: str) -> str:
    return LANG_EXT.get(lang, "txt")


def build_filename(question_id: str, title_slug: str, lang: str) -> str:
    return f"{int(question_id):04d}-{title_slug}.{get_extension(lang)}"


def make_session() -> requests.Session:
    leetcode_session = os.environ["LEETCODE_SESSION"]
    csrftoken = os.environ["LEETCODE_CSRFTOKEN"]

    s = requests.Session()
    s.cookies.set("LEETCODE_SESSION", leetcode_session, domain="leetcode.com")
    s.cookies.set("csrftoken", csrftoken, domain="leetcode.com")
    s.headers.update({
        "Content-Type": "application/json",
        "Referer": "https://leetcode.com/submissions/",
        "x-csrftoken": csrftoken,
    })
    return s


def graphql(session: requests.Session, query: str, variables: dict) -> dict:
    resp = session.post(GRAPHQL_URL, json={
                        "query": query, "variables": variables})
    resp.raise_for_status()
    data = resp.json()
    if "errors" in data:
        raise RuntimeError(data["errors"])
    return data["data"]


SUBMISSION_LIST_QUERY = """
query submissionList($offset: Int!, $limit: Int!) {
  submissionList(offset: $offset, limit: $limit) {
    hasNext
    submissions {
      id
      statusDisplay
      titleSlug
    }
  }
}
"""

SUBMISSION_DETAIL_QUERY = """
query submissionDetails($submissionId: Int!) {
  submissionDetails(submissionId: $submissionId) {
    code
    lang { name }
    question { questionFrontendId }
  }
}
"""


def iter_accepted_submissions(session: requests.Session):
    """Yields (submission_id, title_slug) for accepted submissions, newest first."""
    offset = 0
    limit = 20
    while True:
        data = graphql(session, SUBMISSION_LIST_QUERY, {
                       "offset": offset, "limit": limit})
        page = data["submissionList"]
        for sub in page["submissions"]:
            if sub["statusDisplay"] == "Accepted":
                yield sub["id"], sub["titleSlug"]
        if not page["hasNext"]:
            return
        offset += limit


def backup(output_dir: str) -> None:
    session = make_session()
    os.makedirs(output_dir, exist_ok=True)

    seen_slugs = set()
    saved = 0
    for submission_id, title_slug in iter_accepted_submissions(session):
        if title_slug in seen_slugs:
            continue  # keep only the most recent accepted submission per problem
        seen_slugs.add(title_slug)

        detail = graphql(session, SUBMISSION_DETAIL_QUERY, {
                         "submissionId": submission_id})["submissionDetails"]
        filename = build_filename(
            detail["question"]["questionFrontendId"], title_slug, detail["lang"]["name"])
        path = os.path.join(output_dir, filename)
        with open(path, "w") as f:
            f.write(detail["code"])
        print(f"saved {filename}")
        saved += 1

    print(f"done: {saved} solutions saved to {output_dir}/")


if __name__ == "__main__":
    backup(sys.argv[1] if len(sys.argv) > 1 else "leetcode-solutions")
