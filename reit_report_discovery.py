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
# REIT REPORT DISCOVERY ENGINE v3
#
# READ ONLY
#
# أهم التحسينات عن v2:
#
# 1) Deep Discovery داخل صفحة الصندوق نفسها
# 2) تتبع صفحات داخلية مرتبطة بالصندوق فقط
# 3) استخدام Anchor Text مع URL في تقييم المستند
# 4) منع الزحف العام داخل موقع مدير الصندوق
# 5) Same-Domain Crawl
# 6) حد أقصى للصفحات والروابط
# 7) تقييم أكثر صرامة للمستند:
#       Symbol
#       Company Name
#       REIT
#       Year
#       Quarter / H1 / FY
#       Financial / Quarterly terminology
# 8) استبعاد:
#       FATCA
#       CRS
#       Privacy
#       Prospectus
#       Sukuk
#       Daily Reports
#       Generic NAV
#
# عام لجميع صناديق REIT.
#
# لا توجد كتابة في Supabase.
# ============================================================


ENGINE_NAME = "REIT REPORT DISCOVERY ENGINE v3"

REGISTRY_FILENAME = "reit_official_sources.json"

HTTP_TIMEOUT = 30

MAX_MANAGER_PAGES = 12
MAX_LINKS_PER_PAGE = 150
MAX_DOCUMENT_CHECKS = 50

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
# HTML Link Parser
# ============================================================


class LinkParser(HTMLParser):

    def __init__(self):

        super().__init__()

        self.links = []

        self.current_href = None
        self.current_text = []


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
        self.current_text = []


    def handle_data(
        self,
        data
    ):

        if self.current_href is None:
            return

        text = str(
            data
        ).strip()

        if text:
            self.current_text.append(
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

            "text":
                " ".join(
                    self.current_text
                )
        })

        self.current_href = None
        self.current_text = []


# ============================================================
# General tools
# ============================================================


def print_header(title):

    print(
        "\n"
        + "=" * 112,
        flush=True
    )

    print(
        title,
        flush=True
    )

    print(
        "=" * 112,
        flush=True
    )


def print_separator():

    print(
        "-" * 112,
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


def get_domain(url):

    if not url:
        return None

    try:

        parsed = urllib.parse.urlparse(
            url
        )

        return (
            parsed.netloc
            .lower()
            .replace(
                "www.",
                ""
            )
        )

    except Exception:

        return None


def same_domain(
    url_a,
    url_b
):

    domain_a = get_domain(
        url_a
    )

    domain_b = get_domain(
        url_b
    )

    if (
        not domain_a
        or not domain_b
    ):
        return False

    return (
        domain_a == domain_b
        or domain_a.endswith(
            "." + domain_b
        )
        or domain_b.endswith(
            "." + domain_a
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
# Document type
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
# HTML links
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

        if not url:
            continue

        url = normalize_url(
            url
        )

        if (
            not url
            or not is_http_url(
                url
            )
        ):
            continue

        if url in seen:
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
                        "text"
                    )
                ),
        })


    return results


# ============================================================
# Company tokens
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
        "reit",
        "reits",
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
# Report period metadata
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


