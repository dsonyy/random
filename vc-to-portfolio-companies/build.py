"""<vault>/vc/vc-<region>.md  ->  <vault>/companies/companies-<region>.md

    python3 build.py ~/brain/career/vc/vc-poland.md
    python3 build.py ~/brain/career/vc/vc-poland.md --funds 3   # trial run
    python3 build.py --test                                     # self-check, no network

The output path is derived from the input: the sibling companies/ directory of the
vc/ directory the input file sits in. Checkpoints land next to this script.

Crawling is pure Python and costs nothing. Only field extraction hits a model.
Default is local Ollama; the script derives a context-extended variant automatically,
because Ollama caps context at 4096 tokens and would silently truncate a batch.

    OR_KEY=$(cat ~/.openrouter_key) python3 build.py vc-poland     # OpenRouter instead

Every stage appends to <region>.*.jsonl, so interrupting loses nothing and a rerun
resumes. The final stage OVERWRITES companies/companies-<region>.md.
"""
from __future__ import annotations

import json
import os
import re
import sys
import threading
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from html import unescape
from typing import Any, Callable, Iterable, Iterator, NotRequired, TypedDict

SCRIPT_DIR: str = os.path.dirname(os.path.abspath(__file__))

OPENROUTER_KEY: str | None = os.environ.get("OR_KEY")
API_BASE_URL: str = os.environ.get("BASE_URL") or (
    "https://openrouter.ai/api/v1" if OPENROUTER_KEY else "http://localhost:11434/v1")
API_KEY: str = OPENROUTER_KEY or "ollama"
BASE_MODEL: str = os.environ.get("MODEL") or (
    "qwen/qwen3.7-flash" if OPENROUTER_KEY else "qwen3.5:9b-q4_K_M")
CONTEXT_TOKENS: int = int(os.environ.get("NUM_CTX", "12288"))
COMPANIES_PER_REQUEST: int = int(os.environ.get("BATCH", "20"))
# Crawling is free, so these caps only bound time. They were 45/120, which silently
# truncated large funds: General Catalyst lists 800+ companies and yielded 119.
PAGE_BUDGET: int = int(os.environ.get("PAGE_BUDGET", "1000"))
COMPANY_PAGE_LIMIT: int = int(os.environ.get("COMPANY_PAGE_LIMIT", "1200"))
# The context window holds prompt AND answer. Overflow makes the server truncate the
# prompt, and the model then answers about companies it can no longer see. Pack batches
# by size, not by count: 20 pages can be 30k characters or 43k depending on the sites.
OUTPUT_TOKEN_RESERVE: int = 2600
CHARS_PER_TOKEN: float = 3.0
BATCH_CHAR_BUDGET: int = int((CONTEXT_TOKENS - OUTPUT_TOKEN_RESERVE) * CHARS_PER_TOKEN)
MODEL_WORKERS: int = int(os.environ.get("LLM_WORKERS", "4" if OPENROUTER_KEY else "1"))
HTTP_WORKERS: int = int(os.environ.get("HTTP_WORKERS", "16"))

active_model: str = BASE_MODEL

DOMAIN_TAGS: str = (
    "fintech payments insurtech lending banking-infra wealthtech crypto ecommerce marketplace "
    "retail-tech logistics mobility travel proptech construction healthtech medtech biotech "
    "mental-health pharma hrtech edtech legaltech govtech martech adtech sales-tech "
    "customer-support cybersecurity devtools data-infra cloud-infra observability ai-ml "
    "agent-infra computer-vision nlp speech robotics iot hardware semiconductors manufacturing "
    "industry-4.0 space geospatial defence energy cleantech climate agritech foodtech gaming "
    "media sports consumer-app social telco quantum materials saas-horizontal saas-vertical "
    "services other")

BROWSER_HEADERS: dict[str, str] = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/131.0.0.0 Safari/537.36"}

PORTFOLIO_URL_HINT: re.Pattern[str] = re.compile(
    r"portfolio|portfel|companies|inwestycj|spolki|spółki|investments|startups|nasze", re.I)

NON_COMPANY_DOMAINS: re.Pattern[str] = re.compile(
    r"(^|\.)(linkedin|twitter|x|facebook|instagram|youtube|tiktok|medium|github|gitlab|"
    r"crunchbase|dealroom|pitchbook|angel|f6s|google|goo|apple|microsoft|amazon|adobe|"
    r"wordpress|wix|wixsite|squarespace|webflow|shopify|hubspot|mailchimp|calendly|typeform|"
    r"eventbrite|vimeo|spotify|substack|gravatar|cloudflare|jsdelivr|bootstrapcdn|fontawesome|"
    r"w3|schema|creativecommons|techcrunch|forbes|bloomberg|reuters|wired|businessinsider|"
    r"sifted|eu-startups|tech\.eu|wyborcza|pb|money|bankier|parkiet|rp|puls|gmail|outlook|"
    r"marketwatch|wsj|ft|cnbc|economictimes|indiatimes|techfundingnews|vcbay|prnewswire|"
    r"businesswire|globenewswire|bit|t|goo)\.")

# A money figure or a fragment of prose is a press citation, not a portfolio company.
# Anchors seen in the wild: "3.6", "~2.5", "$11.01 billion US", "worth roughly EUR 856 million".
CITATION_ANCHOR: re.Pattern[str] = re.compile(
    r"^\s*(?:[~<>]?[$€£]?[\d.,]+\s*(?:[MKB]|m|k|bn|mln|million|billion)?(?:\s+\w+){0,2}"
    r"|worth\b.*|(?:\S+\s+){5,}\S+)\s*$", re.I)

