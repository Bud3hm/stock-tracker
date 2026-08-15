import os
import re
import json
import html
import heapq
import urllib.error
import urllib.parse
import urllib.request

from collections import deque
from pathlib import Path
from datetime import datetime, timezone
from html.parser import HTMLParser

from supabase import create_client


# ============================================================
# REIT REPORT DISCOVERY ENGINE v5.2
#
# FAST + CACHED + STRICT DATE MATCH
#
# READ ONLY
#
# التحسينات الرئيسية:
#
# 1) HTTP CACHE
#    نفس الرابط لا يُطلب أكثر من مرة في نفس التشغيل.
#
# 2) PAGE CACHE
#    Q2 و H1 يعيدون استخدام نفس HTML المحمّل.
#
# 3) STRICT DATE VALIDATION
#    أي تقرير لا يطابق سنة period_end لا يمكن اعتباره VERIFIED.
#
# 4) Period guard
#    يحاول منع اختيار Q1/Q3/H1/FY كبديل خاطئ.
#
# 5) Early Stop
#    فقط إذا:
#       - Score قوي
#       - السنة صحيحة
#       - الفترة متوافقة
#
# 6) عام لجميع صناديق REIT.
#
# لا توجد كتابة في Supabase.
# ============================================================


ENGINE_NAME = "REIT REPORT DISCOVERY ENGINE v5.2 FAST CACHED"

REGISTRY_FILENAME = "reit_official_sources.json"

HTTP_TIMEOUT = 8

MAX_CRAWL_DEPTH = 2
MAX_PAGES = 10
MAX_LINKS_PER_PAGE = 120
MAX_DOCUMENT_CHECKS = 20

MIN_ACCEPT_SCORE = 60.0
STRONG_ACCEPT_SCORE = 80.0
EARLY_STOP_SCORE = 90.0


# ============================================================
# Runtime caches
# ============================================================


HTTP_CACHE = {}

LINK_CACHE = {}


# ============================================================
# Supabase
# ============================================================


SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_SECRET_KEY = os.environ.get("SUPABASE_SECRET_KEY")


if not SUPABASE_URL:
    raise RuntimeError(
        "SUPABASE_URL environment variable is missing"
    )


if not SUPABASE_SECRET_KEY:
    raise RuntimeError(
        "SUPABASE_SECRET_KEY environment variable is missing"
    )


supabase = create_client(
    SUPABASE_URL,
    SUPABASE_SECRET_KEY
)


# ============================================================
# HTML parser
# ============================================================


class ContextLinkParser(HTMLParser):

    def __init__(self):

        super().__init__()

        self.links = []

        self.recent_text = deque(
            maxlen=16
        )

        self.current_href = None
        self.current_anchor = []
        self.before_context = ""


    def handle_starttag(
        self,
        tag,
        attrs
    ):

        if tag.lower() != "a":
            return

        attrs = dict(
            attrs
        )

        href = attrs.get(
            "href"
        )

        if not href:
            return

        self.current_href = href
        self.current_anchor = []

        self.before_context = " ".join(
            self.recent_text
        )


    def handle_data(
        self,
        data
    ):

        text = str(
            data
        ).strip()

        if not text:
            return

        self.recent_text.append(
            text
        )

        if self.current_href is not None:

            self.current_anchor.append(
                text
            )


    def handle_endtag(
        self,
        tag
    ):

        if (
            tag.lower() != "a"
            or self.current_href is None
        ):

            return

        self.links.append({
            "href":
                self.current_href,

            "anchor_text":
                " ".join(
                    self.current_anchor
                ),

            "context":
                self.before_context
        })

        self.current_href = None
        self.current_anchor = []
        self.before_context = ""


# ============================================================
# أدوات عامة
# ============================================================


def print_header(title):

    print(
        "\n"
        + "=" * 118,
        flush=True
    )

    print(
        title,
        flush=True
    )

    print(
        "=" * 118,
        flush=True
    )


def print_separator():

    print(
        "-" * 118,
        flush=True
    )


def normalize_symbol(symbol):

    if not symbol:
        return None

    return str(
        symbol
    ).strip().upper()


def exchange_code(symbol):

    symbol = normalize_symbol(
        symbol
    )

    if not symbol:
        return None

    if symbol.endswith(
        ".SR"
    ):

        return symbol[:-3]

    return symbol


def normalize_text(value):

    if not value:
        return ""

    value = html.unescape(
        str(
            value
        )
    )

    value = value.lower()

    value = value.replace(
        "\xa0",
        " "
    )

    value = re.sub(
        r"[_\-/%?=&]+",
        " ",
        value
    )

    value = re.sub(
        r"\s+",
        " ",
        value
    )

    return value.strip()


def normalize_url(url):

    if not url:
        return None

    return html.unescape(
        str(
            url
        ).strip()
    )


def canonical_url(url):

    url = normalize_url(
        url
    )

    if not url:
        return None

    try:

        parsed = urllib.parse.urlsplit(
            url
        )

        cleaned = urllib.parse.urlunsplit(
            (
                parsed.scheme,
                parsed.netloc,
                parsed.path,
                parsed.query,
                ""
            )
        )

        path = urllib.parse.urlsplit(
            cleaned
        ).path

        if (
            cleaned.endswith("/")
            and len(path) > 1
        ):

            cleaned = cleaned.rstrip(
                "/"
            )

        return cleaned

    except Exception:

        return url


