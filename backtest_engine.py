import os
from collections import defaultdict
from supabase import create_client


# ============================================================
# إعداد Supabase
# ============================================================

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_SECRET_KEY = os.environ.get("SUPABASE_SECRET_KEY")

supabase = create_client(
    SUPABASE_URL,
    SUPABASE_SECRET_KEY
)


# ============================================================
# إعدادات الاختبار
# ============================================================

ENGINE_PREFIX = "engine22_"

FORWARD_QUARTERS = [
    1,
    2,
    4
]


# ============================================================
# أدوات مساعدة
# ============================================================

def safe_number(value):

    if value is None:
        return None

    try:
        return float(value)

    except (TypeError, ValueError):
        return None


def clamp(value, minimum, maximum):

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

    return sum(clean) / len(clean)


def growth_rate(current, previous):

    current = safe_number(
        current
    )

    previous = safe_number(
        previous
    )

    if (
        current is None
        or previous is None
        or previous == 0
    ):
        return None

    return (
        (
            current - previous
        )
        / abs(previous)
    ) * 100


# ============================================================
# نمو مضبوط ضد Base Effect
#
# للتدفقات النقدية خصوصًا
# ============================================================

def robust_growth(
    current,
    previous
):

    current = safe_number(
        current
    )

    previous = safe_number(
        previous
    )

    if (
        current is None
        or previous is None
    ):
        return None

    scale = max(
        abs(previous),
        abs(current),
        1.0
    )

    normalized_change = (
        current - previous
    ) / scale

    score_like_growth = (
        normalized_change
        * 100
    )

    return clamp(
        score_like_growth,
        -100,
        100
    )


# ============================================================
# جلب المؤشرات
# ============================================================

def get_metrics(stock_id):

    response = (
        supabase
        .table("financial_metrics")
        .select(
            "stock_id,"
            "period_end,"
            "metric_name,"
            "metric_value"
        )
        .eq("stock_id", stock_id)
        .execute()
    )

    return response.data


# ============================================================
# تنظيم البيانات حسب الفترة
# ============================================================

def organize_metrics(rows):

    periods = {}

    for row in rows:

        period_end = str(
            row.get("period_end")
        )

        metric_name = row.get(
            "metric_name"
        )

        metric_value = safe_number(
            row.get("metric_value")
        )

        if (
            not period_end
            or not metric_name
            or metric_value is None
        ):
            continue

        if period_end not in periods:
            periods[period_end] = {}

        periods[
            period_end
        ][
            metric_name
        ] = metric_value

    return periods


# ============================================================
# تحديد الأرباع
# ============================================================

def get_quarter_dates(periods):

    dates = []

    for period_end, metrics in periods.items():

        if (
            "q_revenue" in metrics
            or "q_net_income" in metrics
            or f"{ENGINE_PREFIX}net_score" in metrics
        ):

            dates.append(
                period_end
            )

    return sorted(
        dates
    )


# ============================================================
# تصنيف الإشارة
# ============================================================

def classify_signal(
    net_score,
    confidence
):

    net_score = safe_number(
        net_score
    )

    confidence = safe_number(
        confidence
    )

    if (
        net_score is None
        or confidence is None
    ):
        return "NO_SIGNAL"

    if confidence < 55:
        return "LOW_CONFIDENCE"

    if net_score >= 20:
        return "POSITIVE"

    if net_score <= -20:
        return "NEGATIVE"

    if net_score >= 5:
        return "EARLY_POSITIVE"

    if net_score <= -5:
        return "EARLY_NEGATIVE"

    return "NEUTRAL"


# ============================================================
# Outcome خام
# ============================================================