VALID_DOMAIN: re.Pattern[str] = re.compile(r"^[a-z0-9][a-z0-9-]*(\.[a-z0-9-]+)*\.[a-z]{2,}$")
# Sections of a site, not companies of their own.
SECTION_SUBDOMAIN: re.Pattern[str] = re.compile(
    r"^(www\d?|blog|about|en|pl|news|docs|help|support|shop|store|app|go|my|get|try|info|"
    r"careers|jobs|press|media)\.")

ANCHOR_TAG: re.Pattern[str] = re.compile(
    r'<a\b[^>]*?href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', re.S | re.I)
URL_IN_JSON_BLOB: re.Pattern[str] = re.compile(r'https?://([a-z0-9][a-z0-9.-]*\.[a-z]{2,})', re.I)

# The model spells the city the way the page does; these let an English answer
# match a Polish page and the other way round.
CITY_SPELLING_ALIASES: dict[str, str] = {
    "warsaw": "warszaw", "cracow": "krakow", "prague": "prah", "vienna": "wien",
    "munich": "munch", "cologne": "koln", "copenhagen": "kobenhavn", "lisbon": "lisbo",
    "milan": "milan"}

output_lock: threading.Lock = threading.Lock()
usage_totals: dict[str, int] = {"input_tokens": 0, "output_tokens": 0, "requests": 0}


# ---------- record shapes carried between stages -----------------------------

class Fund(TypedDict):
    fund: str
    site: str


class CrawledCompany(TypedDict):
    domain: str
    name: str


class CrawlRecord(TypedDict):
    fund: str
    site: str
    companies: list[CrawledCompany]
    pages: NotRequired[int]
    err: NotRequired[str]


class Company(TypedDict):
    """A crawled company once it is attached to the funds that back it."""
    domain: str
    name: str
    funds: list[str]


class CompanyPage(TypedDict):
    domain: str
    ok: bool
    url: NotRequired[str]
    title: NotRequired[str]
    desc: NotRequired[str]
    text: NotRequired[str]


class DescribedCompany(TypedDict, total=False):
    """What the model returns, plus the identity fields we attach afterwards."""
    name: str
    hq: str
    what: str
    tags: str
    stage: str
    skip: bool
    domain: str
    funds: list[str]
    url: str


# ---------- HTTP -------------------------------------------------------------

def fetch_url(url: str, max_bytes: int = 900_000, timeout: int = 15) -> tuple[str, str]:
    """Return (body, final_url). Never raises - unreachable pages return an empty body."""
    try:
        request = urllib.request.Request(url, headers=BROWSER_HEADERS)
        response = urllib.request.urlopen(request, timeout=timeout)
        content_type = response.headers.get("Content-Type", "")
        if content_type and not re.search(r"html|xml|text", content_type, re.I):
            return "", response.geturl()
        return response.read(max_bytes).decode("utf8", "replace"), response.geturl()
    except Exception:
        return "", url


def domain_of(url: str) -> str:
    """Return the company's own domain, or "" for anything that is not one.

    Section subdomains are stripped so blog.foo.com and about.foo.com do not become
    separate companies; a malformed netloc (spaces, no dot) is rejected outright.
    """
    hostname = urllib.parse.urlparse(url).netloc.lower().split(":")[0].strip(".")
    hostname = SECTION_SUBDOMAIN.sub("", hostname)
    return hostname if VALID_DOMAIN.match(hostname) else ""


def is_same_site(one_domain: str, other_domain: str) -> bool:
    return (one_domain == other_domain
            or one_domain.endswith("." + other_domain)
            or other_domain.endswith("." + one_domain))


