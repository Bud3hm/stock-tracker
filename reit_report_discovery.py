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
# REIT REPORT DISCOVERY ENGINE v5.3
#
# FAST + CACHED
# STRICT YEAR
# STRICT PERIOD
# STRICT DOCUMENT TYPE
#
# READ ONLY
#
# الهدف:
# 1) منع التقارير القديمة
# 2) منع تقارير التقييم العقاري من المرور كتقرير مالي
# 3) منع Factsheets / NAV / Portfolio من المرور
# 4) Q1/Q2/Q3/Q4 تحتاج Quarterly identity
# 5) H1 يحتاج Semiannual / Interim / Financial identity
# 6) FY يحتاج Annual Financial identity
# 7) HTTP + Link Cache
# 8) Early Stop فقط بعد اجتياز جميع Gates
#
# عام لجميع صناديق REIT
# ============================================================


ENGINE_NAME = (
    "REIT REPORT DISCOVERY ENGINE "
    "v5.3 STRICT DOCUMENT TYPE"
)

REGISTRY_FILENAME = "reit_official_sources.json"

HTTP_TIMEOUT = 8

MAX_CRAWL_DEPTH = 2
MAX_PAGES = 10
MAX_LINKS_PER_PAGE = 140
MAX_DOCUMENT_CHECKS = 25

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


SUPABASE_URL = os.environ.get(
    "SUPABASE_URL"
)

SUPABASE_SECRET_KEY = os.environ.get(
    "SUPABASE_SECRET_KEY"
)


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


class ContextLinkParser(
    HTMLParser
):

    def __init__(self):

        super().__init__()

        self.links = []

        self.recent_text = deque(
            maxlen=20
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


        self.links.append(
            {
                "href":
                    self.current_href,

                "anchor_text":
                    " ".join(
                        self.current_anchor
                    ),

                "context":
                    self.before_context
            }
        )


        self.current_href = None
        self.current_anchor = []
        self.before_context = ""


# ============================================================
# Print
# ============================================================


def print_header(
    title
):

    print(
        "\n"
        + "=" * 120,
        flush=True
    )

    print(
        title,
        flush=True
    )

    print(
        "=" * 120,
        flush=True
    )


def print_separator():

    print(
        "-" * 120,
        flush=True
    )


# ============================================================
# Normalize
# ============================================================


def normalize_symbol(
    symbol
):

    if not symbol:

        return None


    return str(
        symbol
    ).strip().upper()


def exchange_code(
    symbol
):

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


def normalize_text(
    value
):

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


def normalize_url(
    url
):

    if not url:

        return None


    return html.unescape(
        str(
            url
        ).strip()
    )


def canonical_url(
    url
):

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
            and len(
                path
            ) > 1
        ):

            cleaned = cleaned.rstrip(
                "/"
            )


        return cleaned


    except Exception:

        return url


def is_http_url(
    url
):

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


def get_domain(
    url
):

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


def looks_like_pdf(
    url
):

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

        (
            Path(
                __file__
            )
            .resolve()
            .parent
            / REGISTRY_FILENAME
        ),

        (
            Path.cwd()
            / REGISTRY_FILENAME
        )
    ]


    for candidate in candidates:

        candidate = (
            candidate.resolve()
        )


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
        .table(
            "stocks"
        )
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
# HTTP cache
# ============================================================


def fetch_url(
    url
):

    url = canonical_url(
        url
    )


    if url in HTTP_CACHE:

        result = (
            HTTP_CACHE[
                url
            ].copy()
        )

        result[
            "from_cache"
        ] = True

        return result


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
                "ar,en-US;q=0.9,en;q=0.8"
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
# Document type
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
# Link cache
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


        results.append(
            {
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
            }
        )


    LINK_CACHE[
        base_url
    ] = results


    return results


# ============================================================
# Company metadata
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
            len(
                token
            ) >= 3
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


def extract_years(
    text
):

    return sorted(
        set(
            re.findall(
                r"\b(20\d{2})\b",
                normalize_text(
                    text
                )
            )
        )
    )


