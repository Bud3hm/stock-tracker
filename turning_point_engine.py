import os
from datetime import datetime, timezone
from supabase import create_client


# ============================================================
# TURNING POINT ENGINE v2.0.1
#
# الهدف:
# - اكتشاف التحول المالي الحقيقي عبر عدة أرباع.
# - التفريق بين Turning Point وبين استمرار القوة.
# - دعم standard / bank / insurance / reit.
# - حساب Rolling History لكل فترة وليس أحدث فترة فقط.
# - حفظ turning_engine_score لكل فترة مؤهلة.
#
# أهم إصلاحات v2.0.1:
# 1) Comparability لا يعاقب المؤشرات التي ظهرت لاحقًا لأنها
#    أصبحت قابلة للحساب لأول مرة.
# 2) فصل Continuity عن Breadth.
# 3) عدم القفز فوق ربع مفقود في delta / acceleration / streak.
# 4) فصل مرشحي Turning عن الشركات المتدهورة في الترتيب.
#
# READ:
#   stocks
#   financial_metrics
#
# WRITE:
#   financial_metrics
#
# Prefix:
#   turning_engine_
#
# ملاحظة:
# turning_engine_score يبقى بنفس الاسم القديم حتى لا تنكسر
# المحركات الحالية التي تعتمد عليه.
# ============================================================


# ============================================================
# Supabase
# ============================================================

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_SECRET_KEY = os.environ.get("SUPABASE_SECRET_KEY")

if not SUPABASE_URL:
    raise RuntimeError("SUPABASE_URL is missing")

if not SUPABASE_SECRET_KEY:
    raise RuntimeError("SUPABASE_SECRET_KEY is missing")

supabase = create_client(
    SUPABASE_URL,
    SUPABASE_SECRET_KEY
)


# ============================================================
# Settings
# ============================================================

ENGINE_VERSION = "2.0.1"

MIN_HISTORY = 2
PREFERRED_HISTORY = 4

MIN_CONFIDENCE_FOR_DIRECTION = 55.0
MIN_COMPARABILITY_FOR_DIRECTION = 50.0
MIN_COMMON_INPUTS_FOR_DIRECTION = 3

TURNING_SCORE_METRIC = "turning_engine_score"
TURNING_PREFIX = "turning_engine_"

MODEL_PREFIX = {
    "standard": "q_",
    "bank": "bank_q_",
    "insurance": "insurance_q_",
    "reit": "reit_q_"
}

MODEL_CONFIDENCE_METRIC = {
    "standard": "data_confidence_score",
    "bank": "bank_data_confidence_score",
    "insurance": "insurance_data_confidence_score",
    "reit": "reit_data_confidence_score"
}

MODEL_SIGNAL_PREFIX = {
    "standard": "engine22_",
    "bank": "bank_signal_",
    "insurance": "insurance_signal_",
    "reit": "engine22_"
}

STATE_CODE = {
    "LOW_CONFIDENCE": 0,
    "WEAK": 1,
    "DETERIORATING": 2,
    "NEUTRAL": 3,
    "IMPROVING": 4,
    "EARLY_TURNING_POINT": 5,
    "STRONG_TURNING_POINT": 6,
    "STRONG_CONTINUATION": 7
}


# ============================================================
# Helpers
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


def fmt(
    value,
    decimals=2
):

    value = safe_number(value)

    if value is None:
        return "N/A"

    return f"{value:.{decimals}f}"


def signed_fmt(
    value,
    decimals=2
):

    value = safe_number(value)

    if value is None:
        return "N/A"

    return f"{value:+.{decimals}f}"


def average(values):

    cleaned = []

    for value in values:

        value = safe_number(value)

        if value is not None:
            cleaned.append(value)

    if not cleaned:
        return None

    return sum(cleaned) / len(cleaned)


def print_header(title):

    print(
        "\n" + "=" * 96,
        flush=True
    )

    print(
        title,
        flush=True
    )

    print(
        "=" * 96,
        flush=True
    )


def print_separator():

    print(
        "-" * 96,
        flush=True
    )


# ============================================================
# Supabase Reads
# ============================================================

