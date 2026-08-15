import os
import re
import json
import html
import urllib.error
import urllib.request

from io import BytesIO
from pathlib import Path
from datetime import datetime, timezone
from html.parser import HTMLParser

from supabase import create_client


# ============================================================
# REIT OFFICIAL REPORT READER v1
#
# MODE: READ ONLY
#
# الهدف:
# 1) قراءة جميع REITs من Registry
# 2) قراءة التقارير الرسمية المسجلة
# 3) تجربة الرابط الأساسي + الروابط البديلة إن وجدت
# 4) التعامل مع:
#       HTML
#       PDF
#       403
#       redirects
# 5) استخراج مؤشرات REIT الممكنة من التقرير
# 6) طباعة النتائج فقط
#
# لا توجد أي كتابة في Supabase.
# ============================================================


ENGINE_NAME = "REIT OFFICIAL REPORT READER v1"

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
# Optional PDF support
#
# إذا كانت pypdf موجودة نستخدمها.
# إذا لم تكن موجودة لا يفشل المحرك.
# ============================================================


try:

    from pypdf import PdfReader

    PDF_SUPPORT = True

except ImportError:

    PdfReader = None
    PDF_SUPPORT = False


# ============================================================
# HTML text parser
# ============================================================


class VisibleTextParser(HTMLParser):

    def __init__(self):

        super().__init__()

        self.parts = []

        self.ignore_depth = 0


    def handle_starttag(
        self,
        tag,
        attrs
    ):

        tag = tag.lower()

        if tag in {
            "script",
            "style",
            "noscript"
        }:

            self.ignore_depth += 1


    def handle_endtag(
        self,
        tag
    ):

        tag = tag.lower()

        if (
            tag in {
                "script",
                "style",
                "noscript"
            }
            and self.ignore_depth > 0
        ):

            self.ignore_depth -= 1


    def handle_data(
        self,
        data
    ):

        if self.ignore_depth > 0:
            return

        value = str(
            data
        ).strip()

        if value:

            self.parts.append(
                value
            )


    def get_text(self):

        return "\n".join(
            self.parts
        )


# ============================================================
# أدوات طباعة
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


# ============================================================
# أدوات نص
# ============================================================


def normalize_space(value):

    if value is None:
        return ""

    value = html.unescape(
        str(value)
    )

    value = value.replace(
        "\xa0",
        " "
    )

    value = re.sub(
        r"[ \t]+",
        " ",
        value
    )

    value = re.sub(
        r"\n{3,}",
        "\n\n",
        value
    )

    return value.strip()


