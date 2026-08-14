import os
from datetime import datetime, timezone
from supabase import create_client


# ============================================================
# FINAL DECISION ENGINE v2
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

DECISION_SCORE_METRIC = "decision_score"
DECISION_CONFIDENCE_METRIC = "decision_confidence"
DECISION_MOMENTUM_METRIC = "decision_momentum_score"
DECISION_RELIABILITY_METRIC = "decision_reliability_score"


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


def weighted_average(items):

    total = 0.0
    weight_sum = 0.0

    for value, weight in items:

        value = safe_number(value)
        weight = safe_number(weight)

        if (
            value is None
            or weight is None
            or weight <= 0
        ):
            continue

        total += (
            value
            * weight
        )

        weight_sum += weight

    if weight_sum == 0:
        return None

    return (
        total
        / weight_sum
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
# استخراج المؤشرات الموحدة
# ============================================================

def score_block(metrics):

    return {

        "growth":
            safe_number(
                metrics.get(
                    "score_growth_score"
                )
            ),

        "quality":
            safe_number(
                metrics.get(
                    "score_quality_score"
                )
            ),

        "cash":
            safe_number(
                metrics.get(
                    "score_cash_score"
                )
            ),

        "balance":
            safe_number(
                metrics.get(
                    "score_balance_score"
                )
            ),

        "opportunity":
            safe_number(
                metrics.get(
                    "score_opportunity_score"
                )
            ),

        "risk":
            safe_number(
                metrics.get(
                    "score_risk_score"
                )
            ),

        "turning_base":
            safe_number(
                metrics.get(
                    "score_turning_point_score"
                )
            ),

        "confidence":
            safe_number(
                metrics.get(
                    "score_confidence_score"
                )
            ),

        "turning_engine":
            safe_number(
                metrics.get(
                    "turning_engine_score"
                )
            ),

        # ====================================================
        # Data Quality Engine
        # ====================================================

        "data_quality":
            safe_number(
                metrics.get(
                    "data_quality_score"
                )
            ),

        "freshness":
            safe_number(
                metrics.get(
                    "data_freshness_score"
                )
            ),

        "coverage":
            safe_number(
                metrics.get(
                    "data_coverage_score"
                )
            ),

        "history_quality":
            safe_number(
                metrics.get(
                    "data_history_score"
                )
            ),

        "continuity":
            safe_number(
                metrics.get(
                    "data_continuity_score"
                )
            ),

        "market_lag_days":
            safe_number(
                metrics.get(
                    "data_market_lag_days"
                )
            )
    }


# ============================================================
# Momentum
# ============================================================

def calculate_delta(
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

    return (
        current
        - previous
    )


def get_momentum(
    current_scores,
    previous_scores
):

    return {

        "opportunity_delta":
            calculate_delta(
                current_scores.get(
                    "opportunity"
                ),
                previous_scores.get(
                    "opportunity"
                )
            ),

        "risk_delta":
            calculate_delta(
                current_scores.get(
                    "risk"
                ),
                previous_scores.get(
                    "risk"
                )
            ),

        "turning_delta":
            calculate_delta(
                current_scores.get(
                    "turning_base"
                ),
                previous_scores.get(
                    "turning_base"
                )
            ),

        "growth_delta":
            calculate_delta(
                current_scores.get(
                    "growth"
                ),
                previous_scores.get(
                    "growth"
                )
            ),

        "quality_delta":
            calculate_delta(
                current_scores.get(
                    "quality"
                ),
                previous_scores.get(
                    "quality"
                )
            )
    }


# ============================================================
# Momentum Score v2
# أكثر تحفظًا من النسخة الأولى
# ============================================================

def calculate_momentum_score(momentum):

    score = 50.0

    used = 0

    positive_confirmations = 0
    negative_confirmations = 0

    opportunity_delta = safe_number(
        momentum.get(
            "opportunity_delta"
        )
    )

    if opportunity_delta is not None:

        used += 1

        if opportunity_delta >= 20:

            score += 10
            positive_confirmations += 1

        elif opportunity_delta >= 8:

            score += 6
            positive_confirmations += 1

        elif opportunity_delta >= 3:

            score += 3

        elif opportunity_delta <= -20:

            score -= 10
            negative_confirmations += 1

        elif opportunity_delta <= -8:

            score -= 6
            negative_confirmations += 1

        elif opportunity_delta <= -3:

            score -= 3


    risk_delta = safe_number(
        momentum.get(
            "risk_delta"
        )
    )

    if risk_delta is not None:

        used += 1

        if risk_delta <= -20:

            score += 10
            positive_confirmations += 1

        elif risk_delta <= -8:

            score += 6
            positive_confirmations += 1

        elif risk_delta <= -3:

            score += 3

        elif risk_delta >= 20:

            score -= 10
            negative_confirmations += 1

        elif risk_delta >= 8:

            score -= 6
            negative_confirmations += 1

        elif risk_delta >= 3:

            score -= 3


    turning_delta = safe_number(
        momentum.get(
            "turning_delta"
        )
    )

    if turning_delta is not None:

        used += 1

        if turning_delta >= 20:

            score += 10
            positive_confirmations += 1

        elif turning_delta >= 8:

            score += 6
            positive_confirmations += 1

        elif turning_delta >= 3:

            score += 3

        elif turning_delta <= -20:

            score -= 10
            negative_confirmations += 1

        elif turning_delta <= -8:

            score -= 6
            negative_confirmations += 1

        elif turning_delta <= -3:

            score -= 3


    quality_delta = safe_number(
        momentum.get(
            "quality_delta"
        )
    )

    if quality_delta is not None:

        used += 1

        if quality_delta >= 20:

            score += 8
            positive_confirmations += 1

        elif quality_delta >= 8:

            score += 4

        elif quality_delta <= -20:

            score -= 8
            negative_confirmations += 1

        elif quality_delta <= -8:

            score -= 4


    growth_delta = safe_number(
        momentum.get(
            "growth_delta"
        )
    )

    if growth_delta is not None:

        used += 1

        if growth_delta >= 20:

            score += 7
            positive_confirmations += 1

        elif growth_delta >= 8:

            score += 4

        elif growth_delta <= -20:

            score -= 7
            negative_confirmations += 1

        elif growth_delta <= -8:

            score -= 4


    if used == 0:

        return 50.0


    # ========================================================
    # تأكيد متعدد
    # ========================================================

    if positive_confirmations >= 3:

        score += 5

    if negative_confirmations >= 2:

        score -= 5


    # ========================================================
    # كشف التناقض
    # ========================================================

    if (
        opportunity_delta is not None
        and opportunity_delta > 5
        and risk_delta is not None
        and risk_delta > 5
    ):

        score -= 7


    if (
        turning_delta is not None
        and turning_delta > 5
        and quality_delta is not None
        and quality_delta < -10
    ):

        score -= 7


    # سقف مقصود حتى لا يصبح 100 بسهولة
    return clamp(
        score,
        10.0,
        92.0
    )


# ============================================================
# Consistency
# ============================================================

def calculate_consistency_score(
    latest,
    previous
):

    score = 50.0

    current_opportunity = safe_number(
        latest.get(
            "opportunity"
        )
    )

    previous_opportunity = safe_number(
        previous.get(
            "opportunity"
        )
    )

    current_risk = safe_number(
        latest.get(
            "risk"
        )
    )

    previous_risk = safe_number(
        previous.get(
            "risk"
        )
    )

    current_quality = safe_number(
        latest.get(
            "quality"
        )
    )

    previous_quality = safe_number(
        previous.get(
            "quality"
        )
    )


    if (
        current_opportunity is not None
        and previous_opportunity is not None
    ):

        if (
            current_opportunity >= 60
            and previous_opportunity >= 60
        ):

            score += 18

        elif (
            current_opportunity < 45
            and previous_opportunity < 45
        ):

            score -= 15


    if (
        current_risk is not None
        and previous_risk is not None
    ):

        if (
            current_risk <= 40
            and previous_risk <= 40
        ):

            score += 14

        elif (
            current_risk >= 60
            and previous_risk >= 60
        ):

            score -= 15


    if (
        current_quality is not None
        and previous_quality is not None
    ):

        if (
            current_quality >= 60
            and previous_quality >= 60
        ):

            score += 8

        elif (
            current_quality < 40
            and previous_quality < 40
        ):

            score -= 8


    return clamp(
        score
    )


# ============================================================
# Reliability Score
# ============================================================

def calculate_reliability_score(scores):

    confidence = safe_number(
        scores.get(
            "confidence"
        )
    )

    data_quality = safe_number(
        scores.get(
            "data_quality"
        )
    )

    freshness = safe_number(
        scores.get(
            "freshness"
        )
    )

    coverage = safe_number(
        scores.get(
            "coverage"
        )
    )

    history_quality = safe_number(
        scores.get(
            "history_quality"
        )
    )

    continuity = safe_number(
        scores.get(
            "continuity"
        )
    )


    reliability = weighted_average([

        (
            data_quality,
            40
        ),

        (
            confidence,
            25
        ),

        (
            freshness,
            15
        ),

        (
            coverage,
            10
        ),

        (
            history_quality,
            5
        ),

        (
            continuity,
            5
        )
    ])


    if reliability is None:

        return 0.0


    return clamp(
        reliability
    )


# ============================================================
# Bonus / Penalty
# ============================================================

def calculate_penalty_bonus(
    scores,
    momentum_score,
    consistency_score,
    reliability_score
):

    bonus = 0.0
    penalty = 0.0

    reasons = []


    opportunity = safe_number(
        scores.get(
            "opportunity"
        )
    )

    risk = safe_number(
        scores.get(
            "risk"
        )
    )

    turning_engine = safe_number(
        scores.get(
            "turning_engine"
        )
    )

    financial_quality = safe_number(
        scores.get(
            "quality"
        )
    )

    balance = safe_number(
        scores.get(
            "balance"
        )
    )

    data_quality = safe_number(
        scores.get(
            "data_quality"
        )
    )

    freshness = safe_number(
        scores.get(
            "freshness"
        )
    )

    coverage = safe_number(
        scores.get(
            "coverage"
        )
    )

    market_lag_days = safe_number(
        scores.get(
            "market_lag_days"
        )
    )


    # ========================================================
    # Bonuses
    # ========================================================

    if (
        turning_engine is not None
        and turning_engine >= 80
    ):

        bonus += 5

        reasons.append(
            "Turning Point قوي جدًا"
        )


    if (
        opportunity is not None
        and opportunity >= 80
        and risk is not None
        and risk <= 25
    ):

        bonus += 5

        reasons.append(
            "Opportunity مرتفع جدًا مع Risk منخفض"
        )


    if (
        momentum_score is not None
        and momentum_score >= 78
        and consistency_score is not None
        and consistency_score >= 65
    ):

        bonus += 4

        reasons.append(
            "زخم قوي ومدعوم بالاستمرارية"
        )


    if (
        financial_quality is not None
        and financial_quality >= 80
    ):

        bonus += 3

        reasons.append(
            "جودة مالية مرتفعة"
        )


    if (
        data_quality is not None
        and data_quality >= 90
        and freshness is not None
        and freshness >= 90
        and coverage is not None
        and coverage >= 85
    ):

        bonus += 2

        reasons.append(
            "جودة البيانات ممتازة وحديثة"
        )


    # ========================================================
    # Financial penalties
    # ========================================================

    if (
        risk is not None
        and risk >= 65
    ):

        penalty += 14

        reasons.append(
            "Risk مرتفع"
        )

    elif (
        risk is not None
        and risk >= 55
    ):

        penalty += 7

        reasons.append(
            "Risk أعلى من المفضل"
        )


    if (
        turning_engine is not None
        and turning_engine <= 30
    ):

        penalty += 10

        reasons.append(
            "Turning Point ضعيف"
        )


    if (
        financial_quality is not None
        and financial_quality <= 30
    ):

        penalty += 9

        reasons.append(
            "جودة مالية ضعيفة"
        )


    if (
        balance is not None
        and balance <= 30
    ):

        penalty += 7

        reasons.append(
            "الميزانية ضعيفة"
        )


    if (
        momentum_score is not None
        and momentum_score <= 30
    ):

        penalty += 9

        reasons.append(
            "الزخم يتدهور"
        )


    # ========================================================
    # Data Quality penalties
    # ========================================================

    if data_quality is None:

        penalty += 15

        reasons.append(
            "Data Quality غير متوفر"
        )

    elif data_quality < 40:

        penalty += 22

        reasons.append(
            "جودة البيانات ضعيفة جدًا"
        )

    elif data_quality < 55:

        penalty += 14

        reasons.append(
            "جودة البيانات ضعيفة"
        )

    elif data_quality < 70:

        penalty += 7

        reasons.append(
            "جودة البيانات أقل من المستوى المطلوب"
        )


    if freshness is None:

        penalty += 10

        reasons.append(
            "Freshness غير متوفر"
        )

    elif freshness < 30:

        penalty += 18

        reasons.append(
            "البيانات قديمة جدًا"
        )

    elif freshness < 50:

        penalty += 10

        reasons.append(
            "البيانات متأخرة"
        )

    elif freshness < 70:

        penalty += 5

        reasons.append(
            "حداثة البيانات متوسطة"
        )


    if (
        coverage is not None
        and coverage < 50
    ):

        penalty += 15

        reasons.append(
            "Coverage ضعيف"
        )

    elif (
        coverage is not None
        and coverage < 70
    ):

        penalty += 7

        reasons.append(
            "Coverage غير مكتمل"
        )


    if market_lag_days is not None:

        if market_lag_days >= 165:

            penalty += 18

            reasons.append(
                "متأخر قرابة ربعين عن أحدث بيانات السوق"
            )

        elif market_lag_days >= 75:

            penalty += 10

            reasons.append(
                "متأخر ربعًا عن أحدث بيانات السوق"
            )


    if (
        reliability_score is not None
        and reliability_score < 50
    ):

        penalty += 10

        reasons.append(
            "موثوقية القرار منخفضة"
        )


    return (
        bonus,
        penalty,
        reasons
    )


# ============================================================
# Decision Score
# ============================================================

def calculate_decision_score(
    scores,
    momentum_score,
    consistency_score
):

    opportunity = safe_number(
        scores.get(
            "opportunity"
        )
    )

    turning_engine = safe_number(
        scores.get(
            "turning_engine"
        )
    )

    turning_base = safe_number(
        scores.get(
            "turning_base"
        )
    )

    financial_quality = safe_number(
        scores.get(
            "quality"
        )
    )

    balance = safe_number(
        scores.get(
            "balance"
        )
    )

    risk = safe_number(
        scores.get(
            "risk"
        )
    )

    data_quality = safe_number(
        scores.get(
            "data_quality"
        )
    )


    reliability_score = (
        calculate_reliability_score(
            scores
        )
    )


    turning_score = (
        turning_engine
        if turning_engine is not None
        else turning_base
    )


    risk_quality = (
        100 - risk
        if risk is not None
        else None
    )


    # ========================================================
    # الأوزان الجديدة
    # Data Quality أصبح جزءًا مباشرًا من القرار
    # Momentum أصبح أقل تأثيرًا
    # ========================================================

    raw_score = weighted_average([

        (
            opportunity,
            24
        ),

        (
            turning_score,
            22
        ),

        (
            financial_quality,
            14
        ),

        (
            risk_quality,
            13
        ),

        (
            data_quality,
            12
        ),

        (
            momentum_score,
            7
        ),

        (
            balance,
            5
        ),

        (
            consistency_score,
            3
        )
    ])


    if raw_score is None:

        return (
            None,
            reliability_score,
            []
        )


    (
        bonus,
        penalty,
        reasons
    ) = calculate_penalty_bonus(
        scores,
        momentum_score,
        consistency_score,
        reliability_score
    )


    adjusted = (
        raw_score
        + bonus
        - penalty
    )


    adjusted = clamp(
        adjusted
    )


    # ========================================================
    # Reliability factor
    # ========================================================

    reliability_factor = (
        0.55
        + (
            reliability_score
            / 222.22
        )
    )


    reliability_factor = min(
        reliability_factor,
        1.0
    )


    final_score = (
        adjusted
        * reliability_factor
    )


    # ========================================================
    # Hard Caps
    # ========================================================

    freshness = safe_number(
        scores.get(
            "freshness"
        )
    )

    coverage = safe_number(
        scores.get(
            "coverage"
        )
    )

    market_lag_days = safe_number(
        scores.get(
            "market_lag_days"
        )
    )


    if data_quality is None:

        final_score = min(
            final_score,
            45.0
        )


    elif data_quality < 40:

        final_score = min(
            final_score,
            40.0
        )


    elif data_quality < 55:

        final_score = min(
            final_score,
            52.0
        )


    elif data_quality < 70:

        final_score = min(
            final_score,
            65.0
        )


    if (
        freshness is not None
        and freshness < 30
    ):

        final_score = min(
            final_score,
            38.0
        )


    elif (
        freshness is not None
        and freshness < 50
    ):

        final_score = min(
            final_score,
            58.0
        )


    if (
        coverage is not None
        and coverage < 50
    ):

        final_score = min(
            final_score,
            45.0
        )


    if (
        market_lag_days is not None
        and market_lag_days >= 165
    ):

        final_score = min(
            final_score,
            42.0
        )


    elif (
        market_lag_days is not None
        and market_lag_days >= 75
    ):

        final_score = min(
            final_score,
            62.0
        )


    return (
        clamp(
            final_score
        ),
        reliability_score,
        reasons
    )


# ============================================================
# تصنيف القرار النهائي
# ============================================================

def classify_decision(
    decision_score,
    scores,
    momentum_score,
    reliability_score
):

    decision_score = safe_number(
        decision_score
    )

    risk = safe_number(
        scores.get(
            "risk"
        )
    )

    turning = safe_number(
        scores.get(
            "turning_engine"
        )
    )

    data_quality = safe_number(
        scores.get(
            "data_quality"
        )
    )

    freshness = safe_number(
        scores.get(
            "freshness"
        )
    )

    coverage = safe_number(
        scores.get(
            "coverage"
        )
    )

    market_lag_days = safe_number(
        scores.get(
            "market_lag_days"
        )
    )


    # ========================================================
    # بوابات جودة البيانات
    # ========================================================

    if (
        reliability_score is None
        or reliability_score < 50
    ):

        return (
            "LOW_CONFIDENCE",
            "موثوقية البيانات غير كافية لقرار قوي"
        )


    if (
        data_quality is None
        or data_quality < 40
        or freshness is None
        or freshness < 30
    ):

        return (
            "DATA_WARNING",
            "جودة أو حداثة البيانات لا تسمح بقرار قوي"
        )


    if (
        coverage is not None
        and coverage < 50
    ):

        return (
            "DATA_WARNING",
            "تغطية البيانات غير كافية"
        )


    # ========================================================
    # TOP CANDIDATE
    # ========================================================

    if (
        decision_score is not None
        and decision_score >= 82

        and (
            risk is None
            or risk <= 35
        )

        and (
            turning is None
            or turning >= 65
        )

        and data_quality >= 80
        and freshness >= 80

        and (
            coverage is None
            or coverage >= 75
        )

        and (
            market_lag_days is None
            or market_lag_days < 75
        )

        and reliability_score >= 78
    ):

        return (
            "TOP_CANDIDATE",
            "مرشح قوي جدًا ومدعوم ببيانات حديثة وموثوقة"
        )


    # ========================================================
    # STRONG WATCH
    # ========================================================

    if (
        decision_score is not None
        and decision_score >= 70
        and data_quality >= 70
        and freshness >= 65
        and reliability_score >= 68
    ):

        return (
            "STRONG_WATCH",
            "مرشح قوي للمراقبة"
        )


    # ========================================================
    # WATCH
    # ========================================================

    if (
        decision_score is not None
        and decision_score >= 60
    ):

        return (
            "WATCH",
            "يستحق المتابعة مع مراعاة جودة البيانات"
        )


    if (
        decision_score is not None
        and decision_score >= 48
    ):

        return (
            "NEUTRAL",
            "الصورة مختلطة"
        )


    if (
        risk is not None
        and risk >= 65
    ):

        return (
            "HIGH_RISK",
            "إشارات الخطر مرتفعة"
        )


    if (
        momentum_score is not None
        and momentum_score <= 30
    ):

        return (
            "DETERIORATING",
            "الزخم المالي يتدهور"
        )


    return (
        "WEAK",
        "الإشارات الحالية ضعيفة"
    )


# ============================================================
# حفظ النتائج
# ============================================================

def save_decision(
    stock_id,
    period_end,
    decision_score,
    reliability_score,
    momentum_score
):

    calculated_at = datetime.now(
        timezone.utc
    ).isoformat()


    values = {

        DECISION_SCORE_METRIC:
            decision_score,

        DECISION_CONFIDENCE_METRIC:
            reliability_score,

        DECISION_RELIABILITY_METRIC:
            reliability_score,

        DECISION_MOMENTUM_METRIC:
            momentum_score
    }


    records = []


    for metric_name, metric_value in (
        values.items()
    ):

        metric_value = safe_number(
            metric_value
        )

        if metric_value is None:
            continue

        records.append({

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
        })


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


    previous_period = (
        valid_periods[-2]
        if len(valid_periods) >= 2
        else None
    )


    latest_metrics = periods[
        latest_period
    ]


    previous_metrics = (
        periods.get(
            previous_period,
            {}
        )
    )


    latest_scores = score_block(
        latest_metrics
    )


    previous_scores = score_block(
        previous_metrics
    )


    momentum = get_momentum(
        latest_scores,
        previous_scores
    )


    momentum_score = (
        calculate_momentum_score(
            momentum
        )
    )


    consistency_score = (
        calculate_consistency_score(
            latest_scores,
            previous_scores
        )
    )


    (
        decision_score,
        reliability_score,
        reasons
    ) = calculate_decision_score(
        latest_scores,
        momentum_score,
        consistency_score
    )


    state, description = (
        classify_decision(
            decision_score,
            latest_scores,
            momentum_score,
            reliability_score
        )
    )


    saved = save_decision(
        stock_id,
        latest_period,
        decision_score,
        reliability_score,
        momentum_score
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

        "decision_score":
            decision_score,

        "reliability_score":
            reliability_score,

        "state":
            state,

        "description":
            description,

        "opportunity":
            latest_scores.get(
                "opportunity"
            ),

        "risk":
            latest_scores.get(
                "risk"
            ),

        "turning":
            latest_scores.get(
                "turning_engine"
            ),

        "financial_quality":
            latest_scores.get(
                "quality"
            ),

        "balance":
            latest_scores.get(
                "balance"
            ),

        "data_quality":
            latest_scores.get(
                "data_quality"
            ),

        "freshness":
            latest_scores.get(
                "freshness"
            ),

        "coverage":
            latest_scores.get(
                "coverage"
            ),

        "history_quality":
            latest_scores.get(
                "history_quality"
            ),

        "continuity":
            latest_scores.get(
                "continuity"
            ),

        "market_lag_days":
            latest_scores.get(
                "market_lag_days"
            ),

        "momentum_score":
            momentum_score,

        "consistency_score":
            consistency_score,

        "opportunity_delta":
            momentum.get(
                "opportunity_delta"
            ),

        "risk_delta":
            momentum.get(
                "risk_delta"
            ),

        "turning_delta":
            momentum.get(
                "turning_delta"
            ),

        "growth_delta":
            momentum.get(
                "growth_delta"
            ),

        "quality_delta":
            momentum.get(
                "quality_delta"
            ),

        "reasons":
            reasons,

        "saved":
            saved
    }


# ============================================================
# طباعة شركة
# ============================================================

def print_result(result):

    print_header(
        f"🧠 {result.get('symbol')} | "
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
        f"📅 Period: "
        f"{result['latest_period']}",
        flush=True
    )


    print(
        f"🎯 Decision Score: "
        f"{fmt(result['decision_score'])}",
        flush=True
    )


    print(
        f"🧪 Decision Reliability: "
        f"{fmt(result['reliability_score'])}",
        flush=True
    )


    print(
        f"🧭 Decision: "
        f"{result['state']} | "
        f"{result['description']}",
        flush=True
    )


    print_separator()


    print(
        f"Opportunity: "
        f"{fmt(result['opportunity'])}",
        flush=True
    )


    print(
        f"Risk: "
        f"{fmt(result['risk'])}",
        flush=True
    )


    print(
        f"Turning: "
        f"{fmt(result['turning'])}",
        flush=True
    )


    print(
        f"Financial Quality: "
        f"{fmt(result['financial_quality'])}",
        flush=True
    )


    print(
        f"Balance: "
        f"{fmt(result['balance'])}",
        flush=True
    )


    print(
        f"Momentum Score: "
        f"{fmt(result['momentum_score'])}",
        flush=True
    )


    print(
        f"Consistency: "
        f"{fmt(result['consistency_score'])}",
        flush=True
    )


    print_separator()


    print(
        "🧪 DATA QUALITY",
        flush=True
    )


    print(
        f"Data Quality: "
        f"{fmt(result['data_quality'])}",
        flush=True
    )


    print(
        f"Freshness: "
        f"{fmt(result['freshness'])}",
        flush=True
    )


    print(
        f"Coverage: "
        f"{fmt(result['coverage'])}",
        flush=True
    )


    print(
        f"History Quality: "
        f"{fmt(result['history_quality'])}",
        flush=True
    )


    print(
        f"Continuity: "
        f"{fmt(result['continuity'])}",
        flush=True
    )


    print(
        f"Market Lag Days: "
        f"{fmt(result['market_lag_days'])}",
        flush=True
    )


    print_separator()


    print(
        "🚀 MOMENTUM",
        flush=True
    )


    print(
        f"Opportunity Δ: "
        f"{signed_fmt(result['opportunity_delta'])}",
        flush=True
    )


    print(
        f"Risk Δ: "
        f"{signed_fmt(result['risk_delta'])}",
        flush=True
    )


    print(
        f"Turning Δ: "
        f"{signed_fmt(result['turning_delta'])}",
        flush=True
    )


    print(
        f"Growth Δ: "
        f"{signed_fmt(result['growth_delta'])}",
        flush=True
    )


    print(
        f"Quality Δ: "
        f"{signed_fmt(result['quality_delta'])}",
        flush=True
    )


    if result[
        "reasons"
    ]:

        print_separator()

        print(
            "📌 DECISION FACTORS",
            flush=True
        )

        for reason in result[
            "reasons"
        ]:

            print(
                f"- {reason}",
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

        key=lambda result: (

            result.get(
                "decision_score"
            )

            if result.get(
                "decision_score"
            ) is not None

            else -1
        ),

        reverse=True
    )


    print_header(
        "🏆 FINAL DECISION RANKING v2"
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

            f"Decision="
            f"{fmt(result['decision_score'])} | "

            f"Opportunity="
            f"{fmt(result['opportunity'])} | "

            f"Risk="
            f"{fmt(result['risk'])} | "

            f"Turning="
            f"{fmt(result['turning'])} | "

            f"Momentum="
            f"{fmt(result['momentum_score'])} | "

            f"DataQuality="
            f"{fmt(result['data_quality'])} | "

            f"Freshness="
            f"{fmt(result['freshness'])} | "

            f"Reliability="
            f"{fmt(result['reliability_score'])} | "

            f"{result['state']}",

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

def run_decision_engine():

    stocks = get_active_stocks()


    print_header(
        "🧠 FINAL DECISION ENGINE v2"
    )


    print(
        f"🏢 Total Stocks: "
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
            f"🚦 Decision "
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


        print_result(
            result
        )


    print_summary(
        results
    )


if __name__ == "__main__":

    run_decision_engine()
