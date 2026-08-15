import os
import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

from supabase import create_client


# ============================================================
# REIT OFFICIAL FETCHER v2
#
# READ ONLY
#
# الهدف:
# 1) فحص كل REIT
# 2) محاولة الوصول للمصدر الرسمي
# 3) التعامل الصحيح مع 403 بدون كسر الـ Pipeline
# 4) دعم Official Source Registry اختياري
# 5) تحديد حالة كل صندوق:
#
#    DIRECT_AVAILABLE
#    REGISTRY_AVAILABLE
#    OFFICIAL_PAGE_BLOCKED
#    NO_OFFICIAL_SOURCE
#
# لا توجد كتابة في Supabase.
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


ENGINE_NAME = "REIT OFFICIAL FETCHER v2"

SAUDI_EXCHANGE_BASE = (
    "https://www.saudiexchange.sa"
)

REIT_PROFILE_BASE = (
    "https://www.saudiexchange.sa/"
    "wps/portal/saudiexchange/hidden/"
    "company-profile-reit/"
)


HTTP_TIMEOUT = 25


# ============================================================
# Optional registry
#
# لاحقًا نستطيع وضع روابط رسمية معروفة هنا أو تمريرها
# من GitHub Secret باسم:
#
# REIT_OFFICIAL_SOURCE_REGISTRY
#
# JSON example:
#
# {
#   "4340.SR": {
#       "fund_manager_url": "...",
#       "saudi_exchange_profile": "...",
#       "reports": [...]
#   }
# }
#
# ============================================================


DEFAULT_SOURCE_REGISTRY = {}


# ============================================================
# General tools
# ============================================================


def print_header(title):

    print(
        "\n" + "=" * 100,
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


def exchange_symbol(symbol):

    if not symbol:
        return None

    symbol = str(
        symbol
    ).strip()

    if symbol.upper().endswith(".SR"):
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
# Source registry
# ============================================================


def load_source_registry():

    raw = os.environ.get(
        "REIT_OFFICIAL_SOURCE_REGISTRY"
    )

    if not raw:
        return DEFAULT_SOURCE_REGISTRY

    try:

        data = json.loads(
            raw
        )

        if isinstance(
            data,
            dict
        ):
            return data

    except Exception as error:

        print(
            "⚠️ Invalid "
            "REIT_OFFICIAL_SOURCE_REGISTRY | "
            f"{type(error).__name__}: {error}",
            flush=True
        )

    return DEFAULT_SOURCE_REGISTRY


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
# HTTP
# ============================================================


def fetch_url(url):

    headers = {
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
                "application/xml;q=0.9,"
                "application/pdf;q=0.8,"
                "*/*;q=0.7"
            ),

        "Accept-Language":
            "en-US,en;q=0.9,ar;q=0.8",

        "Cache-Control":
            "no-cache",
    }

    request = urllib.request.Request(
        url,
        headers=headers
    )

    try:

        with urllib.request.urlopen(
            request,
            timeout=HTTP_TIMEOUT
        ) as response:

            content = response.read()

            return {
                "status":
                    "success",

                "http_status":
                    getattr(
                        response,
                        "status",
                        200
                    ),

                "content":
                    content,

                "content_type":
                    response.headers.get(
                        "Content-Type"
                    ),

                "final_url":
                    response.geturl(),
            }

    except urllib.error.HTTPError as error:

        return {
            "status":
                "http_error",

            "http_status":
                error.code,

            "error":
                str(error),

            "content":
                None,

            "final_url":
                url,
        }

    except urllib.error.URLError as error:

        return {
            "status":
                "network_error",

            "http_status":
                None,

            "error":
                str(error),

            "content":
                None,

            "final_url":
                url,
        }

    except Exception as error:

        return {
            "status":
                "error",

            "http_status":
                None,

            "error":
                (
                    f"{type(error).__name__}: "
                    f"{error}"
                ),

            "content":
                None,

            "final_url":
                url,
        }


# ============================================================
# Test official Saudi Exchange profile
# ============================================================


def test_saudi_exchange_profile(
    symbol
):

    profile_url = build_profile_url(
        symbol
    )

    result = fetch_url(
        profile_url
    )

    result[
        "source_type"
    ] = "saudi_exchange_profile"

    result[
        "source_url"
    ] = profile_url

    return result


# ============================================================
# Registry validation
# ============================================================


def inspect_registry_source(
    symbol,
    registry
):

    config = registry.get(
        symbol
    )

    if not config:
        return None

    if not isinstance(
        config,
        dict
    ):
        return None

    reports = config.get(
        "reports"
    )

    if not isinstance(
        reports,
        list
    ):
        reports = []

    fund_manager_url = config.get(
        "fund_manager_url"
    )

    profile_url = config.get(
        "saudi_exchange_profile"
    )

    return {
        "fund_manager_url":
            fund_manager_url,

        "saudi_exchange_profile":
            profile_url,

        "reports":
            reports,
    }


# ============================================================
# Report record validation
# ============================================================


