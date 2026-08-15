import os
import json
from datetime import datetime, timezone
from pathlib import Path

from supabase import create_client


# ============================================================
# REIT OFFICIAL SOURCE REGISTRY v1
#
# READ ONLY بالنسبة لـ Supabase
#
# الهدف:
# 1) قراءة جميع REITs النشطة
# 2) قراءة سجل المصادر الرسمية من JSON
# 3) التحقق من صحة المصادر والتقارير
# 4) اكتشاف REITs غير المسجلة
# 5) اكتشاف روابط مكررة / بيانات غير مكتملة
# 6) تجهيز Registry عام وقابل للتوسع
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


ENGINE_NAME = "REIT OFFICIAL SOURCE REGISTRY v1"

REGISTRY_FILE = Path(
    os.environ.get(
        "REIT_REGISTRY_FILE",
        "reit_official_sources.json"
    )
)


# ============================================================
# أنواع المصادر المقبولة
# ============================================================


ALLOWED_SOURCE_TYPES = {
    "saudi_exchange",
    "fund_manager",
    "official_pdf",
    "official_api",
    "official_announcement",
}


ALLOWED_REPORT_TYPES = {
    "Q1",
    "Q2",
    "Q3",
    "Q4",
    "H1",
    "FY",
    "quarterly_statement",
    "semiannual_financial",
    "annual_financial",
    "valuation_report",
    "distribution_report",
}


# ============================================================
# أدوات
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


def normalize_symbol(symbol):

    if not symbol:
        return None

    return str(
        symbol
    ).strip().upper()


def normalize_url(url):

    if not url:
        return None

    return str(
        url
    ).strip()


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
            "priority,"
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
# Registry loader
# ============================================================


def load_registry():

    if not REGISTRY_FILE.exists():

        return {
            "version":
                1,

            "updated_at":
                None,

            "reits":
                {}
        }


    try:

        with REGISTRY_FILE.open(
            "r",
            encoding="utf-8"
        ) as file:

            data = json.load(
                file
            )

    except json.JSONDecodeError as error:

        raise RuntimeError(
            "Invalid JSON in "
            f"{REGISTRY_FILE}: "
            f"{error}"
        )


    if not isinstance(
        data,
        dict
    ):

        raise RuntimeError(
            "Registry root must be an object"
        )


    data.setdefault(
        "version",
        1
    )

    data.setdefault(
        "updated_at",
        None
    )

    data.setdefault(
        "reits",
        {}
    )


    if not isinstance(
        data["reits"],
        dict
    ):

        raise RuntimeError(
            "Registry 'reits' must be an object"
        )


    return data


# ============================================================
# Registry entry
# ============================================================


def get_registry_entry(
    registry,
    symbol
):

    symbol = normalize_symbol(
        symbol
    )

    return (
        registry
        .get(
            "reits",
            {}
        )
        .get(
            symbol
        )
    )


# ============================================================
# Validate source
# ============================================================


def validate_source(
    source
):

    findings = []


    if not isinstance(
        source,
        dict
    ):

        return [
            {
                "severity":
                    "FAIL",

                "code":
                    "SOURCE_INVALID",

                "message":
                    "Source must be an object"
            }
        ]


    source_type = source.get(
        "source_type"
    )

    url = normalize_url(
        source.get(
            "url"
        )
    )


    if not source_type:

        findings.append({
            "severity":
                "FAIL",

            "code":
                "SOURCE_TYPE_MISSING",

            "message":
                "source_type is missing"
        })


    elif source_type not in ALLOWED_SOURCE_TYPES:

        findings.append({
            "severity":
                "WARN",

            "code":
                "SOURCE_TYPE_UNKNOWN",

            "message":
                (
                    f"Unknown source_type: "
                    f"{source_type}"
                )
        })


    if not url:

        findings.append({
            "severity":
                "FAIL",

            "code":
                "SOURCE_URL_MISSING",

            "message":
                "Source URL is missing"
        })


    elif not is_http_url(
        url
    ):

        findings.append({
            "severity":
                "FAIL",

            "code":
                "SOURCE_URL_INVALID",

            "message":
                (
                    f"Invalid URL: "
                    f"{url}"
                )
        })


    return findings


# ============================================================
# Validate report
# ============================================================


