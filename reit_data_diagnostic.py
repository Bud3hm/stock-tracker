import os
from collections import defaultdict
from supabase import create_client


# ============================================================
# REIT RAW DATA DIAGNOSTIC
#
# الهدف:
# تشخيص بيانات الراجحي ريت 4340.SR
# بدون تعديل أي شيء في قاعدة البيانات
# ============================================================


SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_SECRET_KEY = os.environ.get("SUPABASE_SECRET_KEY")

TARGET_SYMBOL = os.environ.get(
    "TARGET_SYMBOL",
    "4340.SR"
)

supabase = create_client(
    SUPABASE_URL,
    SUPABASE_SECRET_KEY
)


# ============================================================
# الأدوات
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
        return "MISSING"

    return f"{value:,.2f}"


def print_header(title):

    print(
        "\n"
        + "=" * 90,
        flush=True
    )

    print(
        title,
        flush=True
    )

    print(
        "=" * 90,
        flush=True
    )


def print_separator():

    print(
        "-" * 90,
        flush=True
    )


# ============================================================
# جلب stock
# ============================================================

def get_stock(symbol):

    response = (
        supabase
        .table("stocks")
        .select(
            "id,"
            "symbol,"
            "company_name,"
            "analysis_model,"
            "data_status"
        )
        .eq(
            "symbol",
            symbol
        )
        .limit(1)
        .execute()
    )

    if not response.data:
        return None

    return response.data[0]


# ============================================================
# جلب البيانات الخام
# ============================================================

def get_raw_financial_data(stock_id):

    response = (
        supabase
        .table("financial_statements")
        .select(
            "metric,"
            "period_end,"
            "period_type,"
            "value,"
            "currency,"
            "source"
        )
        .eq(
            "stock_id",
            stock_id
        )
        .order(
            "period_end"
        )
        .execute()
    )

    return response.data or []


# ============================================================
# جلب REIT metrics المحسوبة
# ============================================================

def get_calculated_metrics(stock_id):

    response = (
        supabase
        .table("financial_metrics")
        .select(
            "period_end,"
            "metric_name,"
            "metric_value"
        )
        .eq(
            "stock_id",
            stock_id
        )
        .execute()
    )

    return response.data or []


# ============================================================
# تنظيم البيانات الخام
# ============================================================

def organize_raw(rows):

    periods = defaultdict(
        dict
    )

    for row in rows:

        period_end = str(
            row.get("period_end")
        )

        period_type = (
            row.get("period_type")
            or "UNKNOWN"
        )

        metric = row.get(
            "metric"
        )

        value = safe_number(
            row.get("value")
        )

        if (
            not period_end
            or not metric
        ):
            continue

        key = (
            period_type,
            period_end
        )

        periods[
            key
        ][
            metric
        ] = value

    return periods


# ============================================================
# تنظيم المؤشرات المحسوبة
# ============================================================

def organize_metrics(rows):

    periods = defaultdict(
        dict
    )

    for row in rows:

        period_end = str(
            row.get("period_end")
        )

        metric_name = row.get(
            "metric_name"
        )

        value = safe_number(
            row.get("metric_value")
        )

        if (
            not period_end
            or not metric_name
        ):
            continue

        periods[
            period_end
        ][
            metric_name
        ] = value

    return periods


# ============================================================
# أهم البنود المطلوبة
# ============================================================

RAW_METRICS = [

    "quarterlyTotalRevenue",
    "quarterlyOperatingIncome",
    "quarterlyNetIncome",
    "quarterlyTotalAssets",
    "quarterlyStockholdersEquity",
    "quarterlyTotalDebt",
    "quarterlyOperatingCashFlow",
    "quarterlyFreeCashFlow",

    "annualTotalRevenue",
    "annualOperatingIncome",
    "annualNetIncome",
    "annualTotalAssets",
    "annualStockholdersEquity",
    "annualTotalDebt",
    "annualOperatingCashFlow",
    "annualFreeCashFlow"
]


