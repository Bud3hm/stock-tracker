import os
import re
import json
import html
import urllib.error
import urllib.parse
import urllib.request

from pathlib import Path
from datetime import datetime, timezone
from html.parser import HTMLParser

from supabase import create_client


# ============================================================
# REIT REPORT DISCOVERY ENGINE v2
#
# READ ONLY
#
# الهدف:
# 1) العمل على جميع صناديق REIT النشطة
# 2) اكتشاف التقارير الرسمية/مدير الصندوق
# 3) منع اعتماد أي PDF عشوائي
# 4) حساب Document Relevance Score
# 5) مطابقة:
#       - رمز الصندوق
#       - اسم الصندوق
#       - REIT
#       - السنة
#       - الفترة
#       - نوع التقرير
# 6) استبعاد:
#       FATCA
#       CRS
#       Privacy
#       Daily Reports
#       Tick Size
#       General NAV reports غير الخاصة بالتقرير
# 7) عدم الكتابة في Supabase
#
# عام لكل صناديق REIT.
# ============================================================


ENGINE_NAME = "REIT REPORT DISCOVERY ENGINE v2"

REGISTRY_FILENAME = "reit_official_sources.json"

HTTP_TIMEOUT = 30

MAX_DISCOVERED_URLS = 40

MIN_ACCEPT_SCORE = 55.0
STRONG_ACCEPT_SCORE = 75.0


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
# HTML Parser
# ============================================================


class LinkParser(HTMLParser):

    def __init__(self):

        super().__init__()

        self.links = []


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

        if href:

            self.links.append(
                href
            )


# ============================================================
# أدوات عامة
# ============================================================


def print_header(title):

    print(
        "\n"
        + "=" * 108,
        flush=True
    )

    print(
        title,
        flush=True
    )

    print(
        "=" * 108,
        flush=True
    )