def calculate_future_outcome(
    current_metrics,
    future_metrics
):

    current_revenue = safe_number(
        current_metrics.get(
            "q_revenue"
        )
    )

    future_revenue = safe_number(
        future_metrics.get(
            "q_revenue"
        )
    )

    current_profit = safe_number(
        current_metrics.get(
            "q_net_income"
        )
    )

    future_profit = safe_number(
        future_metrics.get(
            "q_net_income"
        )
    )

    current_margin = safe_number(
        current_metrics.get(
            "q_net_margin"
        )
    )

    future_margin = safe_number(
        future_metrics.get(
            "q_net_margin"
        )
    )

    current_ocf = safe_number(
        current_metrics.get(
            "q_operating_cash_flow"
        )
    )

    future_ocf = safe_number(
        future_metrics.get(
            "q_operating_cash_flow"
        )
    )

    current_fcf = safe_number(
        current_metrics.get(
            "q_free_cash_flow"
        )
    )

    future_fcf = safe_number(
        future_metrics.get(
            "q_free_cash_flow"
        )
    )

    revenue_growth = growth_rate(
        future_revenue,
        current_revenue
    )

    profit_growth = growth_rate(
        future_profit,
        current_profit
    )

    margin_change = None

    if (
        current_margin is not None
        and future_margin is not None
    ):

        margin_change = (
            future_margin
            - current_margin
        )

    # robust بدل growth_rate العادي
    ocf_change = robust_growth(
        future_ocf,
        current_ocf
    )

    fcf_change = robust_growth(
        future_fcf,
        current_fcf
    )

    return {
        "future_revenue_growth":
            revenue_growth,

        "future_profit_growth":
            profit_growth,

        "future_margin_change":
            margin_change,

        "future_ocf_change_robust":
            ocf_change,

        "future_fcf_change_robust":
            fcf_change
    }


# ============================================================
# Scoring Components
# ============================================================

def score_revenue(value):

    value = safe_number(
        value
    )

    if value is None:
        return None

    if value >= 20:
        return 90

    if value >= 10:
        return 75

    if value >= 5:
        return 65

    if value >= 0:
        return 55

    if value >= -5:
        return 40

    if value >= -10:
        return 25

    return 10


def score_profit(value):

    value = safe_number(
        value
    )

    if value is None:
        return None

    if value >= 25:
        return 95

    if value >= 15:
        return 85

    if value >= 8:
        return 75

    if value >= 0:
        return 55

    if value >= -8:
        return 40

    if value >= -15:
        return 25

    return 5


def score_margin(value):

    value = safe_number(
        value
    )

    if value is None:
        return None

    if value >= 3:
        return 90

    if value >= 1.5:
        return 80

    if value >= 0.5:
        return 70

    if value >= 0:
        return 55

    if value >= -1:
        return 40

    if value >= -2:
        return 25

    return 10


def score_cash(value):

    value = safe_number(
        value
    )

    if value is None:
        return None

    if value >= 50:
        return 90

    if value >= 20:
        return 80

    if value >= 5:
        return 65

    if value >= 0:
        return 55

    if value >= -10:
        return 40

    if value >= -25:
        return 25

    return 10


# ============================================================
# Outcome Component Scores
# ============================================================

def build_outcome_components(
    outcome
):

    return {
        "revenue_score":
            score_revenue(
                outcome.get(
                    "future_revenue_growth"
                )
            ),

        "profit_score":
            score_profit(
                outcome.get(
                    "future_profit_growth"
                )
            ),

        "margin_score":
            score_margin(
                outcome.get(
                    "future_margin_change"
                )
            ),

        "ocf_score":
            score_cash(
                outcome.get(
                    "future_ocf_change_robust"
                )
            ),

        "fcf_score":
            score_cash(
                outcome.get(
                    "future_fcf_change_robust"
                )
            )
    }


# ============================================================
# Outcome Score مركب
#
# الربح أهم ثم الهوامش
# ============================================================

def calculate_outcome_score(
    components
):

    weights = {
        "revenue_score": 20,
        "profit_score": 30,
        "margin_score": 20,
        "ocf_score": 15,
        "fcf_score": 15
    }

    weighted_sum = 0.0
    total_weight = 0.0

    for name, weight in weights.items():

        value = safe_number(
            components.get(
                name
            )
        )

        if value is None:
            continue

        weighted_sum += (
            value * weight
        )

        total_weight += weight

    if total_weight == 0:
        return None

    return (
        weighted_sum
        / total_weight
    )


