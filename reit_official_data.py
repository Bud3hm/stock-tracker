import os
from datetime import datetime, timezone
from supabase import create_client


# ============================================================
# REIT OFFICIAL DATA ENGINE v1
#
# المرحلة الحالية:
# READ ONLY
#
# الهدف:
# 1) قراءة جميع صناديق REIT من stocks
# 2) فحص البيانات الخام لكل صندوق
# 3) تحديد الفترات السنوية والربعية
# 4) قياس اكتمال كل فترة
# 5) تحديد البيانات المفقودة
# 6) تحديد هل الصندوق يحتاج Official Fallback
# 7) عدم تعديل أي بيانات حاليًا
#
# مهم:
# هذا المحرك عام لجميع REITs وليس لصندوق محدد.
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
# إعدادات عامة
# ============================================================

ENGINE_NAME = "REIT OFFICIAL DATA ENGINE v1"
READ_ONLY = True


# ============================================================
# البنود الأساسية المطلوبة
# ============================================================

QUARTERLY_CORE_METRICS = [

    "quarterlyTotalRevenue",

    "quarterlyOperatingIncome",

    "quarterlyNetIncome",

    "quarterlyTotalAssets",

    "quarterlyTotalLiabilitiesNetMinorityInterest",

    "quarterlyStockholdersEquity",

    "quarterlyTotalDebt",

    "quarterlyOperatingCashFlow",

    "quarterlyFreeCashFlow"
]


QUARTERLY_INCOME_METRICS = [

    "quarterlyTotalRevenue",

    "quarterlyOperatingIncome",

    "quarterlyNetIncome"
]


QUARTERLY_BALANCE_METRICS = [

    "quarterlyTotalAssets",

    "quarterlyTotalLiabilitiesNetMinorityInterest",

    "quarterlyStockholdersEquity",

    "quarterlyTotalDebt"
]


QUARTERLY_CASHFLOW_METRICS = [

    "quarterlyOperatingCashFlow",

    "quarterlyFreeCashFlow"
]


ANNUAL_CORE_METRICS = [

    "annualTotalRevenue",

    "annualOperatingIncome",

    "annualNetIncome",

    "annualTotalAssets",

    "annualTotalLiabilitiesNetMinorityInterest",

    "annualStockholdersEquity",

    "annualTotalDebt",

    "annualOperatingCashFlow",

    "annualFreeCashFlow"
]


# ============================================================
# أدوات عامة
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
        "\n" + "=" * 90,
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
# جلب جميع صناديق REIT
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


# ============================================================
# جلب البيانات المالية الخام
# ============================================================

def get_financial_data(stock_id):

    response = (
        supabase
        .table("financial_statements")
        .select(
            "period_end,"
            "period_type,"
            "metric,"
            "value"
        )
        .eq(
            "stock_id",
            stock_id
        )
        .execute()
    )

    return response.data or []


# ============================================================
# تنظيم البيانات
# ============================================================

def organize_financial_data(rows):

    annual = {}
    quarterly = {}

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

        if period_type == "12M":

            annual.setdefault(
                period_end,
                {}
            )

            annual[
                period_end
            ][
                metric
            ] = metric_value

        elif period_type == "3M":

            quarterly.setdefault(
                period_end,
                {}
            )

            quarterly[
                period_end
            ][
                metric
            ] = metric_value

    return annual, quarterly


# ============================================================
# فحص مجموعة مؤشرات
# ============================================================

def inspect_metric_group(
    data,
    required_metrics
):

    available = []
    missing = []

    for metric_name in required_metrics:

        metric_value = safe_number(
            data.get(
                metric_name
            )
        )

        if metric_value is None:

            missing.append(
                metric_name
            )

        else:

            available.append(
                metric_name
            )

    total = len(
        required_metrics
    )

    available_count = len(
        available
    )

    coverage = (
        (
            available_count
            / total
        )
        * 100
        if total > 0
        else 0.0
    )

    return {
        "available":
            available,

        "missing":
            missing,

        "available_count":
            available_count,

        "total_count":
            total,

        "coverage":
            coverage
    }


# ============================================================
# فحص فترة ربع سنوية
# ============================================================