def print_separator():

    print(
        "-" * 108,
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


def normalize_url(url):

    if not url:
        return None

    return html.unescape(
        str(
            url
        ).strip()
    )


def normalize_text(value):

    if not value:
        return ""

    value = html.unescape(
        str(
            value
        )
    )

    value = value.lower()

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
        / REGISTRY_FILENAME,
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
            "Registry root must be an object"
        )


    reits = data.get(
        "reits"
    )


    if not isinstance(
        reits,
        dict
    ):

        raise RuntimeError(
            "Registry 'reits' must be an object"
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
# HTTP
# ============================================================


def build_request(url):

    return urllib.request.Request(
        url,
        headers={
            "User-Agent":
                (
                    "Mozilla/5.0 "
                    "(Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 "
                    "(KHTML, like Gecko) "
                    "Chrome/126.0 Safari/537.36"
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
                "no-cache",
        }
    )


def fetch_url(url):

    request = build_request(
        url
    )


    try:

        with urllib.request.urlopen(
            request,
            timeout=HTTP_TIMEOUT
        ) as response:

            content = response.read()

            content_type = (
                response.headers.get(
                    "Content-Type"
                )
                or ""
            ).lower()


            return {
                "status":
                    "SUCCESS",

                "http_status":
                    getattr(
                        response,
                        "status",
                        200
                    ),

                "content":
                    content,

                "content_type":
                    content_type,

                "final_url":
                    response.geturl(),

                "error":
                    None,
            }


    except urllib.error.HTTPError as error:

        return {
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
        }


    except urllib.error.URLError as error:

        return {
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
        }


    except Exception as error:

        return {
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
        }


# ============================================================
# Document Type
# ============================================================


def detect_document_type(
    response
):

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


    content = (
        response.get(
            "content"
        )
        or b""
    )


    if (
        "application/pdf"
        in content_type
        or looks_like_pdf(
            final_url
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
# Decode HTML
# ============================================================


def decode_html(content):

    if not content:
        return ""

    try:

        return content.decode(
            "utf-8",
            errors="replace"
        )

    except Exception:

        return str(
            content
        )


# ============================================================
# استخراج روابط HTML
# ============================================================


def extract_links_from_html(
    base_url,
    content
):

    text = decode_html(
        content
    )

    parser = LinkParser()


    try:

        parser.feed(
            text
        )

    except Exception:

        pass


    candidates = []


    for href in parser.links:

        full_url = absolute_url(
            base_url,
            href
        )

        if full_url:

            candidates.append(
                full_url
            )


    regex_urls = re.findall(
        r"""https?://[^\s"'<>]+""",
        text,
        flags=re.IGNORECASE
    )


    candidates.extend(
        regex_urls
    )


    relative_pdf = re.findall(
        r"""["']([^"']+\.pdf(?:\?[^"']*)?)["']""",
        text,
        flags=re.IGNORECASE
    )


    for url in relative_pdf:

        candidates.append(
            absolute_url(
                base_url,
                url
            )
        )


    unique = []

    seen = set()


    for url in candidates:

        url = normalize_url(
            url
        )

        if not url:
            continue

        if not is_http_url(
            url
        ):
            continue

        if url in seen:
            continue

        seen.add(
            url
        )

        unique.append(
            url
        )


    return unique


# ============================================================
# Report Metadata
# ============================================================


def get_report_year(
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

    if not match:
        return None

    return match.group(
        1
    )


def get_period_keywords(
    report_type,
    period_end
):

    report_type = (
        str(
            report_type
        )
        .strip()
        .upper()
    )

    keywords = set()

    if report_type == "Q1":

        keywords.update([
            "q1",
            "quarter 1",
            "quarter1",
            "first quarter",
            "3m",
            "31 march",
            "31-03",
            "03-31",
        ])

    elif report_type == "Q2":

        keywords.update([
            "q2",
            "quarter 2",
            "quarter2",
            "second quarter",
            "6m",
            "30 june",
            "30-06",
            "06-30",
        ])

    elif report_type == "Q3":

        keywords.update([
            "q3",
            "quarter 3",
            "quarter3",
            "third quarter",
            "9m",
            "30 september",
            "30-09",
            "09-30",
        ])

    elif report_type == "Q4":

        keywords.update([
            "q4",
            "quarter 4",
            "quarter4",
            "fourth quarter",
            "31 december",
            "31-12",
            "12-31",
        ])

    elif report_type == "H1":

        keywords.update([
            "h1",
            "half year",
            "half-year",
            "semiannual",
            "semi annual",
            "6m",
            "30 june",
            "30-06",
            "06-30",
        ])

    elif report_type == "FY":

        keywords.update([
            "fy",
            "annual",
            "annual report",
            "year end",
            "year-end",
            "12m",
            "31 december",
            "31-12",
            "12-31",
        ])


    if period_end:

        period_text = str(
            period_end
        )

        keywords.add(
            period_text.lower()
        )

        keywords.add(
            period_text.replace(
                "-",
                ""
            ).lower()
        )


    return keywords


# ============================================================
# Positive / Negative vocabulary
# ============================================================


POSITIVE_REIT_KEYWORDS = {
    "reit",
    "real estate investment traded",
    "quarterly statement",
    "quarterly report",
    "financial statement",
    "financial statements",
    "financial report",
    "fund report",
    "rental income",
    "net asset value",
    "nav",
    "distribution",
    "fund",
}


NEGATIVE_KEYWORDS = {
    "fatca",
    "crs",
    "privacy",
    "privacy notice",
    "tick size",
    "tick-size",
    "daily report",
    "daily-report",
    "daily nav",
    "research listing",
    "terms and conditions",
    "disclaimer",
    "cookie",
    "aml",
    "kyc",
    "brochure",
    "application form",
    "account opening",
}


# ============================================================
# Name tokenization
# ============================================================


def company_tokens(
    company_name
):

    text = normalize_text(
        company_name
    )

    tokens = re.findall(
        r"[\w\u0600-\u06FF]+",
        text
    )

    ignored = {
        "ريت",
        "reits",
        "reit",
        "صندوق",
        "fund",
        "the",
        "and",
    }


    return [
        token
        for token in tokens
        if (
            len(token) >= 3
            and token not in ignored
        )
    ]


# ============================================================
# Document Relevance Score
# ============================================================


def calculate_document_relevance(
    symbol,
    company_name,
    report_type,
    period_end,
    url,
    origin,
    document_type,
    readable
):

    score = 0.0

    reasons = []

    text = normalize_text(
        url
    )

    code = exchange_code(
        symbol
    )

    report_year = get_report_year(
        period_end
    )

    period_keywords = (
        get_period_keywords(
            report_type,
            period_end
        )
    )


    # ========================================================
    # Readability
    # ========================================================

    if readable:

        score += 10

        reasons.append(
            "+10 readable"
        )

    else:

        score -= 25

        reasons.append(
            "-25 unreadable"
        )


    # ========================================================
    # Direct PDF
    # ========================================================

    if (
        document_type
        == "PDF"
    ):

        score += 10

        reasons.append(
            "+10 pdf"
        )


    # ========================================================
    # Registry direct link
    # ========================================================

    if origin in {
        "url",
        "alternate_url",
        "attachment_url",
        "alternate_urls",
    }:

        score += 10

        reasons.append(
            "+10 registry report source"
        )


    # ========================================================
    # Symbol
    # ========================================================

    if (
        code
        and code.lower()
        in text
    ):

        score += 25

        reasons.append(
            "+25 symbol match"
        )


    # ========================================================
    # Company name tokens
    # ========================================================

    tokens = company_tokens(
        company_name
    )

    matched_tokens = 0


    for token in tokens:

        if token in text:

            matched_tokens += 1


    if matched_tokens >= 2:

        score += 25

        reasons.append(
            "+25 company strong match"
        )

    elif matched_tokens == 1:

        score += 12

        reasons.append(
            "+12 company partial match"
        )


    # ========================================================
    # REIT vocabulary
    # ========================================================

    positive_hits = 0


    for keyword in (
        POSITIVE_REIT_KEYWORDS
    ):

        if keyword in text:

            positive_hits += 1


    if positive_hits >= 3:

        score += 15

        reasons.append(
            "+15 REIT report vocabulary"
        )

    elif positive_hits >= 1:

        score += 7

        reasons.append(
            "+7 REIT vocabulary"
        )


    # ========================================================
    # Year
    # ========================================================

    if (
        report_year
        and report_year
        in text
    ):

        score += 15

        reasons.append(
            "+15 year match"
        )


    # ========================================================
    # Quarter / period
    # ========================================================

    period_hit = any(
        normalize_text(
            keyword
        ) in text
        for keyword in period_keywords
        if keyword
    )


    if period_hit:

        score += 20

        reasons.append(
            "+20 period match"
        )


    # ========================================================
    # H1 / FY specific
    # ========================================================

    rt = str(
        report_type
    ).upper()


    if rt == "H1":

        if any(
            keyword in text
            for keyword in [
                "semiannual",
                "semi annual",
                "half year",
                "half-year",
                "6m",
            ]
        ):

            score += 12

            reasons.append(
                "+12 H1 match"
            )


    if rt == "FY":

        if any(
            keyword in text
            for keyword in [
                "annual",
                "year end",
                "year-end",
                "12m",
            ]
        ):

            score += 12

            reasons.append(
                "+12 FY match"
            )


    # ========================================================
    # Negative keywords
    # ========================================================

    negative_hits = []


    for keyword in (
        NEGATIVE_KEYWORDS
    ):

        if keyword in text:

            negative_hits.append(
                keyword
            )


    if negative_hits:

        penalty = min(
            80,
            35
            + (
                len(
                    negative_hits
                )
                * 10
            )
        )

        score -= penalty

        reasons.append(
            f"-{penalty} unrelated document"
        )


    # ========================================================
    # Generic Daily NAV protection
    # ========================================================

    if (
        "daily nav"
        in text
        or "nav report"
        in text
    ):

        if not (
            code
            and code.lower()
            in text
        ):

            score -= 25

            reasons.append(
                "-25 generic NAV"
            )


    # ========================================================
    # Clamp
    # ========================================================

    score = max(
        0.0,
        min(
            100.0,
            score
        )
    )


    return (
        score,
        reasons
    )


# ============================================================
# Candidate classification
# ============================================================


def classify_candidate_url(url):

    value = (
        url
        or ""
    ).lower()


    if looks_like_pdf(
        value
    ):

        return "DIRECT_PDF"


    if (
        "saudiexchange.sa"
        in value
    ):

        return "SAUDI_EXCHANGE"


    if any(
        token in value
        for token in [
            "capital",
            "investment",
            "asset",
            "fund",
        ]
    ):

        return "MANAGER_OR_FINANCIAL"


    return "OTHER"


# ============================================================
# Inspect candidate
# ============================================================


def inspect_candidate(
    symbol,
    company_name,
    report_type,
    period_end,
    url,
    origin
):

    response = fetch_url(
        url
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
        relevance_score,
        relevance_reasons
    ) = calculate_document_relevance(
        symbol,
        company_name,
        report_type,
        period_end,
        url,
        origin,
        document_type,
        readable
    )


    return {
        "url":
            url,

        "origin":
            origin,

        "candidate_type":
            classify_candidate_url(
                url
            ),

        "status":
            response[
                "status"
            ],

        "http_status":
            response.get(
                "http_status"
            ),

        "readable":
            readable,

        "document_type":
            document_type,

        "final_url":
            response.get(
                "final_url"
            ),

        "content":
            response.get(
                "content"
            ),

        "error":
            response.get(
                "error"
            ),

        "relevance_score":
            relevance_score,

        "relevance_reasons":
            relevance_reasons,
    }


# ============================================================
# Initial URLs
# ============================================================


def get_initial_report_urls(
    report,
    reit_entry
):

    items = []


    for field_name in [
        "url",
        "alternate_url",
        "attachment_url",
    ]:

        url = report.get(
            field_name
        )

        if url:

            items.append({
                "url":
                    url,

                "origin":
                    field_name,
            })


    alternate_urls = report.get(
        "alternate_urls"
    )


    if isinstance(
        alternate_urls,
        list
    ):

        for url in alternate_urls:

            if url:

                items.append({
                    "url":
                        url,

                    "origin":
                        "alternate_urls",
                })


    sources = reit_entry.get(
        "sources",
        []
    )


    if isinstance(
        sources,
        list
    ):

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

            url = source.get(
                "url"
            )


            if url:

                items.append({
                    "url":
                        url,

                    "origin":
                        (
                            "source:"
                            + str(
                                source.get(
                                    "source_type"
                                )
                            )
                        ),
                })


    unique = []

    seen = set()


    for item in items:

        url = normalize_url(
            item[
                "url"
            ]
        )


        if not url:
            continue


        if url in seen:
            continue


        seen.add(
            url
        )

        item[
            "url"
        ] = url

        unique.append(
            item
        )


    return unique


# ============================================================
# Discovery
# ============================================================


def discover_report(
    symbol,
    company_name,
    reit_entry,
    report
):

    report_type = report.get(
        "report_type"
    )

    period_end = report.get(
        "period_end"
    )


    initial_urls = (
        get_initial_report_urls(
            report,
            reit_entry
        )
    )


    attempts = []

    discovered_urls = []

    seen_discovered = set()


    # ========================================================
    # Initial pages
    # ========================================================

    for item in initial_urls:

        inspected = (
            inspect_candidate(
                symbol,
                company_name,
                report_type,
                period_end,
                item[
                    "url"
                ],
                item[
                    "origin"
                ]
            )
        )


        attempts.append(
            inspected
        )


        if (
            inspected[
                "readable"
            ]
            and inspected[
                "document_type"
            ]
            == "HTML"
            and inspected.get(
                "content"
            )
        ):

            links = extract_links_from_html(
                inspected[
                    "final_url"
                ]
                or inspected[
                    "url"
                ],
                inspected[
                    "content"
                ]
            )


            for url in links:

                if url in seen_discovered:
                    continue

                seen_discovered.add(
                    url
                )

                discovered_urls.append(
                    url
                )


    # ========================================================
    # Pre-filter URLs
    # ========================================================

    scored_urls = []


    for url in discovered_urls:

        pre_score, _ = (
            calculate_document_relevance(
                symbol,
                company_name,
                report_type,
                period_end,
                url,
                "discovered",
                (
                    "PDF"
                    if looks_like_pdf(
                        url
                    )
                    else "UNKNOWN"
                ),
                True
            )
        )


        scored_urls.append(
            (
                pre_score,
                url
            )
        )


    scored_urls.sort(
        key=lambda item:
            item[
                0
            ],
        reverse=True
    )


    promising_urls = [
        url
        for _score, url
        in scored_urls[
            :MAX_DISCOVERED_URLS
        ]
    ]


    # ========================================================
    # Inspect discovered URLs
    # ========================================================

    existing_urls = {
        attempt[
            "url"
        ]
        for attempt in attempts
    }


    for url in promising_urls:

        if url in existing_urls:
            continue


        inspected = (
            inspect_candidate(
                symbol,
                company_name,
                report_type,
                period_end,
                url,
                "discovered"
            )
        )


        attempts.append(
            inspected
        )


    # ========================================================
    # Select valid candidates
    # ========================================================

    usable = [

        attempt

        for attempt in attempts

        if (
            attempt[
                "readable"
            ]
            and attempt[
                "relevance_score"
            ]
            >= MIN_ACCEPT_SCORE
        )
    ]


    usable.sort(
        key=lambda attempt: (
            attempt[
                "relevance_score"
            ],
            1
            if attempt[
                "document_type"
            ]
            == "PDF"
            else 0
        ),
        reverse=True
    )


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

                discovery_state = (
                    "VERIFIED_DOCUMENT_FOUND"
                )

            else:

                discovery_state = (
                    "VERIFIED_PAGE_FOUND"
                )

        else:

            discovery_state = (
                "CANDIDATE_FOUND_REVIEW"
            )


    else:

        readable_any = any(
            attempt[
                "readable"
            ]
            for attempt in attempts
        )


        blocked_any = any(
            attempt.get(
                "http_status"
            )
            == 403
            for attempt in attempts
        )


        if readable_any:

            discovery_state = (
                "NO_RELEVANT_DOCUMENT"
            )

        elif blocked_any:

            discovery_state = (
                "BLOCKED"
            )

        else:

            discovery_state = (
                "NOT_FOUND"
            )


    # ========================================================
    # Top candidates for diagnostics
    # ========================================================

    ranked_attempts = sorted(
        attempts,
        key=lambda attempt:
            attempt[
                "relevance_score"
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
            discovery_state,

        "best_url":
            (
                best[
                    "url"
                ]
                if best
                else None
            ),

        "best_origin":
            (
                best[
                    "origin"
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

        "best_score":
            (
                best[
                    "relevance_score"
                ]
                if best
                else None
            ),

        "attempt_count":
            len(
                attempts
            ),

        "attempts":
            ranked_attempts,
    }


# ============================================================
# Print
# ============================================================


def print_report_result(
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


    print(
        f"🎯 Best Score: "
        f"{result['best_score'] if result['best_score'] is not None else 'N/A'}",
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
        f"📊 Attempts: "
        f"{result['attempt_count']}",
        flush=True
    )


    print_separator()


    print(
        "🏅 TOP CANDIDATES",
        flush=True
    )


    for index, attempt in enumerate(
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
            f"{attempt['relevance_score']:.2f} | "
            f"{attempt['origin']} | "
            f"{attempt['candidate_type']} | "
            f"{attempt['status']} | "
            f"HTTP="
            f"{attempt['http_status']} | "
            f"Type="
            f"{attempt['document_type']} | "
            f"{attempt['url']}",
            flush=True
        )


# ============================================================
# Summary
# ============================================================


def print_summary(
    results
):

    print_header(
        "🏆 REIT REPORT DISCOVERY SUMMARY v2"
    )


    state_counts = {}


    for index, result in enumerate(
        results,
        start=1
    ):

        state = result[
            "discovery_state"
        ]


        state_counts[
            state
        ] = (
            state_counts.get(
                state,
                0
            )
            + 1
        )


        score_text = (
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
            f"{score_text} | "
            f"Type="
            f"{result['best_document_type']} | "
            f"Attempts="
            f"{result['attempt_count']}",
            flush=True
        )


    print_separator()


    print(
        f"📄 Total Reports: "
        f"{len(results)}",
        flush=True
    )


    print(
        "\n📊 STATES",
        flush=True
    )


    for state, count in sorted(
        state_counts.items()
    ):

        print(
            f"- {state}: "
            f"{count}",
            flush=True
        )


    print(
        "=" * 108,
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
        f"🎯 Minimum Accept Score: "
        f"{MIN_ACCEPT_SCORE}",
        flush=True
    )


    print(
        f"🏆 Strong Accept Score: "
        f"{STRONG_ACCEPT_SCORE}",
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


            print_report_result(
                result
            )


    print_summary(
        results
    )


if __name__ == "__main__":

    run_discovery()