# ============================================================
# Outcome Direction
# ============================================================

def classify_outcome(score):

    score = safe_number(
        score
    )

    if score is None:
        return "NO_DATA"

    if score >= 75:
        return "STRONG_IMPROVEMENT"

    if score >= 60:
        return "IMPROVEMENT"

    if score >= 45:
        return "NEUTRAL"

    if score >= 30:
        return "DETERIORATION"

    return "STRONG_DETERIORATION"


# ============================================================
# تحويل الإشارة إلى Direction رقمي
# ============================================================

def signal_direction(
    signal_class
):

    mapping = {
        "POSITIVE": 1.0,
        "EARLY_POSITIVE": 0.5,
        "NEUTRAL": 0.0,
        "EARLY_NEGATIVE": -0.5,
        "NEGATIVE": -1.0
    }

    return mapping.get(
        signal_class
    )


# ============================================================
# تحويل Outcome إلى Direction رقمي
# ============================================================

def outcome_direction(
    outcome_score
):

    outcome_score = safe_number(
        outcome_score
    )

    if outcome_score is None:
        return None

    # 50 = neutral center
    direction = (
        outcome_score
        - 50
    ) / 25

    return clamp(
        direction,
        -1,
        1
    )


# ============================================================
# Prediction Alignment
#
# 100 = ممتاز
# 50 = جزئي
# 0 = عكس الاتجاه
# ============================================================

def calculate_alignment(
    signal_class,
    outcome_score
):

    signal = signal_direction(
        signal_class
    )

    outcome = outcome_direction(
        outcome_score
    )

    if (
        signal is None
        or outcome is None
    ):
        return None

    distance = abs(
        signal - outcome
    )

    alignment = (
        1
        - (
            distance / 2
        )
    ) * 100

    return clamp(
        alignment,
        0,
        100
    )


# ============================================================
# قوة النتيجة المستقبلية
# ============================================================

def calculate_outcome_strength(
    outcome_score
):

    outcome_score = safe_number(
        outcome_score
    )

    if outcome_score is None:
        return None

    return abs(
        outcome_score - 50
    ) * 2


# ============================================================
# طباعة اختبار
# ============================================================

def print_backtest_result(
    base_date,
    future_date,
    forward_quarters,
    signal_class,
    net_score,
    confidence,
    outcome,
    components,
    outcome_score,
    outcome_class,
    alignment,
    strength
):

    print(
        "\n"
        "------------------------------------------------------------",
        flush=True
    )

    print(
        f"📅 Base Quarter: "
        f"{base_date}",
        flush=True
    )

    print(
        f"🔮 Future Quarter: "
        f"{future_date}",
        flush=True
    )

    print(
        f"⏩ Horizon: "
        f"Q+{forward_quarters}",
        flush=True
    )

    print(
        f"🧠 Signal: "
        f"{signal_class}",
        flush=True
    )

    print(
        f"⚖️ Net Score: "
        f"{net_score}",
        flush=True
    )

    print(
        f"🎯 Confidence: "
        f"{confidence}",
        flush=True
    )

    print(
        "\n📊 Future Raw Outcome",
        flush=True
    )

    print(
        f"Revenue Growth: "
        f"{outcome['future_revenue_growth']}",
        flush=True
    )

    print(
        f"Profit Growth: "
        f"{outcome['future_profit_growth']}",
        flush=True
    )

    print(
        f"Margin Change: "
        f"{outcome['future_margin_change']}",
        flush=True
    )

    print(
        f"OCF Robust Change: "
        f"{outcome['future_ocf_change_robust']}",
        flush=True
    )

    print(
        f"FCF Robust Change: "
        f"{outcome['future_fcf_change_robust']}",
        flush=True
    )

    print(
        "\n🧩 Outcome Components",
        flush=True
    )

    for name, value in (
        components.items()
    ):

        print(
            f"{name}: {value}",
            flush=True
        )

    print(
        f"\n📈 Outcome Score: "
        f"{outcome_score}",
        flush=True
    )

    print(
        f"🧭 Outcome Class: "
        f"{outcome_class}",
        flush=True
    )

    print(
        f"🎯 Prediction Alignment: "
        f"{alignment}",
        flush=True
    )

    print(
        f"💪 Outcome Strength: "
        f"{strength}",
        flush=True
    )