def strip_accents(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", str(text).lower())
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def iter_links(html: str, page_url: str) -> Iterator[tuple[str, str]]:
    """Yield (absolute_url, anchor_text) for every real link on the page."""
    for match in ANCHOR_TAG.finditer(html):
        href = match.group(1).strip()
        if href.startswith(("#", "mailto:", "tel:", "javascript:")):
            continue
        anchor_text = unescape(re.sub(r"<[^>]+>", " ", match.group(2)))
        absolute_url = urllib.parse.urljoin(page_url, href).split("#")[0]
        yield absolute_url, " ".join(anchor_text.split())


def portfolio_urls_from_sitemap(site_url: str) -> list[str]:
    """A sitemap often lists every per-company page directly, sparing us the guessing."""
    for sitemap_name in ("sitemap.xml", "sitemap_index.xml", "sitemap-index.xml"):
        sitemap_url = urllib.parse.urljoin(site_url, "/" + sitemap_name)
        xml, _ = fetch_url(sitemap_url)
        locations = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", xml)
        for location in locations[:200]:
            if location.endswith(".xml") and PORTFOLIO_URL_HINT.search(location):
                nested_xml, _ = fetch_url(location)
                locations += re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", nested_xml)[:400]
        matching = [url for url in locations if PORTFOLIO_URL_HINT.search(url)]
        if matching:
            return list(dict.fromkeys(matching))
    return []


# ---------- 1. crawl a fund's portfolio --------------------------------------

def fetch_homepage(site: str) -> tuple[str, str]:
    """Try https, then www, then http, before calling a site unreachable."""
    base_url = site if site.startswith("http") else "https://" + site
    attempts = (base_url,
                base_url.replace("://", "://www."),
                base_url.replace("https://", "http://"))
    for candidate in attempts:
        html, final_url = fetch_url(candidate)
        if html:
            return html, final_url
    return "", base_url


def collect_portfolio_pages(site_url: str, site_domain: str, homepage_html: str,
                            page_budget: int = PAGE_BUDGET) -> dict[str, str]:
    """Walk the fund site up to two levels deep, keeping pages that look like a portfolio."""
    pages: dict[str, str] = {site_url: homepage_html}
    visited: set[str] = set()
    queue: list[tuple[str, int]] = [
        (url, 1) for url in portfolio_urls_from_sitemap(site_url)][:page_budget]
    queue += [(url, 1) for url, anchor_text in iter_links(homepage_html, site_url)
              if is_same_site(domain_of(url), site_domain)
              and (PORTFOLIO_URL_HINT.search(url) or PORTFOLIO_URL_HINT.search(anchor_text))]

    while queue and len(pages) < page_budget:
        url, depth = queue.pop(0)
        if url in visited or url in pages:
            continue
        visited.add(url)
        html, _ = fetch_url(url)
        if not html:
            continue
        pages[url] = html
        if depth < 2:
            queue += [(link_url, depth + 1) for link_url, _ in iter_links(html, url)
                      if is_same_site(domain_of(link_url), site_domain)
                      and PORTFOLIO_URL_HINT.search(link_url)]
    return pages


def extract_company_candidates(pages: dict[str, str],
                               site_domain: str) -> tuple[dict[str, str], set[str]]:
    """Outbound links are the companies; internal portfolio links are per-company pages."""
    companies_by_domain: dict[str, str] = {}
    per_company_page_urls: set[str] = set()

    for page_url, html in pages.items():
        for link_url, anchor_text in iter_links(html, page_url):
            link_domain = domain_of(link_url)
            if not link_domain:
                continue
            if is_same_site(link_domain, site_domain):
                if PORTFOLIO_URL_HINT.search(link_url):
                    per_company_page_urls.add(link_url)
                continue
            if NON_COMPANY_DOMAINS.search(link_domain + "."):
                continue
            # A citation anchor spoils the name, but the domain may still be a real
            # company linked from prose, so keep it and let its own page name it.
            name = "" if CITATION_ANCHOR.match(anchor_text) else anchor_text
            if not companies_by_domain.get(link_domain):
                companies_by_domain[link_domain] = name

        # Next.js and friends ship the whole company list as JSON even when
        # JavaScript is what renders it, so the links are in the source after all.
        for script_body in re.findall(r"(?is)<script[^>]*>(.*?)</script>", html):
            preceding = html[:html.find(script_body)][-400:]
            if "__NEXT_DATA__" not in preceding and '"props"' not in script_body[:200]:
                continue
            for link_domain in URL_IN_JSON_BLOB.findall(script_body):
                link_domain = link_domain.lower()
                if (not is_same_site(link_domain, site_domain)
                        and not NON_COMPANY_DOMAINS.search(link_domain + ".")):
                    companies_by_domain.setdefault(link_domain, "")

    return companies_by_domain, per_company_page_urls


def crawl_fund_portfolio(fund_name: str, site: str) -> CrawlRecord:
    homepage_html, site_url = fetch_homepage(site)
    if not homepage_html:
        return {"fund": fund_name, "site": site, "companies": [], "err": "unreachable"}

    site_domain = domain_of(site_url)
    pages = collect_portfolio_pages(site_url, site_domain, homepage_html)
    companies_by_domain, per_company_page_urls = extract_company_candidates(pages, site_domain)

    unvisited_company_pages = [
        url for url in per_company_page_urls if url not in pages][:COMPANY_PAGE_LIMIT]

    def harvest_company_page(url: str) -> None:
        """A per-company page holds the real name in its heading and the site in its links."""
        html, _ = fetch_url(url)
        if not html:
            return
        heading = re.search(r"(?is)<h1[^>]*>(.*?)</h1>|<title[^>]*>(.*?)</title>", html)
        groups = heading.groups() if heading else ()
        company_name = " ".join(unescape(
            re.sub(r"<[^>]+>", " ", "".join(group for group in groups if group))).split())
        for link_url, _ in iter_links(html, url):
            link_domain = domain_of(link_url)
            if (link_domain
                    and not is_same_site(link_domain, site_domain)
                    and not NON_COMPANY_DOMAINS.search(link_domain + ".")):
                with output_lock:
                    if not companies_by_domain.get(link_domain):
                        companies_by_domain[link_domain] = company_name

    run_in_parallel(unvisited_company_pages, harvest_company_page, HTTP_WORKERS)

    companies: list[CrawledCompany] = [
        {"domain": company_domain, "name": company_name}
        for company_domain, company_name in sorted(companies_by_domain.items())]
    return {"fund": fund_name, "site": site, "pages": len(pages), "companies": companies}


def resolve_paths(input_path: str) -> tuple[str, str, str]:
    """.../vc/vc-poland.md  ->  (absolute input, 'vc-poland', .../companies/companies-poland.md)"""
    absolute_input = os.path.abspath(os.path.expanduser(input_path))
    region = os.path.splitext(os.path.basename(absolute_input))[0]
    vault_dir = os.path.dirname(os.path.dirname(absolute_input))
    output_path = os.path.join(
        vault_dir, "companies", f"companies-{region.removeprefix('vc-')}.md")
    return absolute_input, region, output_path


def read_funds_from_markdown(markdown_path: str) -> list[Fund]:
    """The region file is a markdown table: fund name in column 1, website in column 4.

    Judge rows by their cells, not by the shape of the line - some of these tables are
    space-padded by the editor, which hides the header and separator from a naive match.
    """
    funds: list[Fund] = []
    for line in open(markdown_path, encoding="utf8"):
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.split("|")[1:-1]]
        if len(cells) <= 3:
            continue
        name, site = cells[0], cells[3]
        is_header = name.lower() == "fund" or site.lower() == "website"
        is_separator = not name or set(name) <= set("-: ")
        if is_header or is_separator or not site or site == "?":
            continue
        funds.append({"fund": name, "site": site})
    return funds