# ============================================================
# Period keywords
# ============================================================


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
            "31 march"
        ],

        "Q2": [
            "q2",
            "second quarter",
            "quarter 2",
            "june",
            "30 june"
        ],

        "Q3": [
            "q3",
            "third quarter",
            "quarter 3",
            "september",
            "30 september"
        ],

        "Q4": [
            "q4",
            "fourth quarter",
            "quarter 4",
            "december",
            "31 december"
        ],

        "H1": [
            "h1",
            "semi annual",
            "semiannual",
            "half year",
            "six months",
            "30 june",
            "june"
        ],

        "FY": [
            "fy",
            "annual",
            "annual report",
            "full year",
            "year end",
            "31 december"
        ]
    }


    return mapping.get(
        rt,
        []
    )


# ============================================================
# Hard reject vocabulary
# ============================================================


HARD_REJECT_DOCUMENT_TYPES = {

    "valuation",
    "valuation report",
    "valuation reports",
    "property valuation",
    "property valuation report",
    "appraisal",
    "appraisal report",

    "portfolio",
    "portfolio report",

    "factsheet",
    "fact sheet",

    "nav report",
    "daily nav",
    "daily nav report",

    "prospectus",
    "sukuk",
    "offering",

    "fatca",
    "crs",
    "privacy",
    "tick size"
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
    "eservices"
}