def validate_report(
    report
):

    findings = []


    if not isinstance(
        report,
        dict
    ):

        return [
            {
                "severity":
                    "FAIL",

                "code":
                    "REPORT_INVALID",

                "message":
                    "Report must be an object"
            }
        ]


    report_type = report.get(
        "report_type"
    )

    period_end = report.get(
        "period_end"
    )

    url = normalize_url(
        report.get(
            "url"
        )
    )

    source_type = report.get(
        "source_type"
    )


    if not report_type:

        findings.append({
            "severity":
                "FAIL",

            "code":
                "REPORT_TYPE_MISSING",

            "message":
                "report_type is missing"
        })


    elif report_type not in ALLOWED_REPORT_TYPES:

        findings.append({
            "severity":
                "WARN",

            "code":
                "REPORT_TYPE_UNKNOWN",

            "message":
                (
                    f"Unknown report_type: "
                    f"{report_type}"
                )
        })


    if not period_end:

        findings.append({
            "severity":
                "WARN",

            "code":
                "REPORT_PERIOD_MISSING",

            "message":
                (
                    f"{report_type or 'report'} "
                    "has no period_end"
                )
        })


    if not url:

        findings.append({
            "severity":
                "FAIL",

            "code":
                "REPORT_URL_MISSING",

            "message":
                (
                    f"{report_type or 'report'} "
                    "has no URL"
                )
        })


    elif not is_http_url(
        url
    ):

        findings.append({
            "severity":
                "FAIL",

            "code":
                "REPORT_URL_INVALID",

            "message":
                (
                    f"Invalid report URL: "
                    f"{url}"
                )
        })


    if (
        source_type
        and source_type
        not in ALLOWED_SOURCE_TYPES
    ):

        findings.append({
            "severity":
                "WARN",

            "code":
                "REPORT_SOURCE_UNKNOWN",

            "message":
                (
                    f"Unknown report source: "
                    f"{source_type}"
                )
        })


    return findings


# ============================================================
# Validate one REIT entry
# ============================================================


def validate_reit_entry(
    symbol,
    entry
):

    findings = []


    if not isinstance(
        entry,
        dict
    ):

        return [
            {
                "severity":
                    "FAIL",

                "code":
                    "REIT_ENTRY_INVALID",

                "message":
                    (
                        f"{symbol} registry entry "
                        "must be an object"
                    )
            }
        ]


    sources = entry.get(
        "sources",
        []
    )

    reports = entry.get(
        "reports",
        []
    )


    if not isinstance(
        sources,
        list
    ):

        findings.append({
            "severity":
                "FAIL",

            "code":
                "SOURCES_INVALID",

            "message":
                "sources must be a list"
        })

        sources = []


    if not isinstance(
        reports,
        list
    ):

        findings.append({
            "severity":
                "FAIL",

            "code":
                "REPORTS_INVALID",

            "message":
                "reports must be a list"
        })

        reports = []


    if not sources:

        findings.append({
            "severity":
                "WARN",

            "code":
                "NO_OFFICIAL_SOURCES",

            "message":
                "No official sources registered"
        })


    if not reports:

        findings.append({
            "severity":
                "WARN",

            "code":
                "NO_REPORTS",

            "message":
                "No official reports registered"
        })


    for index, source in enumerate(
        sources,
        start=1
    ):

        source_findings = (
            validate_source(
                source
            )
        )

        for finding in source_findings:

            finding[
                "message"
            ] = (
                f"Source {index}: "
                f"{finding['message']}"
            )

            findings.append(
                finding
            )


    for index, report in enumerate(
        reports,
        start=1
    ):

        report_findings = (
            validate_report(
                report
            )
        )

        for finding in report_findings:

            finding[
                "message"
            ] = (
                f"Report {index}: "
                f"{finding['message']}"
            )

            findings.append(
                finding
            )


    return findings


# ============================================================
# Duplicate detector
# ============================================================


def find_duplicate_urls(
    registry
):

    url_map = {}

    duplicates = []


    for symbol, entry in (
        registry
        .get(
            "reits",
            {}
        )
        .items()
    ):

        if not isinstance(
            entry,
            dict
        ):
            continue


        for source in entry.get(
            "sources",
            []
        ):

            if not isinstance(
                source,
                dict
            ):
                continue

            url = normalize_url(
                source.get(
                    "url"
                )
            )

            if not url:
                continue

            if url in url_map:

                duplicates.append({
                    "url":
                        url,

                    "first":
                        url_map[
                            url
                        ],

                    "second":
                        (
                            symbol,
                            "source"
                        )
                })

            else:

                url_map[
                    url
                ] = (
                    symbol,
                    "source"
                )


        for report in entry.get(
            "reports",
            []
        ):

            if not isinstance(
                report,
                dict
            ):
                continue

            url = normalize_url(
                report.get(
                    "url"
                )
            )

            if not url:
                continue

            if url in url_map:

                duplicates.append({
                    "url":
                        url,

                    "first":
                        url_map[
                            url
                        ],

                    "second":
                        (
                            symbol,
                            "report"
                        )
                })

            else:

                url_map[
                    url
                ] = (
                    symbol,
                    "report"
                )


    return duplicates


# ============================================================
# Analyze active REIT
# ============================================================


