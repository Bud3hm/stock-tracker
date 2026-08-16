import os
from datetime import datetime, timezone
from supabase import create_client


# ============================================================
# BANK SIGNAL ENGINE v1.0
#
# Specialized Signal Engine for Banks
#
# READ:
# financial_metrics
#
# WRITE:
# financial_metrics
#
# Prefix:
# bank_signal_
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

ENGINE_VERSION = "1.0"

ENGINE_PREFIX = "bank_signal_"

MIN_DATA_CONFIDENCE = 60.0


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


def average(values):

    clean = []

    for value in values:

        value = safe_number(
            value
        )

        if value is not None:
            clean.append(
                value
            )

    if not clean:
        return None

    return (
        sum(clean)
        / len(clean)
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

def get_stock_info(stock_id):

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


# ============================================================
# Metrics
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

def get_bank_quarter_dates(periods):

    quarter_dates = []

    for period_end, metrics in periods.items():

        if any(
            metric_name.startswith(
                "bank_q_"
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
# Generic Growth Score
# ============================================================

def score_growth(value):

    value = safe_number(
        value
    )

    if value is None:
        return None

    if value >= 20:
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

    if value >= -3:
        return 42.0

    if value >= -7:
        return 28.0

    if value >= -12:
        return 15.0

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

    if value >= 20:
        return 100.0

    if value >= 17:
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

    if value >= 2.2:
        return 100.0

    if value >= 1.8:
        return 90.0

    if value >= 1.5:
        return 80.0

    if value >= 1.2:
        return 68.0

    if value >= 1.0:
        return 55.0

    if value >= 0.7:
        return 35.0

    return 15.0


# ============================================================
# Equity / Assets Score
# ============================================================

def score_equity_to_assets(value):

    value = safe_number(
        value
    )

    if value is None:
        return None

    if value >= 15:
        return 100.0

    if value >= 12:
        return 90.0

    if value >= 10:
        return 80.0

    if value >= 8:
        return 65.0

    if value >= 7:
        return 50.0

    if value >= 6:
        return 35.0

    return 15.0


# ============================================================
# Profit Margin Change
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
        return 48.0

    if value >= -2:
        return 32.0

    if value >= -4:
        return 15.0

    return 0.0


# ============================================================
# Growth Component
# ============================================================

def evaluate_growth(metrics):

    revenue_growth = safe_number(
        metrics.get(
            "bank_q_revenue_growth_yoy"
        )
    )

    profit_growth = safe_number(
        metrics.get(
            "bank_q_net_income_growth_yoy"
        )
    )

    assets_growth = safe_number(
        metrics.get(
            "bank_q_assets_growth_yoy"
        )
    )

    equity_growth = safe_number(
        metrics.get(
            "bank_q_equity_growth_yoy"
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
                30
            )
        )

        available += 30

        if revenue_growth >= 10:

            positive.append(
                f"نمو دخل البنك قوي "
                f"({signed_fmt(revenue_growth)}%)"
            )

        elif revenue_growth < 0:

            negative.append(
                f"دخل البنك يتراجع "
                f"({signed_fmt(revenue_growth)}%)"
            )

    if profit_growth is not None:

        items.append(
            (
                score_growth(
                    profit_growth
                ),
                40
            )
        )

        available += 40

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

    if assets_growth is not None:

        items.append(
            (
                score_growth(
                    assets_growth
                ),
                15
            )
        )

        available += 15

    if equity_growth is not None:

        items.append(
            (
                score_growth(
                    equity_growth
                ),
                15
            )
        )

        available += 15

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
# Profitability / Quality Component
# ============================================================

def evaluate_quality(metrics):

    roe = safe_number(
        metrics.get(
            "bank_ttm_roe"
        )
    )

    roa = safe_number(
        metrics.get(
            "bank_ttm_roa"
        )
    )

    margin_change = safe_number(
        metrics.get(
            "bank_q_profit_margin_change_yoy"
        )
    )

    profit_growth = safe_number(
        metrics.get(
            "bank_q_net_income_growth_yoy"
        )
    )

    revenue_growth = safe_number(
        metrics.get(
            "bank_q_revenue_growth_yoy"
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

        elif roe < 10:

            negative.append(
                f"ROE منخفض "
                f"({fmt(roe)}%)"
            )

    if roa is not None:

        items.append(
            (
                score_roa(
                    roa
                ),
                25
            )
        )

        available += 25

        if roa >= 1.5:

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

        conversion_gap = (
            revenue_growth
            - profit_growth
        )

        if conversion_gap <= 0:

            score = 90.0

        elif conversion_gap <= 3:

            score = 75.0

        elif conversion_gap <= 7:

            score = 55.0

        elif conversion_gap <= 12:

            score = 35.0

        else:

            score = 15.0

        items.append(
            (
                score,
                15
            )
        )

        available += 15

        if conversion_gap >= 10:

            negative.append(
                f"نمو الدخل لا يتحول بالكامل إلى الربح "
                f"(Gap {fmt(conversion_gap)} نقطة)"
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
# Balance / Capital Strength
# ============================================================

def evaluate_capital(metrics):

    equity_assets = safe_number(
        metrics.get(
            "bank_q_equity_to_assets"
        )
    )

    assets_growth = safe_number(
        metrics.get(
            "bank_q_assets_growth_yoy"
        )
    )

    equity_growth = safe_number(
        metrics.get(
            "bank_q_equity_growth_yoy"
        )
    )

    items = []

    available = 0.0
    possible = 100.0

    positive = []
    negative = []

    if equity_assets is not None:

        items.append(
            (
                score_equity_to_assets(
                    equity_assets
                ),
                55
            )
        )

        available += 55

        if equity_assets >= 10:

            positive.append(
                f"قاعدة رأس المال جيدة "
                f"({fmt(equity_assets)}% من الأصول)"
            )

        elif equity_assets < 7:

            negative.append(
                f"حقوق المساهمين إلى الأصول منخفضة "
                f"({fmt(equity_assets)}%)"
            )

    if equity_growth is not None:

        items.append(
            (
                score_growth(
                    equity_growth
                ),
                25
            )
        )

        available += 25

    if (
        assets_growth is not None
        and equity_growth is not None
    ):

        gap = (
            assets_growth
            - equity_growth
        )

        if gap <= 3:

            score = 90.0

        elif gap <= 6:

            score = 70.0

        elif gap <= 10:

            score = 50.0

        elif gap <= 15:

            score = 30.0

        else:

            score = 10.0

        items.append(
            (
                score,
                20
            )
        )

        available += 20

        if gap >= 10:

            negative.append(
                f"الأصول تنمو أسرع من حقوق المساهمين "
                f"بفارق {fmt(gap)} نقطة"
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

        "bank_q_revenue_growth_yoy",
        "bank_q_net_income_growth_yoy",
        "bank_q_assets_growth_yoy",
        "bank_q_equity_growth_yoy",
        "bank_q_profit_margin_change_yoy",
        "bank_ttm_roe",
        "bank_ttm_roa"
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
# Finalize
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

        weight = component[
            "weight"
        ]

        coverage = component[
            "coverage"
        ]

        usable_weight = (
            weight
            * coverage
            / 100
        )

        total_possible_weight += weight
        total_available_weight += usable_weight

        improvement_items.append(
            (
                component[
                    "improvement"
                ],
                usable_weight
            )
        )

        risk_items.append(
            (
                component[
                    "risk"
                ],
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
    ):
        return None

    signal_coverage = (
        total_available_weight
        / total_possible_weight
    ) * 100

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

    net_score = scores[
        "net_score"
    ]

    confidence = scores[
        "confidence_score"
    ]

    history = scores[
        "history_sufficiency_score"
    ]

    if (
        confidence < 55
        or history < 35
    ):

        return (
            "INSUFFICIENT_HISTORY",
            "التاريخ أو الثقة غير كافيين"
        )

    if net_score >= 40:

        return (
            "STRONG_IMPROVEMENT",
            "تحسن قوي في مؤشرات البنك"
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
            "الصورة المصرفية متوازنة"
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
# Run
# ============================================================

def run_bank_signal_engine(
    stock_id
):

    stock = get_stock_info(
        stock_id
    )

    if not stock:

        print(
            f"🔴 Stock ID {stock_id} غير موجود",
            flush=True
        )

        return

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
        f"🏦 BANK SIGNAL ENGINE v{ENGINE_VERSION}",
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
        "=" * 80,
        flush=True
    )

    if analysis_model != "bank":

        print(
            "🔴 هذا المحرك مخصص للبنوك فقط.",
            flush=True
        )

        return

    rows = get_financial_metrics(
        stock_id
    )

    if not rows:

        print(
            "🔴 لا توجد Financial Metrics",
            flush=True
        )

        return

    periods = organize_metrics(
        rows
    )

    quarter_dates = get_bank_quarter_dates(
        periods
    )

    if not quarter_dates:

        print(
            "🔴 لا توجد Bank Quarterly Metrics",
            flush=True
        )

        return

    print(
        f"📅 Quarterly Periods Found: "
        f"{len(quarter_dates)}",
        flush=True
    )

    total_saved = 0
    evaluated = 0
    limited = 0

    for index, period_end in enumerate(
        quarter_dates
    ):

        metrics = periods[
            period_end
        ]

        data_confidence = safe_number(
            metrics.get(
                "bank_data_confidence_score"
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

            limited += 1

            print(
                "🟡 LIMITED DATA | "
                "الثقة غير كافية لإصدار Signal",
                flush=True
            )

            continue

        components = []

        all_positive = []
        all_negative = []

        growth = evaluate_growth(
            metrics
        )

        if growth:

            growth[
                "weight"
            ] = 35

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

        capital = evaluate_capital(
            metrics
        )

        if capital:

            capital[
                "weight"
            ] = 25

            components.append(
                capital
            )

            all_positive.extend(
                capital[
                    "positive"
                ]
            )

            all_negative.extend(
                capital[
                    "negative"
                ]
            )

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

            limited += 1

            print(
                "🟡 لا توجد Components كافية",
                flush=True
            )

            continue

        evaluated += 1

        status_code, status_text = (
            classify_result(
                scores
            )
        )

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
            f"💾 تم حفظ Bank Signal | "
            f"{period_end}",
            flush=True
        )

    print(
        "\n"
        + "=" * 80,
        flush=True
    )

    print(
        "📊 BANK SIGNAL ENGINE SUMMARY",
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
        f"🟢 Evaluated: "
        f"{evaluated}",
        flush=True
    )

    print(
        f"🟡 Limited: "
        f"{limited}",
        flush=True
    )

    print(
        f"💾 Metrics Saved: "
        f"{total_saved}",
        flush=True
    )

    print(
        "=" * 80,
        flush=True
    )


# ============================================================
# START
# ============================================================

if __name__ == "__main__":

    stock_id = int(
        os.environ.get(
            "STOCK_ID",
            "1"
        )
    )

    run_bank_signal_engine(
        stock_id
    )
