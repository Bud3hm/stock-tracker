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
# REIT REPORT DISCOVERY ENGINE v1
#
# READ ONLY
#
# الهدف:
# 1) العمل على جميع صناديق REIT النشطة
# 2) قراءة التقارير من reit_official_sources.json
# 3) تجربة:
#       - رابط الإعلان
#       - alternate_url
#       - attachment_url
#       - manager URLs
# 4) اكتشاف روابط PDF والمرفقات الرسمية
# 5) اكتشاف روابط مدير الصندوق
# 6) تصنيف أفضل رابط قابل للقراءة
# 7) عدم الكتابة في Supabase
#
# مهم:
# لا يوجد أي Symbol ثابت داخل الكود.
# ============================================================


ENGINE_NAME = "REIT REPORT DISCOVERY ENGINE v1"

REGISTRY_FILENAME = "reit_official_sources.json"

HTTP_TIMEOUT = 30


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
# أدوات
# ============================================================


def print_header(title):

    print(
        "\n"
        + "=" * 104,
        flush=True
    )

    print(
        title,
        flush=True
    )

    print(
        "=" * 104,
        flush=True
    )


def print_separator():

    print(
        "-" * 104,
        flush=True
    )


def normalize_symbol(symbol):

    if not symbol:
        return None

    return str(
        symbol
    ).strip().upper()


def normalize_url(url):

    if not url:
        return None

    return html.unescape(
        str(
            url
        ).strip()
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
# REITs النشطة
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
# استخراج الروابط من HTML
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

        if not full_url:
            continue

        candidates.append(
            full_url
        )


    # ========================================================
    # استخراج URLs الموجودة داخل scripts / text
    # ========================================================

    regex_urls = re.findall(
        r"""https?://[^\s"'<>]+""",
        text,
        flags=re.IGNORECASE
    )


    for url in regex_urls:

        candidates.append(
            url
        )


    # ========================================================
    # relative PDF links
    # ========================================================

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


    # ========================================================
    # إزالة التكرار
    # ========================================================

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
# تصنيف الرابط
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
# ترتيب أفضلية الروابط
# ============================================================


def candidate_priority(
    candidate
):

    candidate_type = candidate.get(
        "candidate_type"
    )

    readable = candidate.get(
        "readable"
    )


    if (
        candidate_type
        == "DIRECT_PDF"
        and readable
    ):

        return 100


    if (
        candidate_type
        == "MANAGER_OR_FINANCIAL"
        and readable
    ):

        return 90


    if (
        candidate_type
        == "SAUDI_EXCHANGE"
        and readable
    ):

        return 80


    if readable:

        return 70


    if candidate_type == "DIRECT_PDF":

        return 50


    return 10


# ============================================================
# فحص رابط Candidate
# ============================================================


def inspect_candidate(url):

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


    return {
        "url":
            url,

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
    }


# ============================================================
# Registry report URLs
# ============================================================


def get_initial_report_urls(
    report,
    reit_entry
):

    items = []


    # ========================================================
    # روابط التقرير نفسه
    # ========================================================

    for field_name in [
        "url",
        "alternate_url",
        "attachment_url",
    ]:

        url = report.get(
            field_name
        )

        if url:

            items.append(
                {
                    "url":
                        url,

                    "origin":
                        field_name,
                }
            )


    alternate_urls = report.get(
        "alternate_urls"
    )


    if isinstance(
        alternate_urls,
        list
    ):

        for url in alternate_urls:

            if url:

                items.append(
                    {
                        "url":
                            url,

                        "origin":
                            "alternate_urls",
                    }
                )


    # ========================================================
    # مصادر الصندوق
    # ========================================================

    sources = reit_entry.get(
        "sources",
        []
    )


    if isinstance(
        sources,
        list
    ):

        for source in sources:

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
                    {
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
                    }
                )


    # ========================================================
    # إزالة التكرار
    # ========================================================

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
# Discovery لتقرير واحد
# ============================================================


def discover_report(
    symbol,
    company_name,
    reit_entry,
    report
):

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
    # المرحلة الأولى
    # ========================================================

    for item in initial_urls:

        inspected = (
            inspect_candidate(
                item[
                    "url"
                ]
            )
        )


        inspected[
            "origin"
        ] = item[
            "origin"
        ]


        attempts.append(
            inspected
        )


        # ====================================================
        # إذا HTML قابل للقراءة نبحث داخله عن روابط أخرى
        # ====================================================

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
    # فلترة روابط واعدة
    # ========================================================

    promising_urls = []


    for url in discovered_urls:

        lower = url.lower()


        if (
            looks_like_pdf(
                url
            )
            or "report" in lower
            or "financial" in lower
            or "reit" in lower
            or "fund" in lower
            or "quarter" in lower
            or "statement" in lower
        ):

            promising_urls.append(
                url
            )


    # لا نريد مئات الطلبات
    promising_urls = (
        promising_urls[
            :30
        ]
    )


    # ========================================================
    # المرحلة الثانية
    # ========================================================

    for url in promising_urls:

        inspected = inspect_candidate(
            url
        )

        inspected[
            "origin"
        ] = "discovered"

        attempts.append(
            inspected
        )


    # ========================================================
    # اختيار أفضل رابط
    # ========================================================

    usable = [

        attempt

        for attempt in attempts

        if attempt[
            "readable"
        ]
    ]


    usable.sort(
        key=candidate_priority,
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
    # Status
    # ========================================================

    if best:

        if (
            best[
                "document_type"
            ]
            == "PDF"
        ):

            discovery_state = (
                "DIRECT_DOCUMENT_FOUND"
            )

        else:

            discovery_state = (
                "READABLE_PAGE_FOUND"
            )

    else:

        blocked = any(
            attempt.get(
                "http_status"
            )
            == 403
            for attempt in attempts
        )

        if blocked:

            discovery_state = (
                "BLOCKED_OR_NOT_FOUND"
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
            report.get(
                "report_type"
            ),

        "period_end":
            report.get(
                "period_end"
            ),

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

        "attempt_count":
            len(
                attempts
            ),

        "attempts":
            attempts,
    }


# ============================================================
# طباعة نتيجة تقرير
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
        f"🔗 Best URL: "
        f"{result['best_url'] or 'NONE'}",
        flush=True
    )


    print(
        f"📑 Document Type: "
        f"{result['best_document_type'] or 'NONE'}",
        flush=True
    )


    print(
        f"📊 Attempts: "
        f"{result['attempt_count']}",
        flush=True
    )


    print_separator()


    for attempt in result[
        "attempts"
    ]:

        print(
            f"- "
            f"{attempt['origin']} | "
            f"{attempt['candidate_type']} | "
            f"{attempt['status']} | "
            f"HTTP={attempt['http_status']} | "
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
        "🏆 REIT REPORT DISCOVERY SUMMARY v1"
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


        print(
            f"{index:02d}. "
            f"{result['symbol']} | "
            f"{result['report_type']} | "
            f"{result['period_end']} | "
            f"State="
            f"{state} | "
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
        "=" * 104,
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


        # لا نفحص صندوق غير نشط
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