def is_http_url(url):

    if not url:
        return False

    value = str(
        url
    ).lower()

    return (
        value.startswith(
            "https://"
        )
        or value.startswith(
            "http://"
        )
    )


def absolute_url(
    base_url,
    target_url
):

    if not target_url:
        return None

    return urllib.parse.urljoin(
        base_url,
        target_url
    )


def get_domain(url):

    if not url:
        return None

    try:

        domain = (
            urllib.parse.urlparse(
                url
            )
            .netloc
            .lower()
        )

        return domain.replace(
            "www.",
            ""
        )

    except Exception:

        return None


def same_domain(
    url_a,
    url_b
):

    a = get_domain(
        url_a
    )

    b = get_domain(
        url_b
    )

    if not a or not b:
        return False

    return (
        a == b
        or a.endswith(
            "." + b
        )
        or b.endswith(
            "." + a
        )
    )


def looks_like_pdf(url):

    if not url:
        return False

    value = str(
        url
    ).lower()

    return (
        ".pdf" in value
        or "/fspdf/" in value
        or "/resources/" in value
        or "/media/" in value
    )


# ============================================================
# Registry
# ============================================================


def find_registry_file():

    candidates = [

        Path(
            __file__
        ).resolve().parent
        / REGISTRY_FILENAME,

        Path.cwd()
        / REGISTRY_FILENAME
    ]


    for candidate in candidates:

        candidate = candidate.resolve()

        if candidate.exists():

            return candidate


    raise RuntimeError(
        f"{REGISTRY_FILENAME} not found"
    )


def load_registry():

    path = find_registry_file()


    with path.open(
        "r",
        encoding="utf-8"
    ) as file:

        data = json.load(
            file
        )


    if not isinstance(
        data,
        dict
    ):

        raise RuntimeError(
            "Registry root must be object"
        )


    if not isinstance(
        data.get(
            "reits"
        ),
        dict
    ):

        raise RuntimeError(
            "Registry reits must be object"
        )


    return (
        data,
        path
    )


# ============================================================
# Active REITs
# ============================================================


def get_active_reits():

    response = (
        supabase
        .table("stocks")
        .select(
            "id,"
            "symbol,"
            "company_name,"
            "analysis_model,"
            "is_active"
        )
        .eq(
            "analysis_model",
            "reit"
        )
        .eq(
            "is_active",
            True
        )
        .order(
            "id"
        )
        .execute()
    )

    return response.data or []


# ============================================================
# HTTP with cache
# ============================================================


def fetch_url(url):

    url = canonical_url(
        url
    )


    if url in HTTP_CACHE:

        cached = HTTP_CACHE[
            url
        ].copy()

        cached[
            "from_cache"
        ] = True

        return cached


    request = urllib.request.Request(
        url,
        headers={
            "User-Agent":
                (
                    "Mozilla/5.0 "
                    "(Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 "
                    "(KHTML, like Gecko) "
                    "Chrome/126 Safari/537.36"
                ),

            "Accept":
                (
                    "text/html,"
                    "application/xhtml+xml,"
                    "application/pdf,"
                    "application/octet-stream,"
                    "*/*;q=0.8"
                ),

            "Accept-Language":
                "ar,en-US;q=0.9,en;q=0.8",

            "Cache-Control":
                "no-cache"
        }
    )


    try:

        with urllib.request.urlopen(
            request,
            timeout=HTTP_TIMEOUT
        ) as response:

            result = {
                "status":
                    "SUCCESS",

                "http_status":
                    getattr(
                        response,
                        "status",
                        200
                    ),

                "content":
                    response.read(),

                "content_type":
                    (
                        response.headers.get(
                            "Content-Type"
                        )
                        or ""
                    ).lower(),

                "final_url":
                    response.geturl(),

                "error":
                    None,

                "from_cache":
                    False
            }


    except urllib.error.HTTPError as error:

        result = {
            "status":
                "HTTP_ERROR",

            "http_status":
                error.code,

            "content":
                None,

            "content_type":
                "",

            "final_url":
                url,

            "error":
                str(
                    error
                ),

            "from_cache":
                False
        }


    except urllib.error.URLError as error:

        result = {
            "status":
                "NETWORK_ERROR",

            "http_status":
                None,

            "content":
                None,

            "content_type":
                "",

            "final_url":
                url,

            "error":
                str(
                    error
                ),

            "from_cache":
                False
        }


    except Exception as error:

        result = {
            "status":
                "ERROR",

            "http_status":
                None,

            "content":
                None,

            "content_type":
                "",

            "final_url":
                url,

            "error":
                (
                    f"{type(error).__name__}: "
                    f"{error}"
                ),

            "from_cache":
                False
        }


    HTTP_CACHE[
        url
    ] = result.copy()


    return result


# ============================================================
# Document Type
# ============================================================


def detect_document_type(
    response
):

    content = (
        response.get(
            "content"
        )
        or b""
    )

    content_type = (
        response.get(
            "content_type"
        )
        or ""
    ).lower()

    final_url = (
        response.get(
            "final_url"
        )
        or ""
    ).lower()


    if (
        "application/pdf"
        in content_type
        or final_url.endswith(
            ".pdf"
        )
        or content.startswith(
            b"%PDF"
        )
    ):

        return "PDF"


    if (
        "text/html"
        in content_type
        or b"<html"
        in content[
            :2000
        ].lower()
    ):

        return "HTML"


    return "UNKNOWN"


