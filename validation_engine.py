import os
from supabase import create_client


# ============================================================
# VALIDATION ENGINE v1.2.3
#
# الهدف:
# - التحقق من تكامل طبقات التحليل:
#   Scoring / Signal / Turning / Data Quality / Decision
# - احترام Turning Point Engine v2.0.2 كمصدر الحقيقة
#   لحالة التحول النهائية.
# - استخدام Turning Engine Delta كمعلومة زخم فقط، وليس
#   لإعادة تصنيف الحالة.
# - دعم standard / bank / insurance / reit
#
# READ ONLY
# لا يكتب أو يعدل أي بيانات.
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

ENGINE_VERSION = "1.2.3"

DEFAULT_VALIDATION_SYMBOLS = [
    "4030.SR",  # البحري
    "4190.SR",  # جرير
    "8010.SR",  # التعاونية
    "1831.SR",  # مهارة
    "1111.SR",  # مجموعة تداول السعودية
    "2283.SR",  # المطاحن الأولى
    "7203.SR",  # علم
    "1150.SR"   # مصرف الإنماء
]


MODEL_PREFIX = {
    "standard": "q_",
    "bank": "bank_q_",
    "insurance": "insurance_q_",
    "reit": "reit_q_"
}


MODEL_SIGNAL_NET = {
    "standard": "engine22_net_score",
    "bank": "bank_signal_net_score",
    "insurance": "insurance_signal_net_score",
    "reit": "engine22_net_score"
}


MODEL_SIGNAL_CONFIDENCE = {
    "standard": "engine22_confidence_score",
    "bank": "bank_signal_confidence_score",
    "insurance": "insurance_signal_confidence_score",
    "reit": "engine22_confidence_score"
}


TURNING_STATE_MAP = {
    0: "LOW_CONFIDENCE",
    1: "WEAK",
    2: "DETERIORATING",
    3: "NEUTRAL",
    4: "IMPROVING",
    5: "IMPROVING_LIMITED_HISTORY",
    6: "EARLY_TURNING_POINT",
    7: "STRONG_TURNING_POINT",
    8: "STRONG_CONTINUATION"
}


TURNING_STATE_DESCRIPTION = {
    "LOW_CONFIDENCE":
        "الثقة أو التاريخ المقارن غير كافيين",

    "WEAK":
        "لا توجد إشارات تحول إيجابي كافية",

    "DETERIORATING":
        "عدة مؤشرات مالية تتدهور",

    "NEUTRAL":
        "لا يوجد تحول واضح حتى الآن",

    "IMPROVING":
        "تحسن مستمر دون تحقق شروط Turning Point الحقيقي",

    "IMPROVING_LIMITED_HISTORY":
        "تحسن ظاهر لكن الاتساع التاريخي المقارن ما زال محدودًا",

    "EARLY_TURNING_POINT":
        "بوادر تحول مالي حقيقية من قاعدة أضعف",

    "STRONG_TURNING_POINT":
        "تحول مالي قوي ومتعدد الإشارات",

    "STRONG_CONTINUATION":
        "قوة مستمرة وليست Turning Point جديدة"
}


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


def fmt(
    value,
    decimals=2
):

    value = safe_number(
        value
    )

    if value is None:
        return "N/A"

    return f"{value:.{decimals}f}"


def signed_fmt(
    value,
    decimals=2
):

    value = safe_number(
        value
    )

    if value is None:
        return "N/A"

    return f"{value:+.{decimals}f}"


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


def print_header(title):

    print(
        "\n"
        + "=" * 96,
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


def get_validation_symbols():

    env_value = os.environ.get(
        "VALIDATION_SYMBOLS"
    )

    if not env_value:
        return DEFAULT_VALIDATION_SYMBOLS

    symbols = [
        symbol.strip()
        for symbol in env_value.split(",")
        if symbol.strip()
    ]

    return (
        symbols
        if symbols
        else DEFAULT_VALIDATION_SYMBOLS
    )


# ============================================================
# Supabase Reads
# ============================================================

def get_stocks(symbols):

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
        .in_(
            "symbol",
            symbols
        )
        .execute()
    )

    rows = (
        response.data
        or []
    )

    stock_map = {
        row["symbol"]: row
        for row in rows
    }

    ordered = []

    for symbol in symbols:

        stock = stock_map.get(
            symbol
        )

        if stock:

            ordered.append(
                stock
            )

        else:

            print(
                f"⚠️ لم يتم العثور على "
                f"{symbol} في stocks",
                flush=True
            )

    return ordered


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
# Valid Financial Periods
# ============================================================

def find_latest_periods(
    periods,
    analysis_model
):

    prefix = MODEL_PREFIX.get(
        analysis_model
    )

    if prefix is None:
        return None, None

    valid_dates = []

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

            valid_dates.append(
                period_end
            )

    if not valid_dates:
        return None, None

    latest = valid_dates[-1]

    previous = (
        valid_dates[-2]
        if len(valid_dates) >= 2
        else None
    )

    return latest, previous


# ============================================================
# Scoring Block
# ============================================================

