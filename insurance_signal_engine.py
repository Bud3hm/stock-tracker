import os
from datetime import datetime, timezone
from supabase import create_client


# ============================================================
# INSURANCE SIGNAL ENGINE v1.0.1
#
# Specialized Signal Engine for Insurance Companies
#
# READ:
# financial_metrics
#
# WRITE:
# financial_metrics
#
# Prefix:
# insurance_signal_
#
# ملاحظات:
# - لا يستخدم منطق الشركات Standard
# - لا يستخدم Current Ratio / Debt Logic بشكل مصطنع
# - يعتمد على المؤشرات المتوفرة حاليًا لنموذج التأمين
# - يمنع التصنيف القوي عند ضعف Coverage / History / Trend
# - إذا تم تمرير STOCK_ID أو STOCK_SYMBOL يشغل شركة واحدة
# - إذا لم يتم تمريرهما يشغل جميع شركات التأمين النشطة
# ============================================================


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
        "SUPABASE_URL is missing"
    )


if not SUPABASE_SECRET_KEY:
    raise RuntimeError(
        "SUPABASE_SECRET_KEY is missing"
    )


supabase = create_client(
    SUPABASE_URL,
    SUPABASE_SECRET_KEY
)


# ============================================================
# Settings
# ============================================================

ENGINE_VERSION = "1.0.1"

ENGINE_PREFIX = "insurance_signal_"

DEFAULT_SYMBOL = "8010.SR"

MIN_DATA_CONFIDENCE = 60.0

MIN_FINAL_CONFIDENCE = 55.0

MIN_SIGNAL_COVERAGE = 60.0

MIN_HISTORY_SUFFICIENCY = 40.0

MIN_TREND_RELIABILITY = 35.0


# ============================================================
# Helpers
# ============================================================

def safe_number(value):

    if value is None:
        return None

    try:
        return float(value)

    except (
        TypeError,
        ValueError
    ):
        return None


def clamp(
    value,
    minimum=0.0,
    maximum=100.0
):

    value = safe_number(
        value
    )

    if value is None:
        return None

    return max(
        minimum,
        min(
            maximum,
            value
        )
    )


def weighted_average(items):

    total_value = 0.0
    total_weight = 0.0

    for value, weight in items:

        value = safe_number(
            value
        )

        weight = safe_number(
            weight
        )

        if (
            value is None
            or weight is None
            or weight <= 0
        ):
            continue

        total_value += (
            value
            * weight
        )

        total_weight += weight

    if total_weight <= 0:
        return None

    return (
        total_value
        / total_weight
    )


def fmt(
    value,
    decimals=2
):

    value = safe_number(
        value
    )

    if value is None:
        return "N/A"

    return (
        f"{value:.{decimals}f}"
    )


def signed_fmt(
    value,
    decimals=2
):

    value = safe_number(
        value
    )

    if value is None:
        return "N/A"

    return (
        f"{value:+.{decimals}f}"
    )


# ============================================================
# Stock Info
# ============================================================

def get_stock_by_symbol(symbol):

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
            "symbol",
            symbol
        )
        .limit(1)
        .execute()
    )

    rows = (
        response.data
        or []
    )

    if not rows:
        return None

    return rows[0]


def get_stock_by_id(stock_id):

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
            "id",
            stock_id
        )
        .limit(1)
        .execute()
    )

    rows = (
        response.data
        or []
    )

    if not rows:
        return None

    return rows[0]


def get_active_insurance_stocks():

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
            "is_active",
            True
        )
        .eq(
            "analysis_model",
            "insurance"
        )
        .order(
            "id"
        )
        .execute()
    )

    return (
        response.data
        or []
    )


def resolve_stock():

    stock_id_env = os.environ.get(
        "STOCK_ID"
    )

    stock_symbol = os.environ.get(
        "STOCK_SYMBOL",
        DEFAULT_SYMBOL
    )

    if stock_id_env:

        try:

            stock_id = int(
                stock_id_env
            )

            stock = get_stock_by_id(
                stock_id
            )

            if stock:
                return stock

        except ValueError:

            pass

    return get_stock_by_symbol(
        stock_symbol
    )