def get_active_stocks():

    response = (
        supabase
        .table("stocks")
        .select(
            "id,"
            "symbol,"
            "company_name,"
            "sector,"
            "analysis_model,"
            "priority,"
            "data_status,"
            "is_active"
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
# Organize Metrics
# ============================================================

def organize_metrics(rows):

    periods = {}

    for row in rows:

        period_end = row.get("period_end")
        metric_name = row.get("metric_name")
        metric_value = safe_number(
            row.get("metric_value")
        )

        if (
            not period_end
            or not metric_name
            or metric_value is None
        ):
            continue

        period_end = str(period_end)

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
# Valid Financial Periods
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

        period_metrics = periods[
            period_end
        ]

        if any(
            metric_name.startswith(prefix)
            for metric_name in period_metrics
        ):
            valid.append(period_end)

    return valid


# ============================================================
# Series Helpers
# ============================================================

def metric_series(
    history,
    metric_name
):

    return [
        safe_number(
            period_metrics.get(metric_name)
        )
        for period_metrics in history
    ]


def analyze_series(values):
    """
    v2.0.1:
    لا نحذف None من السلسلة.
    latest = قيمة الفترة الحالية فقط.
    previous = الفترة السابقة مباشرة فقط.
    acceleration = آخر 3 فترات متجاورة فقط.
    streak ينقطع عند أي فجوة بيانات.
    """

    values = [
        safe_number(value)
        for value in values
    ]

    result = {
        "latest": None,
        "previous": None,
        "delta": None,
        "acceleration": None,
        "positive_streak": 0,
        "negative_streak": 0,
        "rising_steps": 0,
        "falling_steps": 0,
        "count": sum(
            value is not None
            for value in values
        )
    }

    if not values:
        return result

    latest = values[-1]

    if latest is None:
        return result

    result["latest"] = latest

    if (
        len(values) >= 2
        and values[-2] is not None
    ):

        previous = values[-2]

        result["previous"] = previous

        result["delta"] = (
            latest
            - previous
        )

    if (
        len(values) >= 3
        and values[-2] is not None
        and values[-3] is not None
    ):

        previous_delta = (
            values[-2]
            - values[-3]
        )

        current_delta = (
            values[-1]
            - values[-2]
        )

        result["acceleration"] = (
            current_delta
            - previous_delta
        )

    positive_streak = 0

    for value in reversed(values):

        if value is None:
            break

        if value > 0:
            positive_streak += 1
        else:
            break

    negative_streak = 0

    for value in reversed(values):

        if value is None:
            break

        if value < 0:
            negative_streak += 1
        else:
            break

    rising_steps = 0
    falling_steps = 0

    for index in range(
        1,
        len(values)
    ):

        previous_value = values[
            index - 1
        ]

        current_value = values[
            index
        ]

        if (
            previous_value is None
            or current_value is None
        ):
            continue

        if current_value > previous_value:
            rising_steps += 1

        elif current_value < previous_value:
            falling_steps += 1

    result["positive_streak"] = positive_streak
    result["negative_streak"] = negative_streak
    result["rising_steps"] = rising_steps
    result["falling_steps"] = falling_steps

    return result


# ============================================================
# Signal State
# ============================================================

def new_signals():

    return {
        "reversal": 0.0,
        "momentum": 0.0,
        "acceleration": 0.0,
        "persistence": 0.0,
        "quality": 0.0,
        "cash": 0.0,
        "balance": 0.0,
        "current_strength": 0.0,
        "score_momentum": 0.0,
        "signal_confirmation": 0.0,
        "deterioration": 0.0
    }


def add_signal(
    signals,
    reasons,
    category,
    points,
    reason
):

    points = safe_number(points)

    if points is None:
        return

    signals[
        category
    ] = (
        safe_number(
            signals.get(
                category
            )
        )
        or 0.0
    ) + points

    reasons.append(
        {
            "category": category,
            "points": points,
            "reason": reason
        }
    )


# ============================================================
# Growth Metric Evaluation
# ============================================================

def evaluate_growth_metric(
    history,
    metric_name,
    label,
    signals,
    reasons,
    weight=1.0
):

    trend = analyze_series(
        metric_series(
            history,
            metric_name
        )
    )

    latest = trend["latest"]
    previous = trend["previous"]
    delta = trend["delta"]
    acceleration = trend["acceleration"]

    if latest is None:
        return

    if (
        previous is not None
        and previous < 0
        and latest > 0
    ):

        add_signal(
            signals,
            reasons,
            "reversal",
            12 * weight,
            f"{label}: تحول من انكماش إلى نمو"
        )

    if latest >= 15:

        add_signal(
            signals,
            reasons,
            "current_strength",
            6 * weight,
            f"{label}: نمو حالي قوي "
            f"({signed_fmt(latest)}%)"
        )

    elif latest >= 5:

        add_signal(
            signals,
            reasons,
            "current_strength",
            3 * weight,
            f"{label}: نمو حالي إيجابي "
            f"({signed_fmt(latest)}%)"
        )

    if (
        delta is not None
        and delta >= 10
    ):

        add_signal(
            signals,
            reasons,
            "momentum",
            6 * weight,
            f"{label}: تحسن واضح في الزخم "
            f"({signed_fmt(delta)} نقطة)"
        )

    elif (
        delta is not None
        and delta >= 3
    ):

        add_signal(
            signals,
            reasons,
            "momentum",
            3 * weight,
            f"{label}: الزخم يتحسن"
        )

    if (
        acceleration is not None
        and acceleration >= 5
    ):

        add_signal(
            signals,
            reasons,
            "acceleration",
            4 * weight,
            f"{label}: يوجد تسارع في التحسن"
        )

    if trend["positive_streak"] >= 2:

        add_signal(
            signals,
            reasons,
            "persistence",
            4 * weight,
            f"{label}: نمو إيجابي مستمر "
            f"{trend['positive_streak']} فترات"
        )

    if latest <= -10:

        add_signal(
            signals,
            reasons,
            "deterioration",
            -7 * weight,
            f"{label}: تراجع حالي قوي "
            f"({signed_fmt(latest)}%)"
        )

    if (
        delta is not None
        and delta <= -10
    ):

        add_signal(
            signals,
            reasons,
            "deterioration",
            -5 * weight,
            f"{label}: الزخم يتدهور"
        )


# ============================================================
# Margin Metric Evaluation
# ============================================================

def evaluate_margin_metric(
    history,
    metric_name,
    label,
    signals,
    reasons,
    weight=1.0
):

    trend = analyze_series(
        metric_series(
            history,
            metric_name
        )
    )

    latest = trend["latest"]
    previous = trend["previous"]
    delta = trend["delta"]

    if latest is None:
        return

    if (
        previous is not None
        and previous < 0
        and latest > 0
    ):

        add_signal(
            signals,
            reasons,
            "reversal",
            10 * weight,
            f"{label}: تحول من انكماش الهامش "
            f"إلى توسعه"
        )

    if latest >= 2:

        add_signal(
            signals,
            reasons,
            "quality",
            6 * weight,
            f"{label}: تحسن قوي "
            f"({signed_fmt(latest)} نقطة)"
        )

    elif latest > 0:

        add_signal(
            signals,
            reasons,
            "quality",
            3 * weight,
            f"{label}: يتحسن"
        )

    if (
        delta is not None
        and delta >= 2
    ):

        add_signal(
            signals,
            reasons,
            "momentum",
            3 * weight,
            f"{label}: اتجاه التحسن يتسارع"
        )

    if latest <= -2:

        add_signal(
            signals,
            reasons,
            "deterioration",
            -6 * weight,
            f"{label}: يتآكل "
            f"({signed_fmt(latest)} نقطة)"
        )


# ============================================================
# Standard Model
# ============================================================

def evaluate_standard(history):

    signals = new_signals()
    reasons = []

    evaluate_growth_metric(
        history,
        "q_revenue_growth_yoy",
        "الإيرادات",
        signals,
        reasons,
        1.0
    )

    evaluate_growth_metric(
        history,
        "q_net_income_growth_yoy",
        "صافي الربح",
        signals,
        reasons,
        1.25
    )

    evaluate_growth_metric(
        history,
        "q_ocf_growth_yoy",
        "التدفق التشغيلي",
        signals,
        reasons,
        0.80
    )

    evaluate_growth_metric(
        history,
        "q_fcf_growth_yoy",
        "التدفق النقدي الحر",
        signals,
        reasons,
        0.85
    )

    evaluate_margin_metric(
        history,
        "q_gross_margin_change_yoy",
        "الهامش الإجمالي",
        signals,
        reasons,
        0.75
    )

    evaluate_margin_metric(
        history,
        "q_operating_margin_change_yoy",
        "الهامش التشغيلي",
        signals,
        reasons,
        1.0
    )

    evaluate_margin_metric(
        history,
        "q_net_margin_change_yoy",
        "هامش صافي الربح",
        signals,
        reasons,
        1.0
    )

    latest = history[-1]

    cash_conversion = safe_number(
        latest.get("q_cash_conversion")
    )

    if cash_conversion is not None:

        if cash_conversion >= 1:

            add_signal(
                signals,
                reasons,
                "cash",
                6,
                "تحويل الأرباح إلى نقد جيد"
            )

        elif cash_conversion < 0.70:

            add_signal(
                signals,
                reasons,
                "deterioration",
                -6,
                "تحويل الأرباح إلى نقد ضعيف"
            )

    debt_growth = safe_number(
        latest.get("q_debt_growth_qoq")
    )

    if debt_growth is not None:

        if debt_growth <= -5:

            add_signal(
                signals,
                reasons,
                "balance",
                5,
                "المديونية تنخفض"
            )

        elif debt_growth >= 15:

            add_signal(
                signals,
                reasons,
                "deterioration",
                -5,
                "المديونية ترتفع بسرعة"
            )

    current_ratio = safe_number(
        latest.get("q_current_ratio")
    )

    if (
        current_ratio is not None
        and current_ratio >= 1
    ):

        add_signal(
            signals,
            reasons,
            "balance",
            3,
            "السيولة الجارية مقبولة"
        )

    return signals, reasons


# ============================================================
# Bank Model
# ============================================================

def evaluate_bank(history):

    signals = new_signals()
    reasons = []

    evaluate_growth_metric(
        history,
        "bank_q_revenue_growth_yoy",
        "دخل البنك",
        signals,
        reasons,
        1.0
    )

    evaluate_growth_metric(
        history,
        "bank_q_net_income_growth_yoy",
        "صافي ربح البنك",
        signals,
        reasons,
        1.30
    )

    evaluate_growth_metric(
        history,
        "bank_q_assets_growth_yoy",
        "الأصول",
        signals,
        reasons,
        0.65
    )

    evaluate_growth_metric(
        history,
        "bank_q_equity_growth_yoy",
        "حقوق المساهمين",
        signals,
        reasons,
        0.70
    )

    evaluate_margin_metric(
        history,
        "bank_q_profit_margin_change_yoy",
        "هامش ربح البنك",
        signals,
        reasons,
        1.0
    )

    latest = history[-1]

    roe = safe_number(
        latest.get("bank_ttm_roe")
    )

    if roe is not None:

        if roe >= 15:

            add_signal(
                signals,
                reasons,
                "quality",
                7,
                f"ROE قوي ({fmt(roe)}%)"
            )

        elif roe < 10:

            add_signal(
                signals,
                reasons,
                "deterioration",
                -5,
                f"ROE منخفض ({fmt(roe)}%)"
            )

    equity_assets = safe_number(
        latest.get(
            "bank_q_equity_to_assets"
        )
    )

    if equity_assets is not None:

        if equity_assets >= 10:

            add_signal(
                signals,
                reasons,
                "balance",
                5,
                "قاعدة حقوق المساهمين جيدة"
            )

        elif equity_assets < 7:

            add_signal(
                signals,
                reasons,
                "deterioration",
                -5,
                "حقوق المساهمين إلى الأصول منخفضة"
            )

    return signals, reasons


# ============================================================
# Insurance Model
# ============================================================

def evaluate_insurance(history):

    signals = new_signals()
    reasons = []

    evaluate_growth_metric(
        history,
        "insurance_q_revenue_growth_yoy",
        "إيرادات التأمين",
        signals,
        reasons,
        1.0
    )

    evaluate_growth_metric(
        history,
        "insurance_q_net_income_growth_yoy",
        "صافي ربح التأمين",
        signals,
        reasons,
        1.25
    )

    evaluate_growth_metric(
        history,
        "insurance_q_equity_growth_yoy",
        "حقوق المساهمين",
        signals,
        reasons,
        0.65
    )

    evaluate_growth_metric(
        history,
        "insurance_q_eps_growth_yoy",
        "ربحية السهم",
        signals,
        reasons,
        0.80
    )

    evaluate_margin_metric(
        history,
        "insurance_q_profit_margin_change_yoy",
        "هامش الربح",
        signals,
        reasons,
        1.0
    )

    latest = history[-1]

    roe = safe_number(
        latest.get("insurance_ttm_roe")
    )

    if roe is not None:

        if roe >= 15:

            add_signal(
                signals,
                reasons,
                "quality",
                7,
                f"ROE قوي ({fmt(roe)}%)"
            )

        elif roe < 8:

            add_signal(
                signals,
                reasons,
                "deterioration",
                -5,
                f"ROE ضعيف ({fmt(roe)}%)"
            )

    cash_conversion = safe_number(
        latest.get(
            "insurance_ttm_cash_conversion"
        )
    )

    if cash_conversion is not None:

        if cash_conversion >= 1:

            add_signal(
                signals,
                reasons,
                "cash",
                5,
                "التدفقات تدعم الأرباح"
            )

        elif cash_conversion < 0.50:

            add_signal(
                signals,
                reasons,
                "deterioration",
                -5,
                "جودة التدفقات ضعيفة"
            )

    return signals, reasons


# ============================================================
# REIT Model
# ============================================================

def evaluate_reit(history):

    signals = new_signals()
    reasons = []

    evaluate_growth_metric(
        history,
        "reit_q_revenue_growth_yoy",
        "إيرادات الريت",
        signals,
        reasons,
        1.0
    )

    evaluate_growth_metric(
        history,
        "reit_q_operating_income_growth_yoy",
        "الدخل التشغيلي",
        signals,
        reasons,
        1.15
    )

    evaluate_growth_metric(
        history,
        "reit_q_net_income_growth_yoy",
        "صافي الربح",
        signals,
        reasons,
        0.90
    )

    evaluate_margin_metric(
        history,
        "reit_q_operating_margin_change_yoy",
        "الهامش التشغيلي",
        signals,
        reasons,
        1.0
    )

    evaluate_margin_metric(
        history,
        "reit_q_net_margin_change_yoy",
        "هامش صافي الربح",
        signals,
        reasons,
        0.80
    )

    latest = history[-1]

    debt_assets = safe_number(
        latest.get("reit_q_debt_to_assets")
    )

    if debt_assets is not None:

        if debt_assets <= 35:

            add_signal(
                signals,
                reasons,
                "balance",
                5,
                "المديونية إلى الأصول مقبولة"
            )

        elif debt_assets >= 50:

            add_signal(
                signals,
                reasons,
                "deterioration",
                -6,
                "المديونية إلى الأصول مرتفعة"
            )

    cash_conversion = safe_number(
        latest.get(
            "reit_ttm_cash_conversion"
        )
    )

    if cash_conversion is not None:

        if cash_conversion >= 1:

            add_signal(
                signals,
                reasons,
                "cash",
                5,
                "التدفقات تدعم الأرباح"
            )

        elif cash_conversion < 0.60:

            add_signal(
                signals,
                reasons,
                "deterioration",
                -5,
                "جودة التدفقات ضعيفة"
            )

    return signals, reasons


# ============================================================
# Model Router
# ============================================================

def evaluate_model(
    analysis_model,
    history
):

    if analysis_model == "standard":
        return evaluate_standard(history)

    if analysis_model == "bank":
        return evaluate_bank(history)

    if analysis_model == "insurance":
        return evaluate_insurance(history)

    if analysis_model == "reit":
        return evaluate_reit(history)

    return None, None


# ============================================================
# Scoring History Confirmation
# ============================================================

def evaluate_score_history(history):

    signals = {
        "score_momentum": 0.0
    }

    reasons = []

    opportunity = analyze_series(
        metric_series(
            history,
            "score_opportunity_score"
        )
    )

    risk = analyze_series(
        metric_series(
            history,
            "score_risk_score"
        )
    )

    base_turning = analyze_series(
        metric_series(
            history,
            "score_turning_point_score"
        )
    )

    if (
        opportunity["delta"] is not None
        and opportunity["delta"] >= 5
    ):

        add_signal(
            signals,
            reasons,
            "score_momentum",
            6,
            "Opportunity Score يتحسن "
            f"({signed_fmt(opportunity['delta'])})"
        )

    if (
        risk["delta"] is not None
        and risk["delta"] <= -5
    ):

        add_signal(
            signals,
            reasons,
            "score_momentum",
            6,
            "Risk Score ينخفض "
            f"({signed_fmt(risk['delta'])})"
        )

    if (
        base_turning["delta"] is not None
        and base_turning["delta"] >= 5
    ):

        add_signal(
            signals,
            reasons,
            "score_momentum",
            7,
            "Base Turning Score يتحسن "
            f"({signed_fmt(base_turning['delta'])})"
        )

    if (
        opportunity["delta"] is not None
        and opportunity["delta"] <= -10
    ):

        add_signal(
            signals,
            reasons,
            "score_momentum",
            -5,
            "Opportunity Score يتراجع "
            f"({signed_fmt(opportunity['delta'])})"
        )

    if (
        risk["delta"] is not None
        and risk["delta"] >= 10
    ):

        add_signal(
            signals,
            reasons,
            "score_momentum",
            -6,
            "Risk Score يرتفع "
            f"({signed_fmt(risk['delta'])})"
        )

    return signals, reasons


# ============================================================
# Specialized Signal Engine Confirmation
# ============================================================

def evaluate_signal_confirmation(
    history,
    analysis_model
):

    signals = {
        "signal_confirmation": 0.0
    }

    reasons = []

    prefix = MODEL_SIGNAL_PREFIX.get(
        analysis_model
    )

    if not prefix:
        return signals, reasons

    net_metric = (
        f"{prefix}net_score"
    )

    confidence_metric = (
        f"{prefix}confidence_score"
    )

    net_trend = analyze_series(
        metric_series(
            history,
            net_metric
        )
    )

    latest_net = net_trend["latest"]
    net_delta = net_trend["delta"]

    latest_confidence = safe_number(
        history[-1].get(
            confidence_metric
        )
    )

    if (
        latest_confidence is not None
        and latest_confidence < 55
    ):
        return signals, reasons

    if (
        latest_net is not None
        and latest_net >= 20
    ):

        add_signal(
            signals,
            reasons,
            "signal_confirmation",
            5,
            "Signal Engine يؤكد تحسنًا ماليًا"
        )

    elif (
        latest_net is not None
        and latest_net <= -20
    ):

        add_signal(
            signals,
            reasons,
            "signal_confirmation",
            -5,
            "Signal Engine يؤكد تدهورًا ماليًا"
        )

    if (
        net_delta is not None
        and net_delta >= 12
    ):

        add_signal(
            signals,
            reasons,
            "signal_confirmation",
            5,
            "Signal Engine نفسه يتحسن بوضوح"
        )

    elif (
        net_delta is not None
        and net_delta <= -12
    ):

        add_signal(
            signals,
            reasons,
            "signal_confirmation",
            -5,
            "Signal Engine نفسه يتراجع بوضوح"
        )

    return signals, reasons


# ============================================================
# Historical Data Confidence
# ============================================================

def history_confidence(
    history,
    analysis_model
):

    if not history:
        return 0.0

    history_score = min(
        len(history)
        / PREFERRED_HISTORY,
        1.0
    ) * 50

    confidence_metric = (
        MODEL_CONFIDENCE_METRIC.get(
            analysis_model
        )
    )

    confidence_values = []

    if confidence_metric:

        for period_metrics in history:

            value = safe_number(
                period_metrics.get(
                    confidence_metric
                )
            )

            if value is not None:
                confidence_values.append(value)

    if not confidence_values:

        for period_metrics in history:

            value = safe_number(
                period_metrics.get(
                    "score_confidence_score"
                )
            )

            if value is not None:
                confidence_values.append(value)

    data_confidence = average(
        confidence_values
    )

    if data_confidence is None:
        data_confidence = 50.0

    data_score = (
        clamp(data_confidence)
        / 100
    ) * 50

    return clamp(
        history_score
        + data_score
    )


# ============================================================
# Financial Comparability
# ============================================================

def model_watchlist(
    analysis_model
):

    if analysis_model == "standard":

        return [
            "q_revenue_growth_yoy",
            "q_net_income_growth_yoy",
            "q_ocf_growth_yoy",
            "q_fcf_growth_yoy",
            "q_gross_margin_change_yoy",
            "q_operating_margin_change_yoy",
            "q_net_margin_change_yoy",
            "q_cash_conversion",
            "q_debt_growth_qoq",
            "q_current_ratio"
        ]

    if analysis_model == "bank":

        return [
            "bank_q_revenue_growth_yoy",
            "bank_q_net_income_growth_yoy",
            "bank_q_assets_growth_yoy",
            "bank_q_equity_growth_yoy",
            "bank_q_profit_margin_change_yoy",
            "bank_ttm_roe",
            "bank_ttm_roa",
            "bank_q_equity_to_assets"
        ]

    if analysis_model == "insurance":

        return [
            "insurance_q_revenue_growth_yoy",
            "insurance_q_net_income_growth_yoy",
            "insurance_q_equity_growth_yoy",
            "insurance_q_eps_growth_yoy",
            "insurance_q_profit_margin_change_yoy",
            "insurance_ttm_roe",
            "insurance_ttm_roa",
            "insurance_ttm_cash_conversion"
        ]

    if analysis_model == "reit":

        return [
            "reit_q_revenue_growth_yoy",
            "reit_q_operating_income_growth_yoy",
            "reit_q_net_income_growth_yoy",
            "reit_q_operating_margin_change_yoy",
            "reit_q_net_margin_change_yoy",
            "reit_q_debt_to_assets",
            "reit_ttm_cash_conversion"
        ]

    return []


def financial_comparability(
    history,
    analysis_model
):
    """
    v2.0.1

    continuity_score:
        هل المؤشرات التي كانت متاحة في الربع السابق استمرت
        إلى الربع الحالي؟

    breadth_score:
        كم نسبة المؤشرات المتوقعة التي يمكن مقارنتها فعليًا
        في الربعين؟

    newly_available:
        مؤشرات ظهرت الآن ولم تكن متاحة سابقًا.
        لا تعتبر مشكلة ولا تخفض continuity.

    dropped:
        مؤشرات كانت متاحة سابقًا ثم اختفت الآن.
        هذه مشكلة حقيقية وتخفض continuity.
    """

    watched = model_watchlist(
        analysis_model
    )

    if (
        len(history) < 2
        or not watched
    ):

        return {
            "score": 0.0,
            "continuity_score": 0.0,
            "breadth_score": 0.0,
            "latest_inputs": 0,
            "previous_inputs": 0,
            "common_inputs": 0,
            "newly_available_inputs": 0,
            "dropped_inputs": 0,
            "union_inputs": 0,
            "watched_inputs": len(watched),
            "direction_ready": False
        }

    latest = history[-1]
    previous = history[-2]

    latest_available = {
        metric_name
        for metric_name in watched
        if safe_number(
            latest.get(metric_name)
        ) is not None
    }

    previous_available = {
        metric_name
        for metric_name in watched
        if safe_number(
            previous.get(metric_name)
        ) is not None
    }

    common = (
        latest_available
        & previous_available
    )

    newly_available = (
        latest_available
        - previous_available
    )

    dropped = (
        previous_available
        - latest_available
    )

    union = (
        latest_available
        | previous_available
    )

    if previous_available:

        continuity_score = (
            len(common)
            / len(previous_available)
        ) * 100

    elif latest_available:

        # أول فترة تصبح فيها المقاييس قابلة للحساب.
        # ليست مقارنة تاريخية كاملة، لكن لا نعاقبها كـ 0.
        continuity_score = 70.0

    else:

        continuity_score = 0.0

    breadth_score = (
        len(common)
        / len(watched)
    ) * 100

    # score الأساسي يركز على الاستمرارية لا على عدد المؤشرات
    # الجديدة التي ظهرت للتو.
    score = continuity_score

    direction_ready = (
        score
        >= MIN_COMPARABILITY_FOR_DIRECTION
        and len(common)
        >= MIN_COMMON_INPUTS_FOR_DIRECTION
    )

    return {
        "score": clamp(score),
        "continuity_score":
            clamp(continuity_score),
        "breadth_score":
            clamp(breadth_score),
        "latest_inputs":
            len(latest_available),
        "previous_inputs":
            len(previous_available),
        "common_inputs":
            len(common),
        "newly_available_inputs":
            len(newly_available),
        "dropped_inputs":
            len(dropped),
        "union_inputs":
            len(union),
        "watched_inputs":
            len(watched),
        "direction_ready":
            direction_ready
    }


# ============================================================
# Current Strength / Baseline
# ============================================================

def get_current_context(history):

    latest = history[-1]

    opportunity = safe_number(
        latest.get(
            "score_opportunity_score"
        )
    )

    risk = safe_number(
        latest.get(
            "score_risk_score"
        )
    )

    base_turning = safe_number(
        latest.get(
            "score_turning_point_score"
        )
    )

    previous_opportunity = None
    previous_risk = None
    previous_base_turning = None

    if len(history) >= 2:

        previous = history[-2]

        previous_opportunity = safe_number(
            previous.get(
                "score_opportunity_score"
            )
        )

        previous_risk = safe_number(
            previous.get(
                "score_risk_score"
            )
        )

        previous_base_turning = safe_number(
            previous.get(
                "score_turning_point_score"
            )
        )

    return {
        "opportunity": opportunity,
        "risk": risk,
        "base_turning": base_turning,
        "previous_opportunity":
            previous_opportunity,
        "previous_risk":
            previous_risk,
        "previous_base_turning":
            previous_base_turning
    }


# ============================================================
# Turning Score
# ============================================================

def calculate_turning_score(
    signals,
    confidence,
    comparability
):

    positive_categories = [
        "reversal",
        "momentum",
        "acceleration",
        "persistence",
        "quality",
        "cash",
        "balance",
        "current_strength",
        "score_momentum",
        "signal_confirmation"
    ]

    positive_points = sum(
        max(
            0,
            safe_number(
                signals.get(category)
            )
            or 0.0
        )
        for category in positive_categories
    )

    negative_points = 0.0

    for category in [
        "deterioration",
        "score_momentum",
        "signal_confirmation"
    ]:

        value = (
            safe_number(
                signals.get(category)
            )
            or 0.0
        )

        if value < 0:
            negative_points += abs(value)

    raw_score = (
        25
        + positive_points
        - negative_points
    )

    raw_score = clamp(
        raw_score
    )

    confidence = (
        clamp(confidence)
        or 0.0
    )

    comparability = (
        clamp(comparability)
        or 0.0
    )

    quality_factor = (
        0.45
        + (
            confidence
            / 100
        ) * 0.35
        + (
            comparability
            / 100
        ) * 0.20
    )

    final_score = (
        raw_score
        * quality_factor
    )

    return clamp(
        final_score
    )


# ============================================================
# Turning Classification
# ============================================================

def classify_turning_point(
    score,
    signals,
    confidence,
    comparability,
    context
):

    score = safe_number(score)
    confidence = safe_number(confidence)

    comparability_score = safe_number(
        comparability.get("score")
    )

    common_inputs = (
        comparability.get(
            "common_inputs",
            0
        )
        or 0
    )

    reversal = (
        safe_number(
            signals.get("reversal")
        )
        or 0.0
    )

    momentum = (
        safe_number(
            signals.get("momentum")
        )
        or 0.0
    )

    acceleration = (
        safe_number(
            signals.get("acceleration")
        )
        or 0.0
    )

    persistence = (
        safe_number(
            signals.get("persistence")
        )
        or 0.0
    )

    score_momentum = (
        safe_number(
            signals.get("score_momentum")
        )
        or 0.0
    )

    signal_confirmation = (
        safe_number(
            signals.get("signal_confirmation")
        )
        or 0.0
    )

    deterioration = abs(
        min(
            safe_number(
                signals.get("deterioration")
            )
            or 0.0,
            0.0
        )
    )

    previous_opportunity = safe_number(
        context.get(
            "previous_opportunity"
        )
    )

    previous_risk = safe_number(
        context.get(
            "previous_risk"
        )
    )

    gate_failures = []

    if (
        confidence is None
        or confidence
        < MIN_CONFIDENCE_FOR_DIRECTION
    ):
        gate_failures.append(
            f"Confidence {fmt(confidence)}"
        )

    if (
        comparability_score is None
        or comparability_score
        < MIN_COMPARABILITY_FOR_DIRECTION
    ):
        gate_failures.append(
            f"Comparability "
            f"{fmt(comparability_score)}"
        )

    if (
        common_inputs
        < MIN_COMMON_INPUTS_FOR_DIRECTION
    ):
        gate_failures.append(
            f"CommonInputs "
            f"{common_inputs}"
            f"<{MIN_COMMON_INPUTS_FOR_DIRECTION}"
        )

    if gate_failures:

        return (
            "LOW_CONFIDENCE",
            "لا يصدر حكم Turning قوي بسبب: "
            + " | ".join(gate_failures)
        )

    already_strong = (
        previous_opportunity is not None
        and previous_opportunity >= 70
        and (
            previous_risk is None
            or previous_risk <= 35
        )
    )

    if (
        already_strong
        and score is not None
        and score >= 75
        and deterioration < 12
    ):

        return (
            "STRONG_CONTINUATION",
            "قوة مستمرة؛ الشركة كانت قوية أصلًا "
            "وليست Turning Point جديدة"
        )

    baseline_was_weak_or_mixed = (
        previous_opportunity is None
        or previous_opportunity < 65
        or (
            previous_risk is not None
            and previous_risk > 45
        )
    )

    turning_evidence = (
        reversal >= 8
        or score_momentum >= 10
        or signal_confirmation >= 5
    )

    momentum_evidence = (
        momentum > 0
        or acceleration > 0
        or persistence > 0
    )

    if (
        score is not None
        and score >= 80
        and baseline_was_weak_or_mixed
        and turning_evidence
        and momentum_evidence
        and deterioration < 15
    ):

        return (
            "STRONG_TURNING_POINT",
            "تحول مالي قوي ومتعدد الإشارات"
        )

    if (
        score is not None
        and score >= 65
        and baseline_was_weak_or_mixed
        and turning_evidence
        and deterioration < 18
    ):

        return (
            "EARLY_TURNING_POINT",
            "بوادر تحول مالي حقيقية "
            "من قاعدة أضعف"
        )

    if (
        score is not None
        and score >= 55
        and (
            momentum > 0
            or persistence > 0
            or score_momentum > 0
        )
        and deterioration < 18
    ):

        return (
            "IMPROVING",
            "تحسن مستمر لكنه لا يحقق شروط "
            "Turning Point الحقيقي"
        )

    if deterioration >= 15:

        return (
            "DETERIORATING",
            "عدة مؤشرات مالية تتدهور"
        )

    if (
        score is not None
        and score < 40
    ):

        return (
            "WEAK",
            "لا توجد إشارات تحول إيجابي كافية"
        )

    return (
        "NEUTRAL",
        "لا يوجد تحول واضح حتى الآن"
    )


# ============================================================
# Save Metrics
# ============================================================

def save_turning_metrics(
    stock_id,
    period_end,
    values
):

    calculated_at = datetime.now(
        timezone.utc
    ).isoformat()

    records = []

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
                "stock_id": stock_id,
                "calculated_at": calculated_at,
                "metric_name": metric_name,
                "metric_value": metric_value,
                "period_end": period_end
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

    return len(records)


# ============================================================
# Evaluate One Rolling Period
# ============================================================

def evaluate_period(
    stock_id,
    analysis_model,
    periods,
    valid_periods,
    target_index
):

    selected_periods = valid_periods[
        max(
            0,
            target_index
            - PREFERRED_HISTORY
            + 1
        ):
        target_index
        + 1
    ]

    history = [
        periods[
            period_end
        ]
        for period_end in selected_periods
    ]

    if len(history) < MIN_HISTORY:

        return {
            "status": "insufficient_history",
            "period_end":
                valid_periods[target_index],
            "history_count":
                len(history)
        }

    model_signals, model_reasons = (
        evaluate_model(
            analysis_model,
            history
        )
    )

    if model_signals is None:

        return {
            "status": "unsupported_model",
            "period_end":
                valid_periods[target_index],
            "history_count":
                len(history)
        }

    score_signals, score_reasons = (
        evaluate_score_history(
            history
        )
    )

    signal_signals, signal_reasons = (
        evaluate_signal_confirmation(
            history,
            analysis_model
        )
    )

    signals = dict(
        model_signals
    )

    reasons = list(
        model_reasons
    )

    for signal_block, reason_block in [
        (
            score_signals,
            score_reasons
        ),
        (
            signal_signals,
            signal_reasons
        )
    ]:

        for key, value in (
            signal_block.items()
        ):

            signals[
                key
            ] = (
                safe_number(
                    signals.get(key)
                )
                or 0.0
            ) + (
                safe_number(value)
                or 0.0
            )

        reasons.extend(
            reason_block
        )

    confidence = history_confidence(
        history,
        analysis_model
    )

    comparability = financial_comparability(
        history,
        analysis_model
    )

    context = get_current_context(
        history
    )

    turning_score = calculate_turning_score(
        signals,
        confidence,
        comparability["score"]
    )

    state, description = (
        classify_turning_point(
            turning_score,
            signals,
            confidence,
            comparability,
            context
        )
    )

    latest_period = (
        selected_periods[-1]
    )

    positive_reasons = [
        reason
        for reason in reasons
        if safe_number(
            reason.get("points")
        ) is not None
        and safe_number(
            reason.get("points")
        ) > 0
    ]

    negative_reasons = [
        reason
        for reason in reasons
        if safe_number(
            reason.get("points")
        ) is not None
        and safe_number(
            reason.get("points")
        ) < 0
    ]

    positive_reasons.sort(
        key=lambda item:
            item["points"],
        reverse=True
    )

    negative_reasons.sort(
        key=lambda item:
            item["points"]
    )

    save_values = {
        TURNING_SCORE_METRIC:
            turning_score,

        f"{TURNING_PREFIX}confidence_score":
            confidence,

        f"{TURNING_PREFIX}comparability_score":
            comparability["score"],

        f"{TURNING_PREFIX}comparability_continuity_score":
            comparability[
                "continuity_score"
            ],

        f"{TURNING_PREFIX}comparability_breadth_score":
            comparability[
                "breadth_score"
            ],

        f"{TURNING_PREFIX}common_inputs":
            comparability[
                "common_inputs"
            ],

        f"{TURNING_PREFIX}newly_available_inputs":
            comparability[
                "newly_available_inputs"
            ],

        f"{TURNING_PREFIX}dropped_inputs":
            comparability[
                "dropped_inputs"
            ],

        f"{TURNING_PREFIX}reversal_score":
            signals.get("reversal"),

        f"{TURNING_PREFIX}momentum_score":
            signals.get("momentum"),

        f"{TURNING_PREFIX}acceleration_score":
            signals.get("acceleration"),

        f"{TURNING_PREFIX}persistence_score":
            signals.get("persistence"),

        f"{TURNING_PREFIX}deterioration_score":
            abs(
                min(
                    safe_number(
                        signals.get(
                            "deterioration"
                        )
                    )
                    or 0.0,
                    0.0
                )
            ),

        f"{TURNING_PREFIX}score_momentum":
            signals.get("score_momentum"),

        f"{TURNING_PREFIX}signal_confirmation":
            signals.get("signal_confirmation"),

        f"{TURNING_PREFIX}state_code":
            STATE_CODE.get(
                state
            )
    }

    saved_count = save_turning_metrics(
        stock_id,
        latest_period,
        save_values
    )

    return {
        "status": "success",
        "period_end": latest_period,
        "history_count": len(history),
        "turning_score": turning_score,
        "confidence": confidence,
        "comparability": comparability,
        "state": state,
        "description": description,
        "signals": signals,
        "context": context,
        "positive_reasons":
            positive_reasons,
        "negative_reasons":
            negative_reasons,
        "saved_count": saved_count
    }


# ============================================================
# Analyze Stock
# ============================================================

def analyze_stock(stock):

    stock_id = stock["id"]
    symbol = stock["symbol"]

    company_name = (
        stock.get("company_name")
        or symbol
    )

    analysis_model = (
        stock.get("analysis_model")
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

    if len(valid_periods) < MIN_HISTORY:

        return {
            "status": "insufficient_history",
            "symbol": symbol,
            "company_name": company_name,
            "analysis_model":
                analysis_model,
            "period_count":
                len(valid_periods),
            "evaluated_periods": 0,
            "saved_count": 0
        }

    rolling_results = []

    total_saved = 0

    for target_index in range(
        len(valid_periods)
    ):

        if target_index + 1 < MIN_HISTORY:
            continue

        result = evaluate_period(
            stock_id,
            analysis_model,
            periods,
            valid_periods,
            target_index
        )

        rolling_results.append(
            result
        )

        total_saved += (
            result.get(
                "saved_count",
                0
            )
            or 0
        )

    successful = [
        result
        for result in rolling_results
        if result.get("status")
        == "success"
    ]

    if not successful:

        return {
            "status": "no_scored_periods",
            "symbol": symbol,
            "company_name": company_name,
            "analysis_model":
                analysis_model,
            "period_count":
                len(valid_periods),
            "evaluated_periods": 0,
            "saved_count":
                total_saved
        }

    latest_result = (
        successful[-1]
    )

    return {
        "status": "success",
        "symbol": symbol,
        "company_name": company_name,
        "analysis_model":
            analysis_model,
        "period_count":
            len(valid_periods),
        "evaluated_periods":
            len(successful),
        "saved_count":
            total_saved,
        "latest":
            latest_result,
        "rolling_results":
            rolling_results
    }


# ============================================================
# Print Stock
# ============================================================

def print_stock_result(result):

    print_header(
        f"🧭 {result['symbol']} | "
        f"{result['company_name']} | "
        f"{result['analysis_model']}"
    )

    if result["status"] != "success":

        print(
            f"⚠️ Status: "
            f"{result['status']}",
            flush=True
        )

        print(
            f"📚 Financial Periods: "
            f"{result.get('period_count', 0)}",
            flush=True
        )

        return

    latest = result["latest"]

    print(
        f"📅 Latest Period: "
        f"{latest['period_end']}",
        flush=True
    )

    print(
        f"📚 Financial Periods Found: "
        f"{result['period_count']}",
        flush=True
    )

    print(
        f"🧮 Rolling Periods Evaluated: "
        f"{result['evaluated_periods']}",
        flush=True
    )

    print(
        f"🎯 Turning Point Score: "
        f"{fmt(latest['turning_score'])}",
        flush=True
    )

    print(
        f"🧪 Confidence: "
        f"{fmt(latest['confidence'])}",
        flush=True
    )

    comp = latest[
        "comparability"
    ]

    print(
        f"🧬 Comparability: "
        f"{fmt(comp['score'])}%",
        flush=True
    )

    print(
        f"📐 Breadth: "
        f"{fmt(comp['breadth_score'])}% | "
        f"Common={comp['common_inputs']} | "
        f"New={comp['newly_available_inputs']} | "
        f"Dropped={comp['dropped_inputs']}",
        flush=True
    )

    print(
        f"🧭 State: "
        f"{latest['state']} | "
        f"{latest['description']}",
        flush=True
    )

    print(
        f"💾 Metrics Saved: "
        f"{result['saved_count']}",
        flush=True
    )

    print_separator()

    print(
        "🟢 POSITIVE TURNING SIGNALS",
        flush=True
    )

    positives = latest[
        "positive_reasons"
    ]

    if positives:

        for reason in positives[:10]:

            print(
                f"+{fmt(reason['points'])} | "
                f"{reason['reason']}",
                flush=True
            )

    else:

        print(
            "- لا توجد إشارات تحول إيجابية قوية",
            flush=True
        )

    print(
        "\n🔴 NEGATIVE SIGNALS",
        flush=True
    )

    negatives = latest[
        "negative_reasons"
    ]

    if negatives:

        for reason in negatives[:10]:

            print(
                f"{fmt(reason['points'])} | "
                f"{reason['reason']}",
                flush=True
            )

    else:

        print(
            "- لا توجد إشارات تدهور قوية",
            flush=True
        )


# ============================================================
# Summary Helpers
# ============================================================

def print_ranked_group(
    title,
    results
):

    print_header(title)

    if not results:

        print(
            "- لا توجد شركات في هذه المجموعة",
            flush=True
        )
        return

    ranked = sorted(
        results,
        key=lambda result:
            result["latest"].get(
                "turning_score"
            )
            if result["latest"].get(
                "turning_score"
            ) is not None
            else -1,
        reverse=True
    )

    for index, result in enumerate(
        ranked,
        start=1
    ):

        latest = result["latest"]
        comp = latest["comparability"]

        print(
            f"{index:02d}. "
            f"{result['symbol']} | "
            f"{result['company_name']} | "
            f"{result['analysis_model']} | "
            f"Turning={fmt(latest['turning_score'])} | "
            f"Confidence={fmt(latest['confidence'])} | "
            f"Comparable={fmt(comp['score'])}% | "
            f"Breadth={fmt(comp['breadth_score'])}% | "
            f"{latest['state']}",
            flush=True
        )


# ============================================================
# Summary
# ============================================================

def print_summary(results):

    successful = [
        result
        for result in results
        if result.get("status")
        == "success"
    ]

    skipped = [
        result
        for result in results
        if result.get("status")
        != "success"
    ]

    turning_candidates = [
        result
        for result in successful
        if result["latest"]["state"]
        in [
            "STRONG_TURNING_POINT",
            "EARLY_TURNING_POINT",
            "IMPROVING"
        ]
    ]

    continuations = [
        result
        for result in successful
        if result["latest"]["state"]
        == "STRONG_CONTINUATION"
    ]

    monitoring = [
        result
        for result in successful
        if result["latest"]["state"]
        in [
            "NEUTRAL",
            "WEAK",
            "LOW_CONFIDENCE"
        ]
    ]

    deteriorating = [
        result
        for result in successful
        if result["latest"]["state"]
        == "DETERIORATING"
    ]

    print_ranked_group(
        f"🏆 TURNING CANDIDATES v{ENGINE_VERSION}",
        turning_candidates
    )

    print_ranked_group(
        "💪 STRONG CONTINUATIONS",
        continuations
    )

    print_ranked_group(
        "👀 MONITORING / LOW CONFIDENCE",
        monitoring
    )

    print_ranked_group(
        "🔴 DETERIORATING / NOT TURNING CANDIDATES",
        deteriorating
    )

    strong_turning = sum(
        1
        for result in successful
        if result["latest"]["state"]
        == "STRONG_TURNING_POINT"
    )

    early_turning = sum(
        1
        for result in successful
        if result["latest"]["state"]
        == "EARLY_TURNING_POINT"
    )

    improving = sum(
        1
        for result in successful
        if result["latest"]["state"]
        == "IMPROVING"
    )

    continuation = len(
        continuations
    )

    low_confidence = sum(
        1
        for result in successful
        if result["latest"]["state"]
        == "LOW_CONFIDENCE"
    )

    total_saved = sum(
        result.get(
            "saved_count",
            0
        )
        or 0
        for result in successful
    )

    print_header(
        f"📊 TURNING POINT ENGINE v{ENGINE_VERSION} SUMMARY"
    )

    print(
        f"🏢 Total Companies: "
        f"{len(results)}",
        flush=True
    )

    print(
        f"🟢 Successful: "
        f"{len(successful)}",
        flush=True
    )

    print(
        f"⚠️ Skipped/Failed: "
        f"{len(skipped)}",
        flush=True
    )

    print(
        f"🔄 Strong Turning Points: "
        f"{strong_turning}",
        flush=True
    )

    print(
        f"🌱 Early Turning Points: "
        f"{early_turning}",
        flush=True
    )

    print(
        f"📈 Improving: "
        f"{improving}",
        flush=True
    )

    print(
        f"💪 Strong Continuations: "
        f"{continuation}",
        flush=True
    )

    print(
        f"🟡 Low Confidence: "
        f"{low_confidence}",
        flush=True
    )

    print(
        f"🔴 Deteriorating: "
        f"{len(deteriorating)}",
        flush=True
    )

    print(
        f"💾 Total Metrics Saved: "
        f"{total_saved}",
        flush=True
    )

    if skipped:

        print(
            "\n⚠️ SKIPPED / FAILED",
            flush=True
        )

        for result in skipped:

            print(
                f"- {result.get('symbol')} | "
                f"{result.get('analysis_model')} | "
                f"{result.get('status')}",
                flush=True
            )

    print(
        "\n✅ v2.0.1 Comparability Fix: "
        "المؤشرات الجديدة لا تخفض المقارنة لمجرد أنها لم تكن "
        "قابلة للحساب في الفترة السابقة.",
        flush=True
    )

    print(
        "✅ Gap-safe Series: "
        "لا تتم مقارنة أرباع غير متجاورة عند وجود فجوة بيانات.",
        flush=True
    )

    print(
        "✅ Ranking Safety: "
        "الشركات المتدهورة منفصلة عن Turning Candidates.",
        flush=True
    )

    print(
        "✅ Rolling backfill enabled.",
        flush=True
    )

    print(
        "=" * 96,
        flush=True
    )


# ============================================================
# Run
# ============================================================

def run_turning_point_engine():

    stocks = get_active_stocks()

    print_header(
        f"🧭 TURNING POINT ENGINE v{ENGINE_VERSION}"
    )

    print(
        "🔁 Mode: ROLLING HISTORICAL EVALUATION",
        flush=True
    )

    print(
        f"🏢 Total Active Stocks: "
        f"{len(stocks)}",
        flush=True
    )

    print(
        f"📚 Preferred History: "
        f"{PREFERRED_HISTORY} periods",
        flush=True
    )

    print(
        f"🛡️ Direction Gate: "
        f"Confidence >= "
        f"{MIN_CONFIDENCE_FOR_DIRECTION:.0f} | "
        f"Comparability >= "
        f"{MIN_COMPARABILITY_FOR_DIRECTION:.0f} | "
        f"Common Inputs >= "
        f"{MIN_COMMON_INPUTS_FOR_DIRECTION}",
        flush=True
    )

    results = []

    for index, stock in enumerate(
        stocks,
        start=1
    ):

        print(
            "\n"
            f"🚦 Analyzing "
            f"{index}/{len(stocks)} | "
            f"{stock['symbol']}",
            flush=True
        )

        try:

            result = analyze_stock(
                stock
            )

        except Exception as error:

            result = {
                "status": "error",
                "symbol":
                    stock.get("symbol"),
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

        results.append(result)

        print_stock_result(
            result
        )

    print_summary(
        results
    )


if __name__ == "__main__":

    run_turning_point_engine()
