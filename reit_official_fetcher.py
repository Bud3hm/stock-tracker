import os
import re
import html
import urllib.parse
import urllib.request
from datetime import datetime, timezone

from supabase import create_client


# ============================================================
# REIT OFFICIAL FETCHER v1
#
# READ ONLY
#
# الهدف:
# 1) قراءة جميع REITs من Supabase
# 2) فتح صفحة كل صندوق في Saudi Exchange
# 3) اكتشاف روابط التقارير الرسمية
# 4) تصنيف:
#       Quarterly Report
#       Financial Report
#       Annual Report
#       Valuation Report
#       Risk Assessment Report
# 5) طباعة النتائج فقط
#
# لا توجد أي كتابة في Supabase.
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


ENGINE_NAME = "REIT OFFICIAL FETCHER v1"


# ============================================================
# Saudi Exchange
# ============================================================


SAUDI_EXCHANGE_BASE = (
    "https://www.saudiexchange.sa"
)


REIT_PROFILE_BASE = (
    "https://www.saudiexchange.sa/"
    "wps/portal/saudiexchange/hidden/"
    "company-profile-reit/"
)


# ============================================================
# HTTP
# ============================================================


USER_AGENT = (
    "Mozilla/5.0 "
    "(Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 "
    "(KHTML, like Gecko) "
    "Chrome/126.0 Safari/537.36"
)


HTTP_TIMEOUT = 30


# ============================================================
# Tools
# ============================================================


def print_header(title):

    print(
        "\n"
        + "=" * 100,
        flush=True
    )

    print(
        title,
        flush=True
    )

    print(
        "=" * 100,
        flush=True
    )


def print_separator():

    print(
        "-" * 100,
        flush=True
    )


def normalize_space(value):

    if value is None:
        return ""

    value = html.unescape(
        str(value)
    )

    value = re.sub(
        r"<[^>]+>",
        " ",
        value
    )

    value = re.sub(
        r"\s+",
        " ",
        value
    )

    return value.strip()


def absolute_url(url):

    if not url:
        return None

    url = html.unescape(
        url
    )

    return urllib.parse.urljoin(
        SAUDI_EXCHANGE_BASE,
        url
    )


def fetch_html(url):

    request = urllib.request.Request(
        url,
        headers={
            "User-Agent":
                USER_AGENT,

            "Accept":
                (
                    "text/html,"
                    "application/xhtml+xml,"
                    "application/xml;q=0.9,*/*;q=0.8"
                ),

            "Accept-Language":
                "en-US,en;q=0.9",
        }
    )

    with urllib.request.urlopen(
        request,
        timeout=HTTP_TIMEOUT
    ) as response:

        raw = response.read()

        charset = (
            response.headers.get_content_charset()
            or "utf-8"
        )

        try:

            return raw.decode(
                charset,
                errors="replace"
            )

        except LookupError:

            return raw.decode(
                "utf-8",
                errors="replace"
            )


# ============================================================
# Supabase
# ============================================================


def get_reit_stocks():

    response = (
        supabase
        .table("stocks")
        .select(
            "id,"
            "symbol,"
            "company_name,"
            "analysis_model,"
            "priority"
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
            "priority",
            desc=True
        )
        .order(
            "id"
        )
        .execute()
    )

    return response.data or []


# ============================================================
# Symbol handling
# ============================================================


def exchange_symbol(symbol):

    if not symbol:
        return None

    symbol = str(
        symbol
    ).strip()

    if symbol.upper().endswith(
        ".SR"
    ):

        symbol = symbol[:-3]

    return symbol


def build_profile_url(symbol):

    code = exchange_symbol(
        symbol
    )

    return (
        f"{REIT_PROFILE_BASE}"
        f"?companySymbol={code}"
    )


# ============================================================
# Report classification
# ============================================================


