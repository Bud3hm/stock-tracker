import os
from datetime import datetime, timezone
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


def average(values):

    clean = []

    for value in values:

        value = safe_number(value)

        if value is not None:
            clean.append(value)

    if not clean:
        return None

    return sum(clean) / len(clean)


def growth_rate(current, previous):

    current = safe_number(current)
    previous = safe_number(previous)

    if (
        current is None
        or previous is None
        or previous == 0
    ):
        return None

    return (
        (current - previous)
        / abs(previous)
    ) * 100


# ============================================================
# جلب Financial Metrics
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
# تنظيم البيانات حسب الربع
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
# تحديد الفترات الربعية
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
# حساب Outcome مالي مستقبلي
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

    ocf_growth = growth_rate(
        future_ocf,
        current_ocf
    )

    fcf_growth = growth_rate(
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

        "future_ocf_growth":
            ocf_growth,

        "future_fcf_growth":
            fcf_growth
    }


# ============================================================
# Outcome Score
#
# هذا لا يغيّر Signal Engine
# فقط يقيس ما حدث لاحقًا
# ============================================================

def score_future_outcome(outcome):

    components = []

    revenue_growth = safe_number(
        outcome.get(
            "future_revenue_growth"
        )
    )

    profit_growth = safe_number(
        outcome.get(
            "future_profit_growth"
        )
    )

    margin_change = safe_number(
        outcome.get(
            "future_margin_change"
        )
    )

    ocf_growth = safe_number(
        outcome.get(
            "future_ocf_growth"
        )
    )

    fcf_growth = safe_number(
        outcome.get(
            "future_fcf_growth"
        )
    )

    # --------------------------------------------------------
    # Revenue
    # --------------------------------------------------------

    if revenue_growth is not None:

        if revenue_growth >= 15:
            components.append(80)

        elif revenue_growth >= 5:
            components.append(65)

        elif revenue_growth >= 0:
            components.append(55)

        elif revenue_growth >= -5:
            components.append(40)

        else:
            components.append(20)

    # --------------------------------------------------------
    # Profit
    # أهم من Revenue
    # --------------------------------------------------------

    if profit_growth is not None:

        if profit_growth >= 20:
            components.extend(
                [
                    90,
                    90
                ]
            )

        elif profit_growth >= 8:
            components.extend(
                [
                    75,
                    75
                ]
            )

        elif profit_growth >= 0:
            components.extend(
                [
                    55,
                    55
                ]
            )

        elif profit_growth >= -10:
            components.extend(
                [
                    35,
                    35
                ]
            )

        else:
            components.extend(
                [
                    10,
                    10
                ]
            )

    # --------------------------------------------------------
    # Margin
    # --------------------------------------------------------

    if margin_change is not None:

        if margin_change >= 2:
            components.append(85)

        elif margin_change >= 0.5:
            components.append(70)

        elif margin_change >= 0:
            components.append(55)

        elif margin_change >= -1:
            components.append(40)

        else:
            components.append(20)

    # --------------------------------------------------------
    # OCF
    # --------------------------------------------------------

    if ocf_growth is not None:

        if ocf_growth >= 15:
            components.append(80)

        elif ocf_growth >= 5:
            components.append(65)

        elif ocf_growth >= 0:
            components.append(55)

        elif ocf_growth >= -10:
            components.append(35)

        else:
            components.append(15)

    # --------------------------------------------------------
    # FCF
    # --------------------------------------------------------

    if fcf_growth is not None:

        if fcf_growth >= 15:
            components.append(80)

        elif fcf_growth >= 5:
            components.append(65)

        elif fcf_growth >= 0:
            components.append(55)

        elif fcf_growth >= -10:
            components.append(35)

        else:
            components.append(15)

    return average(
        components
    )


# ============================================================
# تحويل Outcome Score
# ============================================================

def classify_outcome(score):

    score = safe_number(
        score
    )

    if score is None:
        return "NO_DATA"

    if score >= 70:
        return "STRONG_IMPROVEMENT"

    if score >= 58:
        return "IMPROVEMENT"

    if score >= 45:
        return "NEUTRAL"

    if score >= 30:
        return "DETERIORATION"

    return "STRONG_DETERIORATION"


