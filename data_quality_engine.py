import os
from datetime import datetime, timezone
from supabase import create_client


# ============================================================
# DATA QUALITY ENGINE v2
#
# الهدف:
# 1) قياس حداثة البيانات
# 2) قياس التأخر عن أحدث فترة مالية متاحة في السوق
# 3) قياس اكتمال المؤشرات
# 4) قياس جودة التاريخ المتاح
# 5) قياس استمرارية الأرباع
# 6) إخراج Data Quality Score موحد 0-100
# ============================================================


SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_SECRET_KEY = os.environ.get("SUPABASE_SECRET_KEY")

supabase = create_client(
    SUPABASE_URL,
    SUPABASE_SECRET_KEY
)


# ============================================================
# أسماء المؤشرات المحفوظة
# ============================================================

FRESHNESS_METRIC = "data_freshness_score"
COVERAGE_METRIC = "data_coverage_score"
HISTORY_METRIC = "data_history_score"
CONTINUITY_METRIC = "data_continuity_score"
QUALITY_METRIC = "data_quality_score"
MARKET_LAG_METRIC = "data_market_lag_days"


MODEL_PREFIX = {
    "standard": "q_",
    "bank": "bank_q_",
    "insurance": "insurance_q_",
    "reit": "reit_q_"
}


# ============================================================
# الحد الأدنى للمؤشرات المطلوبة حسب النموذج
# ============================================================

REQUIRED_METRICS = {

    "standard": [
        "q_revenue_growth_yoy",
        "q_net_income_growth_yoy",
        "q_gross_margin",
        "q_operating_margin",
        "q_net_margin",
        "q_cash_conversion",
        "q_debt_to_equity",
        "q_current_ratio",
        "q_operating_cash_flow",
        "q_free_cash_flow"
    ],

    "bank": [
        "bank_q_revenue_growth_yoy",
        "bank_q_net_income_growth_yoy",
        "bank_q_assets_growth_yoy",
        "bank_q_equity_growth_yoy",
        "bank_ttm_roe",
        "bank_ttm_roa",
        "bank_q_equity_to_assets"
    ],

    "insurance": [
        "insurance_q_revenue_growth_yoy",
        "insurance_q_net_income_growth_yoy",
        "insurance_q_equity_growth_yoy",
        "insurance_ttm_roe",
        "insurance_ttm_roa",
        "insurance_ttm_cash_conversion"
    ],

    "reit": [
        "reit_q_revenue_growth_yoy",
        "reit_q_operating_income_growth_yoy",
        "reit_q_net_income_growth_yoy",
        "reit_q_debt_to_assets",
        "reit_ttm_cash_conversion"
    ]
}


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


def clamp(
    value,
    minimum=0.0,
    maximum=100.0
):

    value = safe_number(value)

    if value is None:
        return None

    return max(
        minimum,
        min(
            maximum,
            value
        )
    )


def fmt(value):

    value = safe_number(value)

    if value is None:
        return "N/A"

    return f"{value:.2f}"


def print_header(title):

    print(
        "\n" + "=" * 80,
        flush=True
    )

    print(
        title,
        flush=True
    )

    print(
        "=" * 80,
        flush=True
    )


# ============================================================
# Supabase
# ============================================================

def get_active_stocks():

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


def get_metrics(stock_id):

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
# تنظيم المؤشرات
# ============================================================

def organize_metrics(rows):

    periods = {}

    for row in rows:

        period_end = row.get(
            "period_end"
        )

        metric_name = row.get(
            "metric_name"
        )

        metric_value = safe_number(
            row.get(
                "metric_value"
            )
        )

        if (
            not period_end
            or not metric_name
            or metric_value is None
        ):
            continue

        period_end = str(
            period_end
        )

        periods.setdefault(
            period_end,
            {}
        )

        periods[
            period_end
        ][
            metric_name
        ] = metric_value

    return periods


# ============================================================
# الفترات الصالحة
# ============================================================