REPORT_PATTERNS = {

    "quarterly_report": [
        r"quarterly report",
        r"quarterly statement",
        r"quarterly_statement",
        r"quarterly-report",
    ],

    "financial_report": [
        r"financial reports?",
        r"financial statements?",
        r"financial_report",
        r"financial-report",
    ],

    "annual_report": [
        r"annual report",
        r"annual_report",
        r"annual-report",
    ],

    "valuation_report": [
        r"valuation reports?",
        r"valuation_report",
        r"valuation-report",
    ],

    "risk_assessment_report": [
        r"risk assessment",
        r"risk_assessment",
        r"risk-assessment",
    ],
}


def classify_report(
    label,
    url
):

    combined = (
        f"{label or ''} "
        f"{url or ''}"
    ).lower()

    for report_type, patterns in (
        REPORT_PATTERNS.items()
    ):

        for pattern in patterns:

            if re.search(
                pattern,
                combined,
                flags=re.IGNORECASE
            ):

                return report_type

    return None


# ============================================================
# Period extraction
# ============================================================


DATE_PATTERNS = [

    r"\b20\d{2}-\d{2}-\d{2}\b",

    r"\b20\d{2}/\d{2}/\d{2}\b",

    r"\b\d{2}/\d{2}/20\d{2}\b",
]


def extract_date(text):

    if not text:
        return None

    for pattern in DATE_PATTERNS:

        match = re.search(
            pattern,
            text
        )

        if not match:
            continue

        value = match.group(0)

        if re.match(
            r"20\d{2}/",
            value
        ):

            return value.replace(
                "/",
                "-"
            )

        if re.match(
            r"\d{2}/\d{2}/20\d{2}",
            value
        ):

            try:

                parsed = datetime.strptime(
                    value,
                    "%d/%m/%Y"
                )

                return parsed.strftime(
                    "%Y-%m-%d"
                )

            except Exception:

                return value

        return value

    return None


def extract_year(text):

    if not text:
        return None

    match = re.search(
        r"\b(20\d{2})\b",
        text
    )

    if not match:
        return None

    return int(
        match.group(1)
    )


def extract_quarter(text):

    if not text:
        return None

    normalized = text.upper()

    for quarter in [
        "Q1",
        "Q2",
        "Q3",
        "Q4",
    ]:

        if re.search(
            rf"\b{quarter}\b",
            normalized
        ):

            return quarter

    return None


# ============================================================
# Link extraction
# ============================================================


ANCHOR_PATTERN = re.compile(
    r"""
    <a
    \s+
    [^>]*?
    href\s*=\s*
    ["']
    (?P<href>[^"']+)
    ["']
    [^>]*?
    >
    (?P<label>.*?)
    </a>
    """,
    flags=(
        re.IGNORECASE
        |
        re.DOTALL
        |
        re.VERBOSE
    )
)


def extract_links(page_html):

    links = []

    for match in ANCHOR_PATTERN.finditer(
        page_html
    ):

        href = match.group(
            "href"
        )

        label = normalize_space(
            match.group(
                "label"
            )
        )

        full_url = absolute_url(
            href
        )

        if not full_url:
            continue

        links.append({
            "label":
                label,

            "url":
                full_url,
        })

    return links


# ============================================================
# Additional resource URL extraction
#
# بعض صفحات تداول تحتوي PDF links داخل attributes أو scripts
# وليس anchor واضح.
# ============================================================


RESOURCE_PATTERN = re.compile(
    r"""
    (?P<url>
        https?://
        [^"'<> \t\r\n]+
        |
        /Resources/
        [^"'<> \t\r\n]+
    )
    """,
    flags=(
        re.IGNORECASE
        |
        re.VERBOSE
    )
)


def extract_resource_urls(
    page_html
):

    results = []

    seen = set()

    for match in RESOURCE_PATTERN.finditer(
        page_html
    ):

        url = absolute_url(
            match.group(
                "url"
            )
        )

        if not url:
            continue

        url = url.rstrip(
            ").,;"
        )

        if url in seen:
            continue

        seen.add(
            url
        )

        results.append(
            url
        )

    return results