# ============================================================
# HTML links with cache
# ============================================================


def extract_links(
    base_url,
    content
):

    base_url = canonical_url(
        base_url
    )


    if base_url in LINK_CACHE:

        return LINK_CACHE[
            base_url
        ]


    try:

        source = content.decode(
            "utf-8",
            errors="replace"
        )

    except Exception:

        return []


    parser = ContextLinkParser()


    try:

        parser.feed(
            source
        )

    except Exception:

        pass


    results = []

    seen = set()


    for item in parser.links[
        :MAX_LINKS_PER_PAGE
    ]:

        raw_url = absolute_url(
            base_url,
            item.get(
                "href"
            )
        )

        url = canonical_url(
            raw_url
        )


        if (
            not url
            or not is_http_url(
                url
            )
            or url in seen
        ):

            continue


        seen.add(
            url
        )


        results.append({
            "url":
                url,

            "anchor_text":
                normalize_text(
                    item.get(
                        "anchor_text"
                    )
                ),

            "context":
                normalize_text(
                    item.get(
                        "context"
                    )
                )
        })


    LINK_CACHE[
        base_url
    ] = results


    return results


# ============================================================
# Metadata
# ============================================================


def company_tokens(
    company_name
):

    text = normalize_text(
        company_name
    )


    ignored = {
        "ريت",
        "reit",
        "reits",
        "fund",
        "صندوق",
        "the",
        "and"
    }


    return [
        token
        for token in re.findall(
            r"[\w\u0600-\u06FF]+",
            text
        )
        if (
            len(token) >= 3
            and token not in ignored
        )
    ]


def report_year(
    period_end
):

    if not period_end:
        return None

    match = re.match(
        r"(\d{4})",
        str(
            period_end
        )
    )

    return (
        match.group(
            1
        )
        if match
        else None
    )


def period_keywords(
    report_type
):

    rt = str(
        report_type
    ).upper()


    mapping = {

        "Q1": [
            "q1",
            "first quarter",
            "quarter 1",
            "march",
            "31 march",
            "03 31",
            "31 03"
        ],

        "Q2": [
            "q2",
            "second quarter",
            "quarter 2",
            "june",
            "30 june",
            "06 30",
            "30 06"
        ],

        "Q3": [
            "q3",
            "third quarter",
            "quarter 3",
            "september",
            "30 september",
            "09 30",
            "30 09"
        ],

        "Q4": [
            "q4",
            "fourth quarter",
            "quarter 4",
            "december",
            "31 december",
            "12 31",
            "31 12"
        ],

        "H1": [
            "h1",
            "semi annual",
            "semiannual",
            "semi annual report",
            "half year",
            "half yearly",
            "six months",
            "6m",
            "june"
        ],

        "FY": [
            "fy",
            "annual",
            "annual report",
            "full year",
            "year end",
            "12m",
            "december"
        ]
    }


    return mapping.get(
        rt,
        []
    )


# ============================================================
# Strict date helpers
# ============================================================


def extract_years(text):

    text = normalize_text(
        text
    )

    years = re.findall(
        r"\b(20\d{2})\b",
        text
    )

    return sorted(
        set(
            years
        )
    )


def strict_year_match(
    period_end,
    url,
    anchor_text,
    context
):

    required_year = report_year(
        period_end
    )


    if not required_year:

        return False


    combined = normalize_text(
        f"{url} {anchor_text} {context}"
    )


    years_found = extract_years(
        combined
    )


    if not years_found:

        return False


    return (
        required_year in years_found
    )


def strict_period_match(
    report_type,
    url,
    anchor_text,
    context
):

    combined = normalize_text(
        f"{url} {anchor_text} {context}"
    )


    rt = str(
        report_type
    ).upper()


    if rt == "Q1":

        positive = any(
            keyword in combined
            for keyword in [
                "q1",
                "first quarter",
                "quarter 1",
                "march",
                "31 march"
            ]
        )


    elif rt == "Q2":

        positive = any(
            keyword in combined
            for keyword in [
                "q2",
                "second quarter",
                "quarter 2",
                "june",
                "30 june"
            ]
        )


    elif rt == "Q3":

        positive = any(
            keyword in combined
            for keyword in [
                "q3",
                "third quarter",
                "quarter 3",
                "september",
                "30 september"
            ]
        )


    elif rt == "Q4":

        positive = any(
            keyword in combined
            for keyword in [
                "q4",
                "fourth quarter",
                "quarter 4",
                "december",
                "31 december"
            ]
        )


    elif rt == "H1":

        positive = any(
            keyword in combined
            for keyword in [
                "h1",
                "semi annual",
                "semiannual",
                "half year",
                "six months",
                "30 june",
                "june"
            ]
        )


    elif rt == "FY":

        positive = any(
            keyword in combined
            for keyword in [
                "fy",
                "annual",
                "annual report",
                "full year",
                "year end",
                "31 december",
                "december"
            ]
        )


    else:

        positive = True


    return positive


# ============================================================
# Vocabulary
# ============================================================