def get_valid_periods(
    periods,
    analysis_model
):

    prefix = MODEL_PREFIX.get(
        analysis_model
    )

    if prefix is None:
        return []

    valid = []

    for period_end in sorted(
        periods.keys()
    ):

        metrics = periods[
            period_end
        ]

        if any(
            metric_name.startswith(
                prefix
            )
            for metric_name in metrics
        ):

            valid.append(
                period_end
            )

    return valid


# ============================================================
# تجهيز بيانات الشركات مرة واحدة
# ============================================================

def prepare_stock_data(stocks):

    prepared = {}

    for stock in stocks:

        stock_id = stock[
            "id"
        ]

        analysis_model = (
            stock.get(
                "analysis_model"
            )
            or "standard"
        )

        rows = get_metrics(
            stock_id
        )

        periods = organize_metrics(
            rows
        )

        valid_periods = get_valid_periods(
            periods,
            analysis_model
        )

        prepared[
            stock_id
        ] = {
            "periods":
                periods,

            "valid_periods":
                valid_periods
        }

    return prepared


# ============================================================
# أحدث فترة مالية بين الشركات
# ============================================================

def get_market_latest_period(
    stocks,
    prepared_data
):

    latest_period = None
    latest_date = None

    for stock in stocks:

        stock_data = prepared_data.get(
            stock["id"],
            {}
        )

        valid_periods = stock_data.get(
            "valid_periods",
            []
        )

        if not valid_periods:
            continue

        candidate_period = (
            valid_periods[-1]
        )

        try:

            candidate_date = (
                datetime.strptime(
                    candidate_period,
                    "%Y-%m-%d"
                ).date()
            )

        except Exception:
            continue

        if (
            latest_date is None
            or candidate_date > latest_date
        ):

            latest_date = candidate_date
            latest_period = candidate_period

    return latest_period


# ============================================================
# Freshness
# ============================================================

def calculate_freshness_score(
    latest_period,
    market_latest_period=None
):

    try:

        latest_date = datetime.strptime(
            latest_period,
            "%Y-%m-%d"
        ).date()

    except Exception:

        return (
            0.0,
            None,
            None
        )

    today = datetime.now(
        timezone.utc
    ).date()

    age_days = (
        today - latest_date
    ).days

    # حماية من تاريخ مستقبلي
    if age_days < 0:
        age_days = 0

    # --------------------------------------------------------
    # Freshness الأساسي
    # صار أكثر صرامة من v1
    # --------------------------------------------------------

    if age_days <= 75:

        score = 100.0

    elif age_days <= 105:

        score = 92.0

    elif age_days <= 135:

        score = 80.0

    elif age_days <= 165:

        score = 65.0

    elif age_days <= 195:

        score = 50.0

    elif age_days <= 240:

        score = 35.0

    elif age_days <= 300:

        score = 20.0

    else:

        score = 5.0

    # --------------------------------------------------------
    # التأخر عن أحدث فترة مالية بالسوق
    # --------------------------------------------------------

    market_lag_days = None

    if market_latest_period:

        try:

            market_latest_date = (
                datetime.strptime(
                    market_latest_period,
                    "%Y-%m-%d"
                ).date()
            )

            market_lag_days = (
                market_latest_date
                - latest_date
            ).days

            if market_lag_days < 0:
                market_lag_days = 0

            # متأخر تقريبًا ربع كامل
            if market_lag_days >= 75:

                score -= 20.0

            # متأخر تقريبًا ربعين أو أكثر
            if market_lag_days >= 165:

                score -= 20.0

        except Exception:

            market_lag_days = None

    return (
        clamp(score),
        age_days,
        market_lag_days
    )


# ============================================================
# Coverage
# ============================================================

def calculate_coverage_score(
    latest_metrics,
    analysis_model
):

    required = REQUIRED_METRICS.get(
        analysis_model,
        []
    )

    if not required:

        return (
            0.0,
            0,
            0,
            []
        )

    available = 0
    missing = []

    for metric_name in required:

        value = safe_number(
            latest_metrics.get(
                metric_name
            )
        )

        if value is not None:

            available += 1

        else:

            missing.append(
                metric_name
            )

    total = len(
        required
    )

    score = (
        available
        / total
    ) * 100

    return (
        clamp(score),
        available,
        total,
        missing
    )