# ---------- progress ---------------------------------------------------------

class ProgressDisplay:
    """Two bars pinned to the bottom of the terminal; log() prints above them."""

    def __init__(self, total_funds: int) -> None:
        self.is_terminal: bool = sys.stdout.isatty()
        self.total_funds: int = total_funds
        self.funds_done: int = 0
        self.current_fund: str = ""
        self.total_companies: int = 0
        self.companies_done: int = 0
        self.phase: str = ""
        self.current_company: str = ""
        self.lines_drawn: int = 0
        self.started_at: float = time.time()

    @staticmethod
    def _render_bar(done: int, total: int, width: int = 24) -> str:
        filled = 0 if not total else min(width, int(width * done / total))
        return "█" * filled + "░" * (width - filled)

    def draw(self) -> None:
        if not self.is_terminal:
            return
        elapsed = int(time.time() - self.started_at)
        lines = [
            f"  FUNDS      {self._render_bar(self.funds_done, self.total_funds)} "
            f"{self.funds_done:>3}/{self.total_funds}  "
            f"{elapsed // 60:>2}m{elapsed % 60:02d}s  {self.current_fund[:32]}",
            f"  COMPANIES  {self._render_bar(self.companies_done, self.total_companies)} "
            f"{self.companies_done:>3}/{self.total_companies}  "
            f"{self.phase:<10} {self.current_company[:30]}",
        ]
        with output_lock:
            if self.lines_drawn:
                sys.stdout.write(f"\033[{self.lines_drawn}A")
            sys.stdout.write("".join("\033[2K" + line + "\n" for line in lines))
            self.lines_drawn = len(lines)
            sys.stdout.flush()

    def log(self, message: str) -> None:
        with output_lock:
            if self.is_terminal and self.lines_drawn:
                sys.stdout.write(f"\033[{self.lines_drawn}A\033[J")
                self.lines_drawn = 0
            print(message, flush=True)
        self.draw()

    def start_fund(self, index: int, fund_name: str) -> None:
        self.funds_done = index
        self.current_fund = fund_name
        self.total_companies = 0
        self.companies_done = 0
        self.phase = "crawling"
        self.current_company = ""
        self.draw()

    def start_phase(self, phase: str, total_companies: int) -> None:
        self.phase = phase
        self.total_companies = total_companies
        self.companies_done = 0
        self.current_company = ""
        self.draw()

    def advance(self, company_domain: str = "") -> None:
        self.companies_done += 1
        self.current_company = company_domain
        self.draw()


# ---------- 2. company pages -------------------------------------------------

def extract_readable_text(html: str, head_chars: int = 900,
                          tail_chars: int = 500) -> dict[str, str]:
    """The top of a page says what a company does, the footer says where it sits."""
    title_match = re.search(r"(?is)<title[^>]*>(.*?)</title>", html)
    description_match = (
        re.search(r'(?is)<meta[^>]+name=["\']description["\'][^>]*content=["\']([^"\']*)', html)
        or re.search(r'(?is)<meta[^>]+property=["\']og:description["\'][^>]*content=["\']([^"\']*)',
                     html))

    without_code = re.sub(r"(?is)<(script|style|svg|noscript)\b[^>]*>.*?</\1>", " ", html)
    body = unescape(" ".join(re.sub(r"<[^>]+>", " ", without_code).split()))
    if len(body) <= head_chars + tail_chars:
        text = body
    else:
        text = body[:head_chars] + " ... " + body[-tail_chars:]

    def cleaned(match: re.Match[str] | None) -> str:
        if not match:
            return ""
        return " ".join(unescape(re.sub(r"<[^>]+>", " ", match.group(1))).split())

    return {"title": cleaned(title_match)[:140],
            "desc": cleaned(description_match)[:300],
            "text": text}


def fetch_company_page(company_domain: str) -> CompanyPage:
    html, final_url = fetch_homepage(company_domain)
    page: CompanyPage = {"domain": company_domain, "ok": bool(html)}
    if not html:
        return page

    page.update(extract_readable_text(html), url=final_url)
    for subpage in ("/contact", "/about", "/kontakt", "/o-nas"):
        subpage_html, _ = fetch_url(urllib.parse.urljoin(final_url, subpage))
        if subpage_html:
            page["text"] = (page.get("text", "") + " | "
                            + extract_readable_text(subpage_html, 300, 400)["text"])
            break
    return page


# ---------- 3. field extraction ----------------------------------------------

