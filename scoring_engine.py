import os
from datetime import datetime, timezone
from supabase import create_client


# ============================================================
# HISTORICAL SCORING ENGINE v3
#
# SAFE DATA GATE
#
# أهم التغييرات:
#
# 1) نقص البيانات لا يتحول إلى Opportunity وهمي.
# 2) REIT لديه Data Gate مستقل.
# 3) لا يعاد توزيع الأوزان بشكل مضلل عند غياب معظم المكونات.
# 4) تنظيف درجات Scoring القديمة باستخدام UPSERT + NULL
#    بدل DELETE.
# 5) Missing data = NOT SCORED وليس Score=0.
# 6) Standard / Bank / Insurance تبقى تعمل بنفس المنطق.
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


ENGINE_NAME = (
    "HISTORICAL SCORING ENGINE v3 | SAFE DATA GATE"
)


# ============================================================
# Scoring metric names
#
# تستخدم لتنظيف النتائج القديمة قبل إعادة الحساب.
# ============================================================


SCORING_METRIC_NAMES = [
    "score_growth_score",
    "score_quality_score",
    "score_cash_score",
    "score_balance_score",
    "score_confidence_score",
    "score_opportunity_score",
    "score_risk_score",
    "score_turning_point_score",
    "score_data_gate_passed",
    "score_components_available",
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

    for item_value, weight in items:

        item_value = safe_number(
            item_value
        )

        weight = safe_number(
            weight
        )

        if (
            item_value is None
            or weight is None
            or weight <= 0
        ):
            continue

        total += (
            item_value
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

    value = safe_number(
        value
    )

    if value is None:
        return "N/A"

    return f"{value:.2f}"


def signed_fmt(value):

    value = safe_number(
        value
    )

    if value is None:
        return "N/A"

    return f"{value:+.2f}"


# ============================================================
# تحويل المؤشرات إلى Scores
# ============================================================


def score_growth(value):

    value = safe_number(
        value
    )

    if value is None:
        return None

    if value >= 20:
        return 100.0

    if value >= 10:
        return 80.0

    if value >= 0:
        return 60.0

    if value >= -10:
        return 35.0

    return 10.0


def score_margin_change(value):

    value = safe_number(
        value
    )

    if value is None:
        return None

    if value >= 3:
        return 100.0

    if value >= 1:
        return 80.0

    if value >= 0:
        return 60.0

    if value >= -2:
        return 35.0

    return 10.0


def score_high_good(
    value,
    excellent,
    good,
    weak
):

    value = safe_number(
        value
    )

    if value is None:
        return None

    if value >= excellent:
        return 100.0

    if value >= good:
        return 80.0

    if value >= weak:
        return 55.0

    return 20.0


def score_low_good(
    value,
    excellent,
    acceptable,
    high
):

    value = safe_number(
        value
    )

    if value is None:
        return None

    if value <= excellent:
        return 100.0

    if value <= acceptable:
        return 75.0

    if value <= high:
        return 45.0

    return 15.0


def score_cash_conversion(value):

    value = safe_number(
        value
    )

    if value is None:
        return None

    if value >= 1.20:
        return 100.0

    if value >= 1.00:
        return 85.0

    if value >= 0.80:
        return 65.0

    if value >= 0.50:
        return 35.0

    return 10.0


def inverse_growth_score(value):

    value = safe_number(
        value
    )

    if value is None:
        return None

    return score_growth(
        -value
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
        .order("id")
        .execute()
    )

    return response.data or []


def get_stock_metrics(stock_id):

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
# تنظيف Scoring القديم
#
# لا نستخدم DELETE.
# نكتب NULL فوق القيم القديمة عبر UPSERT.
#
# organize_metrics يتجاهل NULL لاحقًا.
# ============================================================


def clear_old_scoring_metrics(
    stock_id,
    period_end
):

    calculated_at = datetime.now(
        timezone.utc
    ).isoformat()

    records = []

    for metric_name in SCORING_METRIC_NAMES:

        records.append({
            "stock_id":
                stock_id,

            "calculated_at":
                calculated_at,

            "metric_name":
                metric_name,

            "metric_value":
                None,

            "period_end":
                period_end
        })

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


MODEL_PREFIX = {
    "standard":
        "q_",

    "bank":
        "bank_q_",

    "insurance":
        "insurance_q_",

    "reit":
        "reit_q_"
}


# ============================================================
# Period validation
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

        if not any(
            metric_name.startswith(
                prefix
            )
            for metric_name in metrics
        ):
            continue

        valid.append(
            period_end
        )

    return valid


# ============================================================
# Standard Scoring
# ============================================================


def score_standard(metrics):

    growth = weighted_average([
        (
            score_growth(
                metrics.get(
                    "q_revenue_growth_yoy"
                )
            ),
            30
        ),
        (
            score_growth(
                metrics.get(
                    "q_net_income_growth_yoy"
                )
            ),
            35
        ),
        (
            score_growth(
                metrics.get(
                    "q_ocf_growth_yoy"
                )
            ),
            15
        ),
        (
            score_growth(
                metrics.get(
                    "q_fcf_growth_yoy"
                )
            ),
            20
        )
    ])

    quality = weighted_average([
        (
            score_margin_change(
                metrics.get(
                    "q_gross_margin_change_yoy"
                )
            ),
            20
        ),
        (
            score_margin_change(
                metrics.get(
                    "q_operating_margin_change_yoy"
                )
            ),
            25
        ),
        (
            score_margin_change(
                metrics.get(
                    "q_net_margin_change_yoy"
                )
            ),
            25
        ),
        (
            score_cash_conversion(
                metrics.get(
                    "q_cash_conversion"
                )
            ),
            30
        )
    ])

    cash = weighted_average([
        (
            score_cash_conversion(
                metrics.get(
                    "q_cash_conversion"
                )
            ),
            40
        ),
        (
            score_growth(
                metrics.get(
                    "q_ocf_growth_yoy"
                )
            ),
            30
        ),
        (
            score_growth(
                metrics.get(
                    "q_fcf_growth_yoy"
                )
            ),
            30
        )
    ])

    balance = weighted_average([
        (
            score_low_good(
                metrics.get(
                    "q_debt_to_equity"
                ),
                excellent=0.50,
                acceptable=1.00,
                high=2.00
            ),
            35
        ),
        (
            score_high_good(
                metrics.get(
                    "q_current_ratio"
                ),
                excellent=1.50,
                good=1.00,
                weak=0.80
            ),
            25
        ),
        (
            inverse_growth_score(
                metrics.get(
                    "q_debt_growth_qoq"
                )
            ),
            20
        ),
        (
            score_growth(
                metrics.get(
                    "q_cash_growth_qoq"
                )
            ),
            20
        )
    ])

    confidence = (
        clamp(
            metrics.get(
                "data_confidence_score"
            )
        )
        or 0.0
    )

    return {
        "growth_score":
            growth,

        "quality_score":
            quality,

        "cash_score":
            cash,

        "balance_score":
            balance,

        "confidence_score":
            confidence,

        "data_gate_passed":
            1.0
    }


# ============================================================
# Bank Scoring
# ============================================================


def score_bank(metrics):

    growth = weighted_average([
        (
            score_growth(
                metrics.get(
                    "bank_q_revenue_growth_yoy"
                )
            ),
            30
        ),
        (
            score_growth(
                metrics.get(
                    "bank_q_net_income_growth_yoy"
                )
            ),
            35
        ),
        (
            score_growth(
                metrics.get(
                    "bank_q_assets_growth_yoy"
                )
            ),
            20
        ),
        (
            score_growth(
                metrics.get(
                    "bank_q_equity_growth_yoy"
                )
            ),
            15
        )
    ])

    quality = weighted_average([
        (
            score_high_good(
                metrics.get(
                    "bank_ttm_roe"
                ),
                excellent=20,
                good=15,
                weak=10
            ),
            45
        ),
        (
            score_high_good(
                metrics.get(
                    "bank_ttm_roa"
                ),
                excellent=2.00,
                good=1.50,
                weak=1.00
            ),
            30
        ),
        (
            score_margin_change(
                metrics.get(
                    "bank_q_profit_margin_change_yoy"
                )
            ),
            25
        )
    ])

    balance = weighted_average([
        (
            score_high_good(
                metrics.get(
                    "bank_q_equity_to_assets"
                ),
                excellent=15,
                good=10,
                weak=7
            ),
            60
        ),
        (
            score_growth(
                metrics.get(
                    "bank_q_equity_growth_yoy"
                )
            ),
            40
        )
    ])

    confidence = (
        clamp(
            metrics.get(
                "bank_data_confidence_score"
            )
        )
        or 0.0
    )

    return {
        "growth_score":
            growth,

        "quality_score":
            quality,

        "cash_score":
            None,

        "balance_score":
            balance,

        "confidence_score":
            confidence,

        "data_gate_passed":
            1.0
    }


# ============================================================
# Insurance Scoring
# ============================================================


def score_insurance(metrics):

    growth = weighted_average([
        (
            score_growth(
                metrics.get(
                    "insurance_q_revenue_growth_yoy"
                )
            ),
            30
        ),
        (
            score_growth(
                metrics.get(
                    "insurance_q_net_income_growth_yoy"
                )
            ),
            35
        ),
        (
            score_growth(
                metrics.get(
                    "insurance_q_equity_growth_yoy"
                )
            ),
            20
        ),
        (
            score_growth(
                metrics.get(
                    "insurance_q_eps_growth_yoy"
                )
            ),
            15
        )
    ])

    quality = weighted_average([
        (
            score_high_good(
                metrics.get(
                    "insurance_ttm_roe"
                ),
                excellent=20,
                good=15,
                weak=10
            ),
            40
        ),
        (
            score_high_good(
                metrics.get(
                    "insurance_ttm_roa"
                ),
                excellent=4,
                good=2,
                weak=1
            ),
            25
        ),
        (
            score_margin_change(
                metrics.get(
                    "insurance_q_profit_margin_change_yoy"
                )
            ),
            20
        ),
        (
            score_cash_conversion(
                metrics.get(
                    "insurance_ttm_cash_conversion"
                )
            ),
            15
        )
    ])

    cash = weighted_average([
        (
            score_cash_conversion(
                metrics.get(
                    "insurance_ttm_cash_conversion"
                )
            ),
            60
        ),
        (
            score_growth(
                metrics.get(
                    "insurance_q_ocf_growth_yoy"
                )
            ),
            40
        )
    ])

    balance = weighted_average([
        (
            score_high_good(
                metrics.get(
                    "insurance_q_equity_to_assets"
                ),
                excellent=25,
                good=15,
                weak=8
            ),
            70
        ),
        (
            score_growth(
                metrics.get(
                    "insurance_q_equity_growth_yoy"
                )
            ),
            30
        )
    ])

    confidence = (
        clamp(
            metrics.get(
                "insurance_data_confidence_score"
            )
        )
        or 0.0
    )

    return {
        "growth_score":
            growth,

        "quality_score":
            quality,

        "cash_score":
            cash,

        "balance_score":
            balance,

        "confidence_score":
            confidence,

        "data_gate_passed":
            1.0
    }


# ============================================================
# REIT SAFE DATA GATE
# ============================================================


def reit_data_gate(metrics):

    usable_flag = safe_number(
        metrics.get(
            "reit_data_usable_flag"
        )
    )

    current_coverage = safe_number(
        metrics.get(
            "reit_data_current_coverage_pct"
        )
    )

    if usable_flag is not None:

        return (
            usable_flag >= 1.0
            and (
                current_coverage is None
                or current_coverage >= 50.0
            )
        )

    if current_coverage is not None:

        return (
            current_coverage >= 50.0
        )

    return False


# ============================================================
# REIT Scoring
# ============================================================


def score_reit(metrics):

    confidence = (
        clamp(
            metrics.get(
                "reit_data_confidence_score"
            )
        )
        or 0.0
    )

    gate_passed = reit_data_gate(
        metrics
    )

    if not gate_passed:

        return {
            "growth_score":
                None,

            "quality_score":
                None,

            "cash_score":
                None,

            "balance_score":
                None,

            "confidence_score":
                confidence,

            "data_gate_passed":
                0.0
        }

    growth = weighted_average([
        (
            score_growth(
                metrics.get(
                    "reit_q_revenue_growth_yoy"
                )
            ),
            30
        ),
        (
            score_growth(
                metrics.get(
                    "reit_q_operating_income_growth_yoy"
                )
            ),
            30
        ),
        (
            score_growth(
                metrics.get(
                    "reit_q_net_income_growth_yoy"
                )
            ),
            25
        ),
        (
            score_growth(
                metrics.get(
                    "reit_q_equity_growth_yoy"
                )
            ),
            15
        )
    ])

    quality = weighted_average([
        (
            score_margin_change(
                metrics.get(
                    "reit_q_operating_margin_change_yoy"
                )
            ),
            35
        ),
        (
            score_margin_change(
                metrics.get(
                    "reit_q_net_margin_change_yoy"
                )
            ),
            25
        ),
        (
            score_cash_conversion(
                metrics.get(
                    "reit_ttm_cash_conversion"
                )
            ),
            40
        )
    ])

    cash = weighted_average([
        (
            score_cash_conversion(
                metrics.get(
                    "reit_ttm_cash_conversion"
                )
            ),
            60
        ),
        (
            score_growth(
                metrics.get(
                    "reit_q_ocf_growth_yoy"
                )
            ),
            40
        )
    ])

    balance = weighted_average([
        (
            score_low_good(
                metrics.get(
                    "reit_q_debt_to_assets"
                ),
                excellent=25,
                acceptable=35,
                high=50
            ),
            60
        ),
        (
            inverse_growth_score(
                metrics.get(
                    "reit_q_debt_growth_yoy"
                )
            ),
            40
        )
    ])

    return {
        "growth_score":
            growth,

        "quality_score":
            quality,

        "cash_score":
            cash,

        "balance_score":
            balance,

        "confidence_score":
            confidence,

        "data_gate_passed":
            1.0
    }


# ============================================================
# Router
# ============================================================


def calculate_component_scores(
    analysis_model,
    metrics
):

    if analysis_model == "standard":
        return score_standard(
            metrics
        )

    if analysis_model == "bank":
        return score_bank(
            metrics
        )

    if analysis_model == "insurance":
        return score_insurance(
            metrics
        )

    if analysis_model == "reit":
        return score_reit(
            metrics
        )

    return None


# ============================================================
# عدد المكونات المتاحة
# ============================================================


def count_available_components(
    components
):

    names = [
        "growth_score",
        "quality_score",
        "cash_score",
        "balance_score"
    ]

    return sum(
        1
        for name in names
        if safe_number(
            components.get(
                name
            )
        ) is not None
    )


# ============================================================
# الدرجات النهائية
# ============================================================


def calculate_final_scores(
    components,
    analysis_model
):

    growth = safe_number(
        components.get(
            "growth_score"
        )
    )

    quality = safe_number(
        components.get(
            "quality_score"
        )
    )

    cash = safe_number(
        components.get(
            "cash_score"
        )
    )

    balance = safe_number(
        components.get(
            "balance_score"
        )
    )

    confidence = (
        safe_number(
            components.get(
                "confidence_score"
            )
        )
        or 0.0
    )

    data_gate_passed = (
        safe_number(
            components.get(
                "data_gate_passed"
            )
        )
        or 0.0
    )

    available_components = (
        count_available_components(
            components
        )
    )

    if (
        analysis_model == "reit"
        and data_gate_passed < 1.0
    ):

        return {
            "opportunity_score":
                None,

            "risk_score":
                None,

            "turning_point_score":
                None,

            "components_available":
                float(
                    available_components
                )
        }

    opportunity_raw = None

    if available_components >= 2:

        opportunity_raw = weighted_average([
            (
                growth,
                35
            ),
            (
                quality,
                30
            ),
            (
                cash,
                20
            ),
            (
                balance,
                15
            )
        ])

    risk_inputs = sum(
        1
        for item in [
            quality,
            cash,
            balance
        ]
        if item is not None
    )

    risk_raw = None

    if risk_inputs >= 2:

        risk_raw = weighted_average([
            (
                (
                    100 - quality
                    if quality is not None
                    else None
                ),
                40
            ),
            (
                (
                    100 - cash
                    if cash is not None
                    else None
                ),
                30
            ),
            (
                (
                    100 - balance
                    if balance is not None
                    else None
                ),
                30
            )
        ])

    turning_raw = None

    if (
        growth is not None
        and quality is not None
    ):

        turning_raw = weighted_average([
            (
                growth,
                45
            ),
            (
                quality,
                35
            ),
            (
                cash,
                20
            )
        ])

    confidence_clamped = (
        clamp(
            confidence
        )
        or 0.0
    )

    confidence_factor = (
        0.50
        + (
            confidence_clamped
            / 200.0
        )
    )

    opportunity = (
        opportunity_raw
        * confidence_factor
        if opportunity_raw is not None
        else None
    )

    turning_point = (
        turning_raw
        * confidence_factor
        if turning_raw is not None
        else None
    )

    return {
        "opportunity_score":
            clamp(
                opportunity
            ),

        "risk_score":
            clamp(
                risk_raw
            ),

        "turning_point_score":
            clamp(
                turning_point
            ),

        "components_available":
            float(
                available_components
            )
    }


# ============================================================
# حفظ Scoring
# ============================================================


def save_scoring_metrics(
    stock_id,
    period_end,
    scores
):

    calculated_at = datetime.now(
        timezone.utc
    ).isoformat()

    records = []

    for (
        metric_name,
        metric_value
    ) in scores.items():

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
                f"score_{metric_name}",

            "metric_value":
                metric_value,

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

    return len(
        records
    )


# ============================================================
# حساب تاريخ الشركة
# ============================================================


def score_stock_history(stock):

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

    rows = get_stock_metrics(
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
            "symbol":
                symbol,

            "company_name":
                company_name,

            "analysis_model":
                analysis_model,

            "status":
                "no_periods",

            "history":
                [],

            "saved":
                0
        }

    history = []
    total_saved = 0

    for period_end in valid_periods:

        metrics = periods[
            period_end
        ]

        # ====================================================
        # تنظيف النتائج القديمة بدون DELETE
        # ====================================================

        clear_old_scoring_metrics(
            stock_id,
            period_end
        )

        components = (
            calculate_component_scores(
                analysis_model,
                metrics
            )
        )

        if components is None:
            continue

        final_scores = calculate_final_scores(
            components,
            analysis_model
        )

        all_scores = {}

        all_scores.update(
            components
        )

        all_scores.update(
            final_scores
        )

        saved = save_scoring_metrics(
            stock_id,
            period_end,
            all_scores
        )

        total_saved += saved

        history.append({
            "period_end":
                period_end,

            "growth":
                all_scores.get(
                    "growth_score"
                ),

            "quality":
                all_scores.get(
                    "quality_score"
                ),

            "cash":
                all_scores.get(
                    "cash_score"
                ),

            "balance":
                all_scores.get(
                    "balance_score"
                ),

            "confidence":
                all_scores.get(
                    "confidence_score"
                ),

            "data_gate":
                all_scores.get(
                    "data_gate_passed"
                ),

            "components_available":
                all_scores.get(
                    "components_available"
                ),

            "opportunity":
                all_scores.get(
                    "opportunity_score"
                ),

            "risk":
                all_scores.get(
                    "risk_score"
                ),

            "turning":
                all_scores.get(
                    "turning_point_score"
                )
        })

    if not history:

        return {
            "symbol":
                symbol,

            "company_name":
                company_name,

            "analysis_model":
                analysis_model,

            "status":
                "no_scores",

            "history":
                [],

            "saved":
                total_saved
        }

    latest = history[
        -1
    ]

    if (
        analysis_model == "reit"
        and safe_number(
            latest.get(
                "data_gate"
            )
        ) == 0.0
    ):

        status = (
            "limited_data"
        )

    else:

        status = (
            "success"
        )

    return {
        "symbol":
            symbol,

        "company_name":
            company_name,

        "analysis_model":
            analysis_model,

        "status":
            status,

        "history":
            history,

        "saved":
            total_saved
    }


# ============================================================
# Momentum
# ============================================================


def calculate_history_momentum(
    history
):

    if len(
        history
    ) < 2:

        return {
            "opportunity_delta":
                None,

            "risk_delta":
                None,

            "turning_delta":
                None,

            "growth_delta":
                None,

            "quality_delta":
                None
        }

    current = history[
        -1
    ]

    previous = history[
        -2
    ]

    def delta(key):

        current_value = safe_number(
            current.get(
                key
            )
        )

        previous_value = safe_number(
            previous.get(
                key
            )
        )

        if (
            current_value is None
            or previous_value is None
        ):
            return None

        return (
            current_value
            - previous_value
        )

    return {
        "opportunity_delta":
            delta(
                "opportunity"
            ),

        "risk_delta":
            delta(
                "risk"
            ),

        "turning_delta":
            delta(
                "turning"
            ),

        "growth_delta":
            delta(
                "growth"
            ),

        "quality_delta":
            delta(
                "quality"
            )
    }


# ============================================================
# Trend
# ============================================================


def calculate_trend(
    history
):

    if len(
        history
    ) < 3:
        return "INSUFFICIENT_HISTORY"

    recent = history[
        -3:
    ]

    opportunities = [
        safe_number(
            item.get(
                "opportunity"
            )
        )
        for item in recent
    ]

    risks = [
        safe_number(
            item.get(
                "risk"
            )
        )
        for item in recent
    ]

    if any(
        value is None
        for value in opportunities
    ):

        return "INSUFFICIENT_DATA"

    if (
        opportunities[
            0
        ]
        < opportunities[
            1
        ]
        < opportunities[
            2
        ]
    ):

        if (
            all(
                value is not None
                for value in risks
            )
            and risks[
                2
            ]
            <= risks[
                0
            ]
        ):

            return (
                "IMPROVING_PERSISTENT"
            )

        return "IMPROVING"

    if (
        opportunities[
            0
        ]
        > opportunities[
            1
        ]
        > opportunities[
            2
        ]
    ):

        return "DETERIORATING"

    return "MIXED"


# ============================================================
# Main
# ============================================================


def run_scoring_engine():

    stocks = get_active_stocks()

    print(
        "\n"
        + "=" * 84,
        flush=True
    )

    print(
        f"🎯 {ENGINE_NAME}",
        flush=True
    )

    print(
        "=" * 84,
        flush=True
    )

    print(
        "🛡 Missing data does not generate investment scores",
        flush=True
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
            + "-" * 84,
            flush=True
        )

        print(
            f"🚦 Scoring "
            f"{index}/{len(stocks)} | "
            f"{stock['symbol']}",
            flush=True
        )

        try:

            result = score_stock_history(
                stock
            )

        except Exception as error:

            result = {
                "symbol":
                    stock[
                        "symbol"
                    ],

                "company_name":
                    stock.get(
                        "company_name"
                    ),

                "analysis_model":
                    stock.get(
                        "analysis_model"
                    ),

                "status":
                    "error",

                "history":
                    [],

                "saved":
                    0,

                "error":
                    str(
                        error
                    )
            }

            print(
                f"🔴 "
                f"{stock['symbol']} | "
                f"{type(error).__name__}: "
                f"{error}",
                flush=True
            )

        if result.get(
            "status"
        ) in [
            "success",
            "limited_data"
        ]:

            history = result[
                "history"
            ]

            latest = history[
                -1
            ]

            momentum = (
                calculate_history_momentum(
                    history
                )
            )

            trend = calculate_trend(
                history
            )

            result[
                "latest"
            ] = latest

            result[
                "momentum"
            ] = momentum

            result[
                "trend"
            ] = trend

            print(
                f"📚 Historical Periods: "
                f"{len(history)}",
                flush=True
            )

            print(
                f"📅 Latest: "
                f"{latest['period_end']}",
                flush=True
            )

            print(
                f"🛡 Data Gate: "
                f"{fmt(latest['data_gate'])}",
                flush=True
            )

            print(
                f"📦 Components Available: "
                f"{fmt(latest['components_available'])}",
                flush=True
            )

            print(
                f"🎯 Opportunity: "
                f"{fmt(latest['opportunity'])}",
                flush=True
            )

            print(
                f"🔴 Risk: "
                f"{fmt(latest['risk'])}",
                flush=True
            )

            print(
                f"🧭 Turning: "
                f"{fmt(latest['turning'])}",
                flush=True
            )

            print(
                f"🧬 Trend: "
                f"{trend}",
                flush=True
            )

        results.append(
            result
        )

    successful = [
        result

        for result in results

        if (
            result.get(
                "status"
            )
            == "success"

            and safe_number(
                result.get(
                    "latest",
                    {}
                ).get(
                    "opportunity"
                )
            )
            is not None
        )
    ]

    successful.sort(
        key=lambda result:
            safe_number(
                result[
                    "latest"
                ][
                    "opportunity"
                ]
            ),
        reverse=True
    )

    print(
        "\n"
        + "=" * 84,
        flush=True
    )

    print(
        "🏆 LATEST OPPORTUNITY RANKING",
        flush=True
    )

    print(
        "=" * 84,
        flush=True
    )

    for rank, result in enumerate(
        successful,
        start=1
    ):

        latest = result[
            "latest"
        ]

        momentum = result[
            "momentum"
        ]

        print(
            f"{rank:02d}. "
            f"{result['symbol']} | "
            f"{result['company_name']} | "
            f"{result['analysis_model']} | "
            f"Opportunity="
            f"{fmt(latest['opportunity'])} | "
            f"Risk="
            f"{fmt(latest['risk'])} | "
            f"Turning="
            f"{fmt(latest['turning'])} | "
            f"OppΔ="
            f"{signed_fmt(momentum['opportunity_delta'])} | "
            f"RiskΔ="
            f"{signed_fmt(momentum['risk_delta'])} | "
            f"Trend="
            f"{result['trend']}",
            flush=True
        )

    limited = [
        result

        for result in results

        if result.get(
            "status"
        )
        == "limited_data"
    ]

    failures = [
        result

        for result in results

        if result.get(
            "status"
        )
        not in [
            "success",
            "limited_data"
        ]
    ]

    total_saved = sum(
        result.get(
            "saved",
            0
        )
        for result in results
    )

    print(
        "\n"
        + "=" * 84,
        flush=True
    )

    print(
        "📊 HISTORICAL SCORING SUMMARY v3",
        flush=True
    )

    print(
        "=" * 84,
        flush=True
    )

    print(
        f"🟢 Scored: "
        f"{len(successful)}",
        flush=True
    )

    print(
        f"🟡 Limited Data: "
        f"{len(limited)}",
        flush=True
    )

    print(
        f"🔴 Failed/Skipped: "
        f"{len(failures)}",
        flush=True
    )

    print(
        f"💾 Score Records Saved: "
        f"{total_saved}",
        flush=True
    )

    if limited:

        print(
            "\n🟡 LIMITED DATA:",
            flush=True
        )

        for result in limited:

            latest = result.get(
                "latest",
                {}
            )

            print(
                f"{result.get('symbol')} | "
                f"{result.get('company_name')} | "
                f"{result.get('analysis_model')} | "
                f"Confidence="
                f"{fmt(latest.get('confidence'))} | "
                f"Opportunity=N/A",
                flush=True
            )

    if failures:

        print(
            "\n⚠️ Failed / Skipped:",
            flush=True
        )

        for result in failures:

            print(
                f"{result.get('symbol')} | "
                f"{result.get('analysis_model')} | "
                f"{result.get('status')} | "
                f"{result.get('error', '')}",
                flush=True
            )

    print(
        "=" * 84,
        flush=True
    )


if __name__ == "__main__":

    run_scoring_engine()