NEGATIVE_KEYWORDS = {

    "fatca",
    "crs",
    "privacy",
    "privacy notice",
    "prospectus",
    "sukuk",
    "tick size",
    "daily report",
    "daily nav",
    "ipo",
    "offering",
    "application form",
    "account opening",
    "cookie",
    "kyc"
}


GENERAL_NAVIGATION_NOISE = {

    "brokerage",
    "faq",
    "contact us",
    "about us",
    "careers",
    "research",
    "awards",
    "organizational chart",
    "shariah",
    "investment banking",
    "open account",
    "eservices",
    "e services"
}


# ============================================================
# Page priority
# ============================================================


def calculate_page_priority(
    symbol,
    company_name,
    report_type,
    period_end,
    url,
    anchor_text,
    context
):

    combined = normalize_text(
        f"{url} {anchor_text} {context}"
    )


    score = 0.0


    if "reit" in combined:

        score += 30


    code = exchange_code(
        symbol
    )


    if (
        code
        and code.lower()
        in combined
    ):

        score += 30


    matched_tokens = sum(
        1
        for token in company_tokens(
            company_name
        )
        if token in combined
    )


    if matched_tokens >= 2:

        score += 35

    elif matched_tokens == 1:

        score += 20


    rt = str(
        report_type
    ).upper()


    if rt.startswith(
        "Q"
    ):

        if any(
            keyword in combined
            for keyword in [
                "announcement",
                "announcements",
                "quarter",
                "quarterly"
            ]
        ):

            score += 60


    elif rt == "H1":

        if any(
            keyword in combined
            for keyword in [
                "semi annual",
                "semiannual",
                "half year",
                "financial statement",
                "financial statements"
            ]
        ):

            score += 65


    elif rt == "FY":

        if any(
            keyword in combined
            for keyword in [
                "annual",
                "annual report",
                "financial statement",
                "financial statements"
            ]
        ):

            score += 65


    if "announcement" in combined:

        score += 35


    if "financial" in combined:

        score += 30


    if "statement" in combined:

        score += 25


    if "report" in combined:

        score += 20


    if "factsheet" in combined:

        score += 10


    year = report_year(
        period_end
    )


    if (
        year
        and year in combined
    ):

        score += 20


    if any(
        keyword in combined
        for keyword in period_keywords(
            report_type
        )
    ):

        score += 25


    if any(
        noise in combined
        for noise in GENERAL_NAVIGATION_NOISE
    ):

        score -= 60


    if any(
        bad in combined
        for bad in NEGATIVE_KEYWORDS
    ):

        score -= 100


    return score


# ============================================================
# Document score
# ============================================================


def calculate_document_score(
    symbol,
    company_name,
    report_type,
    period_end,
    url,
    anchor_text,
    context,
    document_type,
    readable
):

    combined = normalize_text(
        f"{url} {anchor_text} {context}"
    )


    score = 0.0

    reasons = []


    if readable:

        score += 10

        reasons.append(
            "+10 readable"
        )

    else:

        score -= 30

        reasons.append(
            "-30 unreadable"
        )


    if document_type == "PDF":

        score += 10

        reasons.append(
            "+10 PDF"
        )


    code = exchange_code(
        symbol
    )


    if (
        code
        and code.lower()
        in combined
    ):

        score += 20

        reasons.append(
            "+20 symbol"
        )


    matched_tokens = sum(
        1
        for token in company_tokens(
            company_name
        )
        if token in combined
    )


    if matched_tokens >= 2:

        score += 25

        reasons.append(
            "+25 company"
        )

    elif matched_tokens == 1:

        score += 15

        reasons.append(
            "+15 company partial"
        )


    if "reit" in combined:

        score += 15

        reasons.append(
            "+15 REIT"
        )


    required_year = report_year(
        period_end
    )


    if (
        required_year
        and required_year in combined
    ):

        score += 25

        reasons.append(
            "+25 exact year"
        )


    if strict_period_match(
        report_type,
        url,
        anchor_text,
        context
    ):

        score += 25

        reasons.append(
            "+25 period"
        )


    rt = str(
        report_type
    ).upper()


    if rt.startswith(
        "Q"
    ):

        if any(
            keyword in combined
            for keyword in [
                "quarterly",
                "quarterly statement",
                "quarterly report",
                "quarter"
            ]
        ):

            score += 20

            reasons.append(
                "+20 quarterly"
            )


        if "announcement" in combined:

            score += 15

            reasons.append(
                "+15 announcement"
            )


    elif rt == "H1":

        if any(
            keyword in combined
            for keyword in [
                "semi annual",
                "semiannual",
                "half year",
                "six months",
                "interim financial"
            ]
        ):

            score += 25

            reasons.append(
                "+25 H1"
            )


        if (
            "financial statement"
            in combined
            or "financial statements"
            in combined
        ):

            score += 15

            reasons.append(
                "+15 financial"
            )


    elif rt == "FY":

        if any(
            keyword in combined
            for keyword in [
                "annual",
                "annual report",
                "full year",
                "year end"
            ]
        ):

            score += 25

            reasons.append(
                "+25 FY"
            )


    if (
        "financial statement"
        in combined
        or "financial statements"
        in combined
    ):

        score += 10

        reasons.append(
            "+10 statement"
        )


    if "report" in combined:

        score += 5

        reasons.append(
            "+5 report"
        )


    negative_hits = [
        item
        for item in NEGATIVE_KEYWORDS
        if item in combined
    ]


    if negative_hits:

        penalty = min(
            100,
            60
            + 10 * len(
                negative_hits
            )
        )

        score -= penalty

        reasons.append(
            f"-{penalty} unrelated"
        )


    if (
        "prospectus" in combined
        or "sukuk" in combined
    ):

        score = min(
            score,
            20
        )

        reasons.append(
            "hard-cap prospectus/sukuk"
        )


    # ========================================================
    # STRICT YEAR GATE
    # ========================================================

    year_ok = strict_year_match(
        period_end,
        url,
        anchor_text,
        context
    )


    period_ok = strict_period_match(
        report_type,
        url,
        anchor_text,
        context
    )


    if not year_ok:

        score = min(
            score,
            45.0
        )

        reasons.append(
            "YEAR_GATE_FAIL"
        )


    if not period_ok:

        score = min(
            score,
            55.0
        )

        reasons.append(
            "PERIOD_GATE_FAIL"
        )


    score = max(
        0.0,
        min(
            100.0,
            score
        )
    )


    return (
        score,
        reasons,
        year_ok,
        period_ok
    )


