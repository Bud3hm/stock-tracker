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
# REIT REPORT DISCOVERY ENGINE v5
#
# READ ONLY
#
# أهداف v5:
#
# 1) دمج نجاح v3 في التعرف على:
#       - Semi Annual Report
#       - Financial Statements
#       - REIT Announcements
#
# 2) الاحتفاظ بقدرة v4 على:
#       - Deep Crawl
#       - قراءة السياق المحيط بالروابط
#
# 3) إصلاح مشكلة هدر MAX_PAGES على:
#       - #fragments
#       - روابط القوائم العامة
#       - روابط غير مرتبطة بالصندوق
#
# 4) Priority Crawl:
#       الصفحات الأكثر صلة بالتقرير تُفحص أولاً
#
# 5) Canonical URLs:
#       إزالة fragments والتكرار
#
# 6) صفحة HTML نفسها قد تكون التقرير الصحيح،
#    وليست الـPDF فقط.
#
# 7) عام لجميع صناديق REIT.
#
# لا توجد كتابة في Supabase.
# ============================================================


ENGINE_NAME = "REIT REPORT DISCOVERY ENGINE v5"

REGISTRY_FILENAME = "reit_official_sources.json"

HTTP_TIMEOUT = 30

MAX_CRAWL_DEPTH = 3
MAX_PAGES = 30
MAX_LINKS_PER_PAGE = 300
MAX_DOCUMENT_CHECKS = 80

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
# HTML PARSER WITH LINK CONTEXT
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
        + "=" * 116,
        flush=True
    )

    print(
        title,
        flush=True
    )

    print(
        "=" * 116,
        flush=True
    )