def inspect_quarter(
    period_end,
    data
):

    core = inspect_metric_group(
        data,
        QUARTERLY_CORE_METRICS
    )

    income = inspect_metric_group(
        data,
        QUARTERLY_INCOME_METRICS
    )

    balance = inspect_metric_group(
        data,
        QUARTERLY_BALANCE_METRICS
    )

    cashflow = inspect_metric_group(
        data,
        QUARTERLY_CASHFLOW_METRICS
    )

    # --------------------------------------------------------
    # هل الفترة تحتوي قائمة دخل؟
    # --------------------------------------------------------

    has_income_statement = (
        income[
            "available_count"
        ] > 0
    )

    income_complete = (
        income[
            "available_count"
        ]
        ==
        income[
            "total_count"
        ]
    )

    # --------------------------------------------------------
    # هل الميزانية موجودة؟
    # --------------------------------------------------------

    has_balance_sheet = (
        balance[
            "available_count"
        ] > 0
    )

    balance_complete = (
        balance[
            "available_count"
        ]
        ==
        balance[
            "total_count"
        ]
    )

    # --------------------------------------------------------
    # هل التدفقات موجودة؟
    # --------------------------------------------------------

    has_cashflow = (
        cashflow[
            "available_count"
        ] > 0
    )

    cashflow_complete = (
        cashflow[
            "available_count"
        ]
        ==
        cashflow[
            "total_count"
        ]
    )

    # --------------------------------------------------------
    # تصنيف الفترة
    # --------------------------------------------------------

    if (
        income_complete
        and balance_complete
        and cashflow_complete
    ):

        status = "COMPLETE"

    elif (
        has_balance_sheet
        and not has_income_statement
    ):

        status = "BALANCE_ONLY"

    elif (
        has_income_statement
        and not income_complete
    ):

        status = "PARTIAL_INCOME"

    elif core[
        "available_count"
    ] > 0:

        status = "PARTIAL"

    else:

        status = "EMPTY"

    # --------------------------------------------------------
    # هل نحتاج مصدر رسمي؟
    # --------------------------------------------------------

    needs_official_fallback = (
        not income_complete
        or not balance_complete
        or not cashflow_complete
    )

    return {
        "period_end":
            period_end,

        "status":
            status,

        "coverage":
            core[
                "coverage"
            ],

        "available_count":
            core[
                "available_count"
            ],

        "required_count":
            core[
                "total_count"
            ],

        "missing":
            core[
                "missing"
            ],

        "income_coverage":
            income[
                "coverage"
            ],

        "balance_coverage":
            balance[
                "coverage"
            ],

        "cashflow_coverage":
            cashflow[
                "coverage"
            ],

        "has_income_statement":
            has_income_statement,

        "has_balance_sheet":
            has_balance_sheet,

        "has_cashflow":
            has_cashflow,

        "needs_official_fallback":
            needs_official_fallback
    }


# ============================================================
# فحص الفترة السنوية
# ============================================================

def inspect_annual_period(
    period_end,
    data
):

    result = inspect_metric_group(
        data,
        ANNUAL_CORE_METRICS
    )

    if (
        result[
            "available_count"
        ]
        ==
        result[
            "total_count"
        ]
    ):

        status = "COMPLETE"

    elif result[
        "available_count"
    ] > 0:

        status = "PARTIAL"

    else:

        status = "EMPTY"

    return {
        "period_end":
            period_end,

        "status":
            status,

        "coverage":
            result[
                "coverage"
            ],

        "available_count":
            result[
                "available_count"
            ],

        "required_count":
            result[
                "total_count"
            ],

        "missing":
            result[
                "missing"
            ]
    }


# ============================================================
# فحص توفر YoY
# ============================================================