# ============================================================
# Crawl
# ============================================================


def crawl_manager_site(
    symbol,
    company_name,
    report_type,
    period_end,
    start_urls
):

    queue = []

    sequence = 0

    visited = set()

    pages = []

    page_candidates = []

    document_candidates = []


    for url in start_urls:

        url = canonical_url(
            url
        )

        if not url:
            continue


        heapq.heappush(
            queue,
            (
                -1000.0,
                sequence,
                0,
                url,
                "",
                ""
            )
        )

        sequence += 1


    while (
        queue
        and len(
            visited
        ) < MAX_PAGES
    ):

        (
            negative_priority,
            _sequence,
            depth,
            url,
            incoming_anchor,
            incoming_context
        ) = heapq.heappop(
            queue
        )


        url = canonical_url(
            url
        )


        if (
            not url
            or url in visited
        ):

            continue


        visited.add(
            url
        )


        response = fetch_url(
            url
        )


        cache_text = (
            "CACHE"
            if response.get(
                "from_cache"
            )
            else "LIVE"
        )


        print(
            f"🌐 Crawl "
            f"{len(visited)}/{MAX_PAGES} | "
            f"{cache_text} | "
            f"Depth={depth} | "
            f"{url}",
            flush=True
        )


        if response[
            "status"
        ] != "SUCCESS":

            continue


        document_type = (
            detect_document_type(
                response
            )
        )


        if document_type != "HTML":

            document_candidates.append({
                "url":
                    url,

                "anchor_text":
                    incoming_anchor,

                "context":
                    incoming_context,

                "origin":
                    f"crawl_direct_depth_{depth}"
            })

            continue


        pages.append({
            "url":
                url,

            "depth":
                depth,

            "priority":
                -negative_priority,

            "anchor_text":
                incoming_anchor,

            "context":
                incoming_context
        })


        page_score = (
            calculate_page_priority(
                symbol,
                company_name,
                report_type,
                period_end,
                url,
                incoming_anchor,
                incoming_context
            )
        )


        if page_score >= 25:

            page_candidates.append({
                "url":
                    url,

                "anchor_text":
                    incoming_anchor,

                "context":
                    incoming_context,

                "origin":
                    f"page_depth_{depth}"
            })


        links = extract_links(
            response.get(
                "final_url"
            )
            or url,
            response[
                "content"
            ]
        )


        ranked_links = []


        for link in links:

            link_url = canonical_url(
                link[
                    "url"
                ]
            )


            if not link_url:
                continue


            if not same_domain(
                url,
                link_url
            ):

                continue


            if link_url == url:
                continue


            priority = (
                calculate_page_priority(
                    symbol,
                    company_name,
                    report_type,
                    period_end,
                    link_url,
                    link[
                        "anchor_text"
                    ],
                    link[
                        "context"
                    ]
                )
            )


            ranked_links.append({
                "url":
                    link_url,

                "anchor_text":
                    link[
                        "anchor_text"
                    ],

                "context":
                    link[
                        "context"
                    ],

                "priority":
                    priority
            })


        ranked_links.sort(
            key=lambda item:
                item[
                    "priority"
                ],
            reverse=True
        )


        for link in ranked_links:

            link_url = link[
                "url"
            ]

            anchor = link[
                "anchor_text"
            ]

            context = link[
                "context"
            ]

            combined = normalize_text(
                f"{link_url} {anchor} {context}"
            )


            potential_document = (
                looks_like_pdf(
                    link_url
                )
                or any(
                    keyword in combined
                    for keyword in [
                        "quarter",
                        "quarterly",
                        "financial",
                        "statement",
                        "report",
                        "semi annual",
                        "semiannual",
                        "annual",
                        "announcement",
                        "announcements",
                        "factsheet",
                        "fact sheet",
                        "here"
                    ]
                )
            )


            if potential_document:

                document_candidates.append({
                    "url":
                        link_url,

                    "anchor_text":
                        anchor,

                    "context":
                        context,

                    "origin":
                        f"link_depth_{depth}"
                })


            if depth >= MAX_CRAWL_DEPTH:

                continue


            if looks_like_pdf(
                link_url
            ):

                continue


            if link[
                "priority"
            ] < 10:

                continue


            if link_url in visited:

                continue


            heapq.heappush(
                queue,
                (
                    -link[
                        "priority"
                    ],
                    sequence,
                    depth + 1,
                    link_url,
                    anchor,
                    context
                )
            )

            sequence += 1


    return (
        pages,
        page_candidates,
        document_candidates
    )


