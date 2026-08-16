import os
from supabase import create_client


# ============================================================
# VALIDATION ENGINE v1.2.1
#
# READ ONLY
#
# v1.2.1:
#
# 1) إصلاح أولوية Turning:
#    STRONG_CONTINUATION قبل EARLY_TURNING
#
# 2) فصل:
#    Base Turning Delta
#    Turning Engine Delta
#
# 3) System Layer Coverage
# 4) Financial Comparability
# 5) Momentum Reliability v2
# 6) Extreme / Base Effect Review
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
# عينة التحقق
# ============================================================

DEFAULT_VALIDATION_SYMBOLS = [

    "4030.SR",  # البحري
    "4190.SR",  # جرير
    "8010.SR",  # التعاونية
    "1831.SR",  # مهارة
    "1111.SR",  # مجموعة تداول
    "2283.SR",  # المطاحن الأولى
    "7203.SR",  # علم
    "1150.SR"   # مصرف الإنماء
]


def get_validation_symbols():

    env_value = os.environ.get(
        "VALIDATION_SYMBOLS"
    )

    if not env_value:
        return DEFAULT_VALIDATION_SYMBOLS

    symbols = [

        symbol.strip()

        for symbol
        in env_value.split(",")

        if symbol.strip()
    ]

    return (
        symbols
        if symbols
        else DEFAULT_VALIDATION_SYMBOLS
    )


# ============================================================
# أدوات عامة
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


def print_separator():

    print(
        "-" * 96,
        flush=True
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


# ============================================================
# Stocks
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
            "data_status"
        )
        .in_(
            "symbol",
            symbols
        )
        .execute()
    )

    rows = response.data or []

    stock_map = {

        row["symbol"]:
            row

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


# ============================================================
# Financial Metrics
# ============================================================

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
# Model Prefix
# ============================================================

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
# Financial Comparability Inputs
# ============================================================

MODEL_COMPARABILITY_INPUTS = {

    "standard": [

        "q_revenue_growth_yoy",
        "q_net_income_growth_yoy",
        "q_revenue_growth_qoq",
        "q_net_income_growth_qoq",

        "q_gross_margin_change_yoy",
        "q_operating_margin_change_yoy",
        "q_net_margin_change_yoy",

        "q_cash_conversion",
        "q_ocf_growth_yoy",
        "q_fcf_growth_yoy",

        "q_debt_growth_qoq",
        "q_debt_to_equity",
        "q_current_ratio",
        "q_cash_growth_qoq",

        "q_inventory_growth_qoq",
        "q_receivables_growth_qoq"
    ],

    "bank": [

        "bank_q_revenue_growth_yoy",
        "bank_q_net_income_growth_yoy",
        "bank_q_assets_growth_yoy",
        "bank_q_equity_growth_yoy",
        "bank_q_profit_margin_change_yoy",
        "bank_q_equity_to_assets",
        "bank_ttm_roe",
        "bank_ttm_roa"
    ],

    "insurance": [

        "insurance_q_revenue_growth_yoy",
        "insurance_q_net_income_growth_yoy",
        "insurance_q_equity_growth_yoy",
        "insurance_q_profit_margin_change_yoy",
        "insurance_q_ocf_growth_yoy",
        "insurance_ttm_cash_conversion",
        "insurance_ttm_roe",
        "insurance_ttm_roa"
    ],

    "reit": [

        "reit_q_revenue_growth_yoy",
        "reit_q_operating_income_growth_yoy",
        "reit_q_net_income_growth_yoy",
        "reit_q_operating_margin_change_yoy",
        "reit_q_net_margin_change_yoy",
        "reit_q_debt_growth_yoy",
        "reit_q_debt_to_assets",
        "reit_ttm_cash_conversion"
    ]
}


# ============================================================
# Latest Periods
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

    return (
        latest,
        previous
    )


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

        "turning":
            safe_number(
                metrics.get(
                    "score_turning_point_score"
                )
            )
    }


