import os
import re
import json
import html
import urllib.error
import urllib.parse
import urllib.request

from collections import deque
from pathlib import Path
from datetime import datetime, timezone
from html.parser import HTMLParser

from supabase import create_client


# ============================================================
# REIT REPORT DISCOVERY ENGINE v4
#
# READ ONLY
#
# التحسين الرئيسي:
# - Deep crawl متعدد المستويات داخل صفحة الصندوق
# - قراءة السياق المحيط بالروابط مثل:
#
#   "Quarterly statement ... 2026-06-30"
#                 ↓
#               [here]
#
# حتى لو اسم الرابط نفسه لا يحتوي Q2 أو التاريخ.
#
# عام لجميع صناديق REIT.
# ============================================================


ENGINE_NAME = "REIT REPORT DISCOVERY ENGINE v4"

REGISTRY_FILENAME = "reit_official_sources.json"

HTTP_TIMEOUT = 30

MAX_CRAWL_DEPTH = 2
MAX_PAGES = 20
MAX_LINKS_PER_PAGE = 250
MAX_DOCUMENT_CHECKS = 60

MIN_ACCEPT_SCORE = 60.0
STRONG_ACCEPT_SCORE = 80.0


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
# HTML PARSER WITH CONTEXT
# ============================================================


class ContextLinkParser(HTMLParser):

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
# General
# ============================================================


def print_header(title):

    print(
        "\n"
        + "=" * 114,
        flush=True
    )

    print(
        title,
        flush=True
    )

    print(
        "=" * 114,
        flush=True
    )


def print_separator():

    print(
        "-" * 114,
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


def is_http_url(url):

    if not url:
        return False

    url = str(
        url
    ).lower()

    return (
        url.startswith(
            "https://"
        )
        or
        url.startswith(
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
        or "/media/" in value
        or "/resources/" in value
        or "/fspdf/" in value
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


def fetch_url(url):

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
                    None
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
                )
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
                )
        }


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
# HTML links + surrounding context
# ============================================================


def extract_links(
    base_url,
    content
):

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

        url = absolute_url(
            base_url,
            item.get(
                "href"
            )
        )

        url = normalize_url(
            url
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
            "march",
            "31 march",
            "03 31",
            "31 03"
        ],

        "Q2": [
            "q2",
            "second quarter",
            "june",
            "30 june",
            "06 30",
            "30 06"
        ],

        "Q3": [
            "q3",
            "third quarter",
            "september",
            "30 september"
        ],

        "Q4": [
            "q4",
            "fourth quarter",
            "december",
            "31 december"
        ],

        "H1": [
            "h1",
            "semi annual",
            "semiannual",
            "half year",
            "six months",
            "6m",
            "june"
        ],

        "FY": [
            "fy",
            "annual",
            "full year",
            "year end",
            "12m"
        ]
    }


    return mapping.get(
        rt,
        []
    )


# ============================================================
# Relevant navigation pages
# ============================================================


NAVIGATION_KEYWORDS = {

    "reit",
    "announcement",
    "announcements",
    "quarterly",
    "factsheet",
    "fact sheet",
    "financial",
    "statement",
    "semi annual",
    "semiannual",
    "annual report",
    "reports"
}


NEGATIVE_KEYWORDS = {

    "fatca",
    "crs",
    "privacy",
    "prospectus",
    "sukuk",
    "tick size",
    "daily report",
    "ipo",
    "offering",
    "application form"
}


# ============================================================
# Relevance Score
# ============================================================


def calculate_score(
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
            "readable"
        )


    if document_type == "PDF":

        score += 10

        reasons.append(
            "pdf"
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
            "symbol"
        )


    tokens = company_tokens(
        company_name
    )


    matched = sum(
        1
        for token in tokens
        if token in combined
    )


    if matched >= 2:

        score += 25

        reasons.append(
            "company"
        )

    elif matched == 1:

        score += 15

        reasons.append(
            "company-partial"
        )


    if "reit" in combined:

        score += 15

        reasons.append(
            "reit"
        )


    year = report_year(
        period_end
    )


    if (
        year
        and year in combined
    ):

        score += 20

        reasons.append(
            "year"
        )


    if any(
        keyword in combined
        for keyword in period_keywords(
            report_type
        )
    ):

        score += 25

        reasons.append(
            "period"
        )


    rt = str(
        report_type
    ).upper()


    if (
        rt.startswith(
            "Q"
        )
        and (
            "quarterly" in combined
            or "quarter" in combined
        )
    ):

        score += 15

        reasons.append(
            "quarterly"
        )


    if (
        rt == "H1"
        and any(
            item in combined
            for item in [
                "semi annual",
                "semiannual",
                "interim financial",
                "six months"
            ]
        )
    ):

        score += 15

        reasons.append(
            "h1"
        )


    negative_hits = [
        item
        for item in NEGATIVE_KEYWORDS
        if item in combined
    ]


    if negative_hits:

        score -= min(
            100,
            50
            + 10 * len(
                negative_hits
            )
        )

        reasons.append(
            "negative"
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
        reasons
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

    queue = deque()

    visited = set()

    documents = []

    pages = []


    for url in start_urls:

        queue.append(
            (
                url,
                0
            )
        )


    while (
        queue
        and len(
            visited
        ) < MAX_PAGES
    ):

        url, depth = queue.popleft()


        if url in visited:

            continue


        visited.add(
            url
        )


        response = fetch_url(
            url
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

            continue


        pages.append(
            url
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


        for link in links:

            link_url = link[
                "url"
            ]

            anchor = link[
                "anchor_text"
            ]

            context = link[
                "context"
            ]


            if not same_domain(
                url,
                link_url
            ):

                continue


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
                        "financial",
                        "statement",
                        "report",
                        "semi annual",
                        "semiannual",
                        "factsheet",
                        "fact sheet",
                        "here"
                    ]
                )
            )


            if potential_document:

                documents.append({
                    "url":
                        link_url,

                    "anchor_text":
                        anchor,

                    "context":
                        context,

                    "origin":
                        f"crawl_depth_{depth}"
                })


            if depth >= MAX_CRAWL_DEPTH:

                continue


            navigation_candidate = any(
                keyword in combined
                for keyword in NAVIGATION_KEYWORDS
            )


            if navigation_candidate:

                if not looks_like_pdf(
                    link_url
                ):

                    queue.append(
                        (
                            link_url,
                            depth + 1
                        )
                    )


    return (
        pages,
        documents
    )