EXTRACTION_PROMPT: str = """Below is raw text scraped from company websites. For EACH company
fill the fields using ONLY the text given. Do not use your own knowledge of these companies.

Answer in English even when the source text is in another language.

Return a JSON object: {{"rows":[{{"domain":"","name":"","hq":"","what":"","tags":"","stage":"","skip":false}}]}}

- domain: copy the company's domain from the list below, character for character.
  This is what ties your answer to the right company, so never alter or reorder it.
  Every company below appears exactly once in your answer.
- name: the company's real name, taken from the text, not from the domain
- hq: "City, Country". Copy the city EXACTLY as spelled in the text. Not in the text: ""
- what: one phrase, max 12 words, concrete about the product, not marketing language
- tags: 1-2 comma-separated tags, ONLY from this list: {tags}
- stage: pre-seed|seed|Series A|Series B|Series C|Series D+|growth|PE buyout|public|acquired|dead|unknown
  Only if the text says so, otherwise "unknown"
- skip: true ONLY when the page is not a company's own site at all: a news or trade
  publication, a PR wire service, a standalone blog, an investment fund or law firm site,
  a domain-for-sale placeholder, or an empty parking page. Then leave the other fields
  empty. Judge only what the page itself shows. Company size, fame, age and country are
  never reasons to skip - describe the company and let someone else filter later.

Anything not present in the text stays an empty string. An invented value is worse than
an empty one.

COMPANIES:
{block}"""


def ensure_local_model_with_context() -> None:
    """Ollama caps context at 4096 and truncates silently, so derive a wider variant."""
    global active_model
    if OPENROUTER_KEY:
        return

    derived_name = f"{BASE_MODEL.split(':')[0].replace('.', '')}-ctx{CONTEXT_TOKENS}"
    body = json.dumps({
        "model": derived_name,
        "from": BASE_MODEL,
        "parameters": {"num_ctx": CONTEXT_TOKENS, "temperature": 0},
    }).encode()
    request = urllib.request.Request(
        API_BASE_URL.replace("/v1", "") + "/api/create",
        data=body,
        headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(request, timeout=600).read()
    except Exception as error:
        print(f"! could not derive {derived_name} from {BASE_MODEL}: "
              f"{type(error).__name__} {error}")
        print(f"! is ollama running, and is `ollama pull {BASE_MODEL}` done?")
        sys.exit(1)
    active_model = derived_name


def call_model(prompt: str, max_output_tokens: int = 4000) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": active_model,
        "temperature": 0,
        "max_tokens": max_output_tokens,
        "messages": [{"role": "user", "content": prompt}],
        "response_format": {"type": "json_object"},
        "reasoning_effort": "none",
    }
    response: dict[str, Any] = {}
    for attempt in (0, 1):
        try:
            request = urllib.request.Request(
                API_BASE_URL + "/chat/completions",
                data=json.dumps(payload).encode(),
                headers={"Authorization": "Bearer " + API_KEY,
                         "Content-Type": "application/json"})
            response = json.load(urllib.request.urlopen(request, timeout=900))
            break
        except urllib.error.HTTPError as error:
            if attempt or error.code != 400:
                raise
            # Some models reject these two fields; drop them and try once more.
            payload.pop("response_format", None)
            payload.pop("reasoning_effort", None)

    usage: dict[str, int] = response.get("usage") or {}
    with output_lock:
        usage_totals["input_tokens"] += usage.get("prompt_tokens", 0)
        usage_totals["output_tokens"] += usage.get("completion_tokens", 0)
        usage_totals["requests"] += 1
    return parse_json_response(response["choices"][0]["message"]["content"])


def parse_json_response(text: str) -> dict[str, Any]:
    without_fences = re.sub(r"^\s*```(?:json)?|```\s*$", "", str(text).strip(), flags=re.M)
    without_thinking = re.sub(r"(?is)<think>.*?</think>", "", without_fences)
    for pattern in (r"\{.*\}", r"\[.*\]"):
        match = re.search(pattern, without_thinking, re.S)
        if not match:
            continue
        blob = match.group()
        for candidate in (blob, re.sub(r",\s*([\]}])", r"\1", blob)):
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                pass
    raise ValueError(f"no JSON in response: {without_thinking[:200]}")


def drop_unverifiable_fields(row: DescribedCompany, page: CompanyPage) -> DescribedCompany:
    """A value absent from the company's own page was invented. Blank it.

    This also catches the model answering about the wrong company: a name or city
    lifted from a neighbouring entry will not appear on this company's page.
    """
    haystack = strip_accents(
        page.get("title", "") + " " + page.get("desc", "") + " "
        + page.get("text", "") + " " + page.get("domain", ""))

    city = strip_accents(row.get("hq", "")).split(",")[0].strip()
    city = CITY_SPELLING_ALIASES.get(city, city)
    if city and city[:6] not in haystack:
        row["hq"] = ""

    name_letters = re.sub(r"[^a-z0-9]", "", strip_accents(row.get("name", "")))
    if name_letters and name_letters[:8] not in re.sub(r"[^a-z0-9]", "", haystack):
        row["name"] = ""

    return row


def company_block(company: Company, pages: dict[str, CompanyPage]) -> str:
    page = pages[company["domain"]]
    return (f"domain: {company['domain']}\n"
            f"title: {page.get('title', '')}\n"
            f"description: {page.get('desc', '')}\n"
            f"text: {page.get('text', '')}")