CALCULATED_METRICS = [

    "reit_q_revenue",
    "reit_q_operating_income",
    "reit_q_net_income",

    "reit_q_revenue_growth_yoy",
    "reit_q_operating_income_growth_yoy",
    "reit_q_net_income_growth_yoy",

    "reit_q_synthesized_flag",
    "reit_q_yoy_reference_available",
    "reit_data_confidence_score",

    "reit_ttm_revenue",
    "reit_ttm_operating_income",
    "reit_ttm_net_income",

    "score_opportunity_score",
    "score_risk_score",
    "turning_engine_score",

    "data_quality_score",
    "decision_score"
]


# ============================================================
# طباعة البيانات الخام
# ============================================================

def print_raw_periods(periods):

    print_header(
        "📄 RAW FINANCIAL PERIODS"
    )

    sorted_keys = sorted(
        periods.keys(),
        key=lambda item: (
            item[1],
            item[0]
        )
    )

    for (
        period_type,
        period_end
    ) in sorted_keys:

        data = periods[
            (
                period_type,
                period_end
            )
        ]

        print(
            f"\n📅 {period_end} | "
            f"PeriodType={period_type}",
            flush=True
        )

        print_separator()

        relevant_found = False

        for metric_name in RAW_METRICS:

            if metric_name in data:

                relevant_found = True

                print(
                    f"{metric_name:<55}"
                    f"{fmt(data.get(metric_name))}",
                    flush=True
                )

        if not relevant_found:

            print(
                "⚠️ لا توجد بنود رئيسية "
                "ضمن قائمة التشخيص",
                flush=True
            )


# ============================================================
# جدول وجود الفترات الربعية
# ============================================================

def print_quarter_matrix(periods):

    print_header(
        "🧩 QUARTER AVAILABILITY MATRIX"
    )

    quarterly_periods = []

    annual_periods = []

    for (
        period_type,
        period_end
    ) in periods.keys():

        if period_type == "3M":

            quarterly_periods.append(
                period_end
            )

        elif period_type == "12M":

            annual_periods.append(
                period_end
            )

    quarterly_periods = sorted(
        set(
            quarterly_periods
        )
    )

    annual_periods = sorted(
        set(
            annual_periods
        )
    )

    print(
        f"📊 Quarterly periods count: "
        f"{len(quarterly_periods)}",
        flush=True
    )

    print(
        f"📅 Quarterly periods: "
        f"{', '.join(quarterly_periods) or 'NONE'}",
        flush=True
    )

    print()

    print(
        f"📘 Annual periods count: "
        f"{len(annual_periods)}",
        flush=True
    )

    print(
        f"📅 Annual periods: "
        f"{', '.join(annual_periods) or 'NONE'}",
        flush=True
    )

    print_separator()

    quarterly_required = [

        "quarterlyTotalRevenue",
        "quarterlyOperatingIncome",
        "quarterlyNetIncome"

    ]

    for period_end in quarterly_periods:

        data = periods[
            (
                "3M",
                period_end
            )
        ]

        available = [
            metric
            for metric
            in quarterly_required
            if data.get(
                metric
            ) is not None
        ]

        missing = [
            metric
            for metric
            in quarterly_required
            if data.get(
                metric
            ) is None
        ]

        print(
            f"\n📅 {period_end}",
            flush=True
        )

        print(
            f"✅ Available: "
            f"{len(available)}/3",
            flush=True
        )

        for metric in available:

            print(
                f"  ✅ {metric}",
                flush=True
            )

        for metric in missing:

            print(
                f"  ❌ {metric}",
                flush=True
            )


# ============================================================
# تحليل قابلية YoY
# ============================================================