def get_score_block(metrics):

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

        "confidence":
            safe_number(
                metrics.get(
                    "score_confidence_score"
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

        "base_turning":
            safe_number(
                metrics.get(
                    "score_turning_point_score"
                )
            )
    }


# ============================================================
# Current Validation State
# ============================================================

def classify_score(
    opportunity,
    risk,
    confidence
):

    opportunity = safe_number(
        opportunity
    )

    risk = safe_number(
        risk
    )

    confidence = safe_number(
        confidence
    )

    if (
        confidence is None
        or confidence < 60
    ):

        return (
            "LOW_CONFIDENCE",
            "البيانات غير كافية لحكم قوي"
        )

    if (
        opportunity is not None
        and opportunity >= 75
        and risk is not None
        and risk <= 30
    ):

        return (
            "STRONG",
            "القوة والفرصة المالية الحالية مرتفعتان"
        )

    if (
        opportunity is not None
        and opportunity >= 60
        and risk is not None
        and risk <= 45
    ):

        return (
            "POSITIVE",
            "الصورة المالية إيجابية"
        )

    if (
        risk is not None
        and risk >= 60
    ):

        return (
            "HIGH_RISK",
            "إشارات الخطر مرتفعة"
        )

    if (
        opportunity is not None
        and opportunity < 45
    ):

        return (
            "WEAK",
            "الفرصة المالية الحالية ضعيفة"
        )

    return (
        "NEUTRAL",
        "الصورة متوازنة أو مختلطة"
    )


# ============================================================
# Signal Layer
# ============================================================

def get_signal_layer(
    metrics,
    analysis_model
):

    signal_metric = (
        MODEL_SIGNAL_NET.get(
            analysis_model
        )
    )

    confidence_metric = (
        MODEL_SIGNAL_CONFIDENCE.get(
            analysis_model
        )
    )

    if not signal_metric:

        return {
            "available": False,
            "source": "N/A",
            "net_score": None,
            "confidence": None
        }

    net_score = safe_number(
        metrics.get(
            signal_metric
        )
    )

    signal_confidence = None

    if confidence_metric:

        signal_confidence = safe_number(
            metrics.get(
                confidence_metric
            )
        )

    return {
        "available":
            net_score is not None,

        "source":
            signal_metric,

        "net_score":
            net_score,

        "confidence":
            signal_confidence
    }


# ============================================================
# Turning Layer v2.0.2
# ============================================================

def get_turning_layer(metrics):

    score = safe_number(
        metrics.get(
            "turning_engine_score"
        )
    )

    state_code = safe_number(
        metrics.get(
            "turning_engine_state_code"
        )
    )

    confidence = safe_number(
        metrics.get(
            "turning_engine_confidence_score"
        )
    )

    continuity = safe_number(
        metrics.get(
            "turning_engine_comparability_continuity_score"
        )
    )

    breadth = safe_number(
        metrics.get(
            "turning_engine_comparability_breadth_score"
        )
    )

    common_inputs = safe_number(
        metrics.get(
            "turning_engine_common_inputs"
        )
    )

    newly_available = safe_number(
        metrics.get(
            "turning_engine_newly_available_inputs"
        )
    )

    dropped_inputs = safe_number(
        metrics.get(
            "turning_engine_dropped_inputs"
        )
    )

    state = None

    if state_code is not None:

        state = TURNING_STATE_MAP.get(
            int(round(state_code))
        )

    return {
        "available":
            score is not None,

        "source":
            "turning_engine_score",

        "score":
            score,

        "state_code":
            state_code,

        "state":
            state,

        "confidence":
            confidence,

        "continuity":
            continuity,

        "breadth":
            breadth,

        "common_inputs":
            common_inputs,

        "newly_available_inputs":
            newly_available,

        "dropped_inputs":
            dropped_inputs
    }


def validate_turning_layer(
    latest_turning,
    previous_turning
):

    # --------------------------------------------------------
    # v1.2.3:
    # Turning Point Engine state_code هو مصدر الحقيقة.
    # لا نعيد اختراع الحالة من Delta.
    # --------------------------------------------------------

    state = latest_turning.get(
        "state"
    )

    score = safe_number(
        latest_turning.get(
            "score"
        )
    )

    previous_score = (
        safe_number(
            previous_turning.get(
                "score"
            )
        )
        if previous_turning
        else None
    )

    delta = None

    if (
        score is not None
        and previous_score is not None
    ):

        delta = (
            score
            - previous_score
        )

    if state:

        description = (
            TURNING_STATE_DESCRIPTION.get(
                state,
                "حالة Turning صادرة مباشرة من Turning Engine"
            )
        )

        return {
            "state":
                state,

            "description":
                description,

            "delta":
                delta,

            "source":
                "turning_engine_state_code",

            "direct_state":
                True
        }

    # --------------------------------------------------------
    # Legacy fallback فقط لو state_code غير موجود
    # --------------------------------------------------------

    if score is None:

        return {
            "state":
                "NO_TURNING_DATA",

            "description":
                "لا توجد نتيجة Turning Engine لهذه الفترة",

            "delta":
                delta,

            "source":
                "legacy_fallback",

            "direct_state":
                False
        }

    if delta is None:

        return {
            "state":
                "INSUFFICIENT_HISTORY",

            "description":
                "Turning موجود لكن لا توجد فترة سابقة قابلة للمقارنة",

            "delta":
                delta,

            "source":
                "legacy_fallback",

            "direct_state":
                False
        }

    if (
        score >= 80
        and delta >= 20
    ):

        fallback_state = (
            "STRONG_TURNING_POINT"
        )

    elif (
        score >= 65
        and delta >= 15
    ):

        fallback_state = (
            "EARLY_TURNING_POINT"
        )

    elif score >= 55:

        fallback_state = (
            "IMPROVING"
        )

    elif score < 40:

        fallback_state = (
            "WEAK"
        )

    else:

        fallback_state = (
            "NEUTRAL"
        )

    return {
        "state":
            fallback_state,

        "description":
            "Legacy fallback لأن turning_engine_state_code غير موجود",

        "delta":
            delta,

        "source":
            "legacy_fallback",

        "direct_state":
            False
    }


# ============================================================
# System Coverage
# ============================================================

def evaluate_system_coverage(
    latest,
    analysis_model
):

    layers = {
        "scoring":
            safe_number(
                latest.get(
                    "score_opportunity_score"
                )
            ) is not None,

        "signal":
            get_signal_layer(
                latest,
                analysis_model
            )["available"],

        "turning":
            safe_number(
                latest.get(
                    "turning_engine_score"
                )
            ) is not None,

        "data_quality":
            safe_number(
                latest.get(
                    "data_quality_score"
                )
            ) is not None,

        "decision":
            safe_number(
                latest.get(
                    "decision_score"
                )
            ) is not None
    }

    available_count = sum(
        1
        for value in layers.values()
        if value
    )

    total_count = len(
        layers
    )

    coverage = (
        available_count
        / total_count
    ) * 100

    missing = [
        layer_name
        for layer_name, available
        in layers.items()
        if not available
    ]

    if available_count == total_count:

        status = "FULL"

    elif available_count >= 3:

        status = "PARTIAL"

    else:

        status = "LIMITED"

    return {
        "status":
            status,

        "coverage":
            coverage,

        "available_count":
            available_count,

        "total_count":
            total_count,

        "missing":
            missing,

        "layers":
            layers
    }


# ============================================================
# Model Validation Reasons
# ============================================================

def validate_standard(
    latest,
    previous
):

    positives = []
    risks = []
    contradictions = []

    revenue_yoy = safe_number(
        latest.get(
            "q_revenue_growth_yoy"
        )
    )

    profit_yoy = safe_number(
        latest.get(
            "q_net_income_growth_yoy"
        )
    )

    ocf_yoy = safe_number(
        latest.get(
            "q_ocf_growth_yoy"
        )
    )

    fcf_yoy = safe_number(
        latest.get(
            "q_fcf_growth_yoy"
        )
    )

    gross_margin_yoy = safe_number(
        latest.get(
            "q_gross_margin_change_yoy"
        )
    )

    operating_margin_yoy = safe_number(
        latest.get(
            "q_operating_margin_change_yoy"
        )
    )

    net_margin_yoy = safe_number(
        latest.get(
            "q_net_margin_change_yoy"
        )
    )

    cash_conversion = safe_number(
        latest.get(
            "q_cash_conversion"
        )
    )

    debt_growth = safe_number(
        latest.get(
            "q_debt_growth_qoq"
        )
    )

    current_ratio = safe_number(
        latest.get(
            "q_current_ratio"
        )
    )

    receivables_growth = safe_number(
        latest.get(
            "q_receivables_growth_qoq"
        )
    )

    inventory_growth = safe_number(
        latest.get(
            "q_inventory_growth_qoq"
        )
    )

    revenue_qoq = safe_number(
        latest.get(
            "q_revenue_growth_qoq"
        )
    )

    if (
        revenue_yoy is not None
        and revenue_yoy >= 10
    ):

        positives.append(
            f"نمو الإيرادات YoY قوي "
            f"({signed_fmt(revenue_yoy)}%)"
        )

    if (
        profit_yoy is not None
        and profit_yoy >= 10
    ):

        positives.append(
            f"نمو صافي الربح YoY قوي "
            f"({signed_fmt(profit_yoy)}%)"
        )

    if (
        fcf_yoy is not None
        and fcf_yoy >= 10
    ):

        positives.append(
            f"التدفق النقدي الحر يتحسن "
            f"({signed_fmt(fcf_yoy)}%)"
        )

    if (
        cash_conversion is not None
        and cash_conversion >= 1
    ):

        positives.append(
            f"تحويل الأرباح إلى نقد جيد "
            f"({fmt(cash_conversion)})"
        )

    if (
        operating_margin_yoy is not None
        and operating_margin_yoy > 1
    ):

        positives.append(
            f"الهامش التشغيلي يتحسن "
            f"({signed_fmt(operating_margin_yoy)} نقطة)"
        )

    if (
        gross_margin_yoy is not None
        and gross_margin_yoy <= -2
    ):

        risks.append(
            f"تآكل الهامش الإجمالي "
            f"({signed_fmt(gross_margin_yoy)} نقطة)"
        )

    if (
        operating_margin_yoy is not None
        and operating_margin_yoy <= -2
    ):

        risks.append(
            f"تآكل الهامش التشغيلي "
            f"({signed_fmt(operating_margin_yoy)} نقطة)"
        )

    if (
        net_margin_yoy is not None
        and net_margin_yoy <= -2
    ):

        risks.append(
            f"تآكل هامش صافي الربح "
            f"({signed_fmt(net_margin_yoy)} نقطة)"
        )

    if (
        cash_conversion is not None
        and cash_conversion < 0.70
    ):

        risks.append(
            f"تحويل الأرباح إلى نقد ضعيف "
            f"({fmt(cash_conversion)})"
        )

    if (
        debt_growth is not None
        and debt_growth > 15
    ):

        risks.append(
            f"الدين يرتفع سريعًا QoQ "
            f"({signed_fmt(debt_growth)}%)"
        )

    if (
        current_ratio is not None
        and current_ratio < 0.80
    ):

        risks.append(
            f"السيولة الجارية ضعيفة "
            f"({fmt(current_ratio)})"
        )

    if (
        receivables_growth is not None
        and revenue_qoq is not None
        and receivables_growth
        > revenue_qoq + 10
    ):

        risks.append(
            f"الذمم تنمو أسرع من المبيعات "
            f"بفارق "
            f"{fmt(receivables_growth - revenue_qoq)} نقطة"
        )

    if (
        inventory_growth is not None
        and revenue_qoq is not None
        and inventory_growth
        > revenue_qoq + 10
    ):

        risks.append(
            f"المخزون ينمو أسرع من المبيعات "
            f"بفارق "
            f"{fmt(inventory_growth - revenue_qoq)} نقطة"
        )

    if (
        revenue_yoy is not None
        and revenue_yoy >= 10
        and profit_yoy is not None
        and profit_yoy < 3
    ):

        contradictions.append(
            "الإيرادات تنمو لكن الربح لا يواكبها"
        )

    if (
        profit_yoy is not None
        and profit_yoy > 10
        and ocf_yoy is not None
        and ocf_yoy < -10
    ):

        contradictions.append(
            "الأرباح تنمو بينما التدفق التشغيلي يتراجع"
        )

    return (
        positives,
        risks,
        contradictions
    )


def validate_bank(
    latest,
    previous
):

    positives = []
    risks = []
    contradictions = []

    revenue = safe_number(
        latest.get(
            "bank_q_revenue_growth_yoy"
        )
    )

    profit = safe_number(
        latest.get(
            "bank_q_net_income_growth_yoy"
        )
    )

    assets = safe_number(
        latest.get(
            "bank_q_assets_growth_yoy"
        )
    )

    equity = safe_number(
        latest.get(
            "bank_q_equity_growth_yoy"
        )
    )

    roe = safe_number(
        latest.get(
            "bank_ttm_roe"
        )
    )

    roa = safe_number(
        latest.get(
            "bank_ttm_roa"
        )
    )

    equity_assets = safe_number(
        latest.get(
            "bank_q_equity_to_assets"
        )
    )

    margin_change = safe_number(
        latest.get(
            "bank_q_profit_margin_change_yoy"
        )
    )

    if (
        revenue is not None
        and revenue >= 10
    ):

        positives.append(
            f"نمو دخل البنك جيد "
            f"({signed_fmt(revenue)}%)"
        )

    if (
        profit is not None
        and profit >= 10
    ):

        positives.append(
            f"نمو صافي الربح جيد "
            f"({signed_fmt(profit)}%)"
        )

    if (
        roe is not None
        and roe >= 15
    ):

        positives.append(
            f"ROE قوي "
            f"({fmt(roe)}%)"
        )

    if (
        roa is not None
        and roa >= 1.5
    ):

        positives.append(
            f"ROA جيد للبنك "
            f"({fmt(roa)}%)"
        )

    if (
        assets is not None
        and assets >= 8
    ):

        positives.append(
            f"الأصول تنمو "
            f"({signed_fmt(assets)}%)"
        )

    if (
        margin_change is not None
        and margin_change <= -2
    ):

        risks.append(
            f"هامش الربح يتراجع "
            f"({signed_fmt(margin_change)} نقطة)"
        )

    if (
        roe is not None
        and roe < 10
    ):

        risks.append(
            f"ROE منخفض "
            f"({fmt(roe)}%)"
        )

    if (
        equity_assets is not None
        and equity_assets < 7
    ):

        risks.append(
            f"حقوق المساهمين إلى الأصول منخفضة "
            f"({fmt(equity_assets)}%)"
        )

    if (
        assets is not None
        and assets > 10
        and equity is not None
        and equity < 2
    ):

        contradictions.append(
            "الأصول تنمو أسرع بكثير من حقوق المساهمين"
        )

    if (
        revenue is not None
        and revenue > 10
        and profit is not None
        and profit < 3
    ):

        contradictions.append(
            "نمو دخل البنك لا يتحول إلى نمو مماثل في الربح"
        )

    return (
        positives,
        risks,
        contradictions
    )


def validate_insurance(
    latest,
    previous
):

    positives = []
    risks = []
    contradictions = []

    revenue = safe_number(
        latest.get(
            "insurance_q_revenue_growth_yoy"
        )
    )

    profit = safe_number(
        latest.get(
            "insurance_q_net_income_growth_yoy"
        )
    )

    roe = safe_number(
        latest.get(
            "insurance_ttm_roe"
        )
    )

    roa = safe_number(
        latest.get(
            "insurance_ttm_roa"
        )
    )

    cash_conversion = safe_number(
        latest.get(
            "insurance_ttm_cash_conversion"
        )
    )

    equity_growth = safe_number(
        latest.get(
            "insurance_q_equity_growth_yoy"
        )
    )

    if (
        revenue is not None
        and revenue >= 10
    ):

        positives.append(
            f"نمو الإيرادات جيد "
            f"({signed_fmt(revenue)}%)"
        )

    if (
        profit is not None
        and profit >= 10
    ):

        positives.append(
            f"نمو الربح قوي "
            f"({signed_fmt(profit)}%)"
        )

    if (
        roe is not None
        and roe >= 15
    ):

        positives.append(
            f"ROE قوي "
            f"({fmt(roe)}%)"
        )

    if (
        cash_conversion is not None
        and cash_conversion >= 1
    ):

        positives.append(
            f"التدفقات تدعم الأرباح "
            f"({fmt(cash_conversion)})"
        )

    if (
        roe is not None
        and roe < 8
    ):

        risks.append(
            f"ROE ضعيف "
            f"({fmt(roe)}%)"
        )

    if (
        roa is not None
        and roa < 1
    ):

        risks.append(
            f"ROA ضعيف "
            f"({fmt(roa)}%)"
        )

    if (
        cash_conversion is not None
        and cash_conversion < 0.50
    ):

        risks.append(
            f"جودة التدفق النقدي ضعيفة "
            f"({fmt(cash_conversion)})"
        )

    if (
        revenue is not None
        and revenue > 10
        and profit is not None
        and profit < 0
    ):

        contradictions.append(
            "الإيرادات تنمو بينما الأرباح تتراجع"
        )

    if (
        equity_growth is not None
        and equity_growth < -5
    ):

        risks.append(
            f"حقوق المساهمين تتراجع "
            f"({signed_fmt(equity_growth)}%)"
        )

    return (
        positives,
        risks,
        contradictions
    )


def validate_reit(
    latest,
    previous
):

    positives = []
    risks = []
    contradictions = []

    revenue = safe_number(
        latest.get(
            "reit_q_revenue_growth_yoy"
        )
    )

    operating_income = safe_number(
        latest.get(
            "reit_q_operating_income_growth_yoy"
        )
    )

    net_income = safe_number(
        latest.get(
            "reit_q_net_income_growth_yoy"
        )
    )

    debt_assets = safe_number(
        latest.get(
            "reit_q_debt_to_assets"
        )
    )

    debt_growth = safe_number(
        latest.get(
            "reit_q_debt_growth_yoy"
        )
    )

    cash_conversion = safe_number(
        latest.get(
            "reit_ttm_cash_conversion"
        )
    )

    if (
        revenue is not None
        and revenue >= 8
    ):

        positives.append(
            f"الإيرادات العقارية تنمو "
            f"({signed_fmt(revenue)}%)"
        )

    if (
        operating_income is not None
        and operating_income >= 8
    ):

        positives.append(
            f"الدخل التشغيلي يتحسن "
            f"({signed_fmt(operating_income)}%)"
        )

    if (
        cash_conversion is not None
        and cash_conversion >= 1
    ):

        positives.append(
            f"التدفقات تدعم الأرباح "
            f"({fmt(cash_conversion)})"
        )

    if (
        debt_assets is not None
        and debt_assets >= 50
    ):

        risks.append(
            f"المديونية مرتفعة إلى الأصول "
            f"({fmt(debt_assets)}%)"
        )

    if (
        debt_growth is not None
        and debt_growth > 15
    ):

        risks.append(
            f"الدين ينمو سريعًا "
            f"({signed_fmt(debt_growth)}%)"
        )

    if (
        revenue is not None
        and revenue > 8
        and net_income is not None
        and net_income < 0
    ):

        contradictions.append(
            "الإيرادات ترتفع لكن صافي الربح يتراجع"
        )

    return (
        positives,
        risks,
        contradictions
    )


# ============================================================
# Extreme / Base Effect Review
# ============================================================

def extreme_growth_review(
    latest,
    analysis_model
):

    flags = []

    if analysis_model == "standard":

        checks = [
            (
                "q_revenue_growth_yoy",
                "الإيرادات",
                "BASE_EFFECT_REVIEW"
            ),
            (
                "q_net_income_growth_yoy",
                "صافي الربح",
                "BASE_EFFECT_REVIEW"
            ),
            (
                "q_ocf_growth_yoy",
                "التدفق التشغيلي",
                "CASH_FLOW_VOLATILITY"
            ),
            (
                "q_fcf_growth_yoy",
                "التدفق النقدي الحر",
                "CASH_FLOW_VOLATILITY"
            )
        ]

    elif analysis_model == "bank":

        checks = [
            (
                "bank_q_revenue_growth_yoy",
                "دخل البنك",
                "BASE_EFFECT_REVIEW"
            ),
            (
                "bank_q_net_income_growth_yoy",
                "صافي ربح البنك",
                "BASE_EFFECT_REVIEW"
            )
        ]

    elif analysis_model == "insurance":

        checks = [
            (
                "insurance_q_revenue_growth_yoy",
                "إيرادات التأمين",
                "BASE_EFFECT_REVIEW"
            ),
            (
                "insurance_q_net_income_growth_yoy",
                "صافي ربح التأمين",
                "BASE_EFFECT_REVIEW"
            ),
            (
                "insurance_q_ocf_growth_yoy",
                "التدفق التشغيلي",
                "CASH_FLOW_VOLATILITY"
            )
        ]

    elif analysis_model == "reit":

        checks = [
            (
                "reit_q_revenue_growth_yoy",
                "إيرادات الريت",
                "BASE_EFFECT_REVIEW"
            ),
            (
                "reit_q_net_income_growth_yoy",
                "صافي ربح الريت",
                "BASE_EFFECT_REVIEW"
            )
        ]

    else:

        checks = []

    for (
        metric_name,
        label,
        flag_type
    ) in checks:

        value = safe_number(
            latest.get(
                metric_name
            )
        )

        if value is None:
            continue

        threshold = (
            100
            if flag_type
            == "CASH_FLOW_VOLATILITY"
            else 100
        )

        if abs(value) >= threshold:

            flags.append(
                f"{flag_type} | "
                f"{label} {signed_fmt(value)}%"
            )

    return flags


# ============================================================
# Financial Comparability
# ============================================================

def financial_input_watchlist(
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
            "q_current_ratio",
            "q_receivables_growth_qoq",
            "q_inventory_growth_qoq",
            "q_revenue_growth_qoq",
            "q_net_income_growth_qoq",
            "ttm_cash_conversion",
            "ttm_fcf_margin"
        ]

    if analysis_model == "bank":

        return [
            "bank_q_revenue_growth_yoy",
            "bank_q_net_income_growth_yoy",
            "bank_q_assets_growth_yoy",
            "bank_q_equity_growth_yoy",
            "bank_q_profit_margin_change_yoy",
            "bank_ttm_roe"
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
    latest,
    previous,
    analysis_model
):

    watched = financial_input_watchlist(
        analysis_model
    )

    latest_inputs = {
        metric_name
        for metric_name in watched
        if safe_number(
            latest.get(
                metric_name
            )
        ) is not None
    }

    previous_inputs = {
        metric_name
        for metric_name in watched
        if safe_number(
            previous.get(
                metric_name
            )
        ) is not None
    }

    common = (
        latest_inputs
        & previous_inputs
    )

    union = (
        latest_inputs
        | previous_inputs
    )

    score = (
        (
            len(common)
            / len(union)
        ) * 100
        if union
        else 0.0
    )

    if score >= 80:

        reliability = "HIGH"

    elif score >= 50:

        reliability = "MEDIUM"

    else:

        reliability = "LOW"

    return {
        "latest_inputs":
            len(latest_inputs),

        "previous_inputs":
            len(previous_inputs),

        "common_inputs":
            len(common),

        "union_inputs":
            len(union),

        "score":
            score,

        "reliability":
            reliability
    }


# ============================================================
# Score Momentum v2.1
# ============================================================

def score_change(
    latest_scores,
    previous_metrics,
    latest_turning,
    previous_turning
):

    previous_scores = (
        get_score_block(
            previous_metrics
        )
        if previous_metrics
        else {}
    )

    keys = [
        "growth",
        "quality",
        "cash",
        "balance",
        "opportunity",
        "risk",
        "base_turning"
    ]

    changes = {}

    comparable_count = 0

    for key in keys:

        current = safe_number(
            latest_scores.get(
                key
            )
        )

        previous = safe_number(
            previous_scores.get(
                key
            )
        )

        if (
            current is None
            or previous is None
        ):

            changes[
                key
            ] = None

        else:

            changes[
                key
            ] = (
                current
                - previous
            )

            comparable_count += 1

    current_turning = safe_number(
        latest_turning.get(
            "score"
        )
    )

    previous_turning_score = (
        safe_number(
            previous_turning.get(
                "score"
            )
        )
        if previous_turning
        else None
    )

    if (
        current_turning is not None
        and previous_turning_score is not None
    ):

        changes[
            "turning_engine"
        ] = (
            current_turning
            - previous_turning_score
        )

    else:

        changes[
            "turning_engine"
        ] = None

    return {
        "changes":
            changes,

        "comparable_scores":
            comparable_count,

        "possible_scores":
            len(keys)
    }


def calculate_momentum_reliability(
    score_momentum,
    comparability
):

    possible_scores = (
        score_momentum[
            "possible_scores"
        ]
    )

    comparable_scores = (
        score_momentum[
            "comparable_scores"
        ]
    )

    score_availability = (
        comparable_scores
        / possible_scores
    ) * 100 if possible_scores else 0.0

    financial_score = safe_number(
        comparability.get(
            "score"
        )
    ) or 0.0

    reliability = (
        score_availability
        * 0.60
        + financial_score
        * 0.40
    )

    reliability = clamp(
        reliability
    ) or 0.0

    if reliability >= 80:

        label = "HIGH"

    elif reliability >= 55:

        label = "MEDIUM"

    else:

        label = "LOW"

    return {
        "score_availability":
            score_availability,

        "reliability":
            reliability,

        "label":
            label
    }


# ============================================================
# Validate One Stock
# ============================================================

def validate_stock(stock):

    rows = get_metrics(
        stock[
            "id"
        ]
    )

    periods = organize_metrics(
        rows
    )

    analysis_model = (
        stock.get(
            "analysis_model"
        )
        or "standard"
    )

    (
        latest_period,
        previous_period
    ) = find_latest_periods(
        periods,
        analysis_model
    )

    print_header(
        f"🔎 {stock['symbol']} | "
        f"{stock.get('company_name')} | "
        f"{analysis_model}"
    )

    if not latest_period:

        print(
            "🔴 لا توجد فترة صالحة للتحقق",
            flush=True
        )

        return None

    latest = periods[
        latest_period
    ]

    previous = (
        periods.get(
            previous_period,
            {}
        )
        if previous_period
        else {}
    )

    scores = get_score_block(
        latest
    )

    state, state_description = (
        classify_score(
            scores.get(
                "opportunity"
            ),
            scores.get(
                "risk"
            ),
            scores.get(
                "confidence"
            )
        )
    )

    system_coverage = (
        evaluate_system_coverage(
            latest,
            analysis_model
        )
    )

    signal_layer = (
        get_signal_layer(
            latest,
            analysis_model
        )
    )

    latest_turning = (
        get_turning_layer(
            latest
        )
    )

    previous_turning = (
        get_turning_layer(
            previous
        )
        if previous
        else {}
    )

    turning_validation = (
        validate_turning_layer(
            latest_turning,
            previous_turning
        )
    )

    print(
        f"📅 Latest Period: "
        f"{latest_period}",
        flush=True
    )

    print(
        f"📅 Previous Period: "
        f"{previous_period or 'N/A'}",
        flush=True
    )

    print(
        f"🧭 Validation State: "
        f"{state} | "
        f"{state_description}",
        flush=True
    )

    print(
        f"🧱 System Coverage: "
        f"{system_coverage['status']} | "
        f"{system_coverage['available_count']}/"
        f"{system_coverage['total_count']} "
        f"({fmt(system_coverage['coverage'])}%)",
        flush=True
    )

    missing_layers_text = (
        ", ".join(
            system_coverage["missing"]
        )
        if system_coverage["missing"]
        else "NONE"
    )

    print(
        f"🧩 Missing Layers: "
        f"{missing_layers_text}",
        flush=True
    )

    print(
        f"📡 Signal Source: "
        f"{signal_layer['source']}",
        flush=True
    )

    print(
        f"🔄 Turning Validation: "
        f"{turning_validation['state']} | "
        f"{turning_validation['description']}",
        flush=True
    )

    print(
        f"🧠 Turning Source: "
        f"{turning_validation['source']}",
        flush=True
    )

    if latest_turning.get(
        "breadth"
    ) is not None:

        print(
            f"📐 Turning Breadth: "
            f"{fmt(latest_turning['breadth'])}% | "
            f"Common="
            f"{fmt(latest_turning['common_inputs'], 0)} | "
            f"New="
            f"{fmt(latest_turning['newly_available_inputs'], 0)} | "
            f"Dropped="
            f"{fmt(latest_turning['dropped_inputs'], 0)}",
            flush=True
        )

    print_separator()

    print(
        "🎯 SCORING COMPONENTS",
        flush=True
    )

    print(
        f"Growth:            "
        f"{fmt(scores.get('growth'))}",
        flush=True
    )

    print(
        f"Quality:           "
        f"{fmt(scores.get('quality'))}",
        flush=True
    )

    print(
        f"Cash:              "
        f"{fmt(scores.get('cash'))}",
        flush=True
    )

    print(
        f"Balance:           "
        f"{fmt(scores.get('balance'))}",
        flush=True
    )

    print(
        f"Opportunity:       "
        f"{fmt(scores.get('opportunity'))}",
        flush=True
    )

    print(
        f"Risk:              "
        f"{fmt(scores.get('risk'))}",
        flush=True
    )

    print(
        f"Base Turning:      "
        f"{fmt(scores.get('base_turning'))}",
        flush=True
    )

    print(
        f"Turning Engine:    "
        f"{fmt(latest_turning.get('score'))}",
        flush=True
    )

    print(
        f"Data Completeness: "
        f"{fmt(scores.get('confidence'))}",
        flush=True
    )

    # ========================================================
    # Reasons
    # ========================================================

    if analysis_model == "standard":

        positives, risks, contradictions = (
            validate_standard(
                latest,
                previous
            )
        )

    elif analysis_model == "bank":

        positives, risks, contradictions = (
            validate_bank(
                latest,
                previous
            )
        )

    elif analysis_model == "insurance":

        positives, risks, contradictions = (
            validate_insurance(
                latest,
                previous
            )
        )

    elif analysis_model == "reit":

        positives, risks, contradictions = (
            validate_reit(
                latest,
                previous
            )
        )

    else:

        positives = []
        risks = []
        contradictions = [
            "نموذج تحليل غير معروف"
        ]

    print_separator()

    print(
        "🟢 أسباب القوة:",
        flush=True
    )

    if positives:

        for item in positives:

            print(
                f"- {item}",
                flush=True
            )

    else:

        print(
            "- لا توجد إشارة قوة واضحة",
            flush=True
        )

    print(
        "\n🔴 أسباب الخطر:",
        flush=True
    )

    if risks:

        for item in risks:

            print(
                f"- {item}",
                flush=True
            )

    else:

        print(
            "- لا توجد إشارة خطر قوية",
            flush=True
        )

    print(
        "\n⚠️ التناقضات:",
        flush=True
    )

    if contradictions:

        for item in contradictions:

            print(
                f"- {item}",
                flush=True
            )

    else:

        print(
            "- لا يوجد تناقض جوهري ظاهر",
            flush=True
        )

    # ========================================================
    # Extreme / Base Effect
    # ========================================================

    extreme_flags = (
        extreme_growth_review(
            latest,
            analysis_model
        )
    )

    print(
        "\n🧨 EXTREME / BASE EFFECT REVIEW:",
        flush=True
    )

    if extreme_flags:

        for item in extreme_flags:

            print(
                f"- {item}",
                flush=True
            )

    else:

        print(
            "- لا توجد حركة متطرفة تحتاج Flag خاص",
            flush=True
        )

    # ========================================================
    # Financial Comparability
    # ========================================================

    comparability = (
        financial_comparability(
            latest,
            previous,
            analysis_model
        )
        if previous
        else {
            "latest_inputs": 0,
            "previous_inputs": 0,
            "common_inputs": 0,
            "union_inputs": 0,
            "score": 0.0,
            "reliability": "LOW"
        }
    )

    print_separator()

    print(
        "🧬 FINANCIAL COMPARABILITY",
        flush=True
    )

    print(
        f"Latest Inputs:    "
        f"{comparability['latest_inputs']}",
        flush=True
    )

    print(
        f"Previous Inputs:  "
        f"{comparability['previous_inputs']}",
        flush=True
    )

    print(
        f"Common Inputs:    "
        f"{comparability['common_inputs']}",
        flush=True
    )

    print(
        f"Union Inputs:     "
        f"{comparability['union_inputs']}",
        flush=True
    )

    print(
        f"Comparability:    "
        f"{fmt(comparability['score'])}% | "
        f"{comparability['reliability']}",
        flush=True
    )

    # ========================================================
    # Momentum
    # ========================================================

    score_momentum = (
        score_change(
            scores,
            previous,
            latest_turning,
            previous_turning
        )
    )

    momentum_reliability = (
        calculate_momentum_reliability(
            score_momentum,
            comparability
        )
    )

    changes = score_momentum[
        "changes"
    ]

    print_separator()

    print(
        "🚀 SCORE MOMENTUM v2.2",
        flush=True
    )

    print(
        f"Comparable Scores: "
        f"{score_momentum['comparable_scores']}/"
        f"{score_momentum['possible_scores']}",
        flush=True
    )

    print(
        f"Score Availability: "
        f"{fmt(momentum_reliability['score_availability'])}%",
        flush=True
    )

    print(
        f"Financial Comparability: "
        f"{fmt(comparability['score'])}%",
        flush=True
    )

    print(
        f"Momentum Reliability: "
        f"{fmt(momentum_reliability['reliability'])}% | "
        f"{momentum_reliability['label']}",
        flush=True
    )

    print(
        f"Opportunity Δ:       "
        f"{signed_fmt(changes.get('opportunity'))}",
        flush=True
    )

    print(
        f"Risk Δ:              "
        f"{signed_fmt(changes.get('risk'))}",
        flush=True
    )

    print(
        f"Base Turning Δ:      "
        f"{signed_fmt(changes.get('base_turning'))}",
        flush=True
    )

    print(
        f"Turning Engine Δ:    "
        f"{signed_fmt(changes.get('turning_engine'))}",
        flush=True
    )

    print(
        f"Growth Δ:            "
        f"{signed_fmt(changes.get('growth'))}",
        flush=True
    )

    print(
        f"Quality Δ:           "
        f"{signed_fmt(changes.get('quality'))}",
        flush=True
    )

    if (
        momentum_reliability[
            "reliability"
        ] < 55
    ):

        print(
            "🟡 Momentum غير موثوق بما يكفي "
            "للحكم على تغير الاتجاه.",
            flush=True
        )

    return {
        "symbol":
            stock[
                "symbol"
            ],

        "company_name":
            stock.get(
                "company_name"
            ),

        "analysis_model":
            analysis_model,

        "latest_period":
            latest_period,

        "state":
            state,

        "system_coverage":
            system_coverage[
                "status"
            ],

        "system_coverage_score":
            system_coverage[
                "coverage"
            ],

        "signal_source":
            signal_layer[
                "source"
            ],

        "turning_validation":
            turning_validation[
                "state"
            ],

        "turning_source":
            turning_validation[
                "source"
            ],

        "turning_engine_score":
            safe_number(
                latest_turning.get(
                    "score"
                )
            ),

        "turning_engine_delta":
            safe_number(
                changes.get(
                    "turning_engine"
                )
            ),

        "turning_breadth":
            safe_number(
                latest_turning.get(
                    "breadth"
                )
            ),

        "opportunity":
            safe_number(
                scores.get(
                    "opportunity"
                )
            ),

        "risk":
            safe_number(
                scores.get(
                    "risk"
                )
            ),

        "base_turning":
            safe_number(
                scores.get(
                    "base_turning"
                )
            ),

        "confidence":
            safe_number(
                scores.get(
                    "confidence"
                )
            ),

        "financial_comparable":
            comparability[
                "score"
            ],

        "momentum_reliability":
            momentum_reliability[
                "reliability"
            ],

        "positive_count":
            len(
                positives
            ),

        "risk_count":
            len(
                risks
            ),

        "contradiction_count":
            len(
                contradictions
            ),

        "extreme_count":
            len(
                extreme_flags
            )
    }


# ============================================================
# Final Summary
# ============================================================

def print_final_summary(results):

    valid = [
        result
        for result in results
        if result is not None
    ]

    valid.sort(
        key=lambda result: (
            result.get(
                "opportunity"
            )
            if result.get(
                "opportunity"
            ) is not None
            else -1
        ),
        reverse=True
    )

    print_header(
        f"📋 VALIDATION SUMMARY v{ENGINE_VERSION}"
    )

    for index, result in enumerate(
        valid,
        start=1
    ):

        print(
            f"{index:02d}. "
            f"{result['symbol']} | "
            f"{result['company_name']} | "
            f"{result['analysis_model']} | "
            f"{result['state']} | "
            f"SystemCoverage="
            f"{result['system_coverage']} "
            f"({fmt(result['system_coverage_score'])}%) | "
            f"SignalSource="
            f"{result['signal_source']} | "
            f"TurningValidation="
            f"{result['turning_validation']} | "
            f"TurningSource="
            f"{result['turning_source']} | "
            f"TurningBreadth="
            f"{fmt(result['turning_breadth'])}% | "
            f"FinancialComparable="
            f"{fmt(result['financial_comparable'])}% | "
            f"MomentumRel="
            f"{fmt(result['momentum_reliability'])}% | "
            f"Opportunity="
            f"{fmt(result['opportunity'])} | "
            f"Risk="
            f"{fmt(result['risk'])} | "
            f"BaseTurning="
            f"{fmt(result['base_turning'])} | "
            f"TurningEngine="
            f"{fmt(result['turning_engine_score'])} | "
            f"TurningEngineΔ="
            f"{signed_fmt(result['turning_engine_delta'])} | "
            f"+Signals="
            f"{result['positive_count']} | "
            f"-Signals="
            f"{result['risk_count']} | "
            f"Contradictions="
            f"{result['contradiction_count']} | "
            f"ExtremeFlags="
            f"{result['extreme_count']}",
            flush=True
        )

    full_count = sum(
        1
        for result in valid
        if result[
            "system_coverage"
        ] == "FULL"
    )

    partial_count = sum(
        1
        for result in valid
        if result[
            "system_coverage"
        ] == "PARTIAL"
    )

    limited_count = sum(
        1
        for result in valid
        if result[
            "system_coverage"
        ] == "LIMITED"
    )

    strong_turning = sum(
        1
        for result in valid
        if result[
            "turning_validation"
        ] == "STRONG_TURNING_POINT"
    )

    early_turning = sum(
        1
        for result in valid
        if result[
            "turning_validation"
        ] == "EARLY_TURNING_POINT"
    )

    improving = sum(
        1
        for result in valid
        if result[
            "turning_validation"
        ] == "IMPROVING"
    )

    limited_history = sum(
        1
        for result in valid
        if result[
            "turning_validation"
        ] == "IMPROVING_LIMITED_HISTORY"
    )

    continuation = sum(
        1
        for result in valid
        if result[
            "turning_validation"
        ] == "STRONG_CONTINUATION"
    )

    deteriorating = sum(
        1
        for result in valid
        if result[
            "turning_validation"
        ] == "DETERIORATING"
    )

    weak = sum(
        1
        for result in valid
        if result[
            "turning_validation"
        ] == "WEAK"
    )

    low_confidence = sum(
        1
        for result in valid
        if result[
            "turning_validation"
        ] == "LOW_CONFIDENCE"
    )

    low_momentum = sum(
        1
        for result in valid
        if (
            safe_number(
                result[
                    "momentum_reliability"
                ]
            )
            or 0
        ) < 55
    )

    total_extreme = sum(
        result[
            "extreme_count"
        ]
        for result in valid
    )

    print_separator()

    print(
        f"🏢 Companies: "
        f"{len(valid)}",
        flush=True
    )

    print(
        f"🟢 FULL System Coverage: "
        f"{full_count}",
        flush=True
    )

    print(
        f"🟡 PARTIAL System Coverage: "
        f"{partial_count}",
        flush=True
    )

    print(
        f"🟠 LIMITED System Coverage: "
        f"{limited_count}",
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
        f"🟠 Improving Limited History: "
        f"{limited_history}",
        flush=True
    )

    print(
        f"💪 Strong Continuations: "
        f"{continuation}",
        flush=True
    )

    print(
        f"🔴 Deteriorating: "
        f"{deteriorating}",
        flush=True
    )

    print(
        f"⚪ Weak: "
        f"{weak}",
        flush=True
    )

    print(
        f"🟡 Low Turning Confidence: "
        f"{low_confidence}",
        flush=True
    )

    print(
        f"🟡 Low Momentum Reliability: "
        f"{low_momentum}",
        flush=True
    )

    print(
        f"🧨 Extreme / Base Effect Flags: "
        f"{total_extreme}",
        flush=True
    )

    print(
        "\n"
        "✅ v1.2.3 Turning Integration: "
        "turning_engine_state_code هو مصدر الحقيقة "
        "لحالة Turning.",
        flush=True
    )

    print(
        "✅ Turning Engine Δ يستخدم للزخم والمقارنة فقط، "
        "ولا يعيد تصنيف الحالة.",
        flush=True
    )

    print(
        "✅ Breadth / Continuity / Common Inputs "
        "تُقرأ مباشرة من Turning Engine v2.0.2.",
        flush=True
    )

    print(
        "⚠️ Data Completeness لا تعني صحة المصدر "
        "أو دقة التنبؤ.",
        flush=True
    )

    print(
        "🔒 VALIDATION ENGINE READ ONLY | "
        "لا يكتب أو يعدل أي بيانات.",
        flush=True
    )

    print(
        "=" * 96,
        flush=True
    )


# ============================================================
# Run
# ============================================================

def run_validation_engine():

    symbols = get_validation_symbols()

    stocks = get_stocks(
        symbols
    )

    print_header(
        f"🧪 VALIDATION ENGINE v{ENGINE_VERSION}"
    )

    print(
        "🔒 Mode: READ ONLY",
        flush=True
    )

    print(
        f"🏢 Validation Companies: "
        f"{len(stocks)}",
        flush=True
    )

    print(
        f"📌 Symbols: "
        f"{', '.join(symbols)}",
        flush=True
    )

    print(
        "🧠 Turning State Source: "
        "turning_engine_state_code "
        "(Turning Engine v2.0.2)",
        flush=True
    )

    results = []

    for stock in stocks:

        try:

            result = validate_stock(
                stock
            )

            results.append(
                result
            )

        except Exception as error:

            print(
                f"🔴 {stock['symbol']} | "
                f"{type(error).__name__}: "
                f"{error}",
                flush=True
            )

    print_final_summary(
        results
    )


if __name__ == "__main__":

    run_validation_engine()