def pack_batches(companies: list[Company],
                 pages: dict[str, CompanyPage]) -> list[list[Company]]:
    """Group companies so no prompt overflows the context window."""
    batches: list[list[Company]] = []
    current: list[Company] = []
    current_chars = 0
    for company in companies:
        size = len(company_block(company, pages))
        too_big = current and (current_chars + size > BATCH_CHAR_BUDGET
                               or len(current) >= COMPANIES_PER_REQUEST)
        if too_big:
            batches.append(current)
            current, current_chars = [], 0
        current.append(company)
        current_chars += size
    if current:
        batches.append(current)
    return batches


def describe_company_batch(batch: list[Company], pages: dict[str, CompanyPage],
                           rows_path: str, progress: ProgressDisplay) -> set[str]:
    """Return the domains actually written, so callers never mark a dropped one done."""
    block = "\n\n".join(company_block(company, pages) for company in batch)

    rows: list[DescribedCompany] = []
    try:
        rows = call_model(EXTRACTION_PROMPT.format(tags=DOMAIN_TAGS, block=block))["rows"]
    except Exception as error:
        progress.log(f"    ! batch {batch[0]['domain'][:24]}: "
                     f"{type(error).__name__} {str(error)[:60]}")

    companies_in_batch = {company["domain"]: company for company in batch}
    described_domains: set[str] = set()
    for row in rows:
        # The domain the model echoed back is the only thing tying a row to a company.
        # Anything it invented or garbled names no company here, so it is dropped.
        company = companies_in_batch.get(str(row.get("domain", "")).strip().lower())
        if company is None or company["domain"] in described_domains:
            continue
        described_domains.add(company["domain"])
        row = drop_unverifiable_fields(row, pages[company["domain"]])
        row.update(domain=company["domain"],
                   funds=company["funds"],
                   url=pages[company["domain"]].get("url", ""))
        append_jsonl(rows_path, row)
        progress.advance(company["domain"])

    for company in batch:
        if company["domain"] not in described_domains:
            progress.advance(company["domain"])
    return described_domains


def crawl_and_describe_all_funds(funds_path: str, region: str,
                                 fund_limit: int | None = None) -> ProgressDisplay:
    crawl_path = f"{SCRIPT_DIR}/{region}.crawl.jsonl"
    pages_path = f"{SCRIPT_DIR}/{region}.pages.jsonl"
    rows_path = f"{SCRIPT_DIR}/{region}.rows.jsonl"

    funds: list[Fund] = read_funds_from_markdown(funds_path)[:fund_limit]
    crawled_funds: dict[str, CrawlRecord] = {
        record["fund"]: record for record in read_jsonl(crawl_path)}
    pages: dict[str, CompanyPage] = {page["domain"]: page for page in read_jsonl(pages_path)}
    already_described: set[str] = {row["domain"] for row in read_jsonl(rows_path)}

    progress = ProgressDisplay(len(funds))
    progress.log(f"{len(funds)} funds from {funds_path}   model {active_model}\n"
                 f"resuming: {len(crawled_funds)} funds crawled, "
                 f"{len(already_described)} companies described\n")

    for fund_index, fund in enumerate(funds, 1):
        progress.start_fund(fund_index, fund["fund"])

        crawl_record = crawled_funds.get(fund["fund"])
        if crawl_record is None:
            crawl_record = crawl_fund_portfolio(fund["fund"], fund["site"])
            append_jsonl(crawl_path, crawl_record)

        companies: list[Company] = [
            {"domain": company["domain"],
             "name": company["name"] or company["domain"].split(".")[0],
             "funds": [fund["fund"]]}
            for company in crawl_record["companies"]]

        unfetched = [company for company in companies if company["domain"] not in pages]
        progress.start_phase("fetching", len(unfetched))

        def fetch_and_record(company: Company) -> None:
            page = fetch_company_page(company["domain"])
            append_jsonl(pages_path, page)
            with output_lock:
                pages[company["domain"]] = page
            progress.advance(company["domain"])

        run_in_parallel(unfetched, fetch_and_record, HTTP_WORKERS)

        undescribed = [company for company in companies
                       if company["domain"] not in already_described
                       and pages.get(company["domain"], {}).get("ok")]
        progress.start_phase("describing", len(undescribed))
        batches = pack_batches(undescribed, pages)
        newly_described: set[str] = set()

        def describe_and_collect(batch: list[Company]) -> None:
            written = describe_company_batch(batch, pages, rows_path, progress)
            with output_lock:
                newly_described.update(written)

        run_in_parallel(batches, describe_and_collect, MODEL_WORKERS)
        already_described |= newly_described

        dropped = len(undescribed) - len(newly_described)
        if dropped:
            progress.log(f"    ! {dropped} companies came back with no row, "
                         f"rerun the script to retry them")

        dead_sites = sum(1 for company in companies
                         if not pages.get(company["domain"], {}).get("ok"))
        error_note = "  " + crawl_record["err"] if crawl_record.get("err") else ""
        progress.log(f"  [{fund_index:>3}/{len(funds)}] {fund['fund'][:30]:30} "
                     f"{len(companies):>3} found, {len(undescribed):>3} new, "
                     f"{dead_sites:>2} dead sites{error_note}")

    misses = [record for record in read_jsonl(crawl_path) if len(record["companies"]) < 2]
    if misses:
        progress.log(f"\nMISSES ({len(misses)}) - funds that yielded no portfolio, "
                     f"check by hand:")
        for record in misses:
            progress.log(f"    {record['fund'][:32]:32} {record['site'][:30]:30} "
                         f"{record.get('err', 'empty')}")
    return progress


