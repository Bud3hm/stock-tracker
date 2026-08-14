import os
from datetime import datetime, timezone
from supabase import create_client


# ============================================================
# TURNING POINT ENGINE v1
#
# الهدف:
# اكتشاف التحول المالي عبر عدة أرباع، وليس تقييم الربع
# الحالي فقط.
#
# النماذج:
# standard / bank / insurance / reit
# ============================================================


SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_SECRET_KEY = os.environ.get("SUPABASE_SECRET_KEY")

supabase = create_client(
    SUPABASE_URL,
    SUPABASE_SECRET_KEY
)


# ============================================================
# إعدادات المحرك
# ============================================================

MIN_HISTORY = 2
PREFERRED_HISTORY = 4

TURNING_METRIC_NAME = "turning_engine_score"

MODEL_PREFIX = {
    "standard": "q_",
    "bank": "bank_q_",
    "insurance": "insurance_q_",
    "reit": "reit_q_"
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


def signed_fmt(value):

    value = safe_number(value)

    if value is None:
        return "N/A"

    return f"{value:+.2f}"


def average(values):

    cleaned = [
        safe_number(value)
        for value in values
    ]

    cleaned = [
        value
        for value in cleaned
        if value is not None
    ]

    if not cleaned:
        return None

    return sum(cleaned) / len(cleaned)


def difference(
    current,
    previous
):

    current = safe_number(current)
    previous = safe_number(previous)

    if (
        current is None
        or previous is None
    ):
        return None

    return current - previous


def print_header(title):

    print(
        "\n"
        + "=" * 80,
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


def print_separator():

    print(
        "-" * 80,
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
            "sector,"
            "analysis_model,"
            "priority,"
            "data_status"
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
# تنظيم المؤشرات حسب الفترة
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
# استخراج سلسلة مؤشر
# ============================================================

def metric_series(
    history,
    metric_name
):

    return [
        safe_number(
            period_metrics.get(
                metric_name
            )
        )
        for period_metrics in history
    ]


# ============================================================
# تحليل اتجاه سلسلة رقمية
# ============================================================

def analyze_series(values):

    values = [
        safe_number(value)
        for value in values
    ]

    valid_values = [
        value
        for value in values
        if value is not None
    ]

    result = {
        "latest": None,
        "previous": None,
        "delta": None,
        "acceleration": None,
        "positive_streak": 0,
        "negative_streak": 0,
        "rising_steps": 0,
        "falling_steps": 0
    }

    if not valid_values:
        return result

    result[
        "latest"
    ] = valid_values[-1]

    if len(valid_values) >= 2:

        result[
            "previous"
        ] = valid_values[-2]

        result[
            "delta"
        ] = (
            valid_values[-1]
            - valid_values[-2]
        )

    if len(valid_values) >= 3:

        previous_delta = (
            valid_values[-2]
            - valid_values[-3]
        )

        current_delta = (
            valid_values[-1]
            - valid_values[-2]
        )

        result[
            "acceleration"
        ] = (
            current_delta
            - previous_delta
        )

    positive_streak = 0

    for value in reversed(
        valid_values
    ):

        if value > 0:
            positive_streak += 1
        else:
            break

    negative_streak = 0

    for value in reversed(
        valid_values
    ):

        if value < 0:
            negative_streak += 1
        else:
            break

    rising_steps = 0
    falling_steps = 0

    for index in range(
        1,
        len(valid_values)
    ):

        if (
            valid_values[index]
            > valid_values[index - 1]
        ):
            rising_steps += 1

        elif (
            valid_values[index]
            < valid_values[index - 1]
        ):
            falling_steps += 1

    result[
        "positive_streak"
    ] = positive_streak

    result[
        "negative_streak"
    ] = negative_streak

    result[
        "rising_steps"
    ] = rising_steps

    result[
        "falling_steps"
    ] = falling_steps

    return result


# ============================================================
# إضافة إشارة
# ============================================================

def add_signal(
    signals,
    reasons,
    category,
    points,
    reason
):

    signals[
        category
    ] += points

    reasons.append(
        {
            "category": category,
            "points": points,
            "reason": reason
        }
    )


# ============================================================
# تحليل مؤشر نمو
# ============================================================

def evaluate_growth_metric(
    history,
    metric_name,
    label,
    signals,
    reasons,
    weight=1.0
):

    series = metric_series(
        history,
        metric_name
    )

    trend = analyze_series(
        series
    )

    latest = trend[
        "latest"
    ]

    delta = trend[
        "delta"
    ]

    acceleration = trend[
        "acceleration"
    ]

    if latest is None:
        return

    # تحول من سالب إلى موجب
    if (
        trend["previous"] is not None
        and trend["previous"] < 0
        and latest > 0
    ):

        add_signal(
            signals,
            reasons,
            "reversal",
            12 * weight,
            f"{label}: تحول من انكماش إلى نمو"
        )

    # نمو قوي
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

    # تحسن عن الربع السابق
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

    # تسارع
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

    # استمرار
    if trend[
        "positive_streak"
    ] >= 2:

        add_signal(
            signals,
            reasons,
            "persistence",
            4 * weight,
            f"{label}: نمو إيجابي مستمر "
            f"{trend['positive_streak']} فترات"
        )

    # تدهور
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
# تحليل تغير الهوامش
# ============================================================

def evaluate_margin_metric(
    history,
    metric_name,
    label,
    signals,
    reasons,
    weight=1.0
):

    series = metric_series(
        history,
        metric_name
    )

    trend = analyze_series(
        series
    )

    latest = trend[
        "latest"
    ]

    delta = trend[
        "delta"
    ]

    if latest is None:
        return

    if (
        trend["previous"] is not None
        and trend["previous"] < 0
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
# STANDARD MODEL
# ============================================================

def evaluate_standard(history):

    signals = {
        "reversal": 0.0,
        "momentum": 0.0,
        "acceleration": 0.0,
        "persistence": 0.0,
        "quality": 0.0,
        "cash": 0.0,
        "balance": 0.0,
        "current_strength": 0.0,
        "deterioration": 0.0
    }

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
        latest.get(
            "q_cash_conversion"
        )
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
        latest.get(
            "q_debt_growth_qoq"
        )
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
        latest.get(
            "q_current_ratio"
        )
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
# BANK MODEL
# ============================================================

def evaluate_bank(history):

    signals = {
        "reversal": 0.0,
        "momentum": 0.0,
        "acceleration": 0.0,
        "persistence": 0.0,
        "quality": 0.0,
        "cash": 0.0,
        "balance": 0.0,
        "current_strength": 0.0,
        "deterioration": 0.0
    }

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
        latest.get(
            "bank_ttm_roe"
        )
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
# INSURANCE MODEL
# ============================================================

def evaluate_insurance(history):

    signals = {
        "reversal": 0.0,
        "momentum": 0.0,
        "acceleration": 0.0,
        "persistence": 0.0,
        "quality": 0.0,
        "cash": 0.0,
        "balance": 0.0,
        "current_strength": 0.0,
        "deterioration": 0.0
    }

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
        latest.get(
            "insurance_ttm_roe"
        )
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
# REIT MODEL
# ============================================================

def evaluate_reit(history):

    signals = {
        "reversal": 0.0,
        "momentum": 0.0,
        "acceleration": 0.0,
        "persistence": 0.0,
        "quality": 0.0,
        "cash": 0.0,
        "balance": 0.0,
        "current_strength": 0.0,
        "deterioration": 0.0
    }

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
        latest.get(
            "reit_q_debt_to_assets"
        )
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
# Router
# ============================================================

def evaluate_model(
    analysis_model,
    history
):

    if analysis_model == "standard":

        return evaluate_standard(
            history
        )

    if analysis_model == "bank":

        return evaluate_bank(
            history
        )

    if analysis_model == "insurance":

        return evaluate_insurance(
            history
        )

    if analysis_model == "reit":

        return evaluate_reit(
            history
        )

    return None, None


# ============================================================
# دمج Historical Scoring
# ============================================================

def evaluate_score_history(
    history
):

    signals = {
        "score_momentum": 0.0
    }

    reasons = []

    opportunity_series = (
        metric_series(
            history,
            "score_opportunity_score"
        )
    )

    risk_series = (
        metric_series(
            history,
            "score_risk_score"
        )
    )

    turning_series = (
        metric_series(
            history,
            "score_turning_point_score"
        )
    )

    opportunity = analyze_series(
        opportunity_series
    )

    risk = analyze_series(
        risk_series
    )

    turning = analyze_series(
        turning_series
    )

    # Opportunity تتحسن
    if (
        opportunity["delta"] is not None
        and opportunity["delta"] >= 5
    ):

        signals[
            "score_momentum"
        ] += 6

        reasons.append(
            {
                "category":
                    "score_momentum",

                "points":
                    6,

                "reason":
                    "Opportunity Score يتحسن "
                    f"({signed_fmt(opportunity['delta'])})"
            }
        )

    # Risk تنخفض
    if (
        risk["delta"] is not None
        and risk["delta"] <= -5
    ):

        signals[
            "score_momentum"
        ] += 6

        reasons.append(
            {
                "category":
                    "score_momentum",

                "points":
                    6,

                "reason":
                    "Risk Score ينخفض "
                    f"({signed_fmt(risk['delta'])})"
            }
        )

    # Turning Score يتحسن
    if (
        turning["delta"] is not None
        and turning["delta"] >= 5
    ):

        signals[
            "score_momentum"
        ] += 7

        reasons.append(
            {
                "category":
                    "score_momentum",

                "points":
                    7,

                "reason":
                    "الـTurning Score الأساسي يتحسن "
                    f"({signed_fmt(turning['delta'])})"
            }
        )

    # تدهور Opportunity
    if (
        opportunity["delta"] is not None
        and opportunity["delta"] <= -10
    ):

        signals[
            "score_momentum"
        ] -= 5

        reasons.append(
            {
                "category":
                    "score_momentum",

                "points":
                    -5,

                "reason":
                    "Opportunity Score يتراجع "
                    f"({signed_fmt(opportunity['delta'])})"
            }
        )

    # ارتفاع Risk
    if (
        risk["delta"] is not None
        and risk["delta"] >= 10
    ):

        signals[
            "score_momentum"
        ] -= 6

        reasons.append(
            {
                "category":
                    "score_momentum",

                "points":
                    -6,

                "reason":
                    "Risk Score يرتفع "
                    f"({signed_fmt(risk['delta'])})"
            }
        )

    return signals, reasons


# ============================================================
# Confidence التاريخي
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

    confidence_metric = {
        "standard":
            "data_confidence_score",

        "bank":
            "bank_data_confidence_score",

        "insurance":
            "insurance_data_confidence_score",

        "reit":
            "reit_data_confidence_score"
    }.get(
        analysis_model
    )

    latest_confidence = None

    if confidence_metric:

        latest_confidence = safe_number(
            history[-1].get(
                confidence_metric
            )
        )

    if latest_confidence is None:

        score_confidence = safe_number(
            history[-1].get(
                "score_confidence_score"
            )
        )

        latest_confidence = (
            score_confidence
            if score_confidence is not None
            else 50.0
        )

    data_score = (
        clamp(
            latest_confidence
        )
        / 100
    ) * 50

    return clamp(
        history_score
        + data_score
    )


# ============================================================
# حساب Turning Point النهائي
# ============================================================

def calculate_turning_score(
    signals,
    confidence
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
        "score_momentum"
    ]

    positive_points = sum(
        max(
            0,
            safe_number(
                signals.get(
                    category
                )
            )
            or 0
        )
        for category in positive_categories
    )

    deterioration = safe_number(
        signals.get(
            "deterioration"
        )
    ) or 0

    negative_points = abs(
        min(
            deterioration,
            0
        )
    )

    raw_score = (
        35
        + positive_points
        - negative_points
    )

    raw_score = clamp(
        raw_score
    )

    confidence = (
        clamp(
            confidence
        )
        or 0
    )

    confidence_factor = (
        0.60
        + (
            confidence
            / 250
        )
    )

    final_score = (
        raw_score
        * confidence_factor
    )

    return clamp(
        final_score
    )


# ============================================================
# تصنيف التحول
# ============================================================

def classify_turning_point(
    score,
    signals,
    confidence
):

    score = safe_number(
        score
    )

    confidence = safe_number(
        confidence
    )

    reversal = safe_number(
        signals.get(
            "reversal"
        )
    ) or 0

    momentum = safe_number(
        signals.get(
            "momentum"
        )
    ) or 0

    acceleration = safe_number(
        signals.get(
            "acceleration"
        )
    ) or 0

    persistence = safe_number(
        signals.get(
            "persistence"
        )
    ) or 0

    deterioration = abs(
        min(
            safe_number(
                signals.get(
                    "deterioration"
                )
            )
            or 0,
            0
        )
    )

    if (
        confidence is None
        or confidence < 50
    ):

        return (
            "LOW_CONFIDENCE",
            "التاريخ المتاح غير كافٍ"
        )

    if (
        score is not None
        and score >= 80
        and reversal >= 8
        and (
            momentum > 0
            or acceleration > 0
        )
    ):

        return (
            "STRONG_TURNING_POINT",
            "تحول مالي قوي ومتعدد الإشارات"
        )

    if (
        score is not None
        and score >= 65
        and (
            reversal > 0
            or momentum > 0
        )
    ):

        return (
            "EARLY_TURNING_POINT",
            "بوادر تحول مالي إيجابي"
        )

    if (
        score is not None
        and score >= 55
        and persistence > 0
    ):

        return (
            "IMPROVING",
            "تحسن مستمر لكنه لم يصل لتحول قوي"
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
# حفظ النتيجة
# ============================================================

def save_turning_score(
    stock_id,
    period_end,
    score
):

    score = safe_number(
        score
    )

    if score is None:
        return

    row = {
        "stock_id":
            stock_id,

        "calculated_at":
            datetime.now(
                timezone.utc
            ).isoformat(),

        "metric_name":
            TURNING_METRIC_NAME,

        "metric_value":
            score,

        "period_end":
            period_end
    }

    (
        supabase
        .table(
            "financial_metrics"
        )
        .upsert(
            row,
            on_conflict=(
                "stock_id,"
                "metric_name,"
                "period_end"
            )
        )
        .execute()
    )


# ============================================================
# تحليل شركة واحدة
# ============================================================

def analyze_stock(stock):

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

    if len(
        valid_periods
    ) < MIN_HISTORY:

        return {
            "status":
                "insufficient_history",

            "symbol":
                symbol,

            "company_name":
                company_name,

            "analysis_model":
                analysis_model,

            "history_count":
                len(
                    valid_periods
                )
        }

    selected_periods = (
        valid_periods[
            -PREFERRED_HISTORY:
        ]
    )

    history = [
        periods[
            period_end
        ]
        for period_end in selected_periods
    ]

    model_signals, model_reasons = (
        evaluate_model(
            analysis_model,
            history
        )
    )

    if model_signals is None:

        return {
            "status":
                "unsupported_model",

            "symbol":
                symbol,

            "company_name":
                company_name,

            "analysis_model":
                analysis_model
        }

    score_signals, score_reasons = (
        evaluate_score_history(
            history
        )
    )

    signals = dict(
        model_signals
    )

    for key, value in (
        score_signals.items()
    ):

        signals[
            key
        ] = (
            signals.get(
                key,
                0
            )
            + value
        )

    reasons = (
        model_reasons
        + score_reasons
    )

    confidence = history_confidence(
        history,
        analysis_model
    )

    turning_score = (
        calculate_turning_score(
            signals,
            confidence
        )
    )

    state, description = (
        classify_turning_point(
            turning_score,
            signals,
            confidence
        )
    )

    latest_period = (
        selected_periods[-1]
    )

    save_turning_score(
        stock_id,
        latest_period,
        turning_score
    )

    positive_reasons = [
        reason
        for reason in reasons
        if reason[
            "points"
        ] > 0
    ]

    negative_reasons = [
        reason
        for reason in reasons
        if reason[
            "points"
        ] < 0
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

        "history_count":
            len(
                selected_periods
            ),

        "turning_score":
            turning_score,

        "confidence":
            confidence,

        "state":
            state,

        "description":
            description,

        "signals":
            signals,

        "positive_reasons":
            positive_reasons,

        "negative_reasons":
            negative_reasons
    }


# ============================================================
# طباعة نتيجة شركة
# ============================================================

def print_stock_result(result):

    print_header(
        f"🧭 {result['symbol']} | "
        f"{result['company_name']} | "
        f"{result['analysis_model']}"
    )

    if result[
        "status"
    ] != "success":

        print(
            f"⚠️ Status: "
            f"{result['status']}",
            flush=True
        )

        print(
            f"📚 History: "
            f"{result.get('history_count', 0)}",
            flush=True
        )

        return

    print(
        f"📅 Latest Period: "
        f"{result['latest_period']}",
        flush=True
    )

    print(
        f"📚 History Used: "
        f"{result['history_count']} periods",
        flush=True
    )

    print(
        f"🎯 Turning Point Score: "
        f"{fmt(result['turning_score'])}",
        flush=True
    )

    print(
        f"🧪 Confidence: "
        f"{fmt(result['confidence'])}",
        flush=True
    )

    print(
        f"🧭 State: "
        f"{result['state']} | "
        f"{result['description']}",
        flush=True
    )

    print_separator()

    print(
        "🟢 POSITIVE TURNING SIGNALS",
        flush=True
    )

    positives = result[
        "positive_reasons"
    ]

    if positives:

        for reason in positives[:8]:

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

    negatives = result[
        "negative_reasons"
    ]

    if negatives:

        for reason in negatives[:8]:

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
# الملخص
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
        key=lambda result:
            result.get(
                "turning_score"
            )
            if result.get(
                "turning_score"
            ) is not None
            else -1,
        reverse=True
    )

    print_header(
        "🏆 TURNING POINT RANKING"
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
            f"Turning="
            f"{fmt(result['turning_score'])} | "
            f"Confidence="
            f"{fmt(result['confidence'])} | "
            f"{result['state']}",
            flush=True
        )

    skipped = [
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
        f"{len(skipped)}",
        flush=True
    )

    if skipped:

        print(
            "\n⚠️ SKIPPED / FAILED",
            flush=True
        )

        for result in skipped:

            print(
                f"{result.get('symbol')} | "
                f"{result.get('analysis_model')} | "
                f"{result.get('status')}",
                flush=True
            )

    print(
        "=" * 80,
        flush=True
    )


# ============================================================
# التشغيل
# ============================================================

def run_turning_point_engine():

    stocks = get_active_stocks()

    print_header(
        "🧭 TURNING POINT ENGINE v1"
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

        print_stock_result(
            result
        )

    print_summary(
        results
    )


if __name__ == "__main__":

    run_turning_point_engine()