# ============================================================
# جودة التاريخ
# ============================================================

def calculate_history_score(
    valid_periods
):

    count = len(
        valid_periods
    )

    if count >= 8:

        score = 100

    elif count >= 6:

        score = 90

    elif count >= 4:

        score = 80

    elif count >= 3:

        score = 65

    elif count >= 2:

        score = 45

    elif count == 1:

        score = 20

    else:

        score = 0

    return float(
        score
    )


# ============================================================
# استقرار تسلسل الأرباع
# ============================================================

def calculate_period_continuity_score(
    valid_periods
):

    if len(
        valid_periods
    ) < 2:

        return 50.0

    dates = []

    for period_end in valid_periods:

        try:

            dates.append(
                datetime.strptime(
                    period_end,
                    "%Y-%m-%d"
                ).date()
            )

        except Exception:

            continue

    if len(
        dates
    ) < 2:

        return 50.0

    good_gaps = 0
    total_gaps = 0

    for index in range(
        1,
        len(dates)
    ):

        gap = (
            dates[index]
            - dates[index - 1]
        ).days

        total_gaps += 1

        # الربع المالي الطبيعي تقريبًا
        if 75 <= gap <= 105:

            good_gaps += 1

    if total_gaps == 0:

        return 50.0

    return (
        good_gaps
        / total_gaps
    ) * 100


# ============================================================
# Data Quality النهائي
# ============================================================

def calculate_quality_score(
    freshness,
    coverage,
    history,
    continuity
):

    # الحداثة والاكتمال أهم عنصرين
    values = [
        (
            freshness,
            35
        ),
        (
            coverage,
            35
        ),
        (
            history,
            20
        ),
        (
            continuity,
            10
        )
    ]

    total = 0.0
    weight_sum = 0.0

    for value, weight in values:

        value = safe_number(
            value
        )

        if value is None:
            continue

        total += (
            value
            * weight
        )

        weight_sum += weight

    if weight_sum == 0:

        return 0.0

    return clamp(
        total
        / weight_sum
    )


# ============================================================
# تصنيف جودة البيانات
# ============================================================

def classify_quality(
    quality_score,
    freshness_score,
    coverage_score
):

    quality_score = safe_number(
        quality_score
    )

    freshness_score = safe_number(
        freshness_score
    )

    coverage_score = safe_number(
        coverage_score
    )

    if quality_score is None:

        return "UNKNOWN"

    # لا نسمح بتصنيف ممتاز إذا الحداثة أو التغطية ضعيفة
    if (
        freshness_score is not None
        and freshness_score < 50
    ):

        if quality_score < 40:
            return "POOR"

        return "WEAK"

    if (
        coverage_score is not None
        and coverage_score < 50
    ):

        if quality_score < 40:
            return "POOR"

        return "WEAK"

    if quality_score >= 90:

        return "EXCELLENT"

    if quality_score >= 80:

        return "VERY_GOOD"

    if quality_score >= 70:

        return "GOOD"

    if quality_score >= 55:

        return "ACCEPTABLE"

    if quality_score >= 40:

        return "WEAK"

    return "POOR"


# ============================================================
# حفظ المؤشرات
# ============================================================

def save_quality_metrics(
    stock_id,
    period_end,
    freshness,
    coverage,
    history,
    continuity,
    quality,
    market_lag_days
):

    calculated_at = datetime.now(
        timezone.utc
    ).isoformat()

    records = []

    values = {

        FRESHNESS_METRIC:
            freshness,

        COVERAGE_METRIC:
            coverage,

        HISTORY_METRIC:
            history,

        CONTINUITY_METRIC:
            continuity,

        QUALITY_METRIC:
            quality,

        MARKET_LAG_METRIC:
            market_lag_days
    }

    for metric_name, metric_value in (
        values.items()
    ):

        metric_value = safe_number(
            metric_value
        )

        if metric_value is None:
            continue

        records.append(
            {
                "stock_id":
                    stock_id,

                "calculated_at":
                    calculated_at,

                "metric_name":
                    metric_name,

                "metric_value":
                    metric_value,

                "period_end":
                    period_end
            }
        )

    if not records:

        return 0

    (
        supabase
        .table(
            "financial_metrics"
        )
        .upsert(
            records,
            on_conflict=(
                "stock_id,"
                "metric_name,"
                "period_end"
            )
        )
        .execute()
    )

    return len(
        records
    )