# ============================================================
# Strict gates
# ============================================================


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


    years = extract_years(
        combined
    )


    if not years:

        return False


    return (
        required_year in years
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


    return any(
        keyword in combined

        for keyword in period_keywords(
            report_type
        )
    )


def hard_reject_document(
    url,
    anchor_text,
    context
):

    combined = normalize_text(
        f"{url} {anchor_text} {context}"
    )


    matches = [
        keyword

        for keyword in HARD_REJECT_DOCUMENT_TYPES

        if keyword in combined
    ]


    return (
        bool(
            matches
        ),
        matches
    )


def strict_document_type_match(
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


    # ========================================================
    # Quarterly
    # ========================================================

    if rt in {
        "Q1",
        "Q2",
        "Q3",
        "Q4"
    }:

        required_identity = any(
            keyword in combined

            for keyword in [
                "quarterly",
                "quarterly statement",
                "quarterly report",
                "quarterly financial",
                "quarter statement"
            ]
        )


        return required_identity


    # ========================================================
    # H1
    # ========================================================

    if rt == "H1":

        required_identity = any(
            keyword in combined

            for keyword in [
                "semi annual",
                "semiannual",
                "semi annual report",
                "half year",
                "half yearly",
                "six months",
                "interim financial",
                "interim financial statement",
                "interim financial statements"
            ]
        )


        financial_identity = any(
            keyword in combined

            for keyword in [
                "financial statement",
                "financial statements",
                "financial report",
                "interim"
            ]
        )


        return (
            required_identity
            or (
                financial_identity
                and "june" in combined
            )
        )


    # ========================================================
    # FY
    # ========================================================

    if rt == "FY":

        return any(
            keyword in combined

            for keyword in [
                "annual financial",
                "annual report",
                "annual financial statement",
                "annual financial statements",
                "audited financial",
                "audited financial statement",
                "audited financial statements",
                "full year financial"
            ]
        )


    return False


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

        if "announcement" in combined:

            score += 70


        if "quarter" in combined:

            score += 70


    elif rt == "H1":

        if any(
            keyword in combined

            for keyword in [
                "semi annual",
                "semiannual",
                "financial statement",
                "financial statements"
            ]
        ):

            score += 80


    elif rt == "FY":

        if any(
            keyword in combined

            for keyword in [
                "annual report",
                "financial statement",
                "financial statements"
            ]
        ):

            score += 80


    if "financial" in combined:

        score += 30


    if "statement" in combined:

        score += 30


    if "report" in combined:

        score += 15


    year = report_year(
        period_end
    )


    if (
        year
        and year in combined
    ):

        score += 25


    if any(
        keyword in combined

        for keyword in period_keywords(
            report_type
        )
    ):

        score += 25


    rejected, _ = hard_reject_document(
        url,
        anchor_text,
        context
    )


    if rejected:

        score -= 200


    if any(
        noise in combined

        for noise in GENERAL_NAVIGATION_NOISE
    ):

        score -= 70


    return score


# ============================================================
# Document score + gates
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


    # ========================================================
    # Gates
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


    document_type_ok = strict_document_type_match(
        report_type,
        url,
        anchor_text,
        context
    )


    hard_reject, reject_reasons = hard_reject_document(
        url,
        anchor_text,
        context
    )


    # ========================================================
    # Base score
    # ========================================================

    if readable:

        score += 10

        reasons.append(
            "+10 readable"
        )


    if document_type == "PDF":

        score += 10

        reasons.append(
            "+10 PDF"
        )


    if "reit" in combined:

        score += 15

        reasons.append(
            "+15 REIT"
        )


    matched_tokens = sum(
        1

        for token in company_tokens(
            company_name
        )

        if token in combined
    )


    if matched_tokens >= 2:

        score += 20

        reasons.append(
            "+20 company"
        )

    elif matched_tokens == 1:

        score += 10

        reasons.append(
            "+10 company partial"
        )


    if year_ok:

        score += 25

        reasons.append(
            "+25 exact year"
        )


    if period_ok:

        score += 20

        reasons.append(
            "+20 period"
        )


    if document_type_ok:

        score += 30

        reasons.append(
            "+30 document type"
        )


    if (
        "financial statement"
        in combined
        or "financial statements"
        in combined
    ):

        score += 10

        reasons.append(
            "+10 financial statement"
        )


    if "quarterly" in combined:

        score += 10

        reasons.append(
            "+10 quarterly"
        )


    if (
        "semi annual" in combined
        or "semiannual" in combined
    ):

        score += 10

        reasons.append(
            "+10 semiannual"
        )


    # ========================================================
    # Hard reject
    # ========================================================

    if hard_reject:

        score = 0.0

        reasons.append(
            "HARD_REJECT="
            + ",".join(
                reject_reasons
            )
        )


    # ========================================================
    # Mandatory gates
    # ========================================================

    if not year_ok:

        score = min(
            score,
            45
        )

        reasons.append(
            "YEAR_GATE_FAIL"
        )


    if not period_ok:

        score = min(
            score,
            50
        )

        reasons.append(
            "PERIOD_GATE_FAIL"
        )


    if not document_type_ok:

        score = min(
            score,
            40
        )

        reasons.append(
            "DOCUMENT_TYPE_GATE_FAIL"
        )


    score = max(
        0.0,
        min(
            100.0,
            score
        )
    )


    return {
        "score":
            score,

        "reasons":
            reasons,

        "year_ok":
            year_ok,

        "period_ok":
            period_ok,

        "document_type_ok":
            document_type_ok,

        "hard_reject":
            hard_reject,

        "hard_reject_reasons":
            reject_reasons
    }


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


        if url in visited:

            continue


        visited.add(
            url
        )


        response = fetch_url(
            url
        )


        cache_state = (
            "CACHE"
            if response.get(
                "from_cache"
            )
            else "LIVE"
        )


        print(
            f"🌐 Crawl "
            f"{len(visited)}/{MAX_PAGES} | "
            f"{cache_state} | "
            f"Depth={depth} | "
            f"{url}",
            flush=True
        )


        if response[
            "status"
        ] != "SUCCESS":

            continue


        detected = detect_document_type(
            response
        )


        if detected != "HTML":

            document_candidates.append(
                {
                    "url":
                        url,

                    "anchor_text":
                        incoming_anchor,

                    "context":
                        incoming_context,

                    "origin":
                        f"crawl_direct_depth_{depth}"
                }
            )

            continue


        pages.append(
            {
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
            }
        )


        page_priority = calculate_page_priority(
            symbol,
            company_name,
            report_type,
            period_end,
            url,
            incoming_anchor,
            incoming_context
        )


        if page_priority >= 25:

            page_candidates.append(
                {
                    "url":
                        url,

                    "anchor_text":
                        incoming_anchor,

                    "context":
                        incoming_context,

                    "origin":
                        f"page_depth_{depth}"
                }
            )


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


            priority = calculate_page_priority(
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


            ranked_links.append(
                {
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
                }
            )


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
                f"{link_url} "
                f"{anchor} "
                f"{context}"
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
                        "semi annual",
                        "semiannual",
                        "interim",
                        "annual report",
                        "announcement",
                        "announcements",
                        "report",
                        "here"
                    ]
                )
            )


            if potential_document:

                document_candidates.append(
                    {
                        "url":
                            link_url,

                        "anchor_text":
                            anchor,

                        "context":
                            context,

                        "origin":
                            f"link_depth_{depth}"
                    }
                )


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
# Manager source
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


    sources = sorted(
        [
            item

            for item in sources

            if isinstance(
                item,
                dict
            )
        ],
        key=lambda item:
            item.get(
                "priority",
                999
            )
    )


    for source in sources:

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
    candidates,
    period_end
):

    unique = {}

    required_year = report_year(
        period_end
    )


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


        combined = normalize_text(
            f"{item.get('anchor_text', '')} "
            f"{item.get('context', '')}"
        )


        item_year_match = (
            required_year
            and required_year in combined
        )


        existing = unique.get(
            url
        )


        if existing is None:

            unique[
                url
            ] = item

            continue


        old_combined = normalize_text(
            f"{existing.get('anchor_text', '')} "
            f"{existing.get('context', '')}"
        )


        old_year_match = (
            required_year
            and required_year in old_combined
        )


        if (
            item_year_match
            and not old_year_match
        ):

            unique[
                url
            ] = item


        elif (
            item_year_match
            == old_year_match
            and len(
                combined
            )
            > len(
                old_combined
            )
        ):

            unique[
                url
            ] = item


    return list(
        unique.values()
    )


