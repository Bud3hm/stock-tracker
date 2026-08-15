import os
from datetime import datetime, timezone
from supabase import create_client

from reit_period_schema import (
    identify_reit_period,
    build_reit_audit_requirements,
    validate_reit_period,
)


# ============================================================
# REIT OFFICIAL DATA ENGINE v2
#
# READ ONLY
#
# الهدف:
# 1) فحص جميع صناديق REIT
# 2) تطبيق REIT Period Schema الصحيح
# 3) الفصل بين:
#       Quarterly Statement
#       H1 Financial Report
#       FY Financial Report
# 4) تحديد ما ينقص كل فترة
# 5) تحديد المصدر المطلوب
# 6) عدم الكتابة في Supabase
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
# أسماء المحرك
# ============================================================

ENGINE_NAME = "REIT OFFICIAL DATA ENGINE v2"
READ_ONLY = True


# ============================================================
# خرائط Yahoo/Raw → REIT Schema
#
# هذه المرحلة لا تجلب المصدر الرسمي بعد.
# فقط نوحد ما لدينا حاليًا.
# ============================================================


QUARTERLY_RAW_MAP = {

    "quarterlyTotalRevenue":
        "rental_income",

    "quarterlyTotalAssets":
        "total_assets",

    "quarterlyTotalDebt":
        "total_debt",

    "quarterlyTotalLiabilitiesNetMinorityInterest":
        "total_liabilities",

    "quarterlyStockholdersEquity":
        "net_asset_value",
}


FINANCIAL_RAW_MAP = {

    "annualTotalRevenue":
        "total_revenue",

    "annualOperatingIncome":
        "operating_income",

    "annualNetIncome":
        "net_income",

    "annualTotalAssets":
        "total_assets",

    "annualTotalLiabilitiesNetMinorityInterest":
        "total_liabilities",

    "annualStockholdersEquity":
        "net_assets",

    "annualTotalDebt":
        "total_debt",

    "annualOperatingCashFlow":
        "operating_cash_flow",

    "annualFreeCashFlow":
        "free_cash_flow",
}


# ============================================================
# أدوات
# ============================================================


def safe_number(value):

    if value is None:
        return None

    try:
        return float(value)

    except (TypeError, ValueError):
        return None


def fmt(value):

    value = safe_number(value)

    if value is None:
        return "N/A"

    return f"{value:.2f}"


def print_header(title):

    print(
        "\n"
        + "=" * 92,
        flush=True
    )

    print(
        title,
        flush=True
    )

    print(
        "=" * 92,
        flush=True
    )