def analyze_reit(
    stock,
    registry
):

    symbol = normalize_symbol(
        stock[
            "symbol"
        ]
    )

    company_name = (
        stock.get(
            "company_name"
        )
        or symbol
    )


    entry = get_registry_entry(
        registry,
        symbol
    )


    if entry is None:

        return {
            "symbol":
                symbol,

            "company_name":
                company_name,

            "registry_state":
                "MISSING",

            "sources":
                0,

            "reports":
                0,

            "fail_count":
                0,

            "warn_count":
                1,

            "findings": [
                {
                    "severity":
                        "WARN",

                    "code":
                        "REGISTRY_ENTRY_MISSING",

                    "message":
                        "REIT is not registered"
                }
            ]
        }


    findings = (
        validate_reit_entry(
            symbol,
            entry
        )
    )


    fail_count = sum(
        1
        for finding in findings
        if finding[
            "severity"
        ] == "FAIL"
    )


    warn_count = sum(
        1
        for finding in findings
        if finding[
            "severity"
        ] == "WARN"
    )


    if fail_count > 0:

        state = "INVALID"

    elif warn_count > 0:

        state = "PARTIAL"

    else:

        state = "READY"


    sources = entry.get(
        "sources",
        []
    )

    reports = entry.get(
        "reports",
        []
    )


    return {
        "symbol":
            symbol,

        "company_name":
            company_name,

        "registry_state":
            state,

        "sources":
            len(
                sources
            )
            if isinstance(
                sources,
                list
            )
            else 0,

        "reports":
            len(
                reports
            )
            if isinstance(
                reports,
                list
            )
            else 0,

        "fail_count":
            fail_count,

        "warn_count":
            warn_count,

        "findings":
            findings
    }


# ============================================================
# Print company
# ============================================================


def print_result(
    result
):

    print_header(
        f"🏢 {result['symbol']} | "
        f"{result['company_name']}"
    )


    print(
        f"🧭 Registry State: "
        f"{result['registry_state']}",
        flush=True
    )


    print(
        f"🌐 Sources: "
        f"{result['sources']}",
        flush=True
    )


    print(
        f"📄 Reports: "
        f"{result['reports']}",
        flush=True
    )


    print(
        f"🔴 Fail: "
        f"{result['fail_count']} | "
        f"🟡 Warning: "
        f"{result['warn_count']}",
        flush=True
    )


    if not result[
        "findings"
    ]:

        print(
            "✅ Registry entry is valid",
            flush=True
        )

        return


    print_separator()


    for finding in result[
        "findings"
    ]:

        severity = finding[
            "severity"
        ]

        icon = (
            "🔴"
            if severity == "FAIL"
            else "🟡"
        )

        print(
            f"{icon} "
            f"[{finding['code']}] "
            f"{finding['message']}",
            flush=True
        )


# ============================================================
# Summary
# ============================================================


def print_summary(
    results,
    registry
):

    print_header(
        "🏆 REIT SOURCE REGISTRY SUMMARY v1"
    )


    for index, result in enumerate(
        results,
        start=1
    ):

        print(
            f"{index:02d}. "
            f"{result['symbol']} | "
            f"{result['company_name']} | "
            f"State="
            f"{result['registry_state']} | "
            f"Sources="
            f"{result['sources']} | "
            f"Reports="
            f"{result['reports']} | "
            f"Fail="
            f"{result['fail_count']} | "
            f"Warn="
            f"{result['warn_count']}",
            flush=True
        )


    print_separator()


    state_counts = {}


    for result in results:

        state = result[
            "registry_state"
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
        f"🏢 Active REITs: "
        f"{len(results)}",
        flush=True
    )


    print(
        f"📚 Registry Entries: "
        f"{len(registry.get('reits', {}))}",
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


    duplicates = (
        find_duplicate_urls(
            registry
        )
    )


    print_separator()


    if duplicates:

        print(
            f"🟡 Duplicate URLs: "
            f"{len(duplicates)}",
            flush=True
        )

        for duplicate in duplicates:

            print(
                f"- {duplicate['url']}",
                flush=True
            )

    else:

        print(
            "✅ No duplicate official URLs",
            flush=True
        )


    print(
        "=" * 100,
        flush=True
    )


# ============================================================
# Main
# ============================================================


def run_registry_audit():

    print_header(
        ENGINE_NAME
    )


    print(
        "🔒 Supabase Mode: READ ONLY",
        flush=True
    )


    print(
        f"📁 Registry File: "
        f"{REGISTRY_FILE}",
        flush=True
    )


    print(
        f"🕐 Started: "
        f"{datetime.now(timezone.utc).isoformat()}",
        flush=True
    )


    stocks = get_reit_stocks()

    registry = load_registry()


    print(
        f"🏢 Active REITs: "
        f"{len(stocks)}",
        flush=True
    )


    print(
        f"📚 Registry Entries: "
        f"{len(registry.get('reits', {}))}",
        flush=True
    )


    results = []


    for stock in stocks:

        result = analyze_reit(
            stock,
            registry
        )

        results.append(
            result
        )

        print_result(
            result
        )


    print_summary(
        results,
        registry
    )


if __name__ == "__main__":

    run_registry_audit()