def validate_report_record(
    report
):

    if not isinstance(
        report,
        dict
    ):
        return False

    url = report.get(
        "url"
    )

    report_type = report.get(
        "report_type"
    )

    if not url:
        return False

    if not report_type:
        return False

    return True


# ============================================================
# Inspect registry reports
# ============================================================


def inspect_registry_reports(
    config
):

    if not config:
        return []

    valid = []

    for report in config.get(
        "reports",
        []
    ):

        if not validate_report_record(
            report
        ):
            continue

        valid.append({
            "report_type":
                report.get(
                    "report_type"
                ),

            "period_end":
                report.get(
                    "period_end"
                ),

            "url":
                report.get(
                    "url"
                ),

            "source":
                report.get(
                    "source"
                )
                or "official_registry",
        })

    return valid


# ============================================================
# Analyze one REIT
# ============================================================


def analyze_reit(
    stock,
    registry
):

    symbol = stock[
        "symbol"
    ]

    company_name = (
        stock.get(
            "company_name"
        )
        or symbol
    )

    direct = (
        test_saudi_exchange_profile(
            symbol
        )
    )

    registry_config = (
        inspect_registry_source(
            symbol,
            registry
        )
    )

    registry_reports = (
        inspect_registry_reports(
            registry_config
        )
        if registry_config
        else []
    )


    # ========================================================
    # State
    # ========================================================

    if direct[
        "status"
    ] == "success":

        source_state = (
            "DIRECT_AVAILABLE"
        )

    elif (
        direct.get(
            "http_status"
        )
        == 403
        and registry_reports
    ):

        source_state = (
            "REGISTRY_AVAILABLE"
        )

    elif (
        direct.get(
            "http_status"
        )
        == 403
    ):

        source_state = (
            "OFFICIAL_PAGE_BLOCKED"
        )

    elif registry_reports:

        source_state = (
            "REGISTRY_AVAILABLE"
        )

    else:

        source_state = (
            "NO_OFFICIAL_SOURCE"
        )


    return {
        "status":
            "success",

        "symbol":
            symbol,

        "company_name":
            company_name,

        "source_state":
            source_state,

        "direct":
            direct,

        "registry":
            registry_config,

        "registry_reports":
            registry_reports,
    }


# ============================================================
# Print
# ============================================================


def print_reit_result(
    result
):

    print_header(
        f"🏢 {result['symbol']} | "
        f"{result['company_name']}"
    )

    print(
        f"🧭 Source State: "
        f"{result['source_state']}",
        flush=True
    )

    direct = result[
        "direct"
    ]

    print_separator()

    print(
        "🌐 SAUDI EXCHANGE PROFILE",
        flush=True
    )

    print(
        f"URL: "
        f"{direct['source_url']}",
        flush=True
    )

    print(
        f"Status: "
        f"{direct['status']}",
        flush=True
    )

    print(
        f"HTTP: "
        f"{direct.get('http_status')}",
        flush=True
    )

    if direct.get(
        "error"
    ):

        print(
            f"Error: "
            f"{direct['error']}",
            flush=True
        )


    print_separator()

    print(
        "📚 OFFICIAL REGISTRY",
        flush=True
    )

    reports = result[
        "registry_reports"
    ]

    if not reports:

        print(
            "⚠️ No registry reports",
            flush=True
        )

    else:

        print(
            f"Reports: "
            f"{len(reports)}",
            flush=True
        )

        for report in reports:

            print(
                "\n"
                f"Type: "
                f"{report['report_type']}",
                flush=True
            )

            print(
                f"Period: "
                f"{report['period_end'] or 'N/A'}",
                flush=True
            )

            print(
                f"Source: "
                f"{report['source']}",
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


def print_summary(
    results
):

    print_header(
        "🏆 REIT OFFICIAL FETCHER SUMMARY v2"
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

    state_counts = {}

    for result in successful:

        state = result[
            "source_state"
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

    for index, result in enumerate(
        successful,
        start=1
    ):

        direct = result[
            "direct"
        ]

        print(
            f"{index:02d}. "
            f"{result['symbol']} | "
            f"{result['company_name']} | "
            f"State="
            f"{result['source_state']} | "
            f"HTTP="
            f"{direct.get('http_status')} | "
            f"RegistryReports="
            f"{len(result['registry_reports'])}",
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

    print(
        "\n📊 SOURCE STATES",
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

    registry = (
        load_source_registry()
    )

    print(
        f"📚 Registry Entries: "
        f"{len(registry)}",
        flush=True
    )

    stocks = (
        get_reit_stocks()
    )

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
            f"🔍 Source Check "
            f"{index}/{len(stocks)} | "
            f"{stock['symbol']}",
            flush=True
        )

        try:

            result = analyze_reit(
                stock,
                registry
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

        results.append(
            result
        )

        if result.get(
            "status"
        ) == "success":

            print_reit_result(
                result
            )

        else:

            print(
                f"🔴 "
                f"{result.get('symbol')} | "
                f"{result.get('error')}",
                flush=True
            )

    print_summary(
        results
    )


if __name__ == "__main__":

    run_reit_official_fetcher()