# ============================================================
# Build candidate report list
# ============================================================


def discover_reports(
    page_html
):

    candidates = []

    seen = set()


    # ========================================================
    # Anchors
    # ========================================================

    for link in extract_links(
        page_html
    ):

        label = link[
            "label"
        ]

        url = link[
            "url"
        ]

        report_type = classify_report(
            label,
            url
        )


        # PDF/Resources URLs are worth keeping even when
        # the anchor label itself is vague.
        is_resource = (
            "/Resources/"
            in url
            or url.lower().endswith(
                ".pdf"
            )
        )


        if (
            report_type is None
            and not is_resource
        ):

            continue


        key = (
            report_type,
            url
        )

        if key in seen:
            continue

        seen.add(
            key
        )


        candidates.append({

            "report_type":
                report_type
                or "resource",

            "label":
                label,

            "url":
                url,

            "period_end":
                extract_date(
                    f"{label} {url}"
                ),

            "year":
                extract_year(
                    f"{label} {url}"
                ),

            "quarter":
                extract_quarter(
                    f"{label} {url}"
                ),
        })


    # ========================================================
    # Raw resource URLs
    # ========================================================

    for url in extract_resource_urls(
        page_html
    ):

        key = (
            "resource",
            url
        )

        if key in seen:
            continue

        seen.add(
            key
        )


        candidates.append({

            "report_type":
                classify_report(
                    "",
                    url
                )
                or "resource",

            "label":
                "",

            "url":
                url,

            "period_end":
                extract_date(
                    url
                ),

            "year":
                extract_year(
                    url
                ),

            "quarter":
                extract_quarter(
                    url
                ),
        })


    return candidates


# ============================================================
# Page-level category detection
# ============================================================


def detect_page_sections(
    page_html
):

    text = normalize_space(
        page_html
    ).lower()

    results = {}


    for report_type, patterns in (
        REPORT_PATTERNS.items()
    ):

        found = False

        for pattern in patterns:

            if re.search(
                pattern,
                text,
                flags=re.IGNORECASE
            ):

                found = True
                break

        results[
            report_type
        ] = found


    return results


# ============================================================
# Analyze one REIT
# ============================================================


def analyze_reit(stock):

    symbol = stock[
        "symbol"
    ]

    company_name = (
        stock.get(
            "company_name"
        )
        or symbol
    )

    profile_url = build_profile_url(
        symbol
    )


    page_html = fetch_html(
        profile_url
    )


    reports = discover_reports(
        page_html
    )


    sections = detect_page_sections(
        page_html
    )


    # ========================================================
    # Group
    # ========================================================

    grouped = {}

    for report in reports:

        grouped.setdefault(
            report[
                "report_type"
            ],
            []
        )

        grouped[
            report[
                "report_type"
            ]
        ].append(
            report
        )


    return {

        "status":
            "success",

        "symbol":
            symbol,

        "company_name":
            company_name,

        "profile_url":
            profile_url,

        "page_size":
            len(
                page_html
            ),

        "sections":
            sections,

        "reports":
            reports,

        "grouped":
            grouped,
    }


# ============================================================
# Printing
# ============================================================