# ============================================================
# Initial URLs
# ============================================================


def get_initial_urls(
    report,
    entry
):

    items = []


    for field in [
        "url",
        "alternate_url",
        "attachment_url"
    ]:

        value = report.get(
            field
        )

        if value:

            items.append(
                value
            )


    for source in entry.get(
        "sources",
        []
    ):

        if not isinstance(
            source,
            dict
        ):
            continue

        url = source.get(
            "url"
        )

        if url:

            items.append(
                url
            )


    unique = []

    seen = set()


    for url in items:

        url = normalize_url(
            url
        )


        if (
            url
            and url not in seen
        ):

            seen.add(
                url
            )

            unique.append(
                url
            )


    return unique


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


    initial_urls = (
        get_initial_urls(
            report,
            entry
        )
    )


    # Saudi Exchange URLs قد تكون 403
    # لكن manager URL يكمل الزحف
    manager_starts = []


    for source in entry.get(
        "sources",
        []
    ):

        if not isinstance(
            source,
            dict
        ):
            continue


        if source.get(
            "source_type"
        ) == "fund_manager":

            url = source.get(
                "url"
            )

            if url:

                manager_starts.append(
                    url
                )


    if not manager_starts:

        manager_starts = initial_urls


    pages, document_links = (
        crawl_manager_site(
            symbol,
            company_name,
            report_type,
            period_end,
            manager_starts
        )
    )


    # ========================================================
    # Remove duplicate documents
    # ========================================================

    unique_documents = {}

    for item in document_links:

        url = item[
            "url"
        ]

        existing = unique_documents.get(
            url
        )


        if existing is None:

            unique_documents[
                url
            ] = item

        else:

            # نحتفظ بالسياق الأطول
            if len(
                item.get(
                    "context",
                    ""
                )
            ) > len(
                existing.get(
                    "context",
                    ""
                )
            ):

                unique_documents[
                    url
                ] = item


    document_links = list(
        unique_documents.values()
    )


    # ========================================================
    # Pre-score before fetching
    # ========================================================

    pre_ranked = []


    for item in document_links:

        pre_score, _ = (
            calculate_score(
                symbol,
                company_name,
                report_type,
                period_end,
                item[
                    "url"
                ],
                item[
                    "anchor_text"
                ],
                item[
                    "context"
                ],
                (
                    "PDF"
                    if looks_like_pdf(
                        item[
                            "url"
                        ]
                    )
                    else "UNKNOWN"
                ),
                True
            )
        )


        item[
            "pre_score"
        ] = pre_score

        pre_ranked.append(
            item
        )


    pre_ranked.sort(
        key=lambda item:
            item[
                "pre_score"
            ],
        reverse=True
    )


    pre_ranked = pre_ranked[
        :MAX_DOCUMENT_CHECKS
    ]


    # ========================================================
    # Fetch & verify
    # ========================================================

    attempts = []


    for item in pre_ranked:

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


        score, reasons = (
            calculate_score(
                symbol,
                company_name,
                report_type,
                period_end,
                item[
                    "url"
                ],
                item[
                    "anchor_text"
                ],
                item[
                    "context"
                ],
                doc_type,
                readable
            )
        )


        attempts.append({
            "url":
                item[
                    "url"
                ],

            "anchor_text":
                item[
                    "anchor_text"
                ],

            "context":
                item[
                    "context"
                ],

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
                score,

            "reasons":
                reasons
        })


    attempts.sort(
        key=lambda item: (
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


    usable = [
        item
        for item in attempts
        if (
            item[
                "status"
            ]
            == "SUCCESS"
            and item[
                "relevance_score"
            ]
            >= MIN_ACCEPT_SCORE
        )
    ]


    best = (
        usable[
            0
        ]
        if usable
        else None
    )


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

    elif pages:

        state = (
            "REIT_PAGE_FOUND_NO_REPORT"
        )

    else:

        state = (
            "NOT_FOUND"
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

        "best_context":
            (
                best[
                    "context"
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
        f"🌐 Pages Crawled: "
        f"{len(result['pages_crawled'])}",
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
            :12
        ],
        start=1
    ):

        context = item[
            "context"
        ]


        if len(
            context
        ) > 180:

            context = (
                context[
                    -180:
                ]
            )


        print(
            f"{index:02d}. "
            f"Score="
            f"{item['relevance_score']:.2f} | "
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


# ============================================================
# Summary
# ============================================================


def print_summary(
    results
):

    print_header(
        "🏆 REIT REPORT DISCOVERY SUMMARY v4"
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
            f"{len(result['pages_crawled'])}",
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
        states.items()
    ):

        print(
            f"- {state}: "
            f"{count}",
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