# ============================================================
# تحليل شركة
# ============================================================

def analyze_stock(
    stock,
    prepared_data,
    market_latest_period
):

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

    analysis_model = (
        stock.get(
            "analysis_model"
        )
        or "standard"
    )

    stock_data = prepared_data.get(
        stock_id,
        {}
    )

    periods = stock_data.get(
        "periods",
        {}
    )

    valid_periods = stock_data.get(
        "valid_periods",
        []
    )

    if not valid_periods:

        return {
            "status":
                "no_period",

            "symbol":
                symbol,

            "company_name":
                company_name,

            "analysis_model":
                analysis_model
        }

    latest_period = (
        valid_periods[-1]
    )

    latest_metrics = periods[
        latest_period
    ]

    (
        freshness_score,
        age_days,
        market_lag_days
    ) = calculate_freshness_score(
        latest_period,
        market_latest_period
    )

    (
        coverage_score,
        available_count,
        required_count,
        missing_metrics
    ) = calculate_coverage_score(
        latest_metrics,
        analysis_model
    )

    history_score = (
        calculate_history_score(
            valid_periods
        )
    )

    continuity_score = (
        calculate_period_continuity_score(
            valid_periods
        )
    )

    quality_score = (
        calculate_quality_score(
            freshness_score,
            coverage_score,
            history_score,
            continuity_score
        )
    )

    quality_state = (
        classify_quality(
            quality_score,
            freshness_score,
            coverage_score
        )
    )

    saved = save_quality_metrics(
        stock_id,
        latest_period,
        freshness_score,
        coverage_score,
        history_score,
        continuity_score,
        quality_score,
        market_lag_days
    )

    return {
        "status":
            "success",

        "symbol":
            symbol,

        "company_name":
            company_name,

        "analysis_model":
            analysis_model,

        "latest_period":
            latest_period,

        "market_latest_period":
            market_latest_period,

        "age_days":
            age_days,

        "market_lag_days":
            market_lag_days,

        "freshness":
            freshness_score,

        "coverage":
            coverage_score,

        "history":
            history_score,

        "continuity":
            continuity_score,

        "quality":
            quality_score,

        "quality_state":
            quality_state,

        "available_count":
            available_count,

        "required_count":
            required_count,

        "missing_metrics":
            missing_metrics,

        "saved":
            saved
    }


# ============================================================
# طباعة شركة
# ============================================================

def print_result(result):

    print_header(
        f"🧪 {result.get('symbol')} | "
        f"{result.get('company_name')} | "
        f"{result.get('analysis_model')}"
    )

    if result.get(
        "status"
    ) != "success":

        print(
            f"⚠️ Status: "
            f"{result.get('status')}",
            flush=True
        )

        return

    print(
        f"📅 Latest Period: "
        f"{result['latest_period']}",
        flush=True
    )

    print(
        f"🌍 Market Latest Period: "
        f"{result['market_latest_period']}",
        flush=True
    )

    print(
        f"🕒 Age Days: "
        f"{result['age_days']}",
        flush=True
    )

    print(
        f"⏳ Market Lag Days: "
        f"{result['market_lag_days']}",
        flush=True
    )

    print(
        f"🆕 Freshness Score: "
        f"{fmt(result['freshness'])}",
        flush=True
    )

    print(
        f"📦 Coverage Score: "
        f"{fmt(result['coverage'])}",
        flush=True
    )

    print(
        f"📚 History Score: "
        f"{fmt(result['history'])}",
        flush=True
    )

    print(
        f"🔗 Continuity Score: "
        f"{fmt(result['continuity'])}",
        flush=True
    )

    print(
        f"🏆 Data Quality Score: "
        f"{fmt(result['quality'])}",
        flush=True
    )

    print(
        f"🧭 Quality State: "
        f"{result['quality_state']}",
        flush=True
    )

    print(
        f"📊 Coverage: "
        f"{result['available_count']}/"
        f"{result['required_count']}",
        flush=True
    )

    if result[
        "missing_metrics"
    ]:

        print(
            "\n⚠️ Missing Metrics:",
            flush=True
        )

        for metric_name in result[
            "missing_metrics"
        ]:

            print(
                f"- {metric_name}",
                flush=True
            )