def inspect_yoy_availability(
    quarter_dates,
    quarterly
):

    results = []

    for period_end in quarter_dates:

        try:

            current_date = datetime.strptime(
                period_end,
                "%Y-%m-%d"
            )

        except Exception:

            continue

        prior_year_date = (
            f"{current_date.year - 1}-"
            f"{current_date.month:02d}-"
            f"{current_date.day:02d}"
        )

        current = quarterly.get(
            period_end,
            {}
        )

        previous_year = quarterly.get(
            prior_year_date
        )

        current_income = (
            inspect_metric_group(
                current,
                QUARTERLY_INCOME_METRICS
            )
        )

        previous_income = (
            inspect_metric_group(
                previous_year or {},
                QUARTERLY_INCOME_METRICS
            )
        )

        exact_reference_exists = (
            previous_year is not None
        )

        yoy_ready = (
            exact_reference_exists
            and
            current_income[
                "available_count"
            ]
            ==
            current_income[
                "total_count"
            ]
            and
            previous_income[
                "available_count"
            ]
            ==
            previous_income[
                "total_count"
            ]
        )

        results.append({
            "period_end":
                period_end,

            "prior_year_period":
                prior_year_date,

            "reference_exists":
                exact_reference_exists,

            "current_income_complete":
                (
                    current_income[
                        "available_count"
                    ]
                    ==
                    current_income[
                        "total_count"
                    ]
                ),

            "previous_income_complete":
                (
                    previous_income[
                        "available_count"
                    ]
                    ==
                    previous_income[
                        "total_count"
                    ]
                ),

            "yoy_ready":
                yoy_ready
        })

    return results


# ============================================================
# تقييم احتياج المصدر الرسمي
# ============================================================

def determine_fallback_need(
    quarter_results,
    yoy_results
):

    reasons = []

    # --------------------------------------------------------
    # لا توجد بيانات ربعية أصلًا
    # --------------------------------------------------------

    if not quarter_results:

        reasons.append(
            "NO_QUARTERLY_DATA"
        )

    # --------------------------------------------------------
    # فترات ناقصة
    # --------------------------------------------------------

    incomplete_periods = [
        result
        for result in quarter_results
        if result[
            "needs_official_fallback"
        ]
    ]

    if incomplete_periods:

        reasons.append(
            "INCOMPLETE_QUARTERLY_PERIODS"
        )

    # --------------------------------------------------------
    # قائمة الدخل ناقصة
    # --------------------------------------------------------

    missing_income_periods = [
        result
        for result in quarter_results
        if not result[
            "has_income_statement"
        ]
    ]

    if missing_income_periods:

        reasons.append(
            "MISSING_QUARTERLY_INCOME"
        )

    # --------------------------------------------------------
    # YoY غير ممكن
    # --------------------------------------------------------

    if yoy_results:

        latest_yoy = yoy_results[
            -1
        ]

        if not latest_yoy[
            "yoy_ready"
        ]:

            reasons.append(
                "LATEST_YOY_NOT_READY"
            )

    # --------------------------------------------------------
    # تاريخ ربعي قصير
    # --------------------------------------------------------

    if len(
        quarter_results
    ) < 5:

        reasons.append(
            "INSUFFICIENT_QUARTER_HISTORY"
        )

    needs_fallback = (
        len(
            reasons
        ) > 0
    )

    return (
        needs_fallback,
        reasons
    )


# ============================================================
# تقييم جودة المصدر الحالي
# ============================================================

def calculate_source_quality(
    quarter_results,
    annual_results,
    yoy_results
):

    components = []

    # --------------------------------------------------------
    # أحدث ربع
    # --------------------------------------------------------

    if quarter_results:

        latest_quarter = quarter_results[
            -1
        ]

        components.append(
            (
                latest_quarter[
                    "coverage"
                ],
                40
            )
        )

    else:

        components.append(
            (
                0.0,
                40
            )
        )

    # --------------------------------------------------------
    # التاريخ الربعي
    # --------------------------------------------------------

    quarter_count = len(
        quarter_results
    )

    if quarter_count >= 8:

        quarter_history_score = 100

    elif quarter_count >= 6:

        quarter_history_score = 90

    elif quarter_count >= 5:

        quarter_history_score = 80

    elif quarter_count >= 4:

        quarter_history_score = 65

    elif quarter_count >= 3:

        quarter_history_score = 45

    elif quarter_count >= 2:

        quarter_history_score = 30

    elif quarter_count == 1:

        quarter_history_score = 15

    else:

        quarter_history_score = 0

    components.append(
        (
            quarter_history_score,
            25
        )
    )

    # --------------------------------------------------------
    # YoY
    # --------------------------------------------------------

    if yoy_results:

        yoy_ready_count = len(
            [
                result
                for result in yoy_results
                if result[
                    "yoy_ready"
                ]
            ]
        )

        yoy_score = (
            yoy_ready_count
            / len(
                yoy_results
            )
        ) * 100

    else:

        yoy_score = 0.0

    components.append(
        (
            yoy_score,
            20
        )
    )

    # --------------------------------------------------------
    # السنوي
    # --------------------------------------------------------

    if annual_results:

        latest_annual = annual_results[
            -1
        ]

        annual_score = latest_annual[
            "coverage"
        ]

    else:

        annual_score = 0.0

    components.append(
        (
            annual_score,
            15
        )
    )

    total = 0.0
    total_weight = 0.0

    for value, weight in components:

        total += (
            value
            * weight
        )

        total_weight += weight

    if total_weight == 0:
        return 0.0

    return (
        total
        / total_weight
    )