# ============================================================
# Turning Engine الحقيقي
# ============================================================

def get_turning_value(metrics):

    engine_value = safe_number(
        metrics.get(
            "turning_engine_score"
        )
    )

    if engine_value is not None:

        return {

            "value":
                engine_value,

            "source":
                "turning_engine_score"
        }

    fallback = safe_number(
        metrics.get(
            "score_turning_point_score"
        )
    )

    if fallback is not None:

        return {

            "value":
                fallback,

            "source":
                "score_turning_point_score_fallback"
        }

    return {

        "value":
            None,

        "source":
            "missing"
    }


# ============================================================
# Turning Engine Delta
# ============================================================

def calculate_turning_engine_delta(
    latest,
    previous
):

    current = get_turning_value(
        latest
    )

    if not previous:

        return {

            "current":
                current[
                    "value"
                ],

            "previous":
                None,

            "delta":
                None,

            "source":
                current[
                    "source"
                ]
        }

    previous_turning = get_turning_value(
        previous
    )

    current_value = safe_number(
        current[
            "value"
        ]
    )

    previous_value = safe_number(
        previous_turning[
            "value"
        ]
    )

    delta = None

    if (
        current_value is not None
        and previous_value is not None
    ):

        delta = (
            current_value
            - previous_value
        )

    return {

        "current":
            current_value,

        "previous":
            previous_value,

        "delta":
            delta,

        "source":
            current[
                "source"
            ]
    }


# ============================================================
# General Classification
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
            "اكتمال البيانات غير كافٍ لحكم قوي"
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
# System Layer Coverage
# ============================================================

def calculate_system_layer_coverage(
    metrics
):

    layers = {

        "scoring":
            safe_number(
                metrics.get(
                    "score_opportunity_score"
                )
            ) is not None,

        "signal":
            safe_number(
                metrics.get(
                    "engine22_net_score"
                )
            ) is not None,

        "turning":
            safe_number(
                metrics.get(
                    "turning_engine_score"
                )
            ) is not None,

        "data_quality":
            safe_number(
                metrics.get(
                    "data_quality_score"
                )
            ) is not None,

        "decision":
            safe_number(
                metrics.get(
                    "decision_score"
                )
            ) is not None
    }

    available = sum(
        1
        for value in layers.values()
        if value
    )

    total = len(
        layers
    )

    score = (
        available
        / total
    ) * 100

    if available == total:

        status = "FULL"

    elif available >= 3:

        status = "PARTIAL"

    else:

        status = "LIMITED"

    missing = [

        name

        for name, value
        in layers.items()

        if not value
    ]

    return {

        "status":
            status,

        "score":
            score,

        "available":
            available,

        "total":
            total,

        "layers":
            layers,

        "missing":
            missing
    }


# ============================================================
# Financial Comparability
# ============================================================

def calculate_financial_comparability(
    latest,
    previous,
    analysis_model
):

    watched = (
        MODEL_COMPARABILITY_INPUTS.get(
            analysis_model,
            []
        )
    )

    if (
        not watched
        or not previous
    ):

        return {

            "score":
                0.0,

            "common":
                0,

            "union":
                0,

            "latest_available":
                0,

            "previous_available":
                0,

            "state":
                "NO_HISTORY"
        }

    latest_available = {

        metric_name

        for metric_name in watched

        if safe_number(
            latest.get(
                metric_name
            )
        ) is not None
    }

    previous_available = {

        metric_name

        for metric_name in watched

        if safe_number(
            previous.get(
                metric_name
            )
        ) is not None
    }

    common = (
        latest_available
        & previous_available
    )

    union = (
        latest_available
        | previous_available
    )

    if not union:

        score = 0.0

    else:

        score = (
            len(common)
            / len(union)
        ) * 100

    if score >= 85:

        state = "HIGH"

    elif score >= 60:

        state = "MEDIUM"

    elif score > 0:

        state = "LOW"

    else:

        state = "NO_HISTORY"

    return {

        "score":
            score,

        "common":
            len(common),

        "union":
            len(union),

        "latest_available":
            len(latest_available),

        "previous_available":
            len(previous_available),

        "state":
            state
    }