def print_yoy_diagnostic(periods):

    print_header(
        "🔎 YOY DIAGNOSTIC"
    )

    quarterly_periods = sorted(
        {
            period_end
            for (
                period_type,
                period_end
            ) in periods.keys()
            if period_type == "3M"
        }
    )

    if not quarterly_periods:

        print(
            "🔴 لا توجد Quarterly periods",
            flush=True
        )

        return

    for current_period in quarterly_periods:

        current_year = int(
            current_period[
                0:4
            ]
        )

        previous_year = (
            current_year - 1
        )

        month_day = (
            current_period[
                4:
            ]
        )

        exact_previous = (
            f"{previous_year}"
            f"{month_day}"
        )

        exact_exists = (
            (
                "3M",
                exact_previous
            )
            in periods
        )

        print(
            f"\n📅 Current: "
            f"{current_period}",
            flush=True
        )

        print(
            f"🎯 Exact YoY target: "
            f"{exact_previous}",
            flush=True
        )

        print(
            f"Exact previous exists: "
            f"{'YES' if exact_exists else 'NO'}",
            flush=True
        )

        if exact_exists:

            previous_data = periods[
                (
                    "3M",
                    exact_previous
                )
            ]

            print(
                "Previous YoY values:",
                flush=True
            )

            print(
                f"Revenue: "
                f"{fmt(previous_data.get('quarterlyTotalRevenue'))}",
                flush=True
            )

            print(
                f"Operating Income: "
                f"{fmt(previous_data.get('quarterlyOperatingIncome'))}",
                flush=True
            )

            print(
                f"Net Income: "
                f"{fmt(previous_data.get('quarterlyNetIncome'))}",
                flush=True
            )

        else:

            same_year_candidates = [
                period
                for period
                in quarterly_periods
                if period.startswith(
                    str(
                        previous_year
                    )
                )
            ]

            print(
                f"Previous year candidates: "
                f"{', '.join(same_year_candidates) or 'NONE'}",
                flush=True
            )


# ============================================================
# فحص Q4 synthetic
# ============================================================

def print_q4_diagnostic(
    raw_periods,
    calculated_periods
):

    print_header(
        "🧩 SYNTHETIC Q4 DIAGNOSTIC"
    )

    all_periods = sorted(
        calculated_periods.keys()
    )

    found = False

    for period_end in all_periods:

        data = calculated_periods[
            period_end
        ]

        flag = safe_number(
            data.get(
                "reit_q_synthesized_flag"
            )
        )

        if flag is None:
            continue

        found = True

        print(
            f"\n📅 {period_end}",
            flush=True
        )

        print(
            f"Synthesized Flag: "
            f"{fmt(flag)}",
            flush=True
        )

        print(
            f"YoY Reference Available: "
            f"{fmt(data.get('reit_q_yoy_reference_available'))}",
            flush=True
        )

        print(
            f"Revenue: "
            f"{fmt(data.get('reit_q_revenue'))}",
            flush=True
        )

        print(
            f"Operating Income: "
            f"{fmt(data.get('reit_q_operating_income'))}",
            flush=True
        )

        print(
            f"Net Income: "
            f"{fmt(data.get('reit_q_net_income'))}",
            flush=True
        )

        print(
            f"Revenue YoY: "
            f"{fmt(data.get('reit_q_revenue_growth_yoy'))}",
            flush=True
        )

        print(
            f"Operating Income YoY: "
            f"{fmt(data.get('reit_q_operating_income_growth_yoy'))}",
            flush=True
        )

        print(
            f"Net Income YoY: "
            f"{fmt(data.get('reit_q_net_income_growth_yoy'))}",
            flush=True
        )

    if not found:

        print(
            "⚠️ لا توجد synthesized flags محفوظة",
            flush=True
        )


# ============================================================
# طباعة المؤشرات المحسوبة
# ============================================================

def print_calculated_periods(periods):

    print_header(
        "🧮 CALCULATED REIT METRICS"
    )

    for period_end in sorted(
        periods.keys()
    ):

        data = periods[
            period_end
        ]

        relevant = {

            metric_name:
                data.get(
                    metric_name
                )

            for metric_name
            in CALCULATED_METRICS

            if metric_name in data
        }

        if not relevant:
            continue

        print(
            f"\n📅 {period_end}",
            flush=True
        )

        print_separator()

        for (
            metric_name,
            metric_value
        ) in relevant.items():

            print(
                f"{metric_name:<50}"
                f"{fmt(metric_value)}",
                flush=True
            )


