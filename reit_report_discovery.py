import os
import re
import io
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

from pypdf import PdfReader
from supabase import create_client


# ============================================================
# REIT REPORT DISCOVERY ENGINE v5.5
#
# PDF CONTENT VERIFICATION
#
# READ ONLY
#
# المراحل:
#
# 1) Discovery / Crawl
# 2) URL + Anchor filtering
# 3) Hard Reject
# 4) PDF content extraction
# 5) Fund verification
# 6) Year verification
# 7) Period verification
# 8) Statement-type verification
# 9) Final VERIFIED only after content validation
#
# عام لكل صناديق REIT.
# ============================================================


ENGINE_NAME = (
    "REIT REPORT DISCOVERY ENGINE "
    "v5.5 PDF CONTENT VERIFICATION"
)

REGISTRY_FILENAME = "reit_official_sources.json"

HTTP_TIMEOUT = 8

MAX_CRAWL_DEPTH = 2
MAX_PAGES = 10
MAX_LINKS_PER_PAGE = 140

MAX_DISCOVERY_CANDIDATES = 25

# لا نقرأ محتوى PDF لكل الملفات
MAX_PDF_CONTENT_CHECKS = 6

# نقرأ فقط أول صفحات كافية للتحقق
MAX_PDF_PAGES_TO_READ = 8

MIN_ACCEPT_SCORE = 65.0
STRONG_ACCEPT_SCORE = 85.0
EARLY_STOP_SCORE = 92.0


# ============================================================
# Runtime cache
# ============================================================


HTTP_CACHE = {}
LINK_CACHE = {}
PDF_TEXT_CACHE = {}


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
# HTML Parser
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
# Print
# ============================================================


def print_header(title):

    print(
        "\n"
        + "=" * 124,
        flush=True
    )

    print(
        title,
        flush=True
    )

    print(
        "=" * 124,
        flush=True
    )


def print_separator():

    print(
        "-" * 124,
        flush=True
    )


# ============================================================
# Normalize
# ============================================================


def normalize_symbol(symbol):

    if not symbol:
        return None

    return str(
        symbol
    ).strip().upper()


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
        r"[_\-/%?=&:,;()\[\]{}]+",
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
        or "/media/" in value
        or "/resources/" in value
        or "/fspdf/" in value
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
# HTTP
# ============================================================


def fetch_url(url):

    url = canonical_url(
        url
    )


    if url in HTTP_CACHE:

        result = HTTP_CACHE[
            url
        ].copy()

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
# Detect type
# ============================================================


def detect_document_type(response):

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
# Links
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


# ============================================================
# Hard reject identity
# ============================================================


HARD_REJECT_IDENTITY = {

    "terms and conditions",
    "terms conditions",

    "valuation",
    "valuation report",
    "property valuation",
    "appraisal",

    "portfolio",
    "portfolio report",

    "factsheet",
    "fact sheet",

    "nav report",
    "daily nav",

    "prospectus",
    "sukuk",
    "offering",

    "fatca",
    "crs",
    "privacy",
    "tick size"
}


def document_identity_text(
    url,
    anchor_text
):

    return normalize_text(
        f"{url} {anchor_text}"
    )


def contextual_text(
    url,
    anchor_text,
    context
):

    return normalize_text(
        f"{url} {anchor_text} {context}"
    )


def hard_reject_document(
    url,
    anchor_text
):

    identity = document_identity_text(
        url,
        anchor_text
    )


    matches = [
        keyword

        for keyword in HARD_REJECT_IDENTITY

        if keyword in identity
    ]


    return (
        bool(matches),
        matches
    )


# ============================================================
# REIT Path Guard
# ============================================================


def get_reit_base_path(
    manager_url
):

    try:

        return (
            urllib.parse.urlparse(
                manager_url
            )
            .path
            .rstrip("/")
        )

    except Exception:

        return None


def is_allowed_reit_path(
    manager_url,
    candidate_url
):

    if not same_domain(
        manager_url,
        candidate_url
    ):
        return False


    manager_path = get_reit_base_path(
        manager_url
    )


    if not manager_path:
        return True


    candidate_path = (
        urllib.parse.urlparse(
            candidate_url
        )
        .path
        .lower()
    )


    manager_path = (
        manager_path.lower()
    )


    if candidate_path.startswith(
        manager_path
    ):
        return True


    if (
        "/media/"
        in candidate_path
        or "/resources/"
        in candidate_path
        or "/fspdf/"
        in candidate_path
        or "/data/"
        in candidate_path
    ):
        return True


    return False