def print_reit_result(result):

    print_header(
        f"🏢 {result['symbol']} | "
        f"{result['company_name']}"
    )


    print(
        f"🌐 Profile: "
        f"{result['profile_url']}",
        flush=True
    )


    print(
        f"📄 HTML Size: "
        f"{result['page_size']}",
        flush=True
    )


    print_separator()


    print(
        "📚 DETECTED SECTIONS",
        flush=True
    )


    for (
        report_type,
        found
    ) in result[
        "sections"
    ].items():

        icon = (
            "✅"
            if found
            else "❌"
        )

        print(
            f"{icon} "
            f"{report_type}",
            flush=True
        )


    print_separator()


    print(
        "🔗 DISCOVERED REPORT LINKS",
        flush=True
    )


    if not result[
        "reports"
    ]:

        print(
            "⚠️ No report links discovered",
            flush=True
        )

        return


    grouped = result[
        "grouped"
    ]


    for report_type in sorted(
        grouped.keys()
    ):

        reports = grouped[
            report_type
        ]


        print(
            f"\n📁 {report_type} "
            f"({len(reports)})",
            flush=True
        )


        reports = sorted(
            reports,
            key=lambda item: (
                item.get(
                    "period_end"
                )
                or "",
                item.get(
                    "year"
                )
                or 0,
                item.get(
                    "url"
                )
                or "",
            ),
            reverse=True
        )


        for report in reports:

            print(
                "\n"
                f"Type: "
                f"{report['report_type']}",
                flush=True
            )

            print(
                f"Label: "
                f"{report['label'] or 'N/A'}",
                flush=True
            )

            print(
                f"Period: "
                f"{report['period_end'] or 'N/A'}",
                flush=True
            )

            print(
                f"Year: "
                f"{report['year'] or 'N/A'}",
                flush=True
            )

            print(
                f"Quarter: "
                f"{report['quarter'] or 'N/A'}",
                flush=True
            )

            print(
                f"URL: "
                f"{report['url']}",
                flush=True
            )


# ============================================================
# Summary
# ============================================================


def print_summary(results):

    print_header(
        "🏆 REIT OFFICIAL FETCHER SUMMARY v1"
    )


    successful = [

        result

        for result in results

        if result.get(
            "status"
        ) == "success"
    ]


    errors = [

        result

        for result in results

        if result.get(
            "status"
        ) != "success"
    ]


    for index, result in enumerate(
        successful,
        start=1
    ):

        grouped = result[
            "grouped"
        ]


        print(
            f"{index:02d}. "
            f"{result['symbol']} | "
            f"{result['company_name']} | "
            f"Reports="
            f"{len(result['reports'])} | "
            f"Quarterly="
            f"{len(grouped.get('quarterly_report', []))} | "
            f"Financial="
            f"{len(grouped.get('financial_report', []))} | "
            f"Annual="
            f"{len(grouped.get('annual_report', []))} | "
            f"Resources="
            f"{len(grouped.get('resource', []))}",
            flush=True
        )


    print_separator()


    print(
        f"🏢 Total REITs: "
        f"{len(results)}",
        flush=True
    )


    print(
        f"🟢 Success: "
        f"{len(successful)}",
        flush=True
    )


    print(
        f"🔴 Errors: "
        f"{len(errors)}",
        flush=True
    )


    if errors:

        print(
            "\n🔴 ERRORS",
            flush=True
        )


        for result in errors:

            print(
                f"- {result.get('symbol')} | "
                f"{result.get('error')}",
                flush=True
            )


    print(
        "=" * 100,
        flush=True
    )


# ============================================================
# Main
# ============================================================


def run_reit_official_fetcher():

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


    stocks = get_reit_stocks()


    print(
        f"🏢 Active REITs: "
        f"{len(stocks)}",
        flush=True
    )


    results = []


    for index, stock in enumerate(
        stocks,
        start=1
    ):

        print(
            "\n"
            f"🌐 Official Discovery "
            f"{index}/{len(stocks)} | "
            f"{stock['symbol']}",
            flush=True
        )


        try:

            result = analyze_reit(
                stock
            )


        except Exception as error:

            result = {

                "status":
                    "error",

                "symbol":
                    stock.get(
                        "symbol"
                    ),

                "company_name":
                    stock.get(
                        "company_name"
                    ),

                "error":
                    (
                        f"{type(error).__name__}: "
                        f"{error}"
                    ),
            }


            print(
                f"🔴 "
                f"{stock.get('symbol')} | "
                f"{result['error']}",
                flush=True
            )


        results.append(
            result
        )


        if result.get(
            "status"
        ) == "success":

            print_reit_result(
                result
            )


    print_summary(
        results
    )


if __name__ == "__main__":

    run_reit_official_fetcher()