# ============================================================
# Summary حسب الأفق
# ============================================================

def print_horizon_summary(
    results_by_horizon
):

    print(
        "\n"
        "============================================================",
        flush=True
    )

    print(
        "📊 BACKTEST SUMMARY BY HORIZON",
        flush=True
    )

    print(
        "============================================================",
        flush=True
    )

    for horizon in sorted(
        results_by_horizon.keys()
    ):

        values = (
            results_by_horizon[
                horizon
            ]
        )

        if not values:
            continue

        average_alignment = (
            sum(values)
            / len(values)
        )

        print(
            f"\nQ+{horizon}",
            flush=True
        )

        print(
            f"Predictions: "
            f"{len(values)}",
            flush=True
        )

        print(
            f"Average Alignment: "
            f"{average_alignment:.2f}%",
            flush=True
        )


# ============================================================
# التشغيل الرئيسي
# ============================================================

def run_backtest(stock_id):

    rows = get_metrics(
        stock_id
    )

    if not rows:

        print(
            "🔴 لا توجد Metrics",
            flush=True
        )

        return

    periods = organize_metrics(
        rows
    )

    quarter_dates = get_quarter_dates(
        periods
    )

    print(
        "\n"
        "============================================================",
        flush=True
    )

    print(
        "🧪 BACKTEST ENGINE v1.1",
        flush=True
    )

    print(
        "============================================================",
        flush=True
    )

    results_by_horizon = defaultdict(
        list
    )

    total_evaluated = 0

    for index, base_date in enumerate(
        quarter_dates
    ):

        current = periods[
            base_date
        ]

        net_score = safe_number(
            current.get(
                f"{ENGINE_PREFIX}net_score"
            )
        )

        confidence = safe_number(
            current.get(
                f"{ENGINE_PREFIX}confidence_score"
            )
        )

        signal_class = classify_signal(
            net_score,
            confidence
        )

        if signal_class in (
            "NO_SIGNAL",
            "LOW_CONFIDENCE"
        ):
            continue

        for forward in FORWARD_QUARTERS:

            future_index = (
                index + forward
            )

            if future_index >= len(
                quarter_dates
            ):
                continue

            future_date = quarter_dates[
                future_index
            ]

            future = periods[
                future_date
            ]

            outcome = (
                calculate_future_outcome(
                    current,
                    future
                )
            )

            components = (
                build_outcome_components(
                    outcome
                )
            )

            outcome_score = (
                calculate_outcome_score(
                    components
                )
            )

            outcome_class = (
                classify_outcome(
                    outcome_score
                )
            )

            alignment = (
                calculate_alignment(
                    signal_class,
                    outcome_score
                )
            )

            strength = (
                calculate_outcome_strength(
                    outcome_score
                )
            )

            print_backtest_result(
                base_date,
                future_date,
                forward,
                signal_class,
                net_score,
                confidence,
                outcome,
                components,
                outcome_score,
                outcome_class,
                alignment,
                strength
            )

            if alignment is not None:

                results_by_horizon[
                    forward
                ].append(
                    alignment
                )

                total_evaluated += 1

    print_horizon_summary(
        results_by_horizon
    )

    print(
        "\n"
        "============================================================",
        flush=True
    )

    print(
        f"🎯 Total Evaluated Predictions: "
        f"{total_evaluated}",
        flush=True
    )

    if total_evaluated < 20:

        print(
            "⚠️ العينة التاريخية ما زالت صغيرة، "
            "ولا نعتمد نسبة دقة نهائية حتى نختبر "
            "شركات وفترات أكثر.",
            flush=True
        )

    print(
        "============================================================",
        flush=True
    )


# ============================================================
# التشغيل
# ============================================================

if __name__ == "__main__":

    stock_id = int(
        os.environ.get(
            "STOCK_ID",
            "1"
        )
    )

    run_backtest(
        stock_id
    )