# ============================================================
# PDF extraction
# ============================================================


def extract_pdf_text(
    url,
    content
):

    url = canonical_url(
        url
    )


    if url in PDF_TEXT_CACHE:

        return PDF_TEXT_CACHE[
            url
        ]


    result = {
        "status":
            "FAILED",

        "text":
            "",

        "pages_read":
            0,

        "total_pages":
            0,

        "error":
            None
    }


    try:

        reader = PdfReader(
            io.BytesIO(
                content
            )
        )


        total_pages = len(
            reader.pages
        )


        texts = []


        pages_to_read = min(
            total_pages,
            MAX_PDF_PAGES_TO_READ
        )


        for index in range(
            pages_to_read
        ):

            try:

                page_text = (
                    reader.pages[
                        index
                    ].extract_text()
                    or ""
                )

                texts.append(
                    page_text
                )

            except Exception:

                continue


        text = "\n".join(
            texts
        )


        result = {
            "status":
                "SUCCESS",

            "text":
                normalize_text(
                    text
                ),

            "pages_read":
                pages_to_read,

            "total_pages":
                total_pages,

            "error":
                None
        }


    except Exception as error:

        result = {
            "status":
                "FAILED",

            "text":
                "",

            "pages_read":
                0,

            "total_pages":
                0,

            "error":
                (
                    f"{type(error).__name__}: "
                    f"{error}"
                )
        }


    PDF_TEXT_CACHE[
        url
    ] = result

    return result


# ============================================================
# Content validation
# ============================================================


def content_company_match(
    company_name,
    text
):

    tokens = company_tokens(
        company_name
    )


    if not tokens:
        return False


    matched = sum(
        1
        for token in tokens
        if token in text
    )


    return matched >= 1


def content_year_match(
    period_end,
    text
):

    year = report_year(
        period_end
    )


    if not year:
        return False


    return year in text


def content_period_match(
    report_type,
    text
):

    rt = str(
        report_type
    ).upper()


    if rt == "Q1":

        return any(
            item in text
            for item in [
                "first quarter",
                "q1",
                "31 march",
                "period ended 31 march"
            ]
        )


    if rt == "Q2":

        return any(
            item in text
            for item in [
                "second quarter",
                "q2",
                "30 june",
                "period ended 30 june",
                "quarter ended 30 june"
            ]
        )


    if rt == "Q3":

        return any(
            item in text
            for item in [
                "third quarter",
                "q3",
                "30 september",
                "period ended 30 september"
            ]
        )


    if rt == "Q4":

        return any(
            item in text
            for item in [
                "fourth quarter",
                "q4",
                "31 december",
                "period ended 31 december"
            ]
        )


    if rt == "H1":

        return any(
            item in text
            for item in [
                "30 june",
                "six months ended",
                "six month period ended",
                "period ended 30 june",
                "half year"
            ]
        )


    if rt == "FY":

        return any(
            item in text
            for item in [
                "31 december",
                "year ended",
                "financial year ended"
            ]
        )


    return False


def content_statement_type_match(
    report_type,
    text
):

    rt = str(
        report_type
    ).upper()


    if rt in {
        "Q1",
        "Q2",
        "Q3",
        "Q4"
    }:

        return any(
            item in text

            for item in [
                "quarterly statement",
                "quarterly report",
                "quarterly financial",
                "quarter ended",
                "quarterly disclosure",
                "quarterly information"
            ]
        )


    if rt == "H1":

        return any(
            item in text

            for item in [
                "interim financial statements",
                "interim condensed financial statements",
                "interim financial report",
                "semi annual report",
                "semiannual report",
                "six months ended",
                "half year"
            ]
        )


    if rt == "FY":

        return any(
            item in text

            for item in [
                "annual financial statements",
                "audited financial statements",
                "annual report",
                "financial statements for the year ended"
            ]
        )


    return False


def content_hard_reject(
    text
):

    reject_terms = [
        "terms and conditions",
        "valuation report",
        "property valuation",
        "appraisal report",
        "prospectus",
        "fact sheet",
        "factsheet",
        "portfolio report"
    ]


    matches = [
        term
        for term in reject_terms
        if term in text
    ]


    return (
        bool(matches),
        matches
    )