def report_period_keywords(
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


    mapping = {

        "Q1": [
            "q1",
            "first quarter",
            "quarter 1",
            "quarter1",
            "march",
            "31 march",
            "03 31",
            "31 03",
        ],

        "Q2": [
            "q2",
            "second quarter",
            "quarter 2",
            "quarter2",
            "june",
            "30 june",
            "06 30",
            "30 06",
        ],

        "Q3": [
            "q3",
            "third quarter",
            "quarter 3",
            "quarter3",
            "september",
            "30 september",
            "09 30",
            "30 09",
        ],

        "Q4": [
            "q4",
            "fourth quarter",
            "quarter 4",
            "quarter4",
            "december",
            "31 december",
            "12 31",
            "31 12",
        ],

        "H1": [
            "h1",
            "half year",
            "half yearly",
            "semiannual",
            "semi annual",
            "six months",
            "6m",
            "june",
        ],

        "FY": [
            "fy",
            "annual",
            "year end",
            "full year",
            "12m",
            "december",
        ],
    }


    keywords = list(
        mapping.get(
            report_type,
            []
        )
    )


    if period_end:

        period_end = str(
            period_end
        )

        keywords.append(
            normalize_text(
                period_end
            )
        )

        keywords.append(
            normalize_text(
                period_end.replace(
                    "-",
                    " "
                )
            )
        )


    return keywords


# ============================================================
# Positive / Negative terms
# ============================================================


REPORT_POSITIVE_WORDS = {
    "reit",
    "quarterly",
    "quarterly report",
    "quarterly statement",
    "financial",
    "financial report",
    "financial statement",
    "interim",
    "semiannual",
    "semi annual",
    "annual report",
    "rental income",
    "net asset value",
    "nav",
    "fund report",
}


REIT_PAGE_WORDS = {
    "reit",
    "real estate",
    "real estate investment",
    "fund",
    "asset management",
    "funds",
}


NEGATIVE_WORDS = {
    "fatca",
    "crs",
    "privacy",
    "privacy notice",
    "tick size",
    "daily report",
    "daily nav",
    "prospectus",
    "sukuk",
    "debt programme",
    "debt program",
    "application form",
    "account opening",
    "terms conditions",
    "terms and conditions",
    "cookie",
    "brochure",
    "ipo",
    "offering",
}


# ============================================================
# REIT page relevance
# ============================================================


def calculate_page_relevance(
    symbol,
    company_name,
    url,
    anchor_text
):

    text = normalize_text(
        f"{url} {anchor_text}"
    )

    score = 0.0


    code = exchange_code(
        symbol
    )


    if (
        code
        and code.lower()
        in text
    ):

        score += 35


    tokens = company_tokens(
        company_name
    )


    matched = sum(
        1
        for token in tokens
        if token in text
    )


    if matched >= 2:

        score += 35

    elif matched == 1:

        score += 20


    if "reit" in text:

        score += 20


    if any(
        keyword in text
        for keyword in REIT_PAGE_WORDS
    ):

        score += 10


    if any(
        bad in text
        for bad in NEGATIVE_WORDS
    ):

        score -= 40


    return max(
        0.0,
        min(
            100.0,
            score
        )
    )


# ============================================================
# Document relevance
# ============================================================


def calculate_document_relevance(
    symbol,
    company_name,
    report_type,
    period_end,
    url,
    anchor_text,
    origin,
    document_type,
    readable
):

    combined = normalize_text(
        f"{url} {anchor_text}"
    )

    score = 0.0

    reasons = []


    # --------------------------------------------------------
    # Readability
    # --------------------------------------------------------

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


    # --------------------------------------------------------
    # PDF
    # --------------------------------------------------------

    if document_type == "PDF":

        score += 10

        reasons.append(
            "+10 pdf"
        )


    # --------------------------------------------------------
    # Registry direct link
    # --------------------------------------------------------

    if origin in {
        "url",
        "alternate_url",
        "attachment_url",
        "alternate_urls",
    }:

        score += 15

        reasons.append(
            "+15 registry"
        )


    # --------------------------------------------------------
    # Symbol
    # --------------------------------------------------------

    code = exchange_code(
        symbol
    )


    if (
        code
        and code.lower()
        in combined
    ):

        score += 30

        reasons.append(
            "+30 symbol"
        )


    # --------------------------------------------------------
    # Company name
    # --------------------------------------------------------

    tokens = company_tokens(
        company_name
    )


    matched_tokens = sum(
        1
        for token in tokens
        if token in combined
    )


    if matched_tokens >= 2:

        score += 30

        reasons.append(
            "+30 company"
        )

    elif matched_tokens == 1:

        score += 15

        reasons.append(
            "+15 company partial"
        )


    # --------------------------------------------------------
    # REIT wording
    # --------------------------------------------------------

    if "reit" in combined:

        score += 15

        reasons.append(
            "+15 reit"
        )


    report_words_found = sum(
        1
        for keyword in REPORT_POSITIVE_WORDS
        if keyword in combined
    )


    if report_words_found >= 3:

        score += 15

        reasons.append(
            "+15 report vocabulary"
        )

    elif report_words_found >= 1:

        score += 8

        reasons.append(
            "+8 report vocabulary"
        )


    # --------------------------------------------------------
    # Year
    # --------------------------------------------------------

    year = get_report_year(
        period_end
    )


    if (
        year
        and year
        in combined
    ):

        score += 20

        reasons.append(
            "+20 year"
        )


    # --------------------------------------------------------
    # Period match
    # --------------------------------------------------------

    period_keywords = (
        report_period_keywords(
            report_type,
            period_end
        )
    )


    matched_periods = [
        keyword
        for keyword in period_keywords
        if normalize_text(
            keyword
        ) in combined
    ]


    if matched_periods:

        score += 25

        reasons.append(
            "+25 period"
        )


    # --------------------------------------------------------
    # Type-specific
    # --------------------------------------------------------

    rt = str(
        report_type
    ).upper()


    if (
        rt.startswith(
            "Q"
        )
        and "quarter" in combined
    ):

        score += 10

        reasons.append(
            "+10 quarter report"
        )


    if (
        rt == "H1"
        and any(
            keyword in combined
            for keyword in [
                "semiannual",
                "semi annual",
                "half year",
                "six months",
                "6m",
            ]
        )
    ):

        score += 15

        reasons.append(
            "+15 H1"
        )


    if (
        rt == "FY"
        and any(
            keyword in combined
            for keyword in [
                "annual",
                "full year",
                "year end",
                "12m",
            ]
        )
    ):

        score += 15

        reasons.append(
            "+15 FY"
        )


    # --------------------------------------------------------
    # Negative keywords
    # --------------------------------------------------------

    negative_hits = [
        bad
        for bad in NEGATIVE_WORDS
        if bad in combined
    ]


    if negative_hits:

        penalty = min(
            100,
            50
            + (
                len(
                    negative_hits
                )
                * 10
            )
        )

        score -= penalty

        reasons.append(
            f"-{penalty} negative"
        )


    # --------------------------------------------------------
    # Prospectus hard block
    # --------------------------------------------------------

    if (
        "prospectus"
        in combined
        or "sukuk"
        in combined
    ):

        score = min(
            score,
            20
        )

        reasons.append(
            "hard-cap prospectus/sukuk"
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
# Candidate inspection
# ============================================================


def inspect_document_candidate(
    symbol,
    company_name,
    report_type,
    period_end,
    url,
    anchor_text,
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
        score,
        reasons
    ) = calculate_document_relevance(
        symbol,
        company_name,
        report_type,
        period_end,
        url,
        anchor_text,
        origin,
        document_type,
        readable
    )


    return {
        "url":
            url,

        "anchor_text":
            anchor_text,

        "origin":
            origin,

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

        "relevance_score":
            score,

        "relevance_reasons":
            reasons,

        "error":
            response.get(
                "error"
            ),
    }


# ============================================================
# Initial sources
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

                "anchor_text":
                    "",

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

                    "anchor_text":
                        "",

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

            url = source.get(
                "url"
            )


            if url:

                items.append({
                    "url":
                        url,

                    "anchor_text":
                        "",

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


        if (
            not url
            or url in seen
        ):
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
# Find manager REIT pages
# ============================================================


def discover_manager_reit_pages(
    symbol,
    company_name,
    initial_results
):

    page_candidates = []


    for result in initial_results:

        if (
            not result[
                "readable"
            ]
            or result[
                "document_type"
            ]
            != "HTML"
            or not result.get(
                "content"
            )
        ):
            continue


        base_url = (
            result.get(
                "final_url"
            )
            or result[
                "url"
            ]
        )


        links = extract_links_from_html(
            base_url,
            result[
                "content"
            ]
        )


        for link in links:

            url = link[
                "url"
            ]

            anchor_text = link[
                "anchor_text"
            ]


            if not same_domain(
                base_url,
                url
            ):
                continue


            if looks_like_pdf(
                url
            ):
                continue


            score = (
                calculate_page_relevance(
                    symbol,
                    company_name,
                    url,
                    anchor_text
                )
            )


            if score < 20:
                continue


            page_candidates.append({
                "url":
                    url,

                "anchor_text":
                    anchor_text,

                "page_score":
                    score,
            })


    # إزالة التكرار
    unique = {}

    for item in page_candidates:

        url = item[
            "url"
        ]

        current = unique.get(
            url
        )


        if (
            current is None
            or item[
                "page_score"
            ]
            > current[
                "page_score"
            ]
        ):

            unique[
                url
            ] = item


    ranked = sorted(
        unique.values(),
        key=lambda item:
            item[
                "page_score"
            ],
        reverse=True
    )


    return ranked[
        :MAX_MANAGER_PAGES
    ]


# ============================================================
# Discover documents inside REIT pages
# ============================================================


def discover_documents_from_pages(
    symbol,
    company_name,
    report_type,
    period_end,
    pages
):

    documents = []

    page_diagnostics = []


    for page in pages:

        response = fetch_url(
            page[
                "url"
            ]
        )


        if response[
            "status"
        ] != "SUCCESS":

            page_diagnostics.append({
                "url":
                    page[
                        "url"
                    ],

                "status":
                    response[
                        "status"
                    ],

                "http_status":
                    response.get(
                        "http_status"
                    ),

                "links":
                    0,
            })

            continue


        if detect_document_type(
            response
        ) != "HTML":

            continue


        links = extract_links_from_html(
            response.get(
                "final_url"
            )
            or page[
                "url"
            ],
            response[
                "content"
            ]
        )


        page_diagnostics.append({
            "url":
                page[
                    "url"
                ],

            "status":
                "SUCCESS",

            "http_status":
                response.get(
                    "http_status"
                ),

            "links":
                len(
                    links
                ),
        })


        for link in links:

            url = link[
                "url"
            ]

            anchor_text = link[
                "anchor_text"
            ]


            if not same_domain(
                page[
                    "url"
                ],
                url
            ):
                continue


            combined = normalize_text(
                f"{url} {anchor_text}"
            )


            # نركز على ملفات/تقارير محتملة فقط
            potential_document = (
                looks_like_pdf(
                    url
                )
                or any(
                    keyword in combined
                    for keyword in [
                        "quarter",
                        "financial",
                        "statement",
                        "report",
                        "annual",
                        "semiannual",
                        "semi annual",
                        "reit",
                        "nav",
                    ]
                )
            )


            if not potential_document:
                continue


            (
                pre_score,
                _reasons
            ) = calculate_document_relevance(
                symbol,
                company_name,
                report_type,
                period_end,
                url,
                anchor_text,
                "deep_discovery",
                (
                    "PDF"
                    if looks_like_pdf(
                        url
                    )
                    else "UNKNOWN"
                ),
                True
            )


            documents.append({
                "url":
                    url,

                "anchor_text":
                    anchor_text,

                "pre_score":
                    pre_score,

                "origin":
                    "deep_discovery",
            })


    # إزالة تكرار
    unique = {}

    for item in documents:

        url = item[
            "url"
        ]


        existing = unique.get(
            url
        )


        if (
            existing is None
            or item[
                "pre_score"
            ]
            > existing[
                "pre_score"
            ]
        ):

            unique[
                url
            ] = item


    ranked = sorted(
        unique.values(),
        key=lambda item:
            item[
                "pre_score"
            ],
        reverse=True
    )


    return (
        ranked[
            :MAX_DOCUMENT_CHECKS
        ],
        page_diagnostics
    )


# ============================================================
# Main discovery for report
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


    attempts = []


    # ========================================================
    # STEP 1 — Initial registered sources
    # ========================================================

    initial_items = (
        get_initial_report_urls(
            report,
            reit_entry
        )
    )


    initial_results = []


    for item in initial_items:

        result = (
            inspect_document_candidate(
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
                    "origin"
                ]
            )
        )


        attempts.append(
            result
        )

        initial_results.append(
            result
        )


    # ========================================================
    # STEP 2 — Find REIT-specific manager pages
    # ========================================================

    manager_pages = (
        discover_manager_reit_pages(
            symbol,
            company_name,
            initial_results
        )
    )


    # ========================================================
    # STEP 3 — Search documents inside those pages
    # ========================================================

    (
        discovered_documents,
        page_diagnostics
    ) = discover_documents_from_pages(
        symbol,
        company_name,
        report_type,
        period_end,
        manager_pages
    )


    # ========================================================
    # STEP 4 — Inspect strongest document candidates
    # ========================================================

    existing_urls = {
        item[
            "url"
        ]
        for item in attempts
    }


    for item in discovered_documents:

        if item[
            "url"
        ] in existing_urls:
            continue


        result = (
            inspect_document_candidate(
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
                    "origin"
                ]
            )
        )


        attempts.append(
            result
        )


    # ========================================================
    # Ranking
    # ========================================================

    ranked_attempts = sorted(
        attempts,
        key=lambda item:
            item[
                "relevance_score"
            ],
        reverse=True
    )


    usable = [

        item

        for item in ranked_attempts

        if (
            item[
                "readable"
            ]
            and item[
                "relevance_score"
            ]
            >= MIN_ACCEPT_SCORE
        )
    ]


    # ========================================================
    # IMPORTANT:
    # PDF له أفضلية فقط إذا الدرجة متقاربة
    # ========================================================

    usable.sort(
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

        readable_count = sum(
            1
            for item in attempts
            if item[
                "readable"
            ]
        )


        blocked_count = sum(
            1
            for item in attempts
            if item.get(
                "http_status"
            )
            == 403
        )


        if (
            manager_pages
            and readable_count > 0
        ):

            discovery_state = (
                "REIT_PAGE_FOUND_NO_REPORT"
            )

        elif readable_count > 0:

            discovery_state = (
                "NO_RELEVANT_DOCUMENT"
            )

        elif blocked_count > 0:

            discovery_state = (
                "BLOCKED"
            )

        else:

            discovery_state = (
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
            discovery_state,

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

        "manager_pages":
            manager_pages,

        "page_diagnostics":
            page_diagnostics,

        "attempts":
            ranked_attempts,

        "attempt_count":
            len(
                attempts
            ),
    }


# ============================================================
# Printing
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


    if result[
        "best_anchor_text"
    ]:

        print(
            f"🏷 Best Anchor: "
            f"{result['best_anchor_text']}",
            flush=True
        )


    print(
        f"📄 REIT Manager Pages: "
        f"{len(result['manager_pages'])}",
        flush=True
    )


    print(
        f"📊 Document Attempts: "
        f"{result['attempt_count']}",
        flush=True
    )


    print_separator()


    print(
        "🏢 TOP REIT PAGES",
        flush=True
    )


    if not result[
        "manager_pages"
    ]:

        print(
            "⚠️ No specific REIT manager page found",
            flush=True
        )


    else:

        for index, page in enumerate(
            result[
                "manager_pages"
            ][
                :10
            ],
            start=1
        ):

            print(
                f"{index:02d}. "
                f"Score="
                f"{page['page_score']:.2f} | "
                f"{page['anchor_text']} | "
                f"{page['url']}",
                flush=True
            )


    print_separator()


    print(
        "🏅 TOP DOCUMENT CANDIDATES",
        flush=True
    )


    for index, attempt in enumerate(
        result[
            "attempts"
        ][
            :12
        ],
        start=1
    ):

        print(
            f"{index:02d}. "
            f"Score="
            f"{attempt['relevance_score']:.2f} | "
            f"{attempt['origin']} | "
            f"{attempt['status']} | "
            f"HTTP="
            f"{attempt['http_status']} | "
            f"Type="
            f"{attempt['document_type']} | "
            f"Anchor="
            f"{attempt['anchor_text'] or 'N/A'} | "
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
        "🏆 REIT REPORT DISCOVERY SUMMARY v3"
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
            f"REITPages="
            f"{len(result['manager_pages'])} | "
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
        "=" * 112,
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