# ============================================================
# Final diagnosis
# ============================================================

def print_final_diagnosis(
    raw_periods,
    calculated_periods
):

    print_header(
        "🩺 FINAL DIAGNOSIS"
    )

    latest_calculated = None

    if calculated_periods:

        latest_calculated = sorted(
            calculated_periods.keys()
        )[-1]

    if not latest_calculated:

        print(
            "🔴 لا توجد calculated periods",
            flush=True
        )

        return

    latest = calculated_periods[
        latest_calculated
    ]

    required = [

        "reit_q_revenue_growth_yoy",
        "reit_q_operating_income_growth_yoy",
        "reit_q_net_income_growth_yoy"

    ]

    missing = [
        metric_name
        for metric_name
        in required
        if safe_number(
            latest.get(
                metric_name
            )
        ) is None
    ]

    print(
        f"📅 Latest calculated period: "
        f"{latest_calculated}",
        flush=True
    )

    if not missing:

        print(
            "✅ جميع مؤشرات YoY الأساسية موجودة",
            flush=True
        )

    else:

        print(
            f"🔴 Missing YoY metrics: "
            f"{len(missing)}",
            flush=True
        )

        for metric_name in missing:

            print(
                f"- {metric_name}",
                flush=True
            )

    quarterly_periods = sorted(
        {
            period_end
            for (
                period_type,
                period_end
            ) in raw_periods.keys()
            if period_type == "3M"
        }
    )

    annual_periods = sorted(
        {
            period_end
            for (
                period_type,
                period_end
            ) in raw_periods.keys()
            if period_type == "12M"
        }
    )

    print_separator()

    print(
        f"Raw quarterly count: "
        f"{len(quarterly_periods)}",
        flush=True
    )

    print(
        f"Raw annual count: "
        f"{len(annual_periods)}",
        flush=True
    )

    print(
        f"Quarterly periods: "
        f"{', '.join(quarterly_periods) or 'NONE'}",
        flush=True
    )

    print(
        f"Annual periods: "
        f"{', '.join(annual_periods) or 'NONE'}",
        flush=True
    )


# ============================================================
# التشغيل
# ============================================================

def run_diagnostic():

    print_header(
        "🔬 REIT RAW DATA DIAGNOSTIC"
    )

    print(
        f"🎯 Target Symbol: "
        f"{TARGET_SYMBOL}",
        flush=True
    )

    print(
        "🔒 Mode: READ ONLY",
        flush=True
    )

    stock = get_stock(
        TARGET_SYMBOL
    )

    if not stock:

        print(
            f"🔴 Stock not found: "
            f"{TARGET_SYMBOL}",
            flush=True
        )

        return

    print(
        f"🏢 Company: "
        f"{stock.get('company_name')}",
        flush=True
    )

    print(
        f"🧠 Analysis Model: "
        f"{stock.get('analysis_model')}",
        flush=True
    )

    raw_rows = get_raw_financial_data(
        stock["id"]
    )

    calculated_rows = (
        get_calculated_metrics(
            stock["id"]
        )
    )

    print(
        f"📄 Raw rows: "
        f"{len(raw_rows)}",
        flush=True
    )

    print(
        f"📊 Calculated rows: "
        f"{len(calculated_rows)}",
        flush=True
    )

    raw_periods = organize_raw(
        raw_rows
    )

    calculated_periods = (
        organize_metrics(
            calculated_rows
        )
    )

    print_raw_periods(
        raw_periods
    )

    print_quarter_matrix(
        raw_periods
    )

    print_yoy_diagnostic(
        raw_periods
    )

    print_q4_diagnostic(
        raw_periods,
        calculated_periods
    )

    print_calculated_periods(
        calculated_periods
    )

    print_final_diagnosis(
        raw_periods,
        calculated_periods
    )


if __name__ == "__main__":

    run_diagnostic()