def verify_pdf_content(
    company_name,
    report_type,
    period_end,
    url,
    response
):

    extraction = extract_pdf_text(
        url,
        response.get(
            "content"
        )
        or b""
    )


    text = extraction[
        "text"
    ]


    if (
        extraction[
            "status"
        ] != "SUCCESS"
        or not text
    ):

        return {
            "content_score":
                0.0,

            "content_company_ok":
                False,

            "content_year_ok":
                False,

            "content_period_ok":
                False,

            "content_statement_ok":
                False,

            "content_hard_reject":
                False,

            "content_reject_reasons":
                [],

            "pages_read":
                extraction[
                    "pages_read"
                ],

            "total_pages":
                extraction[
                    "total_pages"
                ],

            "error":
                extraction[
                    "error"
                ],

            "snippet":
                ""
        }


    company_ok = content_company_match(
        company_name,
        text
    )


    year_ok = content_year_match(
        period_end,
        text
    )


    period_ok = content_period_match(
        report_type,
        text
    )


    statement_ok = (
        content_statement_type_match(
            report_type,
            text
        )
    )


    (
        hard_reject,
        reject_reasons
    ) = content_hard_reject(
        text
    )


    score = 0.0


    if company_ok:
        score += 20


    if year_ok:
        score += 25


    if period_ok:
        score += 25


    if statement_ok:
        score += 30


    if hard_reject:
        score = 0.0


    snippet = text[
        :700
    ]


    return {
        "content_score":
            score,

        "content_company_ok":
            company_ok,

        "content_year_ok":
            year_ok,

        "content_period_ok":
            period_ok,

        "content_statement_ok":
            statement_ok,

        "content_hard_reject":
            hard_reject,

        "content_reject_reasons":
            reject_reasons,

        "pages_read":
            extraction[
                "pages_read"
            ],

        "total_pages":
            extraction[
                "total_pages"
            ],

        "error":
            extraction[
                "error"
            ],

        "snippet":
            snippet
    }


# ============================================================
# Discovery priority
# ============================================================


def discovery_score(
    company_name,
    report_type,
    period_end,
    url,
    anchor_text,
    context
):

    identity = document_identity_text(
        url,
        anchor_text
    )

    combined = contextual_text(
        url,
        anchor_text,
        context
    )


    score = 0.0


    if "reit" in combined:
        score += 20


    for token in company_tokens(
        company_name
    ):

        if token in combined:
            score += 10
            break


    year = report_year(
        period_end
    )


    if (
        year
        and year in combined
    ):
        score += 20


    rt = str(
        report_type
    ).upper()


    if rt.startswith(
        "Q"
    ):

        if "quarter" in combined:
            score += 30

        if "announcement" in combined:
            score += 25


    elif rt == "H1":

        if any(
            item in combined
            for item in [
                "semi annual",
                "semiannual",
                "interim",
                "financial statement"
            ]
        ):
            score += 35


    elif rt == "FY":

        if any(
            item in combined
            for item in [
                "annual report",
                "financial statement"
            ]
        ):
            score += 35


    if looks_like_pdf(
        url
    ):
        score += 10


    rejected, _ = hard_reject_document(
        url,
        anchor_text
    )


    if rejected:
        score -= 200


    if (
        "brokerage" in combined
        or "faq" in combined
        or "contact us" in combined
        or "about us" in combined
    ):
        score -= 100


    return score


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
# Crawl
# ============================================================