# ============================================================
# Financial Metrics
# ============================================================

def get_financial_metrics(stock_id):

    response = (
        supabase
        .table("financial_metrics")
        .select(
            "stock_id,"
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

    return (
        response.data
        or []
    )


# ============================================================
# Organize Metrics
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
# Quarter Dates
# ============================================================

def get_insurance_quarter_dates(periods):

    quarter_dates = []

    for period_end, metrics in periods.items():

        if any(
            metric_name.startswith(
                "insurance_q_"
            )
            for metric_name in metrics
        ):

            quarter_dates.append(
                period_end
            )

    return sorted(
        quarter_dates
    )


# ============================================================
# Growth Score
# ============================================================

def score_growth(value):

    value = safe_number(
        value
    )

    if value is None:
        return None

    if value >= 25:
        return 100.0

    if value >= 15:
        return 90.0

    if value >= 10:
        return 80.0

    if value >= 6:
        return 70.0

    if value >= 3:
        return 60.0

    if value >= 0:
        return 52.0

    if value >= -5:
        return 38.0

    if value >= -10:
        return 22.0

    if value >= -20:
        return 10.0

    return 0.0


# ============================================================
# ROE Score
# ============================================================

def score_roe(value):

    value = safe_number(
        value
    )

    if value is None:
        return None

    if value >= 22:
        return 100.0

    if value >= 18:
        return 90.0

    if value >= 15:
        return 80.0

    if value >= 12:
        return 68.0

    if value >= 10:
        return 55.0

    if value >= 8:
        return 40.0

    return 20.0


# ============================================================
# ROA Score
# ============================================================

def score_roa(value):

    value = safe_number(
        value
    )

    if value is None:
        return None

    if value >= 5:
        return 100.0

    if value >= 4:
        return 90.0

    if value >= 3:
        return 80.0

    if value >= 2:
        return 65.0

    if value >= 1:
        return 50.0

    if value >= 0.5:
        return 30.0

    return 10.0


# ============================================================
# Margin Change Score
# ============================================================

def score_margin_change(value):

    value = safe_number(
        value
    )

    if value is None:
        return None

    if value >= 3:
        return 100.0

    if value >= 2:
        return 90.0

    if value >= 1:
        return 78.0

    if value >= 0:
        return 60.0

    if value >= -1:
        return 45.0

    if value >= -2:
        return 30.0

    if value >= -4:
        return 15.0

    return 0.0


# ============================================================
# Cash Conversion Score
# ============================================================

def score_cash_conversion(value):

    value = safe_number(
        value
    )

    if value is None:
        return None

    if value >= 1.5:
        return 100.0

    if value >= 1.2:
        return 90.0

    if value >= 1.0:
        return 80.0

    if value >= 0.8:
        return 65.0

    if value >= 0.6:
        return 45.0

    if value >= 0.4:
        return 25.0

    return 10.0


# ============================================================
# Growth Component
# ============================================================

def evaluate_growth(metrics):

    revenue_growth = safe_number(
        metrics.get(
            "insurance_q_revenue_growth_yoy"
        )
    )

    profit_growth = safe_number(
        metrics.get(
            "insurance_q_net_income_growth_yoy"
        )
    )

    equity_growth = safe_number(
        metrics.get(
            "insurance_q_equity_growth_yoy"
        )
    )

    items = []

    available = 0.0
    possible = 100.0

    positive = []
    negative = []

    if revenue_growth is not None:

        items.append(
            (
                score_growth(
                    revenue_growth
                ),
                35
            )
        )

        available += 35

        if revenue_growth >= 10:

            positive.append(
                f"نمو الإيرادات قوي "
                f"({signed_fmt(revenue_growth)}%)"
            )

        elif revenue_growth < 0:

            negative.append(
                f"الإيرادات تتراجع "
                f"({signed_fmt(revenue_growth)}%)"
            )

    if profit_growth is not None:

        items.append(
            (
                score_growth(
                    profit_growth
                ),
                45
            )
        )

        available += 45

        if profit_growth >= 10:

            positive.append(
                f"نمو صافي الربح قوي "
                f"({signed_fmt(profit_growth)}%)"
            )

        elif profit_growth < 0:

            negative.append(
                f"صافي الربح يتراجع "
                f"({signed_fmt(profit_growth)}%)"
            )

    if equity_growth is not None:

        items.append(
            (
                score_growth(
                    equity_growth
                ),
                20
            )
        )

        available += 20

        if equity_growth >= 8:

            positive.append(
                f"حقوق المساهمين تنمو "
                f"({signed_fmt(equity_growth)}%)"
            )

        elif equity_growth <= -5:

            negative.append(
                f"حقوق المساهمين تتراجع "
                f"({signed_fmt(equity_growth)}%)"
            )

    score = weighted_average(
        items
    )

    if score is None:
        return None

    return {

        "improvement":
            score,

        "risk":
            100 - score,

        "coverage":
            (
                available
                / possible
            ) * 100,

        "positive":
            positive,

        "negative":
            negative
    }


# ============================================================
# Profitability / Quality
# ============================================================

def evaluate_quality(metrics):

    roe = safe_number(
        metrics.get(
            "insurance_ttm_roe"
        )
    )

    roa = safe_number(
        metrics.get(
            "insurance_ttm_roa"
        )
    )

    margin_change = safe_number(
        metrics.get(
            "insurance_q_profit_margin_change_yoy"
        )
    )

    revenue_growth = safe_number(
        metrics.get(
            "insurance_q_revenue_growth_yoy"
        )
    )

    profit_growth = safe_number(
        metrics.get(
            "insurance_q_net_income_growth_yoy"
        )
    )

    items = []

    available = 0.0
    possible = 100.0

    positive = []
    negative = []

    if roe is not None:

        items.append(
            (
                score_roe(
                    roe
                ),
                35
            )
        )

        available += 35

        if roe >= 15:

            positive.append(
                f"ROE قوي "
                f"({fmt(roe)}%)"
            )

        elif roe < 8:

            negative.append(
                f"ROE ضعيف "
                f"({fmt(roe)}%)"
            )

    if roa is not None:

        items.append(
            (
                score_roa(
                    roa
                ),
                20
            )
        )

        available += 20

        if roa >= 3:

            positive.append(
                f"ROA جيد "
                f"({fmt(roa)}%)"
            )

        elif roa < 1:

            negative.append(
                f"ROA ضعيف "
                f"({fmt(roa)}%)"
            )

    if margin_change is not None:

        items.append(
            (
                score_margin_change(
                    margin_change
                ),
                25
            )
        )

        available += 25

        if margin_change >= 1:

            positive.append(
                f"هامش الربح يتحسن "
                f"({signed_fmt(margin_change)} نقطة)"
            )

        elif margin_change <= -2:

            negative.append(
                f"هامش الربح يتراجع "
                f"({signed_fmt(margin_change)} نقطة)"
            )

    if (
        revenue_growth is not None
        and profit_growth is not None
    ):

        gap = (
            revenue_growth
            - profit_growth
        )

        if gap <= 0:

            score = 90.0

        elif gap <= 3:

            score = 75.0

        elif gap <= 7:

            score = 55.0

        elif gap <= 12:

            score = 35.0

        else:

            score = 15.0

        items.append(
            (
                score,
                20
            )
        )

        available += 20

        if gap >= 10:

            negative.append(
                f"نمو الإيرادات لا يتحول بالكامل إلى الربح "
                f"(Gap {fmt(gap)} نقطة)"
            )

    score = weighted_average(
        items
    )

    if score is None:
        return None

    return {

        "improvement":
            score,

        "risk":
            100 - score,

        "coverage":
            (
                available
                / possible
            ) * 100,

        "positive":
            positive,

        "negative":
            negative
    }


# ============================================================
# Cash / Earnings Support
# ============================================================

def evaluate_cash_support(metrics):

    cash_conversion = safe_number(
        metrics.get(
            "insurance_ttm_cash_conversion"
        )
    )

    ocf_growth = safe_number(
        metrics.get(
            "insurance_q_ocf_growth_yoy"
        )
    )

    items = []

    available = 0.0
    possible = 100.0

    positive = []
    negative = []

    if cash_conversion is not None:

        items.append(
            (
                score_cash_conversion(
                    cash_conversion
                ),
                60
            )
        )

        available += 60

        if cash_conversion >= 1:

            positive.append(
                f"التدفقات تدعم الأرباح "
                f"({fmt(cash_conversion)})"
            )

        elif cash_conversion < 0.50:

            negative.append(
                f"جودة التدفق النقدي ضعيفة "
                f"({fmt(cash_conversion)})"
            )

    if ocf_growth is not None:

        items.append(
            (
                score_growth(
                    ocf_growth
                ),
                40
            )
        )

        available += 40

        if ocf_growth >= 10:

            positive.append(
                f"التدفق التشغيلي يتحسن "
                f"({signed_fmt(ocf_growth)}%)"
            )

        elif ocf_growth <= -10:

            negative.append(
                f"التدفق التشغيلي يتراجع "
                f"({signed_fmt(ocf_growth)}%)"
            )

    score = weighted_average(
        items
    )

    if score is None:
        return None

    return {

        "improvement":
            score,

        "risk":
            100 - score,

        "coverage":
            (
                available
                / possible
            ) * 100,

        "positive":
            positive,

        "negative":
            negative
    }


# ============================================================
# History Sufficiency
# ============================================================

def calculate_history(
    quarter_dates,
    index
):

    count = (
        index + 1
    )

    if count >= 8:
        return 100.0

    if count >= 6:
        return 85.0

    if count >= 4:
        return 70.0

    if count >= 3:
        return 55.0

    if count >= 2:
        return 35.0

    return 15.0


# ============================================================
# Trend Reliability
# ============================================================

def calculate_trend_reliability(
    quarter_dates,
    periods,
    index
):

    if index < 2:

        return 25.0

    watched = [

        "insurance_q_revenue_growth_yoy",
        "insurance_q_net_income_growth_yoy",
        "insurance_q_equity_growth_yoy",
        "insurance_q_profit_margin_change_yoy",
        "insurance_q_ocf_growth_yoy",
        "insurance_ttm_roe",
        "insurance_ttm_roa",
        "insurance_ttm_cash_conversion"
    ]

    dates = quarter_dates[
        index - 2:
        index + 1
    ]

    available = 0
    stable = 0

    for metric_name in watched:

        values = []

        for date in dates:

            value = safe_number(
                periods[
                    date
                ].get(
                    metric_name
                )
            )

            if value is not None:

                values.append(
                    value
                )

        if len(values) < 2:
            continue

        available += 1

        last_move = abs(
            values[-1]
            - values[-2]
        )

        value_range = (
            max(values)
            - min(values)
        )

        if (
            value_range == 0
            or last_move
            <= value_range * 1.25
        ):

            stable += 1

    if available == 0:
        return 25.0

    raw = (
        stable
        / available
    ) * 100

    history_factor = min(
        (
            index + 1
        ) / 6,
        1
    )

    score = (
        raw * 0.75
        + history_factor
        * 100
        * 0.25
    )

    return clamp(
        score
    )


# ============================================================
# Finalize Engine
# ============================================================

def finalize_engine(
    components,
    data_confidence,
    history,
    trend_reliability
):

    if not components:
        return None

    improvement_items = []
    risk_items = []

    total_possible_weight = 0.0
    total_available_weight = 0.0

    for component in components:

        weight = safe_number(
            component.get(
                "weight"
            )
        )

        coverage = safe_number(
            component.get(
                "coverage"
            )
        )

        improvement = safe_number(
            component.get(
                "improvement"
            )
        )

        risk = safe_number(
            component.get(
                "risk"
            )
        )

        if (
            weight is None
            or coverage is None
            or improvement is None
            or risk is None
            or weight <= 0
        ):
            continue

        coverage = clamp(
            coverage
        )

        usable_weight = (
            weight
            * coverage
            / 100
        )

        total_possible_weight += weight

        total_available_weight += (
            usable_weight
        )

        improvement_items.append(
            (
                improvement,
                usable_weight
            )
        )

        risk_items.append(
            (
                risk,
                usable_weight
            )
        )

    raw_improvement = weighted_average(
        improvement_items
    )

    raw_risk = weighted_average(
        risk_items
    )

    if (
        raw_improvement is None
        or raw_risk is None
        or total_possible_weight <= 0
        or total_available_weight <= 0
    ):
        return None

    signal_coverage = (
        total_available_weight
        / total_possible_weight
    ) * 100

    signal_coverage = clamp(
        signal_coverage
    )

    coverage_factor = (
        0.35
        + signal_coverage
        / 100
        * 0.65
    )

    improvement = (
        raw_improvement
        * coverage_factor
    )

    risk = (
        raw_risk
        * coverage_factor
    )

    improvement = clamp(
        improvement
    )

    risk = clamp(
        risk
    )

    net_score = (
        improvement
        - risk
    )

    data_confidence = (
        safe_number(
            data_confidence
        )
        or 0.0
    )

    history = (
        safe_number(
            history
        )
        or 0.0
    )

    trend_reliability = (
        safe_number(
            trend_reliability
        )
        or 0.0
    )

    confidence = (

        data_confidence
        * 0.35

        + signal_coverage
        * 0.25

        + history
        * 0.20

        + trend_reliability
        * 0.20
    )

    confidence = clamp(
        confidence
    )

    return {

        "improvement_score":
            improvement,

        "risk_score":
            risk,

        "net_score":
            net_score,

        "confidence_score":
            confidence,

        "signal_coverage_score":
            signal_coverage,

        "history_sufficiency_score":
            history,

        "trend_reliability_score":
            trend_reliability
    }


# ============================================================
# Classification
# ============================================================

def classify_result(scores):

    net_score = safe_number(
        scores.get(
            "net_score"
        )
    )

    confidence = safe_number(
        scores.get(
            "confidence_score"
        )
    )

    coverage = safe_number(
        scores.get(
            "signal_coverage_score"
        )
    )

    history = safe_number(
        scores.get(
            "history_sufficiency_score"
        )
    )

    reliability = safe_number(
        scores.get(
            "trend_reliability_score"
        )
    )

    if net_score is None:

        return (
            "INSUFFICIENT_DATA",
            "لا توجد درجة نهائية صالحة"
        )

    confidence = (
        confidence
        if confidence is not None
        else 0.0
    )

    coverage = (
        coverage
        if coverage is not None
        else 0.0
    )

    history = (
        history
        if history is not None
        else 0.0
    )

    reliability = (
        reliability
        if reliability is not None
        else 0.0
    )

    limitations = []

    if confidence < MIN_FINAL_CONFIDENCE:

        limitations.append(
            f"Confidence {confidence:.2f}"
            f"<{MIN_FINAL_CONFIDENCE:.0f}"
        )

    if coverage < MIN_SIGNAL_COVERAGE:

        limitations.append(
            f"Coverage {coverage:.2f}"
            f"<{MIN_SIGNAL_COVERAGE:.0f}"
        )

    if history < MIN_HISTORY_SUFFICIENCY:

        limitations.append(
            f"History {history:.2f}"
            f"<{MIN_HISTORY_SUFFICIENCY:.0f}"
        )

    if reliability < MIN_TREND_RELIABILITY:

        limitations.append(
            f"Trend {reliability:.2f}"
            f"<{MIN_TREND_RELIABILITY:.0f}"
        )

    if limitations:

        return (
            "INSUFFICIENT_HISTORY",
            "لا يصدر تصنيف اتجاه قوي بسبب: "
            + " | ".join(
                limitations
            )
        )

    if net_score >= 40:

        return (
            "STRONG_IMPROVEMENT",
            "تحسن قوي في مؤشرات شركة التأمين"
        )

    if net_score >= 18:

        return (
            "IMPROVING",
            "اتجاه تحسن واضح"
        )

    if net_score >= 5:

        return (
            "EARLY_IMPROVEMENT",
            "إشارات تحسن مبكرة"
        )

    if net_score > -5:

        return (
            "NEUTRAL",
            "الصورة التأمينية متوازنة"
        )

    if net_score > -18:

        return (
            "EARLY_RISK",
            "إشارات ضعف مبكرة"
        )

    if net_score > -40:

        return (
            "DETERIORATING",
            "تدهور واضح في المؤشرات"
        )

    return (
        "HIGH_RISK",
        "تدهور قوي ومتعدد الإشارات"
    )


# ============================================================
# Save
# ============================================================

def save_engine_metrics(
    stock_id,
    period_end,
    values
):

    calculated_at = datetime.now(
        timezone.utc
    ).isoformat()

    records = []

    for name, metric_value in values.items():

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
                    f"{ENGINE_PREFIX}{name}",

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
        .table("financial_metrics")
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
# Run One Insurance Company
# ============================================================

def run_insurance_signal_engine(stock=None):

    if stock is None:
        stock = resolve_stock()

    if not stock:

        print(
            "🔴 لم يتم العثور على شركة التأمين المطلوبة",
            flush=True
        )

        return False

    stock_id = stock[
        "id"
    ]

    symbol = (
        stock.get(
            "symbol"
        )
        or str(
            stock_id
        )
    )

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
        or ""
    )

    print(
        "\n"
        + "=" * 80,
        flush=True
    )

    print(
        f"🛡️ INSURANCE SIGNAL ENGINE v{ENGINE_VERSION}",
        flush=True
    )

    print(
        f"🏢 {symbol} | {company_name}",
        flush=True
    )

    print(
        f"🧩 Analysis Model: "
        f"{analysis_model}",
        flush=True
    )

    print(
        f"🆔 Stock ID: "
        f"{stock_id}",
        flush=True
    )

    print(
        "=" * 80,
        flush=True
    )

    if analysis_model != "insurance":

        print(
            "🔴 هذا المحرك مخصص لشركات التأمين فقط.",
            flush=True
        )

        return False

    rows = get_financial_metrics(
        stock_id
    )

    if not rows:

        print(
            "🔴 لا توجد Financial Metrics",
            flush=True
        )

        return False

    periods = organize_metrics(
        rows
    )

    quarter_dates = get_insurance_quarter_dates(
        periods
    )

    if not quarter_dates:

        print(
            "🔴 لا توجد Insurance Quarterly Metrics",
            flush=True
        )

        return False

    print(
        f"📅 Quarterly Periods Found: "
        f"{len(quarter_dates)}",
        flush=True
    )

    scored_periods = 0
    qualified_periods = 0
    gated_periods = 0
    limited_periods = 0
    total_saved = 0

    for index, period_end in enumerate(
        quarter_dates
    ):

        metrics = periods[
            period_end
        ]

        data_confidence = safe_number(
            metrics.get(
                "insurance_data_confidence_score"
            )
        )

        if data_confidence is None:

            data_confidence = safe_number(
                metrics.get(
                    "data_confidence_score"
                )
            )

        print(
            "\n"
            + "-" * 80,
            flush=True
        )

        print(
            f"📅 الفترة: {period_end}",
            flush=True
        )

        print(
            f"🎯 Data Confidence: "
            f"{fmt(data_confidence)}",
            flush=True
        )

        if (
            data_confidence is None
            or data_confidence
            < MIN_DATA_CONFIDENCE
        ):

            limited_periods += 1

            print(
                "🟡 LIMITED DATA | "
                "الثقة الأساسية للبيانات غير كافية "
                "لإصدار Signal",
                flush=True
            )

            continue

        components = []

        all_positive = []
        all_negative = []

        # ====================================================
        # Growth
        # ====================================================

        growth = evaluate_growth(
            metrics
        )

        if growth:

            growth[
                "weight"
            ] = 40

            components.append(
                growth
            )

            all_positive.extend(
                growth[
                    "positive"
                ]
            )

            all_negative.extend(
                growth[
                    "negative"
                ]
            )

        # ====================================================
        # Quality
        # ====================================================

        quality = evaluate_quality(
            metrics
        )

        if quality:

            quality[
                "weight"
            ] = 40

            components.append(
                quality
            )

            all_positive.extend(
                quality[
                    "positive"
                ]
            )

            all_negative.extend(
                quality[
                    "negative"
                ]
            )

        # ====================================================
        # Cash Support
        # ====================================================

        cash_support = evaluate_cash_support(
            metrics
        )

        if cash_support:

            cash_support[
                "weight"
            ] = 20

            components.append(
                cash_support
            )

            all_positive.extend(
                cash_support[
                    "positive"
                ]
            )

            all_negative.extend(
                cash_support[
                    "negative"
                ]
            )

        # ====================================================
        # Historical Quality
        # ====================================================

        history = calculate_history(
            quarter_dates,
            index
        )

        trend_reliability = (
            calculate_trend_reliability(
                quarter_dates,
                periods,
                index
            )
        )

        scores = finalize_engine(
            components,
            data_confidence,
            history,
            trend_reliability
        )

        if not scores:

            limited_periods += 1

            print(
                "🟡 LIMITED DATA | "
                "لا توجد Components كافية للحساب",
                flush=True
            )

            continue

        scored_periods += 1

        status_code, status_text = (
            classify_result(
                scores
            )
        )

        if status_code == "INSUFFICIENT_HISTORY":

            gated_periods += 1

        else:

            qualified_periods += 1

        print(
            f"🟢 Improvement: "
            f"{fmt(scores['improvement_score'])}",
            flush=True
        )

        print(
            f"🔴 Risk: "
            f"{fmt(scores['risk_score'])}",
            flush=True
        )

        print(
            f"⚖️ Net: "
            f"{signed_fmt(scores['net_score'])}",
            flush=True
        )

        print(
            f"🎯 Confidence: "
            f"{fmt(scores['confidence_score'])}",
            flush=True
        )

        print(
            f"📡 Signal Coverage: "
            f"{fmt(scores['signal_coverage_score'])}",
            flush=True
        )

        print(
            f"🗂️ History: "
            f"{fmt(scores['history_sufficiency_score'])}",
            flush=True
        )

        print(
            f"🧬 Trend Reliability: "
            f"{fmt(scores['trend_reliability_score'])}",
            flush=True
        )

        print(
            f"🧭 الحالة: "
            f"{status_code} | "
            f"{status_text}",
            flush=True
        )

        if status_code == "INSUFFICIENT_HISTORY":

            print(
                "🛡️ Quality Gate: "
                "تم منع التصنيف الاتجاهي القوي "
                "حتى تكتمل جودة الإشارة التاريخية.",
                flush=True
            )

        print(
            "\n🟢 أسباب التحسن:",
            flush=True
        )

        if all_positive:

            for reason in all_positive[:6]:

                print(
                    f"- {reason}",
                    flush=True
                )

        else:

            print(
                "- لا توجد إشارة تحسن قوية",
                flush=True
            )

        print(
            "\n🔴 أسباب الخطر:",
            flush=True
        )

        if all_negative:

            for reason in all_negative[:6]:

                print(
                    f"- {reason}",
                    flush=True
                )

        else:

            print(
                "- لا توجد إشارة خطر قوية",
                flush=True
            )

        total_saved += (
            save_engine_metrics(
                stock_id,
                period_end,
                scores
            )
        )

        print(
            f"💾 تم حفظ Insurance Signal | "
            f"{period_end}",
            flush=True
        )

    # ========================================================
    # Summary
    # ========================================================

    print(
        "\n"
        + "=" * 80,
        flush=True
    )

    print(
        f"📊 INSURANCE SIGNAL ENGINE v{ENGINE_VERSION} SUMMARY",
        flush=True
    )

    print(
        "=" * 80,
        flush=True
    )

    print(
        f"🏢 {symbol} | "
        f"{company_name}",
        flush=True
    )

    print(
        f"📅 Periods Found: "
        f"{len(quarter_dates)}",
        flush=True
    )

    print(
        f"🧮 Scored Periods: "
        f"{scored_periods}",
        flush=True
    )

    print(
        f"✅ Qualified Periods: "
        f"{qualified_periods}",
        flush=True
    )

    print(
        f"🛡️ Quality-Gated Periods: "
        f"{gated_periods}",
        flush=True
    )

    print(
        f"🟡 Limited Data Periods: "
        f"{limited_periods}",
        flush=True
    )

    print(
        f"💾 Metrics Saved: "
        f"{total_saved}",
        flush=True
    )

    print(
        "\n🛡️ Classification Gates:",
        flush=True
    )

    print(
        f"- Final Confidence >= "
        f"{MIN_FINAL_CONFIDENCE:.0f}",
        flush=True
    )

    print(
        f"- Signal Coverage >= "
        f"{MIN_SIGNAL_COVERAGE:.0f}",
        flush=True
    )

    print(
        f"- History Sufficiency >= "
        f"{MIN_HISTORY_SUFFICIENCY:.0f}",
        flush=True
    )

    print(
        f"- Trend Reliability >= "
        f"{MIN_TREND_RELIABILITY:.0f}",
        flush=True
    )

    print(
        "=" * 80,
        flush=True
    )

    return True


# ============================================================
# Run All Active Insurance Companies
# ============================================================

def run_all_active_insurance():

    insurance_stocks = (
        get_active_insurance_stocks()
    )

    print(
        "\n"
        + "=" * 80,
        flush=True
    )

    print(
        f"🛡️ INSURANCE SIGNAL ENGINE v{ENGINE_VERSION} | "
        "ALL ACTIVE INSURANCE",
        flush=True
    )

    print(
        f"🏢 Active Insurance Companies Found: "
        f"{len(insurance_stocks)}",
        flush=True
    )

    print(
        "=" * 80,
        flush=True
    )

    if not insurance_stocks:

        print(
            "🟡 لا توجد شركات تأمين نشطة في جدول stocks",
            flush=True
        )

        return

    success = 0
    failed = 0

    for index, stock in enumerate(
        insurance_stocks,
        start=1
    ):

        symbol = (
            stock.get(
                "symbol"
            )
            or str(
                stock.get(
                    "id"
                )
            )
        )

        print(
            "\n"
            f"🚦 Insurance "
            f"{index}/{len(insurance_stocks)} | "
            f"{symbol}",
            flush=True
        )

        try:

            result = run_insurance_signal_engine(
                stock
            )

            if result:
                success += 1
            else:
                failed += 1

        except Exception as error:

            failed += 1

            print(
                f"🔴 {symbol} | "
                f"{type(error).__name__}: "
                f"{error}",
                flush=True
            )

    print(
        "\n"
        + "=" * 80,
        flush=True
    )

    print(
        "📊 ALL INSURANCE SUMMARY",
        flush=True
    )

    print(
        "=" * 80,
        flush=True
    )

    print(
        f"🏢 Insurance Companies Found: "
        f"{len(insurance_stocks)}",
        flush=True
    )

    print(
        f"🟢 Completed: "
        f"{success}",
        flush=True
    )

    print(
        f"🔴 Failed: "
        f"{failed}",
        flush=True
    )

    print(
        "=" * 80,
        flush=True
    )


# ============================================================
# START
#
# إذا تم تمرير STOCK_ID أو STOCK_SYMBOL:
# يشغل شركة واحدة للاختبار.
#
# إذا لم يتم تمرير أي منهما:
# يشغل جميع شركات التأمين النشطة تلقائيًا.
# ============================================================

if __name__ == "__main__":

    stock_id_env = os.environ.get(
        "STOCK_ID"
    )

    stock_symbol_env = os.environ.get(
        "STOCK_SYMBOL"
    )

    if (
        stock_id_env
        or stock_symbol_env
    ):

        stock = resolve_stock()

        if not stock:

            raise RuntimeError(
                "لم يتم العثور على شركة التأمين المطلوبة"
            )

        run_insurance_signal_engine(
            stock
        )

    else:

        run_all_active_insurance()