# ============================================================
# Manager starts
# ============================================================


def get_manager_starts(
    entry
):

    starts = []


    sources = entry.get(
        "sources",
        []
    )


    if not isinstance(
        sources,
        list
    ):

        return starts


    sorted_sources = sorted(
        [
            source
            for source in sources
            if isinstance(
                source,
                dict
            )
        ],
        key=lambda source:
            source.get(
                "priority",
                999
            )
    )


    for source in sorted_sources:

        if source.get(
            "source_type"
        ) != "fund_manager":

            continue


        url = canonical_url(
            source.get(
                "url"
            )
        )


        if url:

            starts.append(
                url
            )


    return starts


# ============================================================
# Dedupe
# ============================================================


def dedupe_candidates(
    candidates
):

    unique = {}


    for item in candidates:

        url = canonical_url(
            item.get(
                "url"
            )
        )


        if not url:
            continue


        item[
            "url"
        ] = url


        existing = unique.get(
            url
        )


        if existing is None:

            unique[
                url
            ] = item

            continue


        current_text = normalize_text(
            f"{item.get('anchor_text', '')} "
            f"{item.get('context', '')}"
        )

        old_text = normalize_text(
            f"{existing.get('anchor_text', '')} "
            f"{existing.get('context', '')}"
        )


        # بدل الاحتفاظ فقط بالأطول،
        # نفضّل السياق الذي يحتوي سنة التقرير المطلوبة.

        required_year = report_year(
            item.get(
                "_period_end"
            )
        )


        current_has_year = (
            required_year
            and required_year
            in current_text
        )

        old_has_year = (
            required_year
            and required_year
            in old_text
        )


        if (
            current_has_year
            and not old_has_year
        ):

            unique[
                url
            ] = item

        elif (
            current_has_year
            == old_has_year
            and len(
                current_text
            ) > len(
                old_text
            )
        ):

            unique[
                url
            ] = item


    return list(
        unique.values()
    )


# ============================================================
# Inspect
# ============================================================


def inspect_candidate(
    symbol,
    company_name,
    report_type,
    period_end,
    item
):

    response = fetch_url(
        item[
            "url"
        ]
    )


    readable = (
        response[
            "status"
        ]
        == "SUCCESS"
    )


    document_type = (
        detect_document_type(
            response
        )
        if readable
        else None
    )


    (
        score,
        reasons,
        year_ok,
        period_ok
    ) = calculate_document_score(
        symbol,
        company_name,
        report_type,
        period_end,
        item[
            "url"
        ],
        item.get(
            "anchor_text",
            ""
        ),
        item.get(
            "context",
            ""
        ),
        document_type,
        readable
    )


    return {
        "url":
            item[
                "url"
            ],

        "anchor_text":
            item.get(
                "anchor_text",
                ""
            ),

        "context":
            item.get(
                "context",
                ""
            ),

        "origin":
            item.get(
                "origin"
            ),

        "status":
            response[
                "status"
            ],

        "http_status":
            response.get(
                "http_status"
            ),

        "document_type":
            document_type,

        "relevance_score":
            score,

        "year_match":
            year_ok,

        "period_match":
            period_ok,

        "from_cache":
            response.get(
                "from_cache",
                False
            ),

        "reasons":
            reasons,

        "error":
            response.get(
                "error"
            )
    }


# ============================================================
# Discover one report
# ============================================================