# ============================================================
# الملخص النهائي
# ============================================================

def print_summary(results):

    successful = [
        result
        for result in results
        if result.get(
            "status"
        ) == "success"
    ]

    successful.sort(
        key=lambda result: (
            result.get(
                "quality"
            )
            if result.get(
                "quality"
            ) is not None
            else -1
        ),
        reverse=True
    )

    print_header(
        "🏆 DATA QUALITY RANKING"
    )

    for index, result in enumerate(
        successful,
        start=1
    ):

        print(
            f"{index:02d}. "
            f"{result['symbol']} | "
            f"{result['company_name']} | "
            f"{result['analysis_model']} | "
            f"Quality="
            f"{fmt(result['quality'])} | "
            f"Freshness="
            f"{fmt(result['freshness'])} | "
            f"Coverage="
            f"{fmt(result['coverage'])} | "
            f"History="
            f"{fmt(result['history'])} | "
            f"Continuity="
            f"{fmt(result['continuity'])} | "
            f"AgeDays="
            f"{result['age_days']} | "
            f"MarketLag="
            f"{result['market_lag_days']} | "
            f"{result['quality_state']}",
            flush=True
        )

    failed = [
        result
        for result in results
        if result.get(
            "status"
        ) != "success"
    ]

    print(
        "\n"
        f"🟢 Success: "
        f"{len(successful)}",
        flush=True
    )

    print(
        f"⚠️ Skipped/Failed: "
        f"{len(failed)}",
        flush=True
    )

    if failed:

        print(
            "\n⚠️ FAILED / SKIPPED",
            flush=True
        )

        for result in failed:

            print(
                f"{result.get('symbol')} | "
                f"{result.get('analysis_model')} | "
                f"{result.get('status')} | "
                f"{result.get('error', '')}",
                flush=True
            )

    print(
        "=" * 80,
        flush=True
    )


# ============================================================
# التشغيل
# ============================================================

def run_data_quality_engine():

    stocks = get_active_stocks()

    print_header(
        "🧪 DATA QUALITY ENGINE v2"
    )

    print(
        f"🏢 Total Stocks: "
        f"{len(stocks)}",
        flush=True
    )

    # --------------------------------------------------------
    # نسحب بيانات الشركات مرة واحدة فقط
    # --------------------------------------------------------

    print(
        "📥 Preparing financial metrics...",
        flush=True
    )

    prepared_data = prepare_stock_data(
        stocks
    )

    market_latest_period = (
        get_market_latest_period(
            stocks,
            prepared_data
        )
    )

    print(
        f"🌍 Market Latest Period: "
        f"{market_latest_period}",
        flush=True
    )

    results = []

    for index, stock in enumerate(
        stocks,
        start=1
    ):

        print(
            "\n"
            f"🚦 Quality Check "
            f"{index}/{len(stocks)} | "
            f"{stock['symbol']}",
            flush=True
        )

        try:

            result = analyze_stock(
                stock,
                prepared_data,
                market_latest_period
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

                "analysis_model":
                    stock.get(
                        "analysis_model"
                    ),

                "error":
                    str(error)
            }

            print(
                f"🔴 "
                f"{stock.get('symbol')} | "
                f"{type(error).__name__}: "
                f"{error}",
                flush=True
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

    run_data_quality_engine()