# ---------- 4. markdown ------------------------------------------------------

def merge_companies_across_funds(region: str) -> list[Company]:
    """One row per domain, listing every fund that links to it."""
    merged: dict[str, Company] = {}
    for crawl_record in read_jsonl(f"{SCRIPT_DIR}/{region}.crawl.jsonl"):
        for company in crawl_record["companies"]:
            entry = merged.setdefault(company["domain"],
                                      {"domain": company["domain"], "name": "", "funds": []})
            if len(company["name"]) > len(entry["name"]) and len(company["name"]) < 60:
                entry["name"] = company["name"]
            if crawl_record["fund"] not in entry["funds"]:
                entry["funds"].append(crawl_record["fund"])

    for entry in merged.values():
        entry["name"] = entry["name"] or entry["domain"].split(".")[0]
    return sorted(merged.values(), key=lambda company: company["name"].lower())


KNOWN_TAGS: set[str] = set(DOMAIN_TAGS.split())
TAG_SYNONYMS: dict[str, str] = {
    "telecom": "telco", "energy-infra": "energy", "renewable": "energy",
    "banking": "banking-infra", "chemistry": "materials", "automation": "industry-4.0",
    "no-code": "devtools", "saas": "saas-horizontal", "aerospace": "space",
    "defense": "defence", "hospitality": "travel", "cyber security": "cybersecurity",
    "recruitment": "hrtech", "design": "other", "ai": "ai-ml", "ml": "ai-ml",
    "e-commerce": "ecommerce"}
KNOWN_STAGES: dict[str, str] = {
    "seed": "seed", "pre-seed": "pre-seed", "exit": "acquired", "acquired": "acquired",
    "dead": "dead", "public": "public", "growth": "growth", "pe buyout": "PE buyout",
    "series a": "Series A", "series b": "Series B", "series c": "Series C",
    "series d+": "Series D+"}


def canonicalize_tags_and_stage(row: DescribedCompany) -> DescribedCompany:
    """Force the model's free text back into the closed vocabularies.

    Separators vary by whim of the model - "fintech, ai-ml" and "fintech ai-ml" both
    show up - so split on whitespace too, after folding the multi-word synonyms.
    """
    value = row.get("tags", "")
    # The model answers "a, b" most of the time and ["a", "b"] the rest of the time.
    raw = (", ".join(str(item) for item in value) if isinstance(value, list) else str(value)).lower()
    for phrase, canonical in TAG_SYNONYMS.items():
        if " " in phrase:
            raw = raw.replace(phrase, canonical)

    tags: list[str] = []
    for raw_tag in re.split(r"[,;/\s]+", raw):
        tag = TAG_SYNONYMS.get(raw_tag.strip(), raw_tag.strip())
        if tag in KNOWN_TAGS and tag not in tags:
            tags.append(tag)
    row["tags"] = ",".join(tags[:2])
    row["stage"] = KNOWN_STAGES.get(str(row.get("stage", "")).strip().lower(), "unknown")
    return row


def write_markdown_table(region: str, companies: list[Company], output_path: str) -> None:
    described_by_domain: dict[str, DescribedCompany] = {
        row["domain"]: canonicalize_tags_and_stage(row)
        for row in read_jsonl(f"{SCRIPT_DIR}/{region}.rows.jsonl")
        if not row.get("skip")}

    def cell(value: object) -> str:
        return str(value or "").replace("|", "-").replace("\n", " ").strip() or "?"

    lines = ["| Company | HQ | What they do | Domain | Stage | Round | Investors | Sources |",
             "|---|---|---|---|---|---|---|---|"]
    for company in companies:
        described: DescribedCompany = described_by_domain.get(company["domain"], {})
        name = cell(described.get("name") or company["name"])
        lines.append("| " + " | ".join([
            f"[{name}](https://{company['domain']})",
            cell(described.get("hq")),
            cell(described.get("what")),
            cell(described.get("tags")),
            cell(described.get("stage")),
            "",
            cell(", ".join(company["funds"])),
            "",
        ]) + " |")

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    open(output_path, "w", encoding="utf8").write("\n".join(lines) + "\n")
    print(f"\n{len(companies)} rows ({len(described_by_domain)} described) -> {output_path}")


# ---------- utils ------------------------------------------------------------

