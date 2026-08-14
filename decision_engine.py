import os
from datetime import datetime, timezone
from supabase import create_client


# ============================================================
# FINAL DECISION ENGINE v1
# ============================================================

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_SECRET_KEY = os.environ.get("SUPABASE_SECRET_KEY")

supabase = create_client(
    SUPABASE_URL,
    SUPABASE_SECRET_KEY
)


# ============================================================
# إعدادات
# ============================================================

DECISION_SCORE_METRIC = "decision_score"
DECISION_CONFIDENCE_METRIC = "decision_confidence"

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


def clamp(value, minimum=0.0, maximum=100.0):

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
    weights = 0.0

    for value, weight in items:

        value = safe_number(value)
        weight = safe_number(weight)

        if (
            value is None
            or weight is None
            or weight <= 0
        ):
            continue

        total += value * weight
        weights += weight

    if weights == 0:
        return None

    return total / weights


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
        .eq("is_active", True)
        .order("priority", desc=True)
        .order("id")
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
        .eq("stock_id", stock_id)
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
            metric_name.startswith(prefix)
            for metric_name in metrics
        ):
            valid.append(
                period_end
            )

    return valid


# ============================================================
# استخراج score block
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

    return current - previous


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
# Momentum Score
# ============================================================

def calculate_momentum_score(momentum):

    score = 50.0
    used = 0

    opportunity_delta = safe_number(
        momentum.get(
            "opportunity_delta"
        )
    )

    if opportunity_delta is not None:

        used += 1

        if opportunity_delta >= 15:
            score += 15

        elif opportunity_delta >= 5:
            score += 8

        elif opportunity_delta <= -15:
            score -= 15

        elif opportunity_delta <= -5:
            score -= 8

    risk_delta = safe_number(
        momentum.get(
            "risk_delta"
        )
    )

    if risk_delta is not None:

        used += 1

        if risk_delta <= -15:
            score += 15

        elif risk_delta <= -5:
            score += 8

        elif risk_delta >= 15:
            score -= 15

        elif risk_delta >= 5:
            score -= 8

    turning_delta = safe_number(
        momentum.get(
            "turning_delta"
        )
    )

    if turning_delta is not None:

        used += 1

        if turning_delta >= 15:
            score += 15

        elif turning_delta >= 5:
            score += 8

        elif turning_delta <= -15:
            score -= 15

        elif turning_delta <= -5:
            score -= 8

    quality_delta = safe_number(
        momentum.get(
            "quality_delta"
        )
    )

    if quality_delta is not None:

        used += 1

        if quality_delta >= 10:
            score += 10

        elif quality_delta <= -10:
            score -= 10

    if used == 0:
        return 50.0

    return clamp(score)


# ============================================================
# Consistency Score
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

    if (
        current_opportunity is not None
        and previous_opportunity is not None
    ):

        if (
            current_opportunity >= 60
            and previous_opportunity >= 60
        ):
            score += 20

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
            score += 15

        elif (
            current_risk >= 60
            and previous_risk >= 60
        ):
            score -= 15

    return clamp(score)


# ============================================================
# Penalty / Bonus
# ============================================================