# ============================================================
# هل الإشارة كانت صحيحة؟
# ============================================================

def evaluate_prediction(
    signal_class,
    outcome_class
):

    if signal_class in (
        "NO_SIGNAL",
        "LOW_CONFIDENCE",
        "NEUTRAL"
    ):

        return None

    positive_signal = (
        signal_class
        in (
            "POSITIVE",
            "EARLY_POSITIVE"
        )
    )

    negative_signal = (
        signal_class
        in (
            "NEGATIVE",
            "EARLY_NEGATIVE"
        )
    )

    positive_outcome = (
        outcome_class
        in (
            "STRONG_IMPROVEMENT",
            "IMPROVEMENT"
        )
    )

    negative_outcome = (
        outcome_class
        in (
            "STRONG_DETERIORATION",
            "DETERIORATION"
        )
    )

    if (
        positive_signal
        and positive_outcome
    ):

        return 1

    if (
        negative_signal
        and negative_outcome
    ):

        return 1

    if (
        positive_signal
        and negative_outcome
    ):

        return 0

    if (
        negative_signal
        and positive_outcome
    ):

        return 0

    # Outcome محايد
    return 0.5


# ============================================================
# طباعة اختبار ربع واحد
# ============================================================

def print_backtest_result(
    base_date,
    forward_quarters,
    signal_class,
    net_score,
    confidence,
    outcome,
    outcome_score,
    outcome_class,
    correct
):

    print(
        "\n"
        "------------------------------------------------------------",
        flush=True
    )

    print(
        f"📅 Base Quarter: {base_date}",
        flush=True
    )

    print(
        f"⏩ Forward: "
        f"{forward_quarters} quarter(s)",
        flush=True
    )

    print(
        f"🧠 Signal: {signal_class}",
        flush=True
    )

    print(
        f"⚖️ Net Score: {net_score}",
        flush=True
    )

    print(
        f"🎯 Confidence: {confidence}",
        flush=True
    )

    print(
        f"📊 Future Revenue Growth: "
        f"{outcome['future_revenue_growth']}",
        flush=True
    )

    print(
        f"💰 Future Profit Growth: "
        f"{outcome['future_profit_growth']}",
        flush=True
    )

    print(
        f"📉 Future Margin Change: "
        f"{outcome['future_margin_change']}",
        flush=True
    )

    print(
        f"💵 Future OCF Growth: "
        f"{outcome['future_ocf_growth']}",
        flush=True
    )

    print(
        f"💸 Future FCF Growth: "
        f"{outcome['future_fcf_growth']}",
        flush=True
    )

    print(
        f"📈 Outcome Score: "
        f"{outcome_score}",
        flush=True
    )

    print(
        f"🧭 Outcome: "
        f"{outcome_class}",
        flush=True
    )

    print(
        f"✅ Prediction Result: "
        f"{correct}",
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
        "🧪 BACKTEST ENGINE v1",
        flush=True
    )

    print(
        "============================================================",
        flush=True
    )

    all_results = []

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

        for forward in FORWARD_QUARTERS:

            future_index = (
                index
                + forward
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

            outcome_score = (
                score_future_outcome(
                    outcome
                )
            )

            outcome_class = (
                classify_outcome(
                    outcome_score
                )
            )

            correct = (
                evaluate_prediction(
                    signal_class,
                    outcome_class
                )
            )

            print_backtest_result(
                base_date,
                forward,
                signal_class,
                net_score,
                confidence,
                outcome,
                outcome_score,
                outcome_class,
                correct
            )

            if correct is not None:

                all_results.append(
                    correct
                )

    print(
        "\n"
        "============================================================",
        flush=True
    )

    print(
        "📊 BACKTEST SUMMARY",
        flush=True
    )

    print(
        "============================================================",
        flush=True
    )

    if not all_results:

        print(
            "⚠️ لا توجد إشارات كافية "
            "لحساب دقة تاريخية",
            flush=True
        )

        return

    hit_rate = (
        sum(all_results)
        / len(all_results)
    ) * 100

    print(
        f"🎯 Evaluated Predictions: "
        f"{len(all_results)}",
        flush=True
    )

    print(
        f"✅ Historical Hit Rate: "
        f"{hit_rate:.2f}%",
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