# ============================================================
# Score Momentum
# ============================================================

MOMENTUM_KEYS = [

    "growth",
    "quality",
    "cash",
    "balance",
    "opportunity",
    "risk",
    "turning"
]


def calculate_momentum(
    latest_scores,
    previous_metrics,
    financial_comparability
):

    if not previous_metrics:

        return {

            "changes":
                {},

            "score_availability":
                0.0,

            "financial_comparability":
                financial_comparability[
                    "score"
                ],

            "reliability":
                0.0,

            "state":
                "NO_HISTORY",

            "comparable_scores":
                0
        }

    previous_scores = get_score_block(
        previous_metrics
    )

    changes = {}

    comparable_scores = 0

    for key in MOMENTUM_KEYS:

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

            comparable_scores += 1

            changes[
                key
            ] = (
                current
                - previous
            )

    score_availability = (
        comparable_scores
        / len(MOMENTUM_KEYS)
    ) * 100

    financial_score = (
        financial_comparability[
            "score"
        ]
    )

    reliability = (

        score_availability
        * 0.40

        + financial_score
        * 0.60
    )

    if reliability >= 85:

        state = "HIGH"

    elif reliability >= 60:

        state = "MEDIUM"

    elif reliability > 0:

        state = "LOW"

    else:

        state = "NO_HISTORY"

    return {

        "changes":
            changes,

        "score_availability":
            score_availability,

        "financial_comparability":
            financial_score,

        "reliability":
            reliability,

        "state":
            state,

        "comparable_scores":
            comparable_scores
    }


# ============================================================
# Turning Validation v1.2.1
#
# مهم:
#
# ترتيب الشروط:
#
# 1) TRUE TURNING
# 2) STRONG CONTINUATION
# 3) EARLY TURNING
#
# حتى لا نصنف شركة قوية أصلًا كتحول جديد.
# ============================================================