def read_jsonl(path: str) -> list[Any]:
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def append_jsonl(path: str, record: Any) -> None:
    with output_lock, open(path, "a", encoding="utf8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def run_in_parallel(items: Iterable[Any], function: Callable[[Any], Any], workers: int) -> None:
    items = list(items)
    if not items:
        return
    with ThreadPoolExecutor(workers) as executor:
        list(executor.map(function, items))


def self_check() -> None:
    assert domain_of("https://www.Foo.COM/bar") == "foo.com"
    assert domain_of("https://blog.infermedica.com/x") == "infermedica.com"
    assert domain_of("https://acquired by commsor") == ""
    assert domain_of("https://rip") == ""
    assert domain_of("https://sub.team.foo.co.uk") == "sub.team.foo.co.uk"
    assert is_same_site("app.foo.com", "foo.com")
    assert not is_same_site("foo.com", "bar.com")

    shifted: DescribedCompany = {"name": "Handwave", "hq": ""}
    gralio_page: CompanyPage = {"domain": "gralio.ai", "ok": True,
                                "title": "Gralio - software comparison", "text": "Compare tools"}
    assert drop_unverifiable_fields(shifted, gralio_page)["name"] == ""
    correct: DescribedCompany = {"name": "Zowie", "hq": ""}
    zowie_page: CompanyPage = {"domain": "getzowie.com", "ok": True, "title": "", "text": ""}
    assert drop_unverifiable_fields(correct, zowie_page)["name"] == "Zowie"
    assert NON_COMPANY_DOMAINS.search("linkedin.com.")
    assert not NON_COMPANY_DOMAINS.search("packhelp.com.")

    assert list(iter_links('<a href="/p">Portfolio</a>', "https://x.pl/")) == [
        ("https://x.pl/p", "Portfolio")]

    parsed = extract_readable_text("<title>Foo &amp; Co</title><script>junk()</script><p>Bar</p>")
    assert parsed["title"] == "Foo & Co"
    assert "..." in extract_readable_text("<p>" + "a" * 3000 + "</p>")["text"]

    verified: DescribedCompany = {"hq": "Warsaw, Poland"}
    invented: DescribedCompany = {"hq": "Berlin, Germany"}
    page: CompanyPage = {"domain": "x.pl", "ok": True, "text": "office in Warszawie"}
    assert drop_unverifiable_fields(verified, page)["hq"] == "Warsaw, Poland"
    assert drop_unverifiable_fields(invented, page)["hq"] == ""

    input_path, region, output_path = resolve_paths("~/vault/vc/vc-poland.md")
    assert region == "vc-poland"
    assert input_path.endswith("/vault/vc/vc-poland.md")
    assert output_path.endswith("/vault/companies/companies-poland.md")
    assert not input_path.startswith("~")

    assert parse_json_response('```json\n{"rows":[{"i":0},]}\n```')["rows"][0]["i"] == 0
    assert parse_json_response('<think>hmm</think>{"rows":[]}')["rows"] == []

    assert CITATION_ANCHOR.match("3.6")
    assert CITATION_ANCHOR.match("~2.5")
    assert CITATION_ANCHOR.match("$11.01 billion US")
    assert CITATION_ANCHOR.match("worth roughly €856 million")
    assert CITATION_ANCHOR.match("A recent survey from GE shows that")
    assert not CITATION_ANCHOR.match("Packhelp")
    assert not CITATION_ANCHOR.match("Market One Capital")
    assert not CITATION_ANCHOR.match("")
    assert NON_COMPANY_DOMAINS.search("marketwatch.com.")

    canonical = canonicalize_tags_and_stage({"tags": "AI, e-commerce, fintech",
                                             "stage": "Series A"})
    assert canonical["tags"] == "ai-ml,ecommerce"
    assert canonical["stage"] == "Series A"
    assert canonicalize_tags_and_stage({"tags": "robotics ai-ml"})["tags"] == "robotics,ai-ml"
    assert canonicalize_tags_and_stage({"tags": "cyber security"})["tags"] == "cybersecurity"
    assert canonicalize_tags_and_stage({"tags": "crypto fintech payments"})["tags"] == "crypto,fintech"
    assert canonicalize_tags_and_stage({"tags": ["ai-ml", "computer-vision"]})["tags"] == "ai-ml,computer-vision"
    assert canonicalize_tags_and_stage({"tags": ["gaming"]})["tags"] == "gaming"
    assert canonicalize_tags_and_stage({"tags": "made-up-tag", "stage": ""})["stage"] == "unknown"

    big: CompanyPage = {"domain": "big.com", "ok": True, "text": "x" * 12000}
    small: CompanyPage = {"domain": "small.com", "ok": True, "text": "y" * 100}
    fake_pages = {f"c{i}.com": (big if i % 2 else small) for i in range(8)}
    fake_companies: list[Company] = [
        {"domain": f"c{i}.com", "name": "", "funds": []} for i in range(8)]
    packed = pack_batches(fake_companies, fake_pages)
    assert sum(len(batch) for batch in packed) == 8
    assert all(sum(len(company_block(c, fake_pages)) for c in batch) <= BATCH_CHAR_BUDGET
               or len(batch) == 1
               for batch in packed)
    assert len(pack_batches(fake_companies[:1], fake_pages)) == 1

    progress = ProgressDisplay(10)
    progress.is_terminal = False
    progress.start_fund(1, "Some Fund")
    progress.start_phase("fetching", 3)
    progress.advance("example.com")
    assert progress.companies_done == 1

    print("ok")


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print(__doc__)
        sys.exit()

    if sys.argv[1] == "--test":
        self_check()
        sys.exit()

    funds_file, region_name, output_file = resolve_paths(sys.argv[1])
    if not os.path.isfile(funds_file):
        print(f"no such file: {funds_file}")
        sys.exit(1)

    if "--funds" in sys.argv:
        fund_limit = int(sys.argv[sys.argv.index("--funds") + 1])
    else:
        fund_limit = None

    ensure_local_model_with_context()
    run_progress = crawl_and_describe_all_funds(funds_file, region_name, fund_limit)
    write_markdown_table(region_name, merge_companies_across_funds(region_name), output_file)

    elapsed_seconds = int(time.time() - run_progress.started_at)
    print(f"{usage_totals['requests']} model calls, "
          f"tokens in {usage_totals['input_tokens']} out {usage_totals['output_tokens']}, "
          f"time {elapsed_seconds // 60}m{elapsed_seconds % 60:02d}s")