def calculate_penalty_bonus(
    scores,
    momentum_score
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

    quality = safe_number(
        scores.get(
            "quality"
        )
    )

    balance = safe_number(
        scores.get(
            "balance"
        )
    )

    confidence = safe_number(
        scores.get(
            "confidence"
        )
    )

    if (
        turning_engine is not None
        and turning_engine >= 75
    ):

        bonus += 8

        reasons.append(
            "Turning Point قوي"
        )

    if (
        opportunity is not None
        and opportunity >= 75
        and risk is not None
        and risk <= 30
    ):

        bonus += 8

        reasons.append(
            "Opportunity مرتفع مع Risk منخفض"
        )

    if (
        momentum_score is not None
        and momentum_score >= 70
    ):

        bonus += 6

        reasons.append(
            "الزخم المالي يتحسن"
        )

    if (
        quality is not None
        and quality >= 75
    ):

        bonus += 4

        reasons.append(
            "جودة مالية مرتفعة"
        )

    if (
        risk is not None
        and risk >= 65
    ):

        penalty += 12

        reasons.append(
            "Risk مرتفع"
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
        quality is not None
        and quality <= 30
    ):

        penalty += 8

        reasons.append(
            "جودة مالية ضعيفة"
        )

    if (
        balance is not None
        and balance <= 30
    ):

        penalty += 6

        reasons.append(
            "الميزانية ضعيفة"
        )

    if (
        momentum_score is not None
        and momentum_score <= 30
    ):

        penalty += 8

        reasons.append(
            "الزخم يتدهور"
        )

    if (
        confidence is not None
        and confidence < 60
    ):

        penalty += 8

        reasons.append(
            "ثقة البيانات منخفضة"
        )

    return bonus, penalty, reasons


# ============================================================
# Decision Score
# ============================================================

def calculate_decision_score(
    scores,
    momentum_score,
    consistency_score
):

    opportunity = scores.get(
        "opportunity"
    )

    turning_engine = scores.get(
        "turning_engine"
    )

    turning_base = scores.get(
        "turning_base"
    )

    quality = scores.get(
        "quality"
    )

    balance = scores.get(
        "balance"
    )

    risk = scores.get(
        "risk"
    )

    confidence = (
        safe_number(
            scores.get(
                "confidence"
            )
        )
        or 0.0
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

    raw_score = weighted_average([
        (
            opportunity,
            27
        ),
        (
            turning_score,
            25
        ),
        (
            quality,
            15
        ),
        (
            risk_quality,
            13
        ),
        (
            momentum_score,
            12
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
        return None, 0.0, []

    bonus, penalty, reasons = (
        calculate_penalty_bonus(
            scores,
            momentum_score
        )
    )

    adjusted = (
        raw_score
        + bonus
        - penalty
    )

    adjusted = clamp(
        adjusted
    )

    confidence_factor = (
        0.60
        + (
            clamp(
                confidence
            )
            / 250.0
        )
    )

    final_score = (
        adjusted
        * confidence_factor
    )

    return (
        clamp(final_score),
        clamp(confidence),
        reasons
    )


# ============================================================
# القرار النهائي
# ============================================================

def classify_decision(
    decision_score,
    scores,
    momentum_score
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

    confidence = safe_number(
        scores.get(
            "confidence"
        )
    )

    if (
        confidence is None
        or confidence < 55
    ):

        return (
            "LOW_CONFIDENCE",
            "البيانات غير كافية لقرار قوي"
        )

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
    ):

        return (
            "TOP_CANDIDATE",
            "مرشح قوي جدًا للمتابعة"
        )

    if (
        decision_score is not None
        and decision_score >= 70
    ):

        return (
            "STRONG_WATCH",
            "مرشح قوي للمراقبة"
        )

    if (
        decision_score is not None
        and decision_score >= 60
    ):

        return (
            "WATCH",
            "يستحق المتابعة"
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
        and momentum_score <= 25
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
    confidence
):

    calculated_at = datetime.now(
        timezone.utc
    ).isoformat()

    records = []

    if decision_score is not None:

        records.append({
            "stock_id":
                stock_id,

            "calculated_at":
                calculated_at,

            "metric_name":
                DECISION_SCORE_METRIC,

            "metric_value":
                decision_score,

            "period_end":
                period_end
        })

    if confidence is not None:

        records.append({
            "stock_id":
                stock_id,

            "calculated_at":
                calculated_at,

            "metric_name":
                DECISION_CONFIDENCE_METRIC,

            "metric_value":
                confidence,

            "period_end":
                period_end
        })

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
# تحليل شركة
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

    decision_score, confidence, reasons = (
        calculate_decision_score(
            latest_scores,
            momentum_score,
            consistency_score
        )
    )

    state, description = (
        classify_decision(
            decision_score,
            latest_scores,
            momentum_score
        )
    )

    saved = save_decision(
        stock_id,
        latest_period,
        decision_score,
        confidence
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

        "confidence":
            confidence,

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

        "quality":
            latest_scores.get(
                "quality"
            ),

        "balance":
            latest_scores.get(
                "balance"
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
        f"🧪 Confidence: "
        f"{fmt(result['confidence'])}",
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
        f"Quality: "
        f"{fmt(result['quality'])}",
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
        "🚀 Momentum",
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

    if result["reasons"]:

        print_separator()

        print(
            "📌 Decision Factors",
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
        "🏆 FINAL DECISION RANKING"
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

def run_decision_engine():

    stocks = get_active_stocks()

    print_header(
        "🧠 FINAL DECISION ENGINE v1"
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