def discover_report(
    symbol,
    company_name,
    entry,
    report
):

    report_type = report.get(
        "report_type"
    )

    period_end = report.get(
        "period_end"
    )


    manager_starts = (
        get_manager_starts(
            entry
        )
    )


    if not manager_starts:

        return {
            "symbol":
                symbol,

            "company_name":
                company_name,

            "report_type":
                report_type,

            "period_end":
                period_end,

            "discovery_state":
                "NO_MANAGER_SOURCE",

            "best_url":
                None,

            "best_score":
                None,

            "best_document_type":
                None,

            "best_anchor_text":
                None,

            "best_context":
                None,

            "pages_crawled":
                [],

            "attempts":
                []
        }


    (
        pages,
        page_candidates,
        document_candidates
    ) = crawl_manager_site(
        symbol,
        company_name,
        report_type,
        period_end,
        manager_starts
    )


    # ========================================================
    # Registry URLs
    # ========================================================

    for field in [
        "url",
        "alternate_url",
        "attachment_url"
    ]:

        value = report.get(
            field
        )


        if not value:
            continue


        document_candidates.append({
            "url":
                canonical_url(
                    value
                ),

            "anchor_text":
                "",

            "context":
                "",

            "origin":
                f"registry:{field}"
        })


    all_candidates = (
        page_candidates
        + document_candidates
    )


    # تمرير period_end للـdedupe
    for item in all_candidates:

        item[
            "_period_end"
        ] = period_end


    all_candidates = (
        dedupe_candidates(
            all_candidates
        )
    )


    # ========================================================
    # Pre-rank
    # ========================================================

    pre_ranked = []


    for item in all_candidates:

        probable_type = (
            "PDF"
            if looks_like_pdf(
                item[
                    "url"
                ]
            )
            else "HTML"
        )


        (
            pre_score,
            _,
            year_ok,
            period_ok
        ) = calculate_document_score(
            symbol,
            company_name,
            report_type,
            period_end,
            item[
                "url"
            ],
            item.get(
                "anchor_text",
                ""
            ),
            item.get(
                "context",
                ""
            ),
            probable_type,
            True
        )


        item[
            "pre_score"
        ] = pre_score

        item[
            "pre_year_ok"
        ] = year_ok

        item[
            "pre_period_ok"
        ] = period_ok


        pre_ranked.append(
            item
        )


    pre_ranked.sort(
        key=lambda item: (
            item[
                "pre_year_ok"
            ],
            item[
                "pre_period_ok"
            ],
            item[
                "pre_score"
            ]
        ),
        reverse=True
    )


    pre_ranked = pre_ranked[
        :MAX_DOCUMENT_CHECKS
    ]


    # ========================================================
    # Fetch + verify
    # ========================================================

    attempts = []

    early_best = None


    for index, item in enumerate(
        pre_ranked,
        start=1
    ):

        print(
            f"📄 Verify "
            f"{index}/{len(pre_ranked)} | "
            f"PreScore="
            f"{item['pre_score']:.2f} | "
            f"YearOK="
            f"{item['pre_year_ok']} | "
            f"PeriodOK="
            f"{item['pre_period_ok']} | "
            f"{item['url']}",
            flush=True
        )


        result = inspect_candidate(
            symbol,
            company_name,
            report_type,
            period_end,
            item
        )


        attempts.append(
            result
        )


        if (
            result[
                "status"
            ]
            == "SUCCESS"
            and result[
                "year_match"
            ]
            and result[
                "period_match"
            ]
            and result[
                "relevance_score"
            ]
            >= EARLY_STOP_SCORE
        ):

            early_best = result

            print(
                f"🚀 EARLY STOP | "
                f"Verified date + period | "
                f"Score="
                f"{result['relevance_score']:.2f}",
                flush=True
            )

            break


    attempts.sort(
        key=lambda item: (
            item[
                "year_match"
            ],
            item[
                "period_match"
            ],
            item[
                "relevance_score"
            ],
            (
                1
                if item[
                    "document_type"
                ]
                == "PDF"
                else 0
            )
        ),
        reverse=True
    )


    # ========================================================
    # STRICT USABLE
    # ========================================================

    usable = [
        item
        for item in attempts
        if (
            item[
                "status"
            ]
            == "SUCCESS"
            and item[
                "year_match"
            ]
            and item[
                "period_match"
            ]
            and item[
                "relevance_score"
            ]
            >= MIN_ACCEPT_SCORE
        )
    ]


    if early_best is not None:

        best = early_best

    else:

        best = (
            usable[
                0
            ]
            if usable
            else None
        )


    # ========================================================
    # Final state
    # ========================================================

    if best:

        if (
            best[
                "relevance_score"
            ]
            >= STRONG_ACCEPT_SCORE
        ):

            if (
                best[
                    "document_type"
                ]
                == "PDF"
            ):

                state = (
                    "VERIFIED_DOCUMENT_FOUND"
                )

            else:

                state = (
                    "VERIFIED_PAGE_FOUND"
                )

        else:

            state = (
                "CANDIDATE_FOUND_REVIEW"
            )


    elif attempts:

        date_failed = all(
            not item[
                "year_match"
            ]
            for item in attempts
        )


        if date_failed:

            state = (
                "ONLY_OLD_OR_WRONG_YEAR_DOCUMENTS"
            )

        else:

            state = (
                "REIT_PAGE_FOUND_NO_VALID_REPORT"
            )


    elif pages:

        state = (
            "REIT_PAGE_FOUND_NO_REPORT"
        )


    else:

        state = (
            "NOT_FOUND"
        )


    ranked_pages = sorted(
        pages,
        key=lambda item:
            item[
                "priority"
            ],
        reverse=True
    )


    return {
        "symbol":
            symbol,

        "company_name":
            company_name,

        "report_type":
            report_type,

        "period_end":
            period_end,

        "discovery_state":
            state,

        "best_url":
            (
                best[
                    "url"
                ]
                if best
                else None
            ),

        "best_score":
            (
                best[
                    "relevance_score"
                ]
                if best
                else None
            ),

        "best_document_type":
            (
                best[
                    "document_type"
                ]
                if best
                else None
            ),

        "best_anchor_text":
            (
                best[
                    "anchor_text"
                ]
                if best
                else None
            ),

        "best_context":
            (
                best[
                    "context"
                ]
                if best
                else None
            ),

        "pages_crawled":
            ranked_pages,

        "attempts":
            attempts
    }


# ============================================================
# Print
# ============================================================