def print_separator():

    print(
        "-" * 92,
        flush=True
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
            "data_status,"
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


def get_financial_rows(stock_id):

    response = (
        supabase
        .table("financial_statements")
        .select(
            "period_end,"
            "period_type,"
            "metric,"
            "value,"
            "source"
        )
        .eq(
            "stock_id",
            stock_id
        )
        .execute()
    )

    return response.data or []


# ============================================================
# تنظيم Raw Data
# ============================================================


def organize_raw_data(rows):

    periods = {}

    for row in rows:

        period_end = row.get(
            "period_end"
        )

        period_type = row.get(
            "period_type"
        )

        metric = row.get(
            "metric"
        )

        metric_value = safe_number(
            row.get(
                "value"
            )
        )

        source = row.get(
            "source"
        )

        if (
            not period_end
            or not period_type
            or not metric
            or metric_value is None
        ):
            continue

        period_end = str(
            period_end
        )

        key = (
            period_end,
            str(period_type)
        )

        periods.setdefault(
            key,
            {
                "period_end":
                    period_end,

                "period_type":
                    str(period_type),

                "metrics":
                    {},

                "sources":
                    set(),
            }
        )

        periods[
            key
        ][
            "metrics"
        ][
            metric
        ] = metric_value

        if source:
            periods[
                key
            ][
                "sources"
            ].add(
                str(source)
            )

    return periods


# ============================================================
# تحويل Raw Quarterly إلى REIT Schema
# ============================================================


def normalize_quarterly_metrics(
    raw_metrics
):

    normalized = {}

    for (
        raw_name,
        schema_name
    ) in QUARTERLY_RAW_MAP.items():

        value = safe_number(
            raw_metrics.get(
                raw_name
            )
        )

        if value is not None:

            normalized[
                schema_name
            ] = value


    # ========================================================
    # مشتقات آمنة من القيم الموجودة
    # ========================================================

    total_assets = safe_number(
        normalized.get(
            "total_assets"
        )
    )

    total_debt = safe_number(
        normalized.get(
            "total_debt"
        )
    )


    if (
        total_assets is not None
        and total_assets != 0
        and total_debt is not None
    ):

        normalized[
            "debt_to_assets"
        ] = (
            total_debt
            / total_assets
        ) * 100


    # لا نحسب nav_per_unit بدون عدد الوحدات
    # لا نخترع market_price
    # لا نخترع expenses
    # لا نخترع occupancy_rate


    return normalized


# ============================================================
# تحويل Annual Financial إلى REIT Schema
# ============================================================


def normalize_financial_metrics(
    raw_metrics
):

    normalized = {}

    for (
        raw_name,
        schema_name
    ) in FINANCIAL_RAW_MAP.items():

        value = safe_number(
            raw_metrics.get(
                raw_name
            )
        )

        if value is not None:

            normalized[
                schema_name
            ] = value


    return normalized


# ============================================================
# تحديد report type المنطقي
#
# Raw period_type الحالي عندنا:
# 3M / 12M
#
# 3M = quarterly statement candidate
# 12M = FY candidate
#
# H1 سيأتي لاحقًا من المصدر الرسمي عند توفر 6M.
# ============================================================


def resolve_report_type(
    period_end,
    raw_period_type
):

    raw_period_type = (
        str(
            raw_period_type
        )
        .strip()
        .upper()
    )


    if raw_period_type == "12M":

        return "FY"


    if raw_period_type == "6M":

        return "H1"


    if raw_period_type == "3M":

        return identify_reit_period(
            period_end
        )


    return None


# ============================================================
# تحليل فترة واحدة
# ============================================================


def analyze_period(
    period_record
):

    period_end = period_record[
        "period_end"
    ]

    raw_period_type = period_record[
        "period_type"
    ]

    raw_metrics = period_record[
        "metrics"
    ]

    sources = sorted(
        period_record[
            "sources"
        ]
    )


    logical_period = (
        resolve_report_type(
            period_end,
            raw_period_type
        )
    )


    # ========================================================
    # لا يمكن تصنيف الفترة
    # ========================================================

    if not logical_period:

        return {

            "period_end":
                period_end,

            "raw_period_type":
                raw_period_type,

            "logical_period":
                None,

            "status":
                "UNKNOWN_PERIOD",

            "quality_score":
                0.0,

            "needs_official":
                True,

            "missing_required":
                [],

            "missing_important":
                [],

            "source_priority":
                [],

            "sources":
                sources,

            "normalized_metrics":
                {},
        }


    # ========================================================
    # Normalization
    # ========================================================

    if logical_period in {
        "Q1",
        "Q2",
        "Q3",
        "Q4",
    }:

        normalized = (
            normalize_quarterly_metrics(
                raw_metrics
            )
        )

    else:

        normalized = (
            normalize_financial_metrics(
                raw_metrics
            )
        )


    # ========================================================
    # Schema requirements
    # ========================================================

    requirements = (
        build_reit_audit_requirements(
            logical_period
        )
    )


    validation = (
        validate_reit_period(
            logical_period,
            normalized
        )
    )


    needs_official = (
        validation[
            "status"
        ] != "READY"
    )


    return {

        "period_end":
            period_end,

        "raw_period_type":
            raw_period_type,

        "logical_period":
            logical_period,

        "status":
            validation[
                "status"
            ],

        "quality_score":
            validation[
                "quality_score"
            ],

        "required_coverage":
            validation[
                "required_coverage"
            ],

        "important_coverage":
            validation[
                "important_coverage"
            ],

        "missing_required":
            validation[
                "required_missing"
            ],

        "missing_important":
            validation[
                "important_missing"
            ],

        "available_required":
            validation[
                "required_available"
            ],

        "available_important":
            validation[
                "important_available"
            ],

        "needs_official":
            needs_official,

        "source_priority":
            requirements[
                "source_priority"
            ],

        "sources":
            sources,

        "normalized_metrics":
            normalized,
    }


# ============================================================
# تحديد هل لدينا H1
# ============================================================


def has_h1_period(
    period_results
):

    return any(
        result.get(
            "logical_period"
        ) == "H1"

        for result in period_results
    )


# ============================================================
# تحديد هل لدينا FY
# ============================================================


def has_fy_period(
    period_results
):

    return any(
        result.get(
            "logical_period"
        ) == "FY"

        for result in period_results
    )


# ============================================================
# تحديد Quarterly history
# ============================================================


def get_quarter_results(
    period_results
):

    return [

        result

        for result in period_results

        if result.get(
            "logical_period"
        ) in {
            "Q1",
            "Q2",
            "Q3",
            "Q4",
        }
    ]


# ============================================================
# فحص YoY structure
#
# لا نحسب YoY هنا.
# فقط نتحقق من وجود نفس Logical Quarter
# في السنة السابقة.
# ============================================================


def analyze_yoy_structure(
    quarter_results
):

    index = {}

    for result in quarter_results:

        period_end = result[
            "period_end"
        ]

        logical_period = result[
            "logical_period"
        ]

        try:

            year = int(
                period_end[
                    0:4
                ]
            )

        except Exception:

            continue

        index[
            (
                year,
                logical_period
            )
        ] = result


    yoy_results = []


    for result in quarter_results:

        period_end = result[
            "period_end"
        ]

        logical_period = result[
            "logical_period"
        ]


        try:

            year = int(
                period_end[
                    0:4
                ]
            )

        except Exception:

            continue


        previous = index.get(
            (
                year - 1,
                logical_period
            )
        )


        current_ready = (
            result.get(
                "status"
            )
            == "READY"
        )


        previous_ready = (
            previous is not None
            and previous.get(
                "status"
            )
            == "READY"
        )


        yoy_ready = (
            current_ready
            and previous_ready
        )


        yoy_results.append({

            "period_end":
                period_end,

            "logical_period":
                logical_period,

            "reference_period":
                (
                    previous[
                        "period_end"
                    ]
                    if previous
                    else None
                ),

            "reference_exists":
                previous is not None,

            "current_ready":
                current_ready,

            "reference_ready":
                previous_ready,

            "yoy_ready":
                yoy_ready,
        })


    return yoy_results


# ============================================================
# تقييم الصندوق كاملًا
# ============================================================


def analyze_reit(stock):

    stock_id = stock[
        "id"
    ]

    symbol = stock[
        "symbol"
    ]

    company_name = (
        stock.get(
            "company_name"
        )
        or symbol
    )


    rows = get_financial_rows(
        stock_id
    )


    periods = organize_raw_data(
        rows
    )


    period_results = []


    for key in sorted(
        periods.keys()
    ):

        period_results.append(
            analyze_period(
                periods[
                    key
                ]
            )
        )


    quarter_results = (
        get_quarter_results(
            period_results
        )
    )


    yoy_results = (
        analyze_yoy_structure(
            quarter_results
        )
    )


    # ========================================================
    # Fallback reasons
    # ========================================================

    fallback_reasons = []


    if not quarter_results:

        fallback_reasons.append(
            "NO_QUARTERLY_REIT_STATEMENTS"
        )


    incomplete_quarters = [

        result

        for result in quarter_results

        if result[
            "status"
        ] != "READY"
    ]


    if incomplete_quarters:

        fallback_reasons.append(
            "INCOMPLETE_QUARTERLY_REIT_STATEMENTS"
        )


    if len(
        quarter_results
    ) < 5:

        fallback_reasons.append(
            "INSUFFICIENT_QUARTER_HISTORY"
        )


    if yoy_results:

        latest_yoy = sorted(
            yoy_results,
            key=lambda item:
                item[
                    "period_end"
                ]
        )[-1]


        if not latest_yoy[
            "yoy_ready"
        ]:

            fallback_reasons.append(
                "LATEST_YOY_NOT_READY"
            )


    if not has_h1_period(
        period_results
    ):

        fallback_reasons.append(
            "H1_FINANCIAL_REPORT_MISSING"
        )


    if not has_fy_period(
        period_results
    ):

        fallback_reasons.append(
            "FY_FINANCIAL_REPORT_MISSING"
        )


    needs_official = (
        len(
            fallback_reasons
        ) > 0
    )


    # ========================================================
    # Quality summary
    # ========================================================

    valid_quality_scores = [

        safe_number(
            result.get(
                "quality_score"
            )
        )

        for result in period_results

        if safe_number(
            result.get(
                "quality_score"
            )
        ) is not None
    ]


    if valid_quality_scores:

        source_quality = (
            sum(
                valid_quality_scores
            )
            / len(
                valid_quality_scores
            )
        )

    else:

        source_quality = 0.0


    return {

        "status":
            "success",

        "symbol":
            symbol,

        "company_name":
            company_name,

        "raw_rows":
            len(
                rows
            ),

        "period_results":
            period_results,

        "quarter_results":
            quarter_results,

        "yoy_results":
            yoy_results,

        "quarter_count":
            len(
                quarter_results
            ),

        "source_quality":
            source_quality,

        "needs_official":
            needs_official,

        "fallback_reasons":
            fallback_reasons,

        "has_h1":
            has_h1_period(
                period_results
            ),

        "has_fy":
            has_fy_period(
                period_results
            ),
    }


# ============================================================
# طباعة فترة
# ============================================================


def print_period_result(result):

    print(
        "\n"
        f"📅 {result['period_end']} | "
        f"Raw={result['raw_period_type']} | "
        f"Logical={result['logical_period']} | "
        f"{result['status']}",
        flush=True
    )


    print(
        f"Quality="
        f"{fmt(result['quality_score'])} | "
        f"Required="
        f"{fmt(result.get('required_coverage'))}% | "
        f"Important="
        f"{fmt(result.get('important_coverage'))}%",
        flush=True
    )


    print(
        f"Existing Sources: "
        f"{', '.join(result['sources']) or 'UNKNOWN'}",
        flush=True
    )


    if result[
        "source_priority"
    ]:

        print(
            "Preferred Source: "
            + " → ".join(
                result[
                    "source_priority"
                ]
            ),
            flush=True
        )


    if result[
        "missing_required"
    ]:

        print(
            "🔴 Missing Required:",
            flush=True
        )

        for metric_name in result[
            "missing_required"
        ]:

            print(
                f"  - {metric_name}",
                flush=True
            )


    if result[
        "missing_important"
    ]:

        print(
            "🟡 Missing Important:",
            flush=True
        )

        for metric_name in result[
            "missing_important"
        ]:

            print(
                f"  - {metric_name}",
                flush=True
            )


# ============================================================
# طباعة صندوق
# ============================================================


def print_reit_result(result):

    print_header(
        f"🏢 {result['symbol']} | "
        f"{result['company_name']}"
    )


    print(
        f"📄 Raw Rows: "
        f"{result['raw_rows']}",
        flush=True
    )


    print(
        f"📗 Quarterly Logical Periods: "
        f"{result['quarter_count']}",
        flush=True
    )


    print(
        f"📘 H1 Available: "
        f"{result['has_h1']}",
        flush=True
    )


    print(
        f"📕 FY Available: "
        f"{result['has_fy']}",
        flush=True
    )


    print(
        f"🧪 Current Source Quality: "
        f"{fmt(result['source_quality'])}",
        flush=True
    )


    print_separator()


    print(
        "📚 PERIOD ANALYSIS",
        flush=True
    )


    for period_result in result[
        "period_results"
    ]:

        print_period_result(
            period_result
        )


    print_separator()


    print(
        "🔁 YOY STRUCTURE",
        flush=True
    )


    if not result[
        "yoy_results"
    ]:

        print(
            "⚠️ No quarterly YoY structure available",
            flush=True
        )


    else:

        for yoy in result[
            "yoy_results"
        ]:

            status = (
                "READY"
                if yoy[
                    "yoy_ready"
                ]
                else "NOT_READY"
            )

            print(
                f"{yoy['period_end']} | "
                f"{yoy['logical_period']} | "
                f"Reference="
                f"{yoy['reference_period'] or 'NONE'} | "
                f"{status}",
                flush=True
            )


    print_separator()


    if result[
        "needs_official"
    ]:

        print(
            "🌐 OFFICIAL SOURCE REQUIRED",
            flush=True
        )


        for reason in result[
            "fallback_reasons"
        ]:

            print(
                f"- {reason}",
                flush=True
            )


    else:

        print(
            "✅ CURRENT SOURCE IS SUFFICIENT",
            flush=True
        )


# ============================================================
# Summary
# ============================================================


def print_summary(results):

    print_header(
        "🏆 REIT OFFICIAL DATA SUMMARY v2"
    )


    successful = [

        result

        for result in results

        if result.get(
            "status"
        ) == "success"
    ]


    successful.sort(
        key=lambda result:
            result.get(
                "source_quality",
                0
            )
    )


    for index, result in enumerate(
        successful,
        start=1
    ):

        fallback = (
            "REQUIRED"
            if result[
                "needs_official"
            ]
            else "NOT_REQUIRED"
        )


        print(
            f"{index:02d}. "
            f"{result['symbol']} | "
            f"{result['company_name']} | "
            f"Quality="
            f"{fmt(result['source_quality'])} | "
            f"Quarters="
            f"{result['quarter_count']} | "
            f"H1="
            f"{result['has_h1']} | "
            f"FY="
            f"{result['has_fy']} | "
            f"Official="
            f"{fallback}",
            flush=True
        )


    official_required = [

        result

        for result in successful

        if result[
            "needs_official"
        ]
    ]


    errors = [

        result

        for result in results

        if result.get(
            "status"
        ) != "success"
    ]


    print_separator()


    print(
        f"🏢 Total REITs: "
        f"{len(results)}",
        flush=True
    )


    print(
        f"✅ Current Source Sufficient: "
        f"{len(successful) - len(official_required)}",
        flush=True
    )


    print(
        f"🌐 Official Source Required: "
        f"{len(official_required)}",
        flush=True
    )


    print(
        f"🔴 Errors: "
        f"{len(errors)}",
        flush=True
    )


    if official_required:

        print(
            "\n🌐 OFFICIAL SOURCE QUEUE",
            flush=True
        )


        for result in official_required:

            print(
                f"- {result['symbol']} | "
                f"{result['company_name']}",
                flush=True
            )


            for reason in result[
                "fallback_reasons"
            ]:

                print(
                    f"    • {reason}",
                    flush=True
                )


    print(
        "=" * 92,
        flush=True
    )


# ============================================================
# تشغيل
# ============================================================


def run_reit_official_data_engine():

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
            f"🔍 REIT Schema Check "
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
                    )
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

    run_reit_official_data_engine()