def validate_turning(
    latest,
    previous,
    momentum_reliability
):

    current = get_turning_value(
        latest
    )

    current_value = current[
        "value"
    ]

    if current_value is None:

        return {

            "state":
                "NO_TURNING_DATA",

            "description":
                "Turning Engine غير متوفر",

            "value":
                None,

            "previous_value":
                None,

            "delta":
                None,

            "source":
                current[
                    "source"
                ]
        }

    if not previous:

        return {

            "state":
                "INSUFFICIENT_HISTORY",

            "description":
                "لا توجد فترة سابقة للمقارنة",

            "value":
                current_value,

            "previous_value":
                None,

            "delta":
                None,

            "source":
                current[
                    "source"
                ]
        }

    previous_turning = get_turning_value(
        previous
    )

    previous_value = previous_turning[
        "value"
    ]

    if previous_value is None:

        return {

            "state":
                "INSUFFICIENT_HISTORY",

            "description":
                "Turning غير متوفر في الفترة السابقة",

            "value":
                current_value,

            "previous_value":
                None,

            "delta":
                None,

            "source":
                current[
                    "source"
                ]
        }

    delta = (
        current_value
        - previous_value
    )

    if momentum_reliability < 60:

        return {

            "state":
                "LOW_COMPARABILITY",

            "description":
                (
                    "التحول ظاهر لكن قابلية المقارنة "
                    "بين الفترتين منخفضة"
                ),

            "value":
                current_value,

            "previous_value":
                previous_value,

            "delta":
                delta,

            "source":
                current[
                    "source"
                ]
        }

    # --------------------------------------------------------
    # TRUE TURNING
    #
    # الشركة كانت ضعيفة/متوسطة ثم قفزت إلى مستوى قوي
    # --------------------------------------------------------

    if (
        current_value >= 70
        and previous_value < 60
        and delta >= 10
    ):

        return {

            "state":
                "TRUE_TURNING",

            "description":
                (
                    f"تحول مؤكد نسبيًا؛ "
                    f"Turning Engine Δ "
                    f"{signed_fmt(delta)}"
                ),

            "value":
                current_value,

            "previous_value":
                previous_value,

            "delta":
                delta,

            "source":
                current[
                    "source"
                ]
        }

    # --------------------------------------------------------
    # STRONG CONTINUATION
    #
    # مهم أن يأتي قبل EARLY_TURNING
    # --------------------------------------------------------

    if (
        current_value >= 70
        and previous_value >= 70
    ):

        return {

            "state":
                "STRONG_CONTINUATION",

            "description":
                (
                    "قوة مستمرة وليست "
                    "Turning Point جديدة"
                ),

            "value":
                current_value,

            "previous_value":
                previous_value,

            "delta":
                delta,

            "source":
                current[
                    "source"
                ]
        }

    # --------------------------------------------------------
    # EARLY TURNING
    # --------------------------------------------------------

    if (
        current_value >= 55
        and previous_value < 70
        and delta >= 10
    ):

        return {

            "state":
                "EARLY_TURNING",

            "description":
                (
                    f"إشارة تحول مبكرة؛ "
                    f"Turning Engine Δ "
                    f"{signed_fmt(delta)}"
                ),

            "value":
                current_value,

            "previous_value":
                previous_value,

            "delta":
                delta,

            "source":
                current[
                    "source"
                ]
        }

    # --------------------------------------------------------
    # NO TURNING
    # --------------------------------------------------------

    if current_value < 55:

        return {

            "state":
                "NO_TURNING",

            "description":
                "لا توجد إشارة تحول قوية حاليًا",

            "value":
                current_value,

            "previous_value":
                previous_value,

            "delta":
                delta,

            "source":
                current[
                    "source"
                ]
        }

    # --------------------------------------------------------
    # MIXED
    # --------------------------------------------------------

    return {

        "state":
            "MIXED_TURNING",

        "description":
            (
                "إشارة التحول مختلطة "
                "ولا تكفي للحكم القوي"
            ),

        "value":
            current_value,

        "previous_value":
            previous_value,

        "delta":
            delta,

        "source":
            current[
                "source"
            ]
    }


# ============================================================
# Extreme / Base Effect
# ============================================================

def detect_extreme_flags(
    latest,
    analysis_model
):

    flags = []

    if analysis_model == "standard":

        growth_metrics = [

            (
                "الإيرادات",
                latest.get(
                    "q_revenue_growth_yoy"
                )
            ),

            (
                "صافي الربح",
                latest.get(
                    "q_net_income_growth_yoy"
                )
            )
        ]

        cash_metrics = [

            (
                "التدفق التشغيلي",
                latest.get(
                    "q_ocf_growth_yoy"
                )
            ),

            (
                "التدفق النقدي الحر",
                latest.get(
                    "q_fcf_growth_yoy"
                )
            )
        ]

    elif analysis_model == "bank":

        growth_metrics = [

            (
                "دخل البنك",
                latest.get(
                    "bank_q_revenue_growth_yoy"
                )
            ),

            (
                "صافي الربح",
                latest.get(
                    "bank_q_net_income_growth_yoy"
                )
            )
        ]

        cash_metrics = []

    elif analysis_model == "insurance":

        growth_metrics = [

            (
                "الإيرادات",
                latest.get(
                    "insurance_q_revenue_growth_yoy"
                )
            ),

            (
                "صافي الربح",
                latest.get(
                    "insurance_q_net_income_growth_yoy"
                )
            )
        ]

        cash_metrics = []

    elif analysis_model == "reit":

        growth_metrics = [

            (
                "إيرادات REIT",
                latest.get(
                    "reit_q_revenue_growth_yoy"
                )
            ),

            (
                "الدخل التشغيلي",
                latest.get(
                    "reit_q_operating_income_growth_yoy"
                )
            ),

            (
                "صافي الربح",
                latest.get(
                    "reit_q_net_income_growth_yoy"
                )
            )
        ]

        cash_metrics = []

    else:

        growth_metrics = []
        cash_metrics = []

    for name, value in growth_metrics:

        value = safe_number(
            value
        )

        if value is None:
            continue

        if value >= 100:

            flags.append(
                (
                    f"BASE_EFFECT_REVIEW | "
                    f"{name} "
                    f"{signed_fmt(value)}%"
                )
            )

        elif value <= -70:

            flags.append(
                (
                    f"EXTREME_DECLINE | "
                    f"{name} "
                    f"{signed_fmt(value)}%"
                )
            )

    for name, value in cash_metrics:

        value = safe_number(
            value
        )

        if value is None:
            continue

        if abs(value) >= 100:

            flags.append(
                (
                    f"CASH_FLOW_VOLATILITY | "
                    f"{name} "
                    f"{signed_fmt(value)}%"
                )
            )

    return flags