def print_result(
    result
):

    print_header(
        f"🔎 {result['symbol']} | "
        f"{result['report_type']} | "
        f"{result['period_end']}"
    )


    print(
        f"🏢 Company: "
        f"{result['company_name']}",
        flush=True
    )


    print(
        f"🧭 Discovery State: "
        f"{result['discovery_state']}",
        flush=True
    )


    score_text = (
        f"{result['best_score']:.2f}"
        if result[
            "best_score"
        ] is not None
        else "N/A"
    )


    print(
        f"🎯 Best Score: "
        f"{score_text}",
        flush=True
    )


    print(
        f"📑 Best Type: "
        f"{result['best_document_type'] or 'NONE'}",
        flush=True
    )


    print(
        f"🔗 Best URL: "
        f"{result['best_url'] or 'NONE'}",
        flush=True
    )


    print(
        f"🌐 Pages Crawled: "
        f"{len(result['pages_crawled'])}",
        flush=True
    )


    print(
        f"📄 Checked: "
        f"{len(result['attempts'])}",
        flush=True
    )


    print_separator()


    print(
        "🏅 TOP DOCUMENT CANDIDATES",
        flush=True
    )


    for index, item in enumerate(
        result[
            "attempts"
        ][
            :10
        ],
        start=1
    ):

        context = item.get(
            "context",
            ""
        )


        if len(
            context
        ) > 180:

            context = context[
                -180:
            ]


        print(
            f"{index:02d}. "
            f"Score="
            f"{item['relevance_score']:.2f} | "
            f"YearOK="
            f"{item['year_match']} | "
            f"PeriodOK="
            f"{item['period_match']} | "
            f"Cache="
            f"{item['from_cache']} | "
            f"HTTP="
            f"{item['http_status']} | "
            f"Type="
            f"{item['document_type']} | "
            f"Anchor="
            f"{item['anchor_text'] or 'N/A'} | "
            f"{item['url']}",
            flush=True
        )


        if context:

            print(
                f"    Context: "
                f"{context}",
                flush=True
            )


        print(
            "    Reasons: "
            + ", ".join(
                item[
                    "reasons"
                ]
            ),
            flush=True
        )


# ============================================================
# Summary
# ============================================================


def print_summary(
    results
):

    print_header(
        "🏆 REIT REPORT DISCOVERY SUMMARY v5.2 FAST CACHED"
    )


    states = {}


    for index, result in enumerate(
        results,
        start=1
    ):

        state = result[
            "discovery_state"
        ]


        states[
            state
        ] = (
            states.get(
                state,
                0
            )
            + 1
        )


        score = (
            f"{result['best_score']:.2f}"
            if result[
                "best_score"
            ] is not None
            else "N/A"
        )


        print(
            f"{index:02d}. "
            f"{result['symbol']} | "
            f"{result['report_type']} | "
            f"{result['period_end']} | "
            f"State="
            f"{state} | "
            f"Score="
            f"{score} | "
            f"Type="
            f"{result['best_document_type']} | "
            f"Pages="
            f"{len(result['pages_crawled'])} | "
            f"Checked="
            f"{len(result['attempts'])}",
            flush=True
        )


    print_separator()


    print(
        f"📄 Total Reports: "
        f"{len(results)}",
        flush=True
    )


    print(
        f"🧠 HTTP Cache Entries: "
        f"{len(HTTP_CACHE)}",
        flush=True
    )


    print(
        f"🔗 Link Cache Entries: "
        f"{len(LINK_CACHE)}",
        flush=True
    )


    print(
        "\n📊 STATES",
        flush=True
    )


    for state, count in sorted(
        states.items()
    ):

        print(
            f"- {state}: "
            f"{count}",
            flush=True
        )


    print(
        "=" * 118,
        flush=True
    )


# ============================================================
# Main
# ============================================================


def run_discovery():

    print_header(
        ENGINE_NAME
    )


    print(
        "🔒 Mode: READ ONLY",
        flush=True
    )


    print(
        f"🕐 Started: "
        f"{datetime.now(timezone.utc).isoformat()}",
        flush=True
    )


    print(
        f"⏱ HTTP Timeout: "
        f"{HTTP_TIMEOUT}s",
        flush=True
    )


    print(
        f"🌐 Max Pages: "
        f"{MAX_PAGES}",
        flush=True
    )


    print(
        f"📄 Max Checks: "
        f"{MAX_DOCUMENT_CHECKS}",
        flush=True
    )


    print(
        "🔐 Strict Year Match: ENABLED",
        flush=True
    )


    registry, registry_path = (
        load_registry()
    )


    print(
        f"📁 Registry: "
        f"{registry_path}",
        flush=True
    )


    active_reits = (
        get_active_reits()
    )


    active_map = {

        normalize_symbol(
            stock[
                "symbol"
            ]
        ):
            stock

        for stock in active_reits
    }


    print(
        f"🏢 Active REITs: "
        f"{len(active_map)}",
        flush=True
    )


    results = []


    for symbol, entry in (
        registry[
            "reits"
        ].items()
    ):

        symbol = normalize_symbol(
            symbol
        )


        if symbol not in active_map:

            continue


        company_name = (
            entry.get(
                "company_name"
            )
            or active_map[
                symbol
            ].get(
                "company_name"
            )
            or symbol
        )


        reports = entry.get(
            "reports",
            []
        )


        if not isinstance(
            reports,
            list
        ):

            continue


        for report in reports:

            if not isinstance(
                report,
                dict
            ):

                continue


            result = discover_report(
                symbol,
                company_name,
                entry,
                report
            )


            results.append(
                result
            )


            print_result(
                result
            )


    print_summary(
        results
    )


if __name__ == "__main__":

    run_discovery()