def crawl_manager_site(
    company_name,
    report_type,
    period_end,
    start_urls
):

    queue = []

    sequence = 0
    visited = set()

    pages = []
    candidates = []


    primary_manager_url = (
        start_urls[
            0
        ]
        if start_urls
        else None
    )


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


        if (
            primary_manager_url
            and not is_allowed_reit_path(
                primary_manager_url,
                url
            )
        ):
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


        if detected == "PDF":

            candidates.append({
                "url":
                    url,

                "anchor_text":
                    incoming_anchor,

                "context":
                    incoming_context,

                "origin":
                    f"crawl_pdf_depth_{depth}"
            })

            continue


        if detected != "HTML":
            continue


        pages.append({
            "url":
                url,

            "depth":
                depth,

            "priority":
                -negative_priority
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


            if (
                primary_manager_url
                and not is_allowed_reit_path(
                    primary_manager_url,
                    link_url
                )
            ):
                continue


            if link_url == url:
                continue


            score = discovery_score(
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
                    score
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


            if looks_like_pdf(
                link_url
            ):

                candidates.append({
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
            ] < 5:
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
                    link[
                        "anchor_text"
                    ],
                    link[
                        "context"
                    ]
                )
            )


            sequence += 1


    return (
        pages,
        candidates
    )


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


        new_context = contextual_text(
            url,
            item.get(
                "anchor_text",
                ""
            ),
            item.get(
                "context",
                ""
            )
        )


        old_context = contextual_text(
            url,
            existing.get(
                "anchor_text",
                ""
            ),
            existing.get(
                "context",
                ""
            )
        )


        if len(
            new_context
        ) > len(
            old_context
        ):

            unique[
                url
            ] = item


    return list(
        unique.values()
    )


# ============================================================
# Candidate pre-score
# ============================================================


def prepare_candidates(
    company_name,
    report_type,
    period_end,
    candidates
):

    prepared = []


    for item in candidates:

        (
            hard_reject,
            reject_reasons
        ) = hard_reject_document(
            item[
                "url"
            ],
            item.get(
                "anchor_text",
                ""
            )
        )


        score = discovery_score(
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
            )
        )


        item[
            "pre_score"
        ] = score

        item[
            "hard_reject"
        ] = hard_reject

        item[
            "hard_reject_reasons"
        ] = reject_reasons


        prepared.append(
            item
        )


    prepared.sort(
        key=lambda item: (
            not item[
                "hard_reject"
            ],
            item[
                "pre_score"
            ]
        ),
        reverse=True
    )


    return prepared[
        :MAX_DISCOVERY_CANDIDATES
    ]


# ============================================================
# Verify PDFs
# ============================================================


def verify_candidates(
    company_name,
    report_type,
    period_end,
    candidates
):

    attempts = []

    pdf_checks = 0

    best = None


    for index, item in enumerate(
        candidates,
        start=1
    ):

        if item[
            "hard_reject"
        ]:

            attempts.append({
                "url":
                    item[
                        "url"
                    ],

                "pre_score":
                    item[
                        "pre_score"
                    ],

                "hard_reject":
                    True,

                "hard_reject_reasons":
                    item[
                        "hard_reject_reasons"
                    ],

                "content_score":
                    0.0,

                "content_company_ok":
                    False,

                "content_year_ok":
                    False,

                "content_period_ok":
                    False,

                "content_statement_ok":
                    False,

                "content_hard_reject":
                    True,

                "content_reject_reasons":
                    item[
                        "hard_reject_reasons"
                    ],

                "pages_read":
                    0,

                "total_pages":
                    0,

                "http_status":
                    None,

                "from_cache":
                    False,

                "state":
                    "HARD_REJECT"
            })

            continue


        if pdf_checks >= MAX_PDF_CONTENT_CHECKS:
            break


        pdf_checks += 1


        print(
            f"📄 PDF CONTENT CHECK "
            f"{pdf_checks}/{MAX_PDF_CONTENT_CHECKS} | "
            f"PreScore="
            f"{item['pre_score']:.2f} | "
            f"{item['url']}",
            flush=True
        )


        response = fetch_url(
            item[
                "url"
            ]
        )


        if response[
            "status"
        ] != "SUCCESS":

            attempts.append({
                "url":
                    item[
                        "url"
                    ],

                "pre_score":
                    item[
                        "pre_score"
                    ],

                "hard_reject":
                    False,

                "hard_reject_reasons":
                    [],

                "content_score":
                    0.0,

                "content_company_ok":
                    False,

                "content_year_ok":
                    False,

                "content_period_ok":
                    False,

                "content_statement_ok":
                    False,

                "content_hard_reject":
                    False,

                "content_reject_reasons":
                    [],

                "pages_read":
                    0,

                "total_pages":
                    0,

                "http_status":
                    response.get(
                        "http_status"
                    ),

                "from_cache":
                    response.get(
                        "from_cache",
                        False
                    ),

                "state":
                    "HTTP_FAILED"
            })

            continue


        detected = detect_document_type(
            response
        )


        if detected != "PDF":

            continue


        content_result = verify_pdf_content(
            company_name,
            report_type,
            period_end,
            item[
                "url"
            ],
            response
        )


        valid = (
            content_result[
                "content_company_ok"
            ]
            and content_result[
                "content_year_ok"
            ]
            and content_result[
                "content_period_ok"
            ]
            and content_result[
                "content_statement_ok"
            ]
            and not content_result[
                "content_hard_reject"
            ]
        )


        state = (
            "CONTENT_VERIFIED"
            if valid
            else "CONTENT_REJECTED"
        )


        attempt = {
            "url":
                item[
                    "url"
                ],

            "pre_score":
                item[
                    "pre_score"
                ],

            "hard_reject":
                False,

            "hard_reject_reasons":
                [],

            "content_score":
                content_result[
                    "content_score"
                ],

            "content_company_ok":
                content_result[
                    "content_company_ok"
                ],

            "content_year_ok":
                content_result[
                    "content_year_ok"
                ],

            "content_period_ok":
                content_result[
                    "content_period_ok"
                ],

            "content_statement_ok":
                content_result[
                    "content_statement_ok"
                ],

            "content_hard_reject":
                content_result[
                    "content_hard_reject"
                ],

            "content_reject_reasons":
                content_result[
                    "content_reject_reasons"
                ],

            "pages_read":
                content_result[
                    "pages_read"
                ],

            "total_pages":
                content_result[
                    "total_pages"
                ],

            "http_status":
                response.get(
                    "http_status"
                ),

            "from_cache":
                response.get(
                    "from_cache",
                    False
                ),

            "state":
                state
        }


        attempts.append(
            attempt
        )


        if valid:

            final_score = (
                content_result[
                    "content_score"
                ]
            )


            if (
                best is None
                or final_score
                > best[
                    "content_score"
                ]
            ):

                best = attempt


            if final_score >= EARLY_STOP_SCORE:

                print(
                    "🚀 CONTENT EARLY STOP | "
                    f"Score={final_score:.2f} | "
                    f"{item['url']}",
                    flush=True
                )

                break


    return (
        best,
        attempts
    )


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

            "pages_crawled":
                [],

            "attempts":
                []
        }


    (
        pages,
        candidates
    ) = crawl_manager_site(
        company_name,
        report_type,
        period_end,
        manager_starts
    )


    # ========================================================
    # Registry attachment/direct links
    # ========================================================

    for field in [
        "attachment_url",
        "alternate_url"
    ]:

        value = report.get(
            field
        )


        if (
            value
            and looks_like_pdf(
                value
            )
        ):

            candidates.append({
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


    candidates = dedupe_candidates(
        candidates
    )


    candidates = prepare_candidates(
        company_name,
        report_type,
        period_end,
        candidates
    )


    (
        best,
        attempts
    ) = verify_candidates(
        company_name,
        report_type,
        period_end,
        candidates
    )


    if best:

        if (
            best[
                "content_score"
            ]
            >= STRONG_ACCEPT_SCORE
        ):

            state = (
                "VERIFIED_DOCUMENT_FOUND"
            )

        else:

            state = (
                "CONTENT_VERIFIED_REVIEW"
            )


    elif attempts:

        if any(
            item[
                "state"
            ]
            == "CONTENT_REJECTED"

            for item in attempts
        ):

            state = (
                "NO_CONTENT_VERIFIED_REPORT"
            )

        else:

            state = (
                "NO_VALID_PDF_CANDIDATE"
            )


    elif pages:

        state = (
            "REIT_PAGE_FOUND_NO_PDF"
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
                    "content_score"
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
        f"🎯 Content Score: "
        f"{result['best_score'] if result['best_score'] is not None else 'N/A'}",
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
        f"📄 PDF Attempts: "
        f"{len(result['attempts'])}",
        flush=True
    )


    print_separator()


    print(
        "🏅 PDF CONTENT RESULTS",
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
            f"State="
            f"{item['state']} | "
            f"ContentScore="
            f"{item['content_score']:.2f} | "
            f"FundOK="
            f"{item['content_company_ok']} | "
            f"YearOK="
            f"{item['content_year_ok']} | "
            f"PeriodOK="
            f"{item['content_period_ok']} | "
            f"StatementOK="
            f"{item['content_statement_ok']} | "
            f"Reject="
            f"{item['content_hard_reject']} | "
            f"Pages="
            f"{item['pages_read']}/"
            f"{item['total_pages']} | "
            f"{item['url']}",
            flush=True
        )


        if item[
            "content_reject_reasons"
        ]:

            print(
                "    Reject Reasons: "
                + ", ".join(
                    item[
                        "content_reject_reasons"
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
        "🏆 REIT REPORT DISCOVERY SUMMARY v5.5"
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
            f"Pages="
            f"{len(result['pages_crawled'])} | "
            f"PDFChecks="
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
        f"📚 PDF Text Cache: "
        f"{len(PDF_TEXT_CACHE)}",
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
        "=" * 124,
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
        "📖 PDF Content Verification: ON",
        flush=True
    )


    print(
        f"📄 Max PDF Checks / Report: "
        f"{MAX_PDF_CONTENT_CHECKS}",
        flush=True
    )


    print(
        f"📑 Max PDF Pages Read: "
        f"{MAX_PDF_PAGES_TO_READ}",
        flush=True
    )


    print(
        "🚫 Terms / Valuation / Factsheet / NAV Reject: ON",
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


    active_reits = get_active_reits()


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