# ============================================================
# STANDARD Validation
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

    gross_margin = safe_number(
        latest.get(
            "q_gross_margin_change_yoy"
        )
    )

    operating_margin = safe_number(
        latest.get(
            "q_operating_margin_change_yoy"
        )
    )

    net_margin = safe_number(
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

    # --------------------------------------------------------
    # Positive
    # --------------------------------------------------------

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
        operating_margin is not None
        and operating_margin > 1
    ):

        positives.append(
            f"الهامش التشغيلي يتحسن "
            f"({signed_fmt(operating_margin)} نقطة)"
        )

    # --------------------------------------------------------
    # Risks
    # --------------------------------------------------------

    if (
        gross_margin is not None
        and gross_margin <= -2
    ):

        risks.append(
            f"تآكل الهامش الإجمالي "
            f"({signed_fmt(gross_margin)} نقطة)"
        )

    if (
        operating_margin is not None
        and operating_margin <= -2
    ):

        risks.append(
            f"تآكل الهامش التشغيلي "
            f"({signed_fmt(operating_margin)} نقطة)"
        )

    if (
        net_margin is not None
        and net_margin <= -2
    ):

        risks.append(
            f"تآكل هامش صافي الربح "
            f"({signed_fmt(net_margin)} نقطة)"
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

    # --------------------------------------------------------
    # Contradictions
    # --------------------------------------------------------

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


# ============================================================
# BANK Validation
# ============================================================

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


# ============================================================
# INSURANCE Validation
# ============================================================

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
        equity_growth is not None
        and equity_growth < -5
    ):

        risks.append(
            f"حقوق المساهمين تتراجع "
            f"({signed_fmt(equity_growth)}%)"
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

    return (
        positives,
        risks,
        contradictions
    )


# ============================================================
# REIT Validation
# ============================================================

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
# Analyze Stock
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

    latest_period, previous_period = (
        find_latest_periods(
            periods,
            analysis_model
        )
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
            previous_period
        )
        if previous_period
        else {}
    )

    scores = get_score_block(
        latest
    )

    # ========================================================
    # Financial Comparability
    # ========================================================

    financial_comparability = (
        calculate_financial_comparability(
            latest,
            previous,
            analysis_model
        )
    )

    # ========================================================
    # Momentum
    # ========================================================

    momentum = calculate_momentum(
        scores,
        previous,
        financial_comparability
    )

    changes = momentum[
        "changes"
    ]

    # ========================================================
    # Turning Engine Delta
    # ========================================================

    turning_engine_change = (
        calculate_turning_engine_delta(
            latest,
            previous
        )
    )

    # ========================================================
    # Turning Validation
    # ========================================================

    turning = validate_turning(
        latest,
        previous,
        momentum[
            "reliability"
        ]
    )

    # ========================================================
    # System Coverage
    # ========================================================

    system_coverage = (
        calculate_system_layer_coverage(
            latest
        )
    )

    # ========================================================
    # General State
    # ========================================================

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

    # ========================================================
    # Extreme Flags
    # ========================================================

    extreme_flags = (
        detect_extreme_flags(
            latest,
            analysis_model
        )
    )

    # ========================================================
    # Model Validation
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

    # ========================================================
    # Header
    # ========================================================

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
        f"{system_coverage['available']}/"
        f"{system_coverage['total']} "
        f"({fmt(system_coverage['score'])}%)",
        flush=True
    )

    if system_coverage[
        "missing"
    ]:

        print(
            "🧩 Missing Layers: "
            + ", ".join(
                system_coverage[
                    "missing"
                ]
            ),
            flush=True
        )

    else:

        print(
            "🧩 Missing Layers: NONE",
            flush=True
        )

    print(
        f"🔄 Turning Validation: "
        f"{turning['state']} | "
        f"{turning['description']}",
        flush=True
    )

    print(
        f"🧠 Turning Source: "
        f"{turning['source']}",
        flush=True
    )

    print_separator()

    # ========================================================
    # Scoring
    # ========================================================

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
        f"{fmt(scores.get('turning'))}",
        flush=True
    )

    print(
        f"Turning Engine:    "
        f"{fmt(turning['value'])}",
        flush=True
    )

    print(
        f"Data Completeness: "
        f"{fmt(scores.get('confidence'))}",
        flush=True
    )

    # ========================================================
    # Strength
    # ========================================================

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

    # ========================================================
    # Risk
    # ========================================================

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

    # ========================================================
    # Contradictions
    # ========================================================

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
    # Extreme
    # ========================================================

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

    print_separator()

    print(
        "🧬 FINANCIAL COMPARABILITY",
        flush=True
    )

    print(
        f"Latest Inputs:    "
        f"{financial_comparability['latest_available']}",
        flush=True
    )

    print(
        f"Previous Inputs:  "
        f"{financial_comparability['previous_available']}",
        flush=True
    )

    print(
        f"Common Inputs:    "
        f"{financial_comparability['common']}",
        flush=True
    )

    print(
        f"Union Inputs:     "
        f"{financial_comparability['union']}",
        flush=True
    )

    print(
        f"Comparability:    "
        f"{fmt(financial_comparability['score'])}% | "
        f"{financial_comparability['state']}",
        flush=True
    )

    # ========================================================
    # Momentum
    # ========================================================

    print_separator()

    print(
        "🚀 SCORE MOMENTUM v2.1",
        flush=True
    )

    print(
        f"Comparable Scores: "
        f"{momentum['comparable_scores']}/"
        f"{len(MOMENTUM_KEYS)}",
        flush=True
    )

    print(
        f"Score Availability: "
        f"{fmt(momentum['score_availability'])}%",
        flush=True
    )

    print(
        f"Financial Comparability: "
        f"{fmt(momentum['financial_comparability'])}%",
        flush=True
    )

    print(
        f"Momentum Reliability: "
        f"{fmt(momentum['reliability'])}% | "
        f"{momentum['state']}",
        flush=True
    )

    if changes:

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
            f"{signed_fmt(changes.get('turning'))}",
            flush=True
        )

        print(
            f"Turning Engine Δ:    "
            f"{signed_fmt(turning_engine_change.get('delta'))}",
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

    else:

        print(
            "لا توجد مقارنة سابقة",
            flush=True
        )

    if momentum[
        "reliability"
    ] < 60:

        print(
            "🟡 Momentum غير موثوق بما يكفي "
            "للحكم على تغير الاتجاه.",
            flush=True
        )

    # ========================================================
    # Result
    # ========================================================

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
                "score"
            ],

        "turning_state":
            turning[
                "state"
            ],

        "turning_source":
            turning[
                "source"
            ],

        "base_turning":
            scores.get(
                "turning"
            ),

        "turning_engine":
            turning[
                "value"
            ],

        "turning_engine_delta":
            turning_engine_change[
                "delta"
            ],

        "financial_comparability":
            financial_comparability[
                "score"
            ],

        "momentum_reliability":
            momentum[
                "reliability"
            ],

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

        "extreme_flag_count":
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
        "📋 VALIDATION SUMMARY v1.2.1"
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

            f"TurningValidation="
            f"{result['turning_state']} | "

            f"TurningSource="
            f"{result['turning_source']} | "

            f"FinancialComparable="
            f"{fmt(result['financial_comparability'])}% | "

            f"MomentumRel="
            f"{fmt(result['momentum_reliability'])}% | "

            f"Opportunity="
            f"{fmt(result['opportunity'])} | "

            f"Risk="
            f"{fmt(result['risk'])} | "

            f"BaseTurning="
            f"{fmt(result['base_turning'])} | "

            f"TurningEngine="
            f"{fmt(result['turning_engine'])} | "

            f"TurningEngineΔ="
            f"{signed_fmt(result['turning_engine_delta'])} | "

            f"+Signals="
            f"{result['positive_count']} | "

            f"-Signals="
            f"{result['risk_count']} | "

            f"Contradictions="
            f"{result['contradiction_count']} | "

            f"ExtremeFlags="
            f"{result['extreme_flag_count']}",

            flush=True
        )

    print_separator()

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

    true_turning_count = sum(

        1
        for result in valid

        if result[
            "turning_state"
        ] == "TRUE_TURNING"
    )

    early_turning_count = sum(

        1
        for result in valid

        if result[
            "turning_state"
        ] == "EARLY_TURNING"
    )

    strong_continuation_count = sum(

        1
        for result in valid

        if result[
            "turning_state"
        ] == "STRONG_CONTINUATION"
    )

    insufficient_turning_count = sum(

        1
        for result in valid

        if result[
            "turning_state"
        ] == "INSUFFICIENT_HISTORY"
    )

    low_momentum_count = sum(

        1
        for result in valid

        if (
            result[
                "momentum_reliability"
            ]
            < 60
        )
    )

    extreme_total = sum(

        result[
            "extreme_flag_count"
        ]

        for result in valid
    )

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
        f"🔄 TRUE Turning Points: "
        f"{true_turning_count}",
        flush=True
    )

    print(
        f"🌱 EARLY Turning Points: "
        f"{early_turning_count}",
        flush=True
    )

    print(
        f"💪 Strong Continuations: "
        f"{strong_continuation_count}",
        flush=True
    )

    print(
        f"🗂️ Insufficient Turning History: "
        f"{insufficient_turning_count}",
        flush=True
    )

    print(
        f"🟡 Low Momentum Reliability: "
        f"{low_momentum_count}",
        flush=True
    )

    print(
        f"🧨 Extreme / Base Effect Flags: "
        f"{extreme_total}",
        flush=True
    )

    print(
        "\n"
        "⚠️ Data Completeness لا تعني "
        "صحة المصدر أو دقة التنبؤ.",
        flush=True
    )

    print(
        "\n"
        "🧬 Momentum Reliability v2.1 يجمع "
        "بين قابلية مقارنة المدخلات المالية "
        "وتوفر درجات Scoring.",
        flush=True
    )

    print(
        "\n"
        "🔄 Base Turning منفصل عن "
        "Turning Engine الحقيقي في العرض والمقارنة.",
        flush=True
    )

    print(
        "\n"
        "🔒 VALIDATION ENGINE READ ONLY | "
        "لا يكتب أو يعدل أي بيانات.",
        flush=True
    )

    print(
        "=" * 96,
        flush=True
    )


# ============================================================
# START
# ============================================================

def run_validation_engine():

    symbols = get_validation_symbols()

    stocks = get_stocks(
        symbols
    )

    print_header(
        "🧪 VALIDATION ENGINE v1.2.1"
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