# ============================================================
# تحليل صندوق واحد
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

    rows = get_financial_data(
        stock_id
    )

    annual, quarterly = (
        organize_financial_data(
            rows
        )
    )

    annual_dates = sorted(
        annual.keys()
    )

    quarter_dates = sorted(
        quarterly.keys()
    )

    annual_results = []

    for period_end in annual_dates:

        annual_results.append(
            inspect_annual_period(
                period_end,
                annual[
                    period_end
                ]
            )
        )

    quarter_results = []

    for period_end in quarter_dates:

        quarter_results.append(
            inspect_quarter(
                period_end,
                quarterly[
                    period_end
                ]
            )
        )

    yoy_results = (
        inspect_yoy_availability(
            quarter_dates,
            quarterly
        )
    )

    (
        needs_fallback,
        fallback_reasons
    ) = determine_fallback_need(
        quarter_results,
        yoy_results
    )

    source_quality = (
        calculate_source_quality(
            quarter_results,
            annual_results,
            yoy_results
        )
    )

    latest_quarter = (
        quarter_results[
            -1
        ]
        if quarter_results
        else None
    )

    latest_annual = (
        annual_results[
            -1
        ]
        if annual_results
        else None
    )

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

        "annual_count":
            len(
                annual_dates
            ),

        "quarter_count":
            len(
                quarter_dates
            ),

        "annual_dates":
            annual_dates,

        "quarter_dates":
            quarter_dates,

        "annual_results":
            annual_results,

        "quarter_results":
            quarter_results,

        "yoy_results":
            yoy_results,

        "latest_quarter":
            latest_quarter,

        "latest_annual":
            latest_annual,

        "source_quality":
            source_quality,

        "needs_fallback":
            needs_fallback,

        "fallback_reasons":
            fallback_reasons
    }


# ============================================================
# طباعة نتيجة صندوق
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
        f"📘 Annual Periods: "
        f"{result['annual_count']}",
        flush=True
    )

    print(
        f"📗 Quarterly Periods: "
        f"{result['quarter_count']}",
        flush=True
    )

    print(
        f"🧪 Current Source Quality: "
        f"{fmt(result['source_quality'])}",
        flush=True
    )

    print_separator()

    # ========================================================
    # الفترات السنوية
    # ========================================================

    print(
        "📘 ANNUAL DATA",
        flush=True
    )

    if not result[
        "annual_results"
    ]:

        print(
            "⚠️ No annual periods",
            flush=True
        )

    else:

        for annual in result[
            "annual_results"
        ]:

            print(
                f"{annual['period_end']} | "
                f"{annual['status']} | "
                f"Coverage="
                f"{fmt(annual['coverage'])}% | "
                f"{annual['available_count']}/"
                f"{annual['required_count']}",
                flush=True
            )

    print_separator()

    # ========================================================
    # الفترات الربعية
    # ========================================================

    print(
        "📗 QUARTERLY DATA",
        flush=True
    )

    if not result[
        "quarter_results"
    ]:

        print(
            "🔴 No quarterly periods",
            flush=True
        )

    else:

        for quarter in result[
            "quarter_results"
        ]:

            print(
                "\n"
                f"📅 {quarter['period_end']} | "
                f"{quarter['status']}",
                flush=True
            )

            print(
                f"Core Coverage: "
                f"{fmt(quarter['coverage'])}% | "
                f"{quarter['available_count']}/"
                f"{quarter['required_count']}",
                flush=True
            )

            print(
                f"Income Coverage: "
                f"{fmt(quarter['income_coverage'])}%",
                flush=True
            )

            print(
                f"Balance Coverage: "
                f"{fmt(quarter['balance_coverage'])}%",
                flush=True
            )

            print(
                f"CashFlow Coverage: "
                f"{fmt(quarter['cashflow_coverage'])}%",
                flush=True
            )

            if quarter[
                "missing"
            ]:

                print(
                    "Missing:",
                    flush=True
                )

                for metric_name in quarter[
                    "missing"
                ]:

                    print(
                        f"  - {metric_name}",
                        flush=True
                    )

    print_separator()

    # ========================================================
    # YoY
    # ========================================================

    print(
        "🔁 YOY READINESS",
        flush=True
    )

    if not result[
        "yoy_results"
    ]:

        print(
            "⚠️ No YoY periods",
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
                f"{yoy['period_end']} → "
                f"{yoy['prior_year_period']} | "
                f"{status}",
                flush=True
            )

    print_separator()

    # ========================================================
    # القرار
    # ========================================================

    if result[
        "needs_fallback"
    ]:

        print(
            "🌐 OFFICIAL FALLBACK: REQUIRED",
            flush=True
        )

        print(
            "Reasons:",
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
            "✅ OFFICIAL FALLBACK: NOT REQUIRED",
            flush=True
        )