def print_separator():

    print(
        "-" * 116,
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

        # حذف fragment بالكامل
        # حتى لا نستهلك صفحات مثل:
        # page#menu1
        # page#menu2
        # page#menu3

        cleaned = urllib.parse.urlunsplit(
            (
                parsed.scheme,
                parsed.netloc,
                parsed.path,
                parsed.query,
                ""
            )
        )

        # إزالة slash إضافي في النهاية إلا الجذر
        if (
            cleaned.endswith("/")
            and len(
                urllib.parse.urlsplit(
                    cleaned
                ).path
            ) > 1
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
        or
        value.startswith(
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
# HTML links
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


    # ========================================================
    # REIT identity
    # ========================================================

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


    # ========================================================
    # Report-specific navigation
    # ========================================================

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


    # ========================================================
    # Generic useful pages
    # ========================================================

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


    # ========================================================
    # Year / period
    # ========================================================

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


    # ========================================================
    # Noise penalty
    # ========================================================

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
# Document relevance
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


    # ========================================================
    # Identity
    # ========================================================

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


    # ========================================================
    # Year
    # ========================================================

    year = report_year(
        period_end
    )


    if (
        year
        and year in combined
    ):

        score += 20

        reasons.append(
            "+20 year"
        )


    # ========================================================
    # Period
    # ========================================================

    if any(
        keyword in combined
        for keyword in period_keywords(
            report_type
        )
    ):

        score += 25

        reasons.append(
            "+25 period"
        )


    # ========================================================
    # Type-specific matching
    # ========================================================

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


        # Announcement page مهم جدًا للربع
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


    # ========================================================
    # Generic financial language
    # ========================================================

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


    # ========================================================
    # Hard penalties
    # ========================================================

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

    # Priority heap:
    # Python heap أصغر رقم أولاً،
    # لذلك نخزن -priority.

    queue = []

    sequence = 0

    visited = set()

    pages = []

    page_candidates = []

    document_candidates = []


    # ========================================================
    # Seed
    # ========================================================

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


    # ========================================================
    # Crawl
    # ========================================================

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


        if response[
            "status"
        ] != "SUCCESS":

            continue


        document_type = (
            detect_document_type(
                response
            )
        )


        # ====================================================
        # Direct document reached
        # ====================================================

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


        # ====================================================
        # HTML page reached
        # ====================================================

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


        # الصفحة نفسها قد تكون التقرير الصحيح
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


        # ====================================================
        # Rank links on page
        # ====================================================

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


        # ====================================================
        # Process links
        # ====================================================

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


            # ------------------------------------------------
            # Potential report/document
            # ------------------------------------------------

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


            # ------------------------------------------------
            # Crawl deeper
            # ------------------------------------------------

            if depth >= MAX_CRAWL_DEPTH:

                continue


            if looks_like_pdf(
                link_url
            ):

                continue


            # لا ندخل روابط ضعيفة جدًا
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


    alternate_urls = report.get(
        "alternate_urls"
    )


    if isinstance(
        alternate_urls,
        list
    ):

        for value in alternate_urls:

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

        url = canonical_url(
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
# Manager start URLs
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
# Dedupe candidates
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


        # نحتفظ بالنسخة ذات السياق الأكثر فائدة

        current_text = normalize_text(
            f"{item.get('anchor_text', '')} "
            f"{item.get('context', '')}"
        )

        old_text = normalize_text(
            f"{existing.get('anchor_text', '')} "
            f"{existing.get('context', '')}"
        )


        if len(
            current_text
        ) > len(
            old_text
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


    initial_urls = (
        get_initial_urls(
            report,
            entry
        )
    )


    manager_starts = (
        get_manager_starts(
            entry
        )
    )


    if not manager_starts:

        manager_starts = (
            initial_urls
        )


    # ========================================================
    # Crawl manager
    # ========================================================

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
    # Add direct report URLs from registry
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


    # ========================================================
    # Merge HTML report pages + discovered docs
    # ========================================================

    all_candidates = (
        page_candidates
        + document_candidates
    )


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


        pre_score, _ = (
            calculate_document_score(
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
    # Fetch and verify
    # ========================================================

    attempts = []


    for item in pre_ranked:

        attempts.append(
            inspect_candidate(
                symbol,
                company_name,
                report_type,
                period_end,
                item
            )
        )


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


    elif pages:

        state = (
            "REIT_PAGE_FOUND_NO_REPORT"
        )


    else:

        state = (
            "NOT_FOUND"
        )


    # ========================================================
    # Top crawled pages
    # ========================================================

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


    if result[
        "best_anchor_text"
    ]:

        print(
            f"🏷 Best Anchor: "
            f"{result['best_anchor_text']}",
            flush=True
        )


    print(
        f"🌐 Pages Crawled: "
        f"{len(result['pages_crawled'])}",
        flush=True
    )


    print_separator()


    print(
        "🌐 TOP CRAWLED PAGES",
        flush=True
    )


    for index, page in enumerate(
        result[
            "pages_crawled"
        ][
            :12
        ],
        start=1
    ):

        print(
            f"{index:02d}. "
            f"Priority="
            f"{page['priority']:.2f} | "
            f"Depth="
            f"{page['depth']} | "
            f"Anchor="
            f"{page['anchor_text'] or 'N/A'} | "
            f"{page['url']}",
            flush=True
        )


    print_separator()


    print(
        "🏅 TOP DOCUMENT CANDIDATES",
        flush=True
    )


    if not result[
        "attempts"
    ]:

        print(
            "⚠️ No document candidates",
            flush=True
        )


    for index, item in enumerate(
        result[
            "attempts"
        ][
            :15
        ],
        start=1
    ):

        context = item.get(
            "context",
            ""
        )


        if len(
            context
        ) > 220:

            context = context[
                -220:
            ]


        print(
            f"{index:02d}. "
            f"Score="
            f"{item['relevance_score']:.2f} | "
            f"Origin="
            f"{item['origin']} | "
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


        if item[
            "reasons"
        ]:

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
        "🏆 REIT REPORT DISCOVERY SUMMARY v5"
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
            f"Candidates="
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
        "=" * 116,
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


            print_result(
                result
            )


    print_summary(
        results
    )


if __name__ == "__main__":

    run_discovery()