# ============================================================
# Inspect candidate
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


    doc_type = (
        detect_document_type(
            response
        )
        if readable
        else None
    )


    validation = calculate_document_score(
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
        doc_type,
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
            doc_type,

        "relevance_score":
            validation[
                "score"
            ],

        "year_match":
            validation[
                "year_ok"
            ],

        "period_match":
            validation[
                "period_ok"
            ],

        "document_type_match":
            validation[
                "document_type_ok"
            ],

        "hard_reject":
            validation[
                "hard_reject"
            ],

        "hard_reject_reasons":
            validation[
                "hard_reject_reasons"
            ],

        "from_cache":
            response.get(
                "from_cache",
                False
            ),

        "reasons":
            validation[
                "reasons"
            ]
    }


# ============================================================
# Discover report
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


    manager_starts = get_manager_starts(
        entry
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
    # Registry report links
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


        document_candidates.append(
            {
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
            }
        )


    candidates = (
        page_candidates
        + document_candidates
    )


    candidates = dedupe_candidates(
        candidates,
        period_end
    )


    # ========================================================
    # Pre-rank
    # ========================================================

    pre_ranked = []


    for item in candidates:

        probable_type = (
            "PDF"
            if looks_like_pdf(
                item[
                    "url"
                ]
            )
            else "HTML"
        )


        validation = calculate_document_score(
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
        ] = validation[
            "score"
        ]


        item[
            "pre_year_ok"
        ] = validation[
            "year_ok"
        ]


        item[
            "pre_period_ok"
        ] = validation[
            "period_ok"
        ]


        item[
            "pre_doc_type_ok"
        ] = validation[
            "document_type_ok"
        ]


        item[
            "pre_hard_reject"
        ] = validation[
            "hard_reject"
        ]


        pre_ranked.append(
            item
        )


    pre_ranked.sort(
        key=lambda item: (
            not item[
                "pre_hard_reject"
            ],
            item[
                "pre_year_ok"
            ],
            item[
                "pre_period_ok"
            ],
            item[
                "pre_doc_type_ok"
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
    # Verify
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
            f"Year="
            f"{item['pre_year_ok']} | "
            f"Period="
            f"{item['pre_period_ok']} | "
            f"DocType="
            f"{item['pre_doc_type_ok']} | "
            f"Reject="
            f"{item['pre_hard_reject']} | "
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


        # ====================================================
        # EARLY STOP
        # ====================================================

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
                "document_type_match"
            ]
            and not result[
                "hard_reject"
            ]
            and result[
                "relevance_score"
            ]
            >= EARLY_STOP_SCORE
        ):

            early_best = result


            print(
                "🚀 EARLY STOP | "
                "All strict gates passed | "
                f"Score="
                f"{result['relevance_score']:.2f}",
                flush=True
            )


            break


    attempts.sort(
        key=lambda item: (
            not item[
                "hard_reject"
            ],
            item[
                "year_match"
            ],
            item[
                "period_match"
            ],
            item[
                "document_type_match"
            ],
            item[
                "relevance_score"
            ]
        ),
        reverse=True
    )


    # ========================================================
    # Strict usable candidates
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
                "document_type_match"
            ]

            and not item[
                "hard_reject"
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
    # State
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

        if all(
            item[
                "hard_reject"
            ]
            for item in attempts
        ):

            state = (
                "ONLY_WRONG_DOCUMENT_TYPES"
            )


        elif all(
            not item[
                "year_match"
            ]
            for item in attempts
        ):

            state = (
                "ONLY_OLD_OR_WRONG_YEAR_DOCUMENTS"
            )


        elif all(
            not item[
                "document_type_match"
            ]
            for item in attempts
        ):

            state = (
                "NO_VALID_FINANCIAL_DOCUMENT_TYPE"
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


    pages = sorted(
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

        "pages_crawled":
            pages,

        "attempts":
            attempts
    }


# ============================================================
# Print result
# ============================================================


def print_result(
    result
):

    print_header(
        f"🔎 "
        f"{result['symbol']} | "
        f"{result['report_type']} | "
        f"{result['period_end']}"
    )


    print(
        f"🧭 State: "
        f"{result['discovery_state']}",
        flush=True
    )


    print(
        f"🎯 Score: "
        f"{result['best_score'] if result['best_score'] is not None else 'N/A'}",
        flush=True
    )


    print(
        f"📑 Type: "
        f"{result['best_document_type'] or 'NONE'}",
        flush=True
    )


    print(
        f"🔗 URL: "
        f"{result['best_url'] or 'NONE'}",
        flush=True
    )


    print(
        f"🌐 Pages: "
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

        print(
            f"{index:02d}. "
            f"Score="
            f"{item['relevance_score']:.2f} | "
            f"YearOK="
            f"{item['year_match']} | "
            f"PeriodOK="
            f"{item['period_match']} | "
            f"DocTypeOK="
            f"{item['document_type_match']} | "
            f"HardReject="
            f"{item['hard_reject']} | "
            f"HTTP="
            f"{item['http_status']} | "
            f"Type="
            f"{item['document_type']} | "
            f"{item['url']}",
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
        "🏆 REIT REPORT DISCOVERY SUMMARY v5.3"
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
        f"🧠 HTTP Cache: "
        f"{len(HTTP_CACHE)}",
        flush=True
    )


    print(
        f"🔗 Link Cache: "
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
        "=" * 120,
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
        "🔐 Strict Year Gate: ON",
        flush=True
    )


    print(
        "🔐 Strict Period Gate: ON",
        flush=True
    )


    print(
        "🔐 Strict Document Type Gate: ON",
        flush=True
    )


    print(
        "🚫 Valuation/Factsheet/NAV Hard Reject: ON",
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