# ============================================================
# الملخص النهائي
# ============================================================

def print_summary(results):

    print_header(
        "🏆 REIT OFFICIAL DATA SUMMARY"
    )

    successful = [
        result
        for result in results
        if result.get(
            "status"
        ) == "success"
    ]

    fallback_required = [
        result
        for result in successful
        if result.get(
            "needs_fallback"
        )
    ]

    fallback_not_required = [
        result
        for result in successful
        if not result.get(
            "needs_fallback"
        )
    ]

    failed = [
        result
        for result in results
        if result.get(
            "status"
        ) != "success"
    ]

    # الأسوأ أولًا
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

        fallback_state = (
            "REQUIRED"
            if result[
                "needs_fallback"
            ]
            else "NOT_REQUIRED"
        )

        latest_quarter = (
            result[
                "latest_quarter"
            ][
                "period_end"
            ]
            if result[
                "latest_quarter"
            ]
            else "NONE"
        )

        latest_coverage = (
            result[
                "latest_quarter"
            ][
                "coverage"
            ]
            if result[
                "latest_quarter"
            ]
            else 0.0
        )

        print(
            f"{index:02d}. "
            f"{result['symbol']} | "
            f"{result['company_name']} | "
            f"Quality="
            f"{fmt(result['source_quality'])} | "
            f"Quarters="
            f"{result['quarter_count']} | "
            f"Latest="
            f"{latest_quarter} | "
            f"Coverage="
            f"{fmt(latest_coverage)}% | "
            f"Fallback="
            f"{fallback_state}",
            flush=True
        )

    print_separator()

    print(
        f"🏢 Total REITs: "
        f"{len(results)}",
        flush=True
    )

    print(
        f"🟢 Fallback Not Required: "
        f"{len(fallback_not_required)}",
        flush=True
    )

    print(
        f"🌐 Official Fallback Required: "
        f"{len(fallback_required)}",
        flush=True
    )

    print(
        f"🔴 Errors: "
        f"{len(failed)}",
        flush=True
    )

    if fallback_required:

        print(
            "\n🌐 REITs requiring official source:",
            flush=True
        )

        for result in fallback_required:

            print(
                f"- {result['symbol']} | "
                f"{result['company_name']} | "
                f"{', '.join(result['fallback_reasons'])}",
                flush=True
            )

    if failed:

        print(
            "\n🔴 ERRORS:",
            flush=True
        )

        for result in failed:

            print(
                f"- {result.get('symbol')} | "
                f"{result.get('error')}",
                flush=True
            )

    print(
        "=" * 90,
        flush=True
    )


# ============================================================
# التشغيل
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
            f"🔍 REIT Check "
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


# ============================================================
# START
# ============================================================

if __name__ == "__main__":

    run_reit_official_data_engine()