def normalize_number_text(value):

    if value is None:
        return None

    value = str(
        value
    ).strip()

    # Arabic comma / ordinary commas
    value = value.replace(
        ",",
        ""
    )

    value = value.replace(
        "٬",
        ""
    )

    value = value.replace(
        "−",
        "-"
    )

    value = value.replace(
        "%",
        ""
    )

    value = value.strip()

    try:

        return float(
            value
        )

    except (
        TypeError,
        ValueError
    ):

        return None


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


    seen = set()


    for candidate in candidates:

        candidate = (
            candidate.resolve()
        )

        if str(
            candidate
        ) in seen:

            continue

        seen.add(
            str(
                candidate
            )
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
# Report URLs
# ============================================================


def get_report_urls(report):

    urls = []


    primary = report.get(
        "url"
    )


    if primary:

        urls.append(
            {
                "url":
                    primary,

                "role":
                    "primary"
            }
        )


    alternate_url = report.get(
        "alternate_url"
    )


    if alternate_url:

        urls.append(
            {
                "url":
                    alternate_url,

                "role":
                    "alternate"
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

            if not url:
                continue

            urls.append(
                {
                    "url":
                        url,

                    "role":
                        "alternate"
                }
            )


    attachment_url = report.get(
        "attachment_url"
    )


    if attachment_url:

        urls.append(
            {
                "url":
                    attachment_url,

                "role":
                    "attachment"
            }
        )


    # إزالة التكرار
    unique = []

    seen = set()


    for item in urls:

        url = str(
            item[
                "url"
            ]
        ).strip()


        if not url:
            continue


        if url in seen:
            continue


        seen.add(
            url
        )

        unique.append(
            item
        )


    return unique


# ============================================================
# Content type
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


    content = response.get(
        "content"
    ) or b""


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
            :1000
        ].lower()
    ):

        return "HTML"


    return "UNKNOWN"


# ============================================================
# HTML extraction
# ============================================================


def extract_html_text(content):

    try:

        decoded = content.decode(
            "utf-8",
            errors="replace"
        )


    except Exception:

        decoded = str(
            content
        )


    parser = VisibleTextParser()

    parser.feed(
        decoded
    )


    return normalize_space(
        parser.get_text()
    )


# ============================================================
# PDF extraction
# ============================================================


def extract_pdf_text(content):

    if not PDF_SUPPORT:

        return (
            None,
            "PYPDF_NOT_INSTALLED"
        )


    try:

        reader = PdfReader(
            BytesIO(
                content
            )
        )


        pages = []


        for page in reader.pages:

            text = page.extract_text()

            if text:

                pages.append(
                    text
                )


        return (
            normalize_space(
                "\n".join(
                    pages
                )
            ),
            None
        )


    except Exception as error:

        return (
            None,
            (
                f"{type(error).__name__}: "
                f"{error}"
            )
        )


# ============================================================
# Metric patterns
#
# هذه الأنماط عامة وليست خاصة بصندوق واحد.
# ============================================================


METRIC_PATTERNS = {

    "net_assets": [

        r"صافي\s+قيمة\s+الأصول[^0-9\-]{0,80}"
        r"([\-]?[0-9][0-9,٬.]*)",

        r"صافي\s+الأصول[^0-9\-]{0,80}"
        r"([\-]?[0-9][0-9,٬.]*)",

        r"net\s+asset(?:s)?[^0-9\-]{0,80}"
        r"([\-]?[0-9][0-9,.]*)",
    ],


    "net_income": [

        r"صافي\s+الربح[^0-9\-]{0,80}"
        r"([\-]?[0-9][0-9,٬.]*)",

        r"صافي\s+الدخل[^0-9\-]{0,80}"
        r"([\-]?[0-9][0-9,٬.]*)",

        r"net\s+(?:profit|income)[^0-9\-]{0,80}"
        r"([\-]?[0-9][0-9,.]*)",
    ],


    "total_expenses": [

        r"إجمالي\s+المصاريف[^0-9\-]{0,80}"
        r"([\-]?[0-9][0-9,٬.]*)",

        r"المصاريف\s+والأتعاب[^0-9\-]{0,80}"
        r"([\-]?[0-9][0-9,٬.]*)",

        r"total\s+(?:expenses|fees)[^0-9\-]{0,80}"
        r"([\-]?[0-9][0-9,.]*)",
    ],


    "total_assets": [

        r"إجمالي\s+الأصول[^0-9\-]{0,80}"
        r"([\-]?[0-9][0-9,٬.]*)",

        r"total\s+assets[^0-9\-]{0,80}"
        r"([\-]?[0-9][0-9,.]*)",
    ],


    "total_debt": [

        r"إجمالي\s+(?:الديون|الاقتراض)[^0-9\-]{0,80}"
        r"([\-]?[0-9][0-9,٬.]*)",

        r"total\s+(?:debt|borrowings)[^0-9\-]{0,80}"
        r"([\-]?[0-9][0-9,.]*)",
    ],


    "rental_income": [

        r"دخل\s+الإيجارات[^0-9\-]{0,80}"
        r"([\-]?[0-9][0-9,٬.]*)",

        r"rental\s+income[^0-9\-]{0,80}"
        r"([\-]?[0-9][0-9,.]*)",
    ],


    "nav_per_unit": [

        r"صافي\s+قيمة\s+الأصول\s+للوحدة[^0-9\-]{0,80}"
        r"([\-]?[0-9][0-9,٬.]*)",

        r"net\s+asset\s+value\s+per\s+unit[^0-9\-]{0,80}"
        r"([\-]?[0-9][0-9,.]*)",

        r"nav\s+per\s+unit[^0-9\-]{0,80}"
        r"([\-]?[0-9][0-9,.]*)",
    ],


    "number_of_units": [

        r"عدد\s+الوحدات[^0-9]{0,80}"
        r"([0-9][0-9,٬.]*)",

        r"number\s+of\s+units[^0-9]{0,80}"
        r"([0-9][0-9,.]*)",
    ],


    "occupancy_rate": [

        r"نسبة\s+الإشغال[^0-9]{0,80}"
        r"([0-9][0-9,.]*)\s*%?",

        r"occupancy\s+rate[^0-9]{0,80}"
        r"([0-9][0-9,.]*)\s*%?",
    ],


    "debt_to_assets": [

        r"نسبة\s+(?:الاقتراض|الديون)[^0-9]{0,80}"
        r"([0-9][0-9,.]*)\s*%?",

        r"(?:debt|borrowing)[^0-9]{0,80}"
        r"([0-9][0-9,.]*)\s*%?",
    ],
}


# ============================================================
# Metric extraction
# ============================================================


def extract_metrics_from_text(
    text
):

    results = {}


    if not text:

        return results


    for (
        metric_name,
        patterns
    ) in METRIC_PATTERNS.items():

        for pattern in patterns:

            match = re.search(
                pattern,
                text,
                flags=re.IGNORECASE
            )


            if not match:
                continue


            value = normalize_number_text(
                match.group(
                    1
                )
            )


            if value is None:
                continue


            results[
                metric_name
            ] = value

            break


    return results


# ============================================================
# Fetch report with fallback
# ============================================================


def fetch_report(
    report
):

    candidates = get_report_urls(
        report
    )


    attempts = []


    for candidate in candidates:

        response = fetch_url(
            candidate[
                "url"
            ]
        )


        attempt = {
            "role":
                candidate[
                    "role"
                ],

            "url":
                candidate[
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

            "final_url":
                response.get(
                    "final_url"
                ),

            "error":
                response.get(
                    "error"
                ),
        }


        attempts.append(
            attempt
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


        text = None
        extraction_error = None


        if document_type == "HTML":

            text = extract_html_text(
                response[
                    "content"
                ]
            )


        elif document_type == "PDF":

            (
                text,
                extraction_error
            ) = extract_pdf_text(
                response[
                    "content"
                ]
            )


        metrics = (
            extract_metrics_from_text(
                text
            )
            if text
            else {}
        )


        return {
            "status":
                "SUCCESS",

            "selected_url":
                candidate[
                    "url"
                ],

            "selected_role":
                candidate[
                    "role"
                ],

            "final_url":
                response.get(
                    "final_url"
                ),

            "http_status":
                response.get(
                    "http_status"
                ),

            "document_type":
                document_type,

            "text_length":
                len(
                    text
                )
                if text
                else 0,

            "metrics":
                metrics,

            "extraction_error":
                extraction_error,

            "attempts":
                attempts,
        }


    return {
        "status":
            "UNAVAILABLE",

        "selected_url":
            None,

        "selected_role":
            None,

        "final_url":
            None,

        "http_status":
            None,

        "document_type":
            None,

        "text_length":
            0,

        "metrics":
            {},

        "extraction_error":
            None,

        "attempts":
            attempts,
    }


# ============================================================
# Analyze one registered report
# ============================================================


def analyze_report(
    symbol,
    company_name,
    report
):

    report_type = report.get(
        "report_type"
    )

    period_end = report.get(
        "period_end"
    )


    result = fetch_report(
        report
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

        "source_type":
            report.get(
                "source_type"
            ),

        "read_status":
            result[
                "status"
            ],

        "selected_url":
            result.get(
                "selected_url"
            ),

        "selected_role":
            result.get(
                "selected_role"
            ),

        "http_status":
            result.get(
                "http_status"
            ),

        "document_type":
            result.get(
                "document_type"
            ),

        "text_length":
            result.get(
                "text_length",
                0
            ),

        "metrics":
            result.get(
                "metrics",
                {}
            ),

        "extraction_error":
            result.get(
                "extraction_error"
            ),

        "attempts":
            result.get(
                "attempts",
                []
            ),
    }


# ============================================================
# Print report
# ============================================================


def print_report_result(
    result
):

    print_header(
        f"📄 {result['symbol']} | "
        f"{result['report_type']} | "
        f"{result['period_end']}"
    )


    print(
        f"🏢 Company: "
        f"{result['company_name']}",
        flush=True
    )


    print(
        f"🧭 Read Status: "
        f"{result['read_status']}",
        flush=True
    )


    print(
        f"🌐 HTTP: "
        f"{result['http_status']}",
        flush=True
    )


    print(
        f"📑 Document Type: "
        f"{result['document_type']}",
        flush=True
    )


    print(
        f"📝 Extracted Text Length: "
        f"{result['text_length']}",
        flush=True
    )


    if result[
        "selected_role"
    ]:

        print(
            f"🔗 Selected Role: "
            f"{result['selected_role']}",
            flush=True
        )


    print_separator()


    print(
        "🌐 URL ATTEMPTS",
        flush=True
    )


    for attempt in result[
        "attempts"
    ]:

        print(
            f"- {attempt['role']} | "
            f"{attempt['status']} | "
            f"HTTP={attempt['http_status']} | "
            f"{attempt['url']}",
            flush=True
        )


    print_separator()


    print(
        "📊 EXTRACTED METRICS",
        flush=True
    )


    metrics = result[
        "metrics"
    ]


    if metrics:

        for (
            metric_name,
            metric_value
        ) in sorted(
            metrics.items()
        ):

            print(
                f"{metric_name:<30} "
                f"{metric_value}",
                flush=True
            )


    else:

        print(
            "⚠️ No financial metrics extracted",
            flush=True
        )


    if result[
        "extraction_error"
    ]:

        print(
            "\n⚠️ Extraction Error: "
            f"{result['extraction_error']}",
            flush=True
        )


# ============================================================
# Summary
# ============================================================


def print_summary(
    results
):

    print_header(
        "🏆 REIT OFFICIAL REPORT READER SUMMARY v1"
    )


    successful = [
        result
        for result in results
        if result[
            "read_status"
        ] == "SUCCESS"
    ]


    unavailable = [
        result
        for result in results
        if result[
            "read_status"
        ] != "SUCCESS"
    ]


    metric_reports = [
        result
        for result in successful
        if result[
            "metrics"
        ]
    ]


    for index, result in enumerate(
        results,
        start=1
    ):

        print(
            f"{index:02d}. "
            f"{result['symbol']} | "
            f"{result['report_type']} | "
            f"{result['period_end']} | "
            f"Read="
            f"{result['read_status']} | "
            f"HTTP="
            f"{result['http_status']} | "
            f"Type="
            f"{result['document_type']} | "
            f"Metrics="
            f"{len(result['metrics'])}",
            flush=True
        )


    print_separator()


    print(
        f"📄 Total Reports: "
        f"{len(results)}",
        flush=True
    )


    print(
        f"🟢 Read Success: "
        f"{len(successful)}",
        flush=True
    )


    print(
        f"📊 Reports With Metrics: "
        f"{len(metric_reports)}",
        flush=True
    )


    print(
        f"🟡 Unavailable: "
        f"{len(unavailable)}",
        flush=True
    )


    print(
        f"📦 PDF Support: "
        f"{PDF_SUPPORT}",
        flush=True
    )


    print(
        "=" * 104,
        flush=True
    )


# ============================================================
# Main
# ============================================================


def run_report_reader():

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


    print(
        f"📦 PDF Support: "
        f"{PDF_SUPPORT}",
        flush=True
    )


    active_reits = (
        get_active_reits()
    )


    active_symbols = {
        str(
            stock[
                "symbol"
            ]
        ).strip().upper():
            stock

        for stock in active_reits
    }


    results = []


    for symbol, entry in (
        registry[
            "reits"
        ].items()
    ):

        symbol = str(
            symbol
        ).strip().upper()


        if symbol not in active_symbols:

            continue


        company_name = (
            entry.get(
                "company_name"
            )
            or active_symbols[
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


            result = analyze_report(
                symbol,
                company_name,
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

    run_report_reader()
