import os
from collections import Counter
from datetime import datetime, timezone

from supabase import create_client


# ============================================================
# SYSTEM AUDIT ENGINE v1.2.1
#
# الهدف:
# تدقيق النظام المالي كاملًا:
#
# 1) stocks
# 2) financial_statements
# 3) financial_metrics
# 4) specialized models
# 5) scoring
# 6) signal engine
# 7) turning point engine v2.0.2
# 8) data quality
# 9) final decision
#
# READ ONLY
# لا يكتب أو يعدل أي بيانات.
#
# v1.2.1:
#
# - تصحيح Turning State Codes لتطابق Turning Engine v2.0.2.
# - دعم IMPROVING_LIMITED_HISTORY بالترتيب الصحيح.
# - turning_engine_state_code هو مصدر الحقيقة لحالة Turning.
# - عدم اعتبار اختلاف Base Turning عن Turning Engine خطأ.
# - التحقق من التناقض الحقيقي بين Turning State والدرجات.
# - تدقيق Signal Layer حسب Analysis Model.
# - إزالة MOMENTUM_BOUNDARY القديم المضلل.
# - الاحتفاظ بمنطق LIMITED DATA للـ REIT.
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

ENGINE_VERSION = "1.2.1"


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
# Signal Engine حسب النموذج
# ============================================================

MODEL_SIGNAL_PREFIX = {

    "standard":
        "engine22_",

    "bank":
        "bank_signal_",

    "insurance":
        "insurance_signal_",

    "reit":
        "engine22_"
}


# ============================================================
# Turning State Codes
#
# IMPORTANT:
# هذا هو الترتيب الفعلي المستخدم في Turning Engine v2.0.2.
#
# 0 = LOW_CONFIDENCE
# 1 = WEAK
# 2 = DETERIORATING
# 3 = NEUTRAL
# 4 = IMPROVING
# 5 = IMPROVING_LIMITED_HISTORY
# 6 = EARLY_TURNING_POINT
# 7 = STRONG_TURNING_POINT
# 8 = STRONG_CONTINUATION
#
# ============================================================

TURNING_STATE_CODES = {

    0:
        "LOW_CONFIDENCE",

    1:
        "WEAK",

    2:
        "DETERIORATING",

    3:
        "NEUTRAL",

    4:
        "IMPROVING",

    5:
        "IMPROVING_LIMITED_HISTORY",

    6:
        "EARLY_TURNING_POINT",

    7:
        "STRONG_TURNING_POINT",

    8:
        "STRONG_CONTINUATION"
}


# ============================================================
# Core Engine Metrics
# ============================================================

CORE_ENGINE_METRICS = {

    "scoring": [

        "score_opportunity_score",
        "score_risk_score",
        "score_turning_point_score",
        "score_confidence_score"
    ],

    "turning": [

        "turning_engine_score",
        "turning_engine_state_code",
        "turning_engine_confidence_score",
        "turning_engine_comparability_score"
    ],

    "data_quality": [

        "data_quality_score",
        "data_freshness_score",
        "data_coverage_score",
        "data_history_score",
        "data_continuity_score"
    ],

    "decision": [

        "decision_score",
        "decision_confidence",
        "decision_reliability_score",
        "decision_momentum_score"
    ]
}


# ============================================================
# Required Financial Metrics
# ============================================================

MODEL_REQUIRED_METRICS = {

    "standard": [

        "q_revenue_growth_yoy",
        "q_net_income_growth_yoy",
        "q_gross_margin",
        "q_operating_margin",
        "q_net_margin",
        "q_cash_conversion",
        "q_debt_to_equity",
        "q_current_ratio"
    ],

    "bank": [

        "bank_q_revenue_growth_yoy",
        "bank_q_net_income_growth_yoy",
        "bank_q_assets_growth_yoy",
        "bank_q_equity_growth_yoy",
        "bank_q_equity_to_assets"
    ],

    "insurance": [

        "insurance_q_revenue_growth_yoy",
        "insurance_q_net_income_growth_yoy",
        "insurance_q_equity_growth_yoy"
    ],

    "reit": [

        "reit_q_revenue_growth_yoy",
        "reit_q_operating_income_growth_yoy",
        "reit_q_net_income_growth_yoy",
        "reit_q_debt_to_assets"
    ]
}


# ============================================================
# Range Rules
# ============================================================

RANGE_RULES = {

    "score_opportunity_score":
        (0, 100),

    "score_risk_score":
        (0, 100),

    "score_turning_point_score":
        (0, 100),

    "score_confidence_score":
        (0, 100),

    "turning_engine_score":
        (0, 100),

    "turning_engine_confidence_score":
        (0, 100),

    "turning_engine_comparability_score":
        (0, 100),

    "turning_engine_breadth_score":
        (0, 100),

    "data_quality_score":
        (0, 100),

    "data_freshness_score":
        (0, 100),

    "data_coverage_score":
        (0, 100),

    "data_history_score":
        (0, 100),

    "data_continuity_score":
        (0, 100),

    "decision_score":
        (0, 100),

    "decision_confidence":
        (0, 100),

    "decision_reliability_score":
        (0, 100),

    "decision_momentum_score":
        (0, 100)
}


# ============================================================
# Helpers
# ============================================================

def safe_number(value):

    if value is None:
        return None

    try:

        return float(
            value
        )

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


def audit_message(
    severity,
    code,
    message
):

    return {

        "severity":
            severity,

        "code":
            code,

        "message":
            message
    }


# ============================================================
# Supabase Reads
# ============================================================

def get_active_stocks():

    response = (
        supabase
        .table(
            "stocks"
        )
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
            "id"
        )
        .execute()
    )

    return (
        response.data
        or []
    )


def get_financial_statements(
    stock_id
):

    response = (
        supabase
        .table(
            "financial_statements"
        )
        .select(
            "metric,"
            "period_end,"
            "period_type,"
            "value,"
            "source"
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


def get_financial_metrics(
    stock_id
):

    response = (
        supabase
        .table(
            "financial_metrics"
        )
        .select(
            "period_end,"
            "metric_name,"
            "metric_value,"
            "calculated_at"
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
# Model Periods
# ============================================================

def get_model_periods(
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
            metric_name.startswith(
                prefix
            )
            for metric_name
            in period_metrics
        ):

            valid.append(
                period_end
            )

    return valid


# ============================================================
# Limited Data Detector
# ============================================================

def detect_limited_data(
    periods,
    analysis_model,
    model_periods
):

    if not model_periods:

        return {

            "limited":
                False,

            "reason":
                None
        }

    latest_period = (
        model_periods[-1]
    )

    latest = periods.get(
        latest_period,
        {}
    )

    if analysis_model == "reit":

        if len(
            model_periods
        ) < 4:

            return {

                "limited":
                    True,

                "reason":
                    (
                        "REIT history limited: "
                        f"{len(model_periods)} "
                        "quarterly periods"
                    )
            }

        yoy_reference = safe_number(
            latest.get(
                "reit_q_yoy_reference_available"
            )
        )

        qoq_reference = safe_number(
            latest.get(
                "reit_q_qoq_reference_available"
            )
        )

        if (
            yoy_reference is not None
            and yoy_reference <= 0
        ):

            return {

                "limited":
                    True,

                "reason":
                    "REIT YoY reference unavailable"
            }

        if (
            qoq_reference is not None
            and qoq_reference <= 0
        ):

            return {

                "limited":
                    True,

                "reason":
                    "REIT QoQ reference unavailable"
            }

    return {

        "limited":
            False,

        "reason":
            None
    }


# ============================================================
# Latest Period For Metric
# ============================================================

def latest_period_for_metric(
    periods,
    metric_name
):

    matches = []

    for period_end in periods:

        if metric_name in periods[
            period_end
        ]:

            matches.append(
                period_end
            )

    if not matches:
        return None

    return sorted(
        matches
    )[-1]


# ============================================================
# Duplicate Detectors
# ============================================================

def find_metric_duplicates(rows):

    counter = Counter()

    for row in rows:

        key = (

            str(
                row.get(
                    "period_end"
                )
            ),

            row.get(
                "metric_name"
            )
        )

        counter[
            key
        ] += 1

    return {

        key:
            count

        for key, count
        in counter.items()

        if count > 1
    }


def find_statement_duplicates(rows):

    counter = Counter()

    for row in rows:

        key = (

            row.get(
                "metric"
            ),

            str(
                row.get(
                    "period_end"
                )
            ),

            row.get(
                "period_type"
            )
        )

        counter[
            key
        ] += 1

    return {

        key:
            count

        for key, count
        in counter.items()

        if count > 1
    }


# ============================================================
# Financial Statements Audit
# ============================================================

def audit_financial_statements(rows):

    findings = []

    if not rows:

        findings.append(
            audit_message(
                "FAIL",
                "RAW_NO_DATA",
                "لا توجد financial_statements للشركة"
            )
        )

        return findings

    if len(
        rows
    ) < 20:

        findings.append(
            audit_message(
                "WARN",
                "RAW_LOW_RECORD_COUNT",
                (
                    "عدد السجلات المالية الخام منخفض: "
                    f"{len(rows)}"
                )
            )
        )

    duplicates = (
        find_statement_duplicates(
            rows
        )
    )

    if duplicates:

        findings.append(
            audit_message(
                "FAIL",
                "RAW_DUPLICATES",
                (
                    "تم اكتشاف "
                    f"{len(duplicates)} "
                    "مفتاح مالي خام مكرر"
                )
            )
        )

    missing_source = sum(
        1
        for row in rows
        if not row.get(
            "source"
        )
    )

    if missing_source > 0:

        findings.append(
            audit_message(
                "WARN",
                "RAW_SOURCE_MISSING",
                (
                    f"{missing_source} "
                    "سجل بدون source"
                )
            )
        )

    period_types = {

        row.get(
            "period_type"
        )

        for row in rows

        if row.get(
            "period_type"
        )
    }

    if not period_types:

        findings.append(
            audit_message(
                "FAIL",
                "RAW_PERIOD_TYPE_MISSING",
                "لا توجد period_type في البيانات الخام"
            )
        )

    return findings


# ============================================================
# Metrics Structure Audit
# ============================================================

def audit_metrics_structure(
    rows,
    periods,
    analysis_model
):

    findings = []

    if not rows:

        findings.append(
            audit_message(
                "FAIL",
                "METRICS_NO_DATA",
                "لا توجد financial_metrics للشركة"
            )
        )

        return findings

    duplicates = (
        find_metric_duplicates(
            rows
        )
    )

    if duplicates:

        findings.append(
            audit_message(
                "FAIL",
                "METRICS_DUPLICATES",
                (
                    "تم اكتشاف "
                    f"{len(duplicates)} "
                    "metric مكرر لنفس الفترة"
                )
            )
        )

    model_periods = (
        get_model_periods(
            periods,
            analysis_model
        )
    )

    if not model_periods:

        findings.append(
            audit_message(
                "FAIL",
                "MODEL_NO_VALID_PERIOD",
                (
                    "لا توجد فترة صالحة "
                    f"لنموذج {analysis_model}"
                )
            )
        )

        return findings

    if len(
        model_periods
    ) < 2:

        findings.append(
            audit_message(
                "WARN",
                "MODEL_SHORT_HISTORY",
                "عدد الفترات الصالحة أقل من فترتين"
            )
        )

    return findings


# ============================================================
# Required Model Metrics Audit
# ============================================================

def audit_model_metrics(
    periods,
    analysis_model,
    latest_period,
    limited_data=False
):

    findings = []

    required = (
        MODEL_REQUIRED_METRICS.get(
            analysis_model,
            []
        )
    )

    if not required:

        findings.append(
            audit_message(
                "FAIL",
                "MODEL_UNKNOWN",
                (
                    "analysis_model غير معروف: "
                    f"{analysis_model}"
                )
            )
        )

        return findings

    latest = periods.get(
        latest_period,
        {}
    )

    missing = [

        metric_name

        for metric_name
        in required

        if latest.get(
            metric_name
        ) is None
    ]

    if not missing:
        return findings

    if limited_data:

        severity = "WARN"

        code = (
            "MODEL_REQUIRED_LIMITED_DATA"
        )

    else:

        severity = (
            "FAIL"
            if len(
                missing
            ) >= len(
                required
            ) / 2
            else "WARN"
        )

        code = (
            "MODEL_REQUIRED_MISSING"
        )

    findings.append(
        audit_message(
            severity,
            code,
            (
                f"مفقود "
                f"{len(missing)}/"
                f"{len(required)} "
                "من المؤشرات الأساسية: "
                + ", ".join(
                    missing
                )
            )
        )
    )

    return findings


# ============================================================
# Specialized Signal Layer Audit
# ============================================================

def audit_signal_layer(
    periods,
    latest_period,
    analysis_model,
    limited_data=False
):

    findings = []

    latest = periods.get(
        latest_period,
        {}
    )

    prefix = (
        MODEL_SIGNAL_PREFIX.get(
            analysis_model
        )
    )

    if not prefix:

        findings.append(
            audit_message(
                "FAIL",
                "SIGNAL_MODEL_UNKNOWN",
                (
                    "لا يوجد Signal Prefix "
                    f"للنموذج {analysis_model}"
                )
            )
        )

        return findings

    net_metric = (
        f"{prefix}net_score"
    )

    confidence_metric = (
        f"{prefix}confidence_score"
    )

    net_score = safe_number(
        latest.get(
            net_metric
        )
    )

    signal_confidence = safe_number(
        latest.get(
            confidence_metric
        )
    )

    if net_score is None:

        if limited_data:

            findings.append(
                audit_message(
                    "WARN",
                    "SIGNAL_LIMITED_DATA",
                    (
                        f"{net_metric} غير متوفر "
                        "بسبب محدودية البيانات"
                    )
                )
            )

        else:

            findings.append(
                audit_message(
                    "FAIL",
                    "SIGNAL_OUTPUT_MISSING",
                    (
                        f"{net_metric} غير متوفر "
                        "لأحدث فترة مالية"
                    )
                )
            )

    if (
        signal_confidence is not None
        and (
            signal_confidence < 0
            or signal_confidence > 100
        )
    ):

        findings.append(
            audit_message(
                "FAIL",
                "SIGNAL_CONFIDENCE_RANGE",
                (
                    f"{confidence_metric}="
                    f"{fmt(signal_confidence)} "
                    "خارج النطاق 0-100"
                )
            )
        )

    return findings


# ============================================================
# Engine Outputs Audit
# ============================================================

def audit_engine_outputs(
    periods,
    latest_period,
    limited_data=False
):

    findings = []

    latest = periods.get(
        latest_period,
        {}
    )

    for engine_name, metrics in (
        CORE_ENGINE_METRICS.items()
    ):

        missing = [

            metric_name

            for metric_name
            in metrics

            if latest.get(
                metric_name
            ) is None
        ]

        if not missing:
            continue

        if limited_data:

            findings.append(
                audit_message(
                    "WARN",
                    "ENGINE_OUTPUT_LIMITED_DATA",
                    (
                        f"{engine_name}: "
                        f"مفقود "
                        f"{len(missing)}/"
                        f"{len(metrics)} "
                        "بسبب محدودية البيانات: "
                        + ", ".join(
                            missing
                        )
                    )
                )
            )

        else:

            findings.append(
                audit_message(
                    "FAIL",
                    "ENGINE_OUTPUT_MISSING",
                    (
                        f"{engine_name}: "
                        f"مفقود "
                        f"{len(missing)}/"
                        f"{len(metrics)}: "
                        + ", ".join(
                            missing
                        )
                    )
                )
            )

    return findings


# ============================================================
# Range Audit
# ============================================================

def audit_ranges(
    periods,
    latest_period
):

    findings = []

    latest = periods.get(
        latest_period,
        {}
    )

    for metric_name, bounds in (
        RANGE_RULES.items()
    ):

        value = safe_number(
            latest.get(
                metric_name
            )
        )

        if value is None:
            continue

        minimum, maximum = bounds

        if (
            value < minimum
            or value > maximum
        ):

            findings.append(
                audit_message(
                    "FAIL",
                    "OUT_OF_RANGE",
                    (
                        f"{metric_name}="
                        f"{fmt(value)} "
                        "خارج النطاق "
                        f"{minimum}-{maximum}"
                    )
                )
            )

    return findings


# ============================================================
# Period Alignment Audit
# ============================================================

def audit_period_alignment(
    periods,
    latest_model_period,
    analysis_model
):

    findings = []

    signal_prefix = (
        MODEL_SIGNAL_PREFIX.get(
            analysis_model
        )
    )

    important_metrics = [

        "score_opportunity_score",

        "turning_engine_score",

        "turning_engine_state_code",

        "data_quality_score",

        "decision_score"
    ]

    if signal_prefix:

        important_metrics.append(
            f"{signal_prefix}net_score"
        )

    for metric_name in important_metrics:

        metric_period = (
            latest_period_for_metric(
                periods,
                metric_name
            )
        )

        if metric_period is None:
            continue

        if (
            metric_period
            != latest_model_period
        ):

            findings.append(
                audit_message(
                    "FAIL",
                    "PERIOD_MISALIGNMENT",
                    (
                        f"{metric_name} "
                        f"آخر فترة له "
                        f"{metric_period} "
                        "بينما أحدث فترة مالية "
                        f"{latest_model_period}"
                    )
                )
            )

    return findings


# ============================================================
# Scoring Internal Logic
#
# Base Turning وTurning Engine مستقلان.
# اختلافهما ليس خطأ.
# ============================================================

def audit_score_logic(
    periods,
    latest_period
):

    findings = []

    latest = periods.get(
        latest_period,
        {}
    )

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

    if (
        opportunity is not None
        and risk is not None
        and opportunity >= 80
        and risk >= 70
    ):

        findings.append(
            audit_message(
                "WARN",
                "OPPORTUNITY_RISK_CONTRADICTION",
                (
                    f"Opportunity="
                    f"{fmt(opportunity)} "
                    "و Risk="
                    f"{fmt(risk)} "
                    "مرتفعان معًا"
                )
            )
        )

    return findings


# ============================================================
# Turning Engine v2.0.2 Audit
# ============================================================

def audit_turning_logic(
    periods,
    latest_period,
    limited_data=False
):

    findings = []

    latest = periods.get(
        latest_period,
        {}
    )

    score = safe_number(
        latest.get(
            "turning_engine_score"
        )
    )

    state_code = safe_number(
        latest.get(
            "turning_engine_state_code"
        )
    )

    confidence = safe_number(
        latest.get(
            "turning_engine_confidence_score"
        )
    )

    comparability = safe_number(
        latest.get(
            "turning_engine_comparability_score"
        )
    )

    breadth = safe_number(
        latest.get(
            "turning_engine_breadth_score"
        )
    )

    deterioration = safe_number(
        latest.get(
            "turning_engine_deterioration_score"
        )
    )

    common_inputs = safe_number(
        latest.get(
            "turning_engine_common_inputs"
        )
    )

    # --------------------------------------------------------
    # LIMITED DATA
    # --------------------------------------------------------

    if limited_data:

        if (
            state_code is None
            or score is None
        ):

            return findings

    # --------------------------------------------------------
    # State Code
    # --------------------------------------------------------

    if state_code is None:

        findings.append(
            audit_message(
                "FAIL",
                "TURNING_STATE_MISSING",
                "turning_engine_state_code غير موجود"
            )
        )

        return findings

    rounded_state = int(
        round(
            state_code
        )
    )

    if abs(
        state_code
        - rounded_state
    ) > 0.001:

        findings.append(
            audit_message(
                "FAIL",
                "TURNING_STATE_INVALID",
                (
                    "turning_engine_state_code "
                    "ليس Integer صالحًا: "
                    f"{fmt(state_code)}"
                )
            )
        )

        return findings

    state = TURNING_STATE_CODES.get(
        rounded_state
    )

    if state is None:

        findings.append(
            audit_message(
                "FAIL",
                "TURNING_STATE_UNKNOWN",
                (
                    "Turning State Code غير معروف: "
                    f"{rounded_state}"
                )
            )
        )

        return findings

    # --------------------------------------------------------
    # LOW CONFIDENCE
    # --------------------------------------------------------

    if state == "LOW_CONFIDENCE":

        gate_reason_exists = False

        if (
            confidence is not None
            and confidence < 55
        ):
            gate_reason_exists = True

        if (
            comparability is not None
            and comparability < 50
        ):
            gate_reason_exists = True

        if (
            common_inputs is not None
            and common_inputs < 3
        ):
            gate_reason_exists = True

        if not gate_reason_exists:

            findings.append(
                audit_message(
                    "WARN",
                    "TURNING_LOW_CONFIDENCE_CONFLICT",
                    (
                        "State=LOW_CONFIDENCE "
                        "لكن بوابات الجودة الظاهرة "
                        "لا تفسر الحالة"
                    )
                )
            )

    # --------------------------------------------------------
    # STRONG TURNING POINT
    # --------------------------------------------------------

    if state == "STRONG_TURNING_POINT":

        if (
            score is not None
            and score < 80
        ):

            findings.append(
                audit_message(
                    "FAIL",
                    "TURNING_STRONG_SCORE_CONFLICT",
                    (
                        "State=STRONG_TURNING_POINT "
                        "لكن Turning Score="
                        f"{fmt(score)}"
                    )
                )
            )

        if (
            breadth is not None
            and breadth < 60
        ):

            findings.append(
                audit_message(
                    "FAIL",
                    "TURNING_STRONG_BREADTH_CONFLICT",
                    (
                        "Strong Turning مع Breadth="
                        f"{fmt(breadth)}% "
                        "أقل من 60%"
                    )
                )
            )

    # --------------------------------------------------------
    # EARLY TURNING POINT
    # --------------------------------------------------------

    if state == "EARLY_TURNING_POINT":

        if (
            score is not None
            and score < 65
        ):

            findings.append(
                audit_message(
                    "FAIL",
                    "TURNING_EARLY_SCORE_CONFLICT",
                    (
                        "State=EARLY_TURNING_POINT "
                        "لكن Turning Score="
                        f"{fmt(score)}"
                    )
                )
            )

        if (
            breadth is not None
            and breadth < 35
        ):

            findings.append(
                audit_message(
                    "FAIL",
                    "TURNING_EARLY_BREADTH_CONFLICT",
                    (
                        "Early Turning مع Breadth="
                        f"{fmt(breadth)}% "
                        "أقل من 35%"
                    )
                )
            )

    # --------------------------------------------------------
    # IMPROVING LIMITED HISTORY
    # --------------------------------------------------------

    if (
        state
        == "IMPROVING_LIMITED_HISTORY"
    ):

        if (
            breadth is not None
            and breadth >= 35
        ):

            findings.append(
                audit_message(
                    "WARN",
                    "TURNING_LIMITED_HISTORY_CONFLICT",
                    (
                        "State="
                        "IMPROVING_LIMITED_HISTORY "
                        "لكن Breadth="
                        f"{fmt(breadth)}%"
                    )
                )
            )

    # --------------------------------------------------------
    # STRONG CONTINUATION
    # --------------------------------------------------------

    if state == "STRONG_CONTINUATION":

        if (
            score is not None
            and score < 75
        ):

            findings.append(
                audit_message(
                    "FAIL",
                    "TURNING_CONTINUATION_SCORE_CONFLICT",
                    (
                        "State=STRONG_CONTINUATION "
                        "لكن Turning Score="
                        f"{fmt(score)}"
                    )
                )
            )

    # --------------------------------------------------------
    # DETERIORATING
    # --------------------------------------------------------

    if state == "DETERIORATING":

        if (
            deterioration is not None
            and deterioration < 15
        ):

            findings.append(
                audit_message(
                    "WARN",
                    "TURNING_DETERIORATION_CONFLICT",
                    (
                        "State=DETERIORATING "
                        "لكن Deterioration Score="
                        f"{fmt(deterioration)}"
                    )
                )
            )

    # --------------------------------------------------------
    # WEAK
    # --------------------------------------------------------

    if state == "WEAK":

        if (
            score is not None
            and score >= 55
        ):

            findings.append(
                audit_message(
                    "WARN",
                    "TURNING_WEAK_SCORE_CONFLICT",
                    (
                        "State=WEAK "
                        "لكن Turning Score="
                        f"{fmt(score)}"
                    )
                )
            )

    return findings


# ============================================================
# Data Quality Logic
# ============================================================

def audit_data_quality_logic(
    periods,
    latest_period
):

    findings = []

    latest = periods.get(
        latest_period,
        {}
    )

    quality = safe_number(
        latest.get(
            "data_quality_score"
        )
    )

    freshness = safe_number(
        latest.get(
            "data_freshness_score"
        )
    )

    coverage = safe_number(
        latest.get(
            "data_coverage_score"
        )
    )

    market_lag = safe_number(
        latest.get(
            "data_market_lag_days"
        )
    )

    if (
        quality is not None
        and quality >= 90
        and freshness is not None
        and freshness < 50
    ):

        findings.append(
            audit_message(
                "FAIL",
                "QUALITY_FRESHNESS_CONFLICT",
                (
                    f"DataQuality="
                    f"{fmt(quality)} "
                    "مع Freshness="
                    f"{fmt(freshness)}"
                )
            )
        )

    if (
        quality is not None
        and quality >= 90
        and coverage is not None
        and coverage < 60
    ):

        findings.append(
            audit_message(
                "FAIL",
                "QUALITY_COVERAGE_CONFLICT",
                (
                    f"DataQuality="
                    f"{fmt(quality)} "
                    "مع Coverage="
                    f"{fmt(coverage)}"
                )
            )
        )

    if (
        freshness is not None
        and freshness >= 90
        and market_lag is not None
        and market_lag >= 75
    ):

        findings.append(
            audit_message(
                "FAIL",
                "FRESHNESS_LAG_CONFLICT",
                (
                    f"Freshness="
                    f"{fmt(freshness)} "
                    "مع MarketLag="
                    f"{fmt(market_lag)}"
                )
            )
        )

    return findings


# ============================================================
# Decision Logic Audit
# ============================================================

def audit_decision_logic(
    periods,
    latest_period
):

    findings = []

    latest = periods.get(
        latest_period,
        {}
    )

    decision = safe_number(
        latest.get(
            "decision_score"
        )
    )

    risk = safe_number(
        latest.get(
            "score_risk_score"
        )
    )

    opportunity = safe_number(
        latest.get(
            "score_opportunity_score"
        )
    )

    turning = safe_number(
        latest.get(
            "turning_engine_score"
        )
    )

    turning_state_code = safe_number(
        latest.get(
            "turning_engine_state_code"
        )
    )

    data_quality = safe_number(
        latest.get(
            "data_quality_score"
        )
    )

    freshness = safe_number(
        latest.get(
            "data_freshness_score"
        )
    )

    coverage = safe_number(
        latest.get(
            "data_coverage_score"
        )
    )

    reliability = safe_number(
        latest.get(
            "decision_reliability_score"
        )
    )

    market_lag = safe_number(
        latest.get(
            "data_market_lag_days"
        )
    )

    state = None

    if turning_state_code is not None:

        rounded_state = int(
            round(
                turning_state_code
            )
        )

        if abs(
            turning_state_code
            - rounded_state
        ) <= 0.001:

            state = TURNING_STATE_CODES.get(
                rounded_state
            )

    # --------------------------------------------------------
    # High Decision vs Data Quality
    # --------------------------------------------------------

    if (
        decision is not None
        and decision >= 75
        and data_quality is not None
        and data_quality < 70
    ):

        findings.append(
            audit_message(
                "FAIL",
                "DECISION_DATA_CONFLICT",
                (
                    f"Decision="
                    f"{fmt(decision)} مرتفع "
                    "مع DataQuality="
                    f"{fmt(data_quality)}"
                )
            )
        )

    # --------------------------------------------------------
    # Stale Data
    # --------------------------------------------------------

    if (
        decision is not None
        and decision >= 70
        and freshness is not None
        and freshness < 50
    ):

        findings.append(
            audit_message(
                "FAIL",
                "DECISION_STALE_DATA",
                (
                    f"Decision="
                    f"{fmt(decision)} مرتفع "
                    "مع Freshness="
                    f"{fmt(freshness)}"
                )
            )
        )

    # --------------------------------------------------------
    # Market Lag
    # --------------------------------------------------------

    if (
        decision is not None
        and decision >= 70
        and market_lag is not None
        and market_lag >= 75
    ):

        findings.append(
            audit_message(
                "FAIL",
                "DECISION_MARKET_LAG_CONFLICT",
                (
                    f"Decision="
                    f"{fmt(decision)} "
                    "مع MarketLag="
                    f"{fmt(market_lag)} يوم"
                )
            )
        )

    # --------------------------------------------------------
    # High Decision / High Risk
    # --------------------------------------------------------

    if (
        decision is not None
        and decision >= 75
        and risk is not None
        and risk >= 60
    ):

        findings.append(
            audit_message(
                "WARN",
                "DECISION_RISK_CONFLICT",
                (
                    f"Decision="
                    f"{fmt(decision)} "
                    "مع Risk="
                    f"{fmt(risk)}"
                )
            )
        )

    # --------------------------------------------------------
    # High Decision / Weak Opportunity
    # --------------------------------------------------------

    if (
        decision is not None
        and decision >= 75
        and opportunity is not None
        and opportunity < 45
    ):

        findings.append(
            audit_message(
                "WARN",
                "DECISION_OPPORTUNITY_CONFLICT",
                (
                    f"Decision="
                    f"{fmt(decision)} "
                    "مع Opportunity="
                    f"{fmt(opportunity)}"
                )
            )
        )

    # --------------------------------------------------------
    # Reliability
    # --------------------------------------------------------

    if (
        decision is not None
        and decision >= 70
        and reliability is not None
        and reliability < 65
    ):

        findings.append(
            audit_message(
                "FAIL",
                "DECISION_RELIABILITY_CONFLICT",
                (
                    f"Decision="
                    f"{fmt(decision)} "
                    "مع Reliability="
                    f"{fmt(reliability)}"
                )
            )
        )

    # --------------------------------------------------------
    # Coverage
    # --------------------------------------------------------

    if (
        decision is not None
        and decision >= 70
        and coverage is not None
        and coverage < 60
    ):

        findings.append(
            audit_message(
                "FAIL",
                "DECISION_COVERAGE_CONFLICT",
                (
                    f"Decision="
                    f"{fmt(decision)} "
                    "مع Coverage="
                    f"{fmt(coverage)}"
                )
            )
        )

    # --------------------------------------------------------
    # Turning vs Decision
    # --------------------------------------------------------

    if (
        turning is not None
        and turning >= 80
        and decision is not None
        and decision < 45
        and state in (
            "STRONG_TURNING_POINT",
            "STRONG_CONTINUATION"
        )
    ):

        findings.append(
            audit_message(
                "INFO",
                "TURNING_DECISION_DIVERGENCE",
                (
                    f"Turning="
                    f"{fmt(turning)} "
                    f"({state}) "
                    "لكن Decision="
                    f"{fmt(decision)}"
                )
            )
        )

    return findings


# ============================================================
# Audit Classification
# ============================================================

def classify_audit(findings):

    fail_count = sum(

        1

        for finding
        in findings

        if finding[
            "severity"
        ] == "FAIL"
    )

    warn_count = sum(

        1

        for finding
        in findings

        if finding[
            "severity"
        ] == "WARN"
    )

    info_count = sum(

        1

        for finding
        in findings

        if finding[
            "severity"
        ] == "INFO"
    )

    if fail_count > 0:

        status = "FAIL"

    elif warn_count > 0:

        status = "WARNING"

    else:

        status = "PASS"

    score = 100.0

    score -= (
        fail_count
        * 25
    )

    score -= (
        warn_count
        * 8
    )

    score -= (
        info_count
        * 1
    )

    score = max(
        0.0,
        score
    )

    return {

        "status":
            status,

        "audit_score":
            score,

        "fail_count":
            fail_count,

        "warn_count":
            warn_count,

        "info_count":
            info_count
    }


# ============================================================
# Audit One Stock
# ============================================================

def audit_stock(stock):

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

    raw_rows = (
        get_financial_statements(
            stock_id
        )
    )

    metric_rows = (
        get_financial_metrics(
            stock_id
        )
    )

    periods = (
        organize_metrics(
            metric_rows
        )
    )

    model_periods = (
        get_model_periods(
            periods,
            analysis_model
        )
    )

    latest_period = (

        model_periods[-1]

        if model_periods

        else None
    )

    limited_info = (
        detect_limited_data(
            periods,
            analysis_model,
            model_periods
        )
    )

    limited_data = (
        limited_info[
            "limited"
        ]
    )

    limited_reason = (
        limited_info[
            "reason"
        ]
    )

    findings = []

    findings.extend(
        audit_financial_statements(
            raw_rows
        )
    )

    findings.extend(
        audit_metrics_structure(
            metric_rows,
            periods,
            analysis_model
        )
    )

    if limited_data:

        findings.append(
            audit_message(
                "WARN",
                "LIMITED_SOURCE_DATA",
                (
                    "البيانات المالية محدودة "
                    "ولكن Pipeline يعمل بصورة صحيحة"
                    + (
                        f": {limited_reason}"
                        if limited_reason
                        else ""
                    )
                )
            )
        )

    if latest_period:

        findings.extend(
            audit_model_metrics(
                periods,
                analysis_model,
                latest_period,
                limited_data
            )
        )

        findings.extend(
            audit_signal_layer(
                periods,
                latest_period,
                analysis_model,
                limited_data
            )
        )

        findings.extend(
            audit_engine_outputs(
                periods,
                latest_period,
                limited_data
            )
        )

        findings.extend(
            audit_ranges(
                periods,
                latest_period
            )
        )

        findings.extend(
            audit_period_alignment(
                periods,
                latest_period,
                analysis_model
            )
        )

        findings.extend(
            audit_score_logic(
                periods,
                latest_period
            )
        )

        findings.extend(
            audit_turning_logic(
                periods,
                latest_period,
                limited_data
            )
        )

        findings.extend(
            audit_data_quality_logic(
                periods,
                latest_period
            )
        )

        findings.extend(
            audit_decision_logic(
                periods,
                latest_period
            )
        )

    classification = (
        classify_audit(
            findings
        )
    )

    latest_values = (

        periods.get(
            latest_period,
            {}
        )

        if latest_period

        else {}
    )

    turning_state_code = safe_number(
        latest_values.get(
            "turning_engine_state_code"
        )
    )

    turning_state = None

    if turning_state_code is not None:

        rounded_state = int(
            round(
                turning_state_code
            )
        )

        if abs(
            turning_state_code
            - rounded_state
        ) <= 0.001:

            turning_state = (
                TURNING_STATE_CODES.get(
                    rounded_state
                )
            )

    return {

        "symbol":
            symbol,

        "company_name":
            company_name,

        "analysis_model":
            analysis_model,

        "latest_period":
            latest_period,

        "raw_records":
            len(
                raw_rows
            ),

        "metric_records":
            len(
                metric_rows
            ),

        "period_count":
            len(
                model_periods
            ),

        "limited_data":
            limited_data,

        "limited_reason":
            limited_reason,

        "decision_score":
            safe_number(
                latest_values.get(
                    "decision_score"
                )
            ),

        "data_quality":
            safe_number(
                latest_values.get(
                    "data_quality_score"
                )
            ),

        "reliability":
            safe_number(
                latest_values.get(
                    "decision_reliability_score"
                )
            ),

        "turning_score":
            safe_number(
                latest_values.get(
                    "turning_engine_score"
                )
            ),

        "turning_state":
            turning_state,

        "turning_breadth":
            safe_number(
                latest_values.get(
                    "turning_engine_breadth_score"
                )
            ),

        "audit_status":
            classification[
                "status"
            ],

        "audit_score":
            classification[
                "audit_score"
            ],

        "fail_count":
            classification[
                "fail_count"
            ],

        "warn_count":
            classification[
                "warn_count"
            ],

        "info_count":
            classification[
                "info_count"
            ],

        "findings":
            findings
    }


# ============================================================
# Print Stock Audit
# ============================================================

def print_stock_audit(result):

    print_header(
        f"🔬 {result['symbol']} | "
        f"{result['company_name']} | "
        f"{result['analysis_model']}"
    )

    print(
        f"📅 Latest Period: "
        f"{result['latest_period'] or 'N/A'}",
        flush=True
    )

    print(
        f"📄 Raw Records: "
        f"{result['raw_records']}",
        flush=True
    )

    print(
        f"📊 Metric Records: "
        f"{result['metric_records']}",
        flush=True
    )

    print(
        f"📚 Financial Periods: "
        f"{result['period_count']}",
        flush=True
    )

    if result[
        "limited_data"
    ]:

        print(
            "🟡 Data Mode: LIMITED DATA",
            flush=True
        )

        print(
            f"📝 Reason: "
            f"{result['limited_reason']}",
            flush=True
        )

    else:

        print(
            "🟢 Data Mode: NORMAL",
            flush=True
        )

    print(
        f"🎯 Decision: "
        f"{fmt(result['decision_score'])}",
        flush=True
    )

    print(
        f"🧪 Data Quality: "
        f"{fmt(result['data_quality'])}",
        flush=True
    )

    print(
        f"🛡 Reliability: "
        f"{fmt(result['reliability'])}",
        flush=True
    )

    print(
        f"🧭 Turning: "
        f"{fmt(result['turning_score'])} | "
        f"{result['turning_state'] or 'N/A'}",
        flush=True
    )

    if (
        result[
            "turning_breadth"
        ] is not None
    ):

        print(
            f"📐 Turning Breadth: "
            f"{fmt(result['turning_breadth'])}%",
            flush=True
        )

    print_separator()

    print(
        f"🧭 AUDIT STATUS: "
        f"{result['audit_status']}",
        flush=True
    )

    print(
        f"🏆 Audit Score: "
        f"{fmt(result['audit_score'])}",
        flush=True
    )

    print(
        f"🔴 Fail: "
        f"{result['fail_count']} | "
        f"🟡 Warning: "
        f"{result['warn_count']} | "
        f"🔵 Info: "
        f"{result['info_count']}",
        flush=True
    )

    if not result[
        "findings"
    ]:

        print(
            "\n"
            "✅ لا توجد ملاحظات تدقيق",
            flush=True
        )

        return

    print(
        "\n📋 FINDINGS",
        flush=True
    )

    for finding in result[
        "findings"
    ]:

        severity = finding[
            "severity"
        ]

        if severity == "FAIL":

            icon = "🔴"

        elif severity == "WARN":

            icon = "🟡"

        else:

            icon = "🔵"

        print(
            f"{icon} "
            f"[{finding['code']}] "
            f"{finding['message']}",
            flush=True
        )


# ============================================================
# System-wide Audit
# ============================================================

def audit_system_consistency(
    results
):

    findings = []

    symbols = [

        result[
            "symbol"
        ]

        for result
        in results
    ]

    duplicate_symbols = [

        symbol

        for symbol, count
        in Counter(
            symbols
        ).items()

        if count > 1
    ]

    if duplicate_symbols:

        findings.append(
            audit_message(
                "FAIL",
                "SYSTEM_DUPLICATE_SYMBOL",
                (
                    "Symbols مكررة: "
                    + ", ".join(
                        duplicate_symbols
                    )
                )
            )
        )

    decision_values = [

        result[
            "decision_score"
        ]

        for result
        in results

        if result[
            "decision_score"
        ] is not None
    ]

    if decision_values:

        high_count = sum(

            1

            for value
            in decision_values

            if value >= 80
        )

        if (
            high_count
            > len(
                decision_values
            ) * 0.50
        ):

            findings.append(
                audit_message(
                    "WARN",
                    "SYSTEM_DECISION_INFLATION",
                    (
                        "أكثر من نصف الشركات "
                        "Decision >= 80"
                    )
                )
            )

        zero_count = sum(

            1

            for value
            in decision_values

            if value == 0
        )

        if (
            zero_count
            > len(
                decision_values
            ) * 0.50
        ):

            findings.append(
                audit_message(
                    "WARN",
                    "SYSTEM_DECISION_COLLAPSE",
                    (
                        "أكثر من نصف الشركات "
                        "Decision = 0"
                    )
                )
            )

    period_counter = Counter(

        result[
            "latest_period"
        ]

        for result
        in results

        if result[
            "latest_period"
        ]
    )

    if period_counter:

        print(
            "\n📅 Latest Period Distribution:",
            flush=True
        )

        for period, count in sorted(
            period_counter.items(),
            reverse=True
        ):

            print(
                f"- {period}: "
                f"{count} companies",
                flush=True
            )

    return findings


# ============================================================
# Final Summary
# ============================================================

def print_final_summary(
    results,
    system_findings
):

    print_header(
        f"🏆 MASTER SYSTEM AUDIT SUMMARY "
        f"v{ENGINE_VERSION}"
    )

    sorted_results = sorted(

        results,

        key=lambda item: (

            item[
                "audit_score"
            ],

            item[
                "symbol"
            ]
        )
    )

    for index, result in enumerate(
        sorted_results,
        start=1
    ):

        data_mode = (

            "LIMITED"

            if result[
                "limited_data"
            ]

            else "NORMAL"
        )

        print(
            f"{index:02d}. "
            f"{result['symbol']} | "
            f"{result['company_name']} | "
            f"{result['analysis_model']} | "
            f"Data={data_mode} | "
            f"Audit={fmt(result['audit_score'])} | "
            f"Status={result['audit_status']} | "
            f"Fail={result['fail_count']} | "
            f"Warn={result['warn_count']} | "
            f"Info={result['info_count']} | "
            f"Decision={fmt(result['decision_score'])} | "
            f"DataQuality={fmt(result['data_quality'])} | "
            f"Turning={fmt(result['turning_score'])} | "
            f"TurningState="
            f"{result['turning_state'] or 'N/A'}",
            flush=True
        )

    pass_count = sum(

        1

        for result
        in results

        if result[
            "audit_status"
        ] == "PASS"
    )

    warning_count = sum(

        1

        for result
        in results

        if result[
            "audit_status"
        ] == "WARNING"
    )

    fail_count = sum(

        1

        for result
        in results

        if result[
            "audit_status"
        ] == "FAIL"
    )

    limited_count = sum(

        1

        for result
        in results

        if result[
            "limited_data"
        ]
    )

    total_company_failures = sum(

        result[
            "fail_count"
        ]

        for result
        in results
    )

    total_company_warnings = sum(

        result[
            "warn_count"
        ]

        for result
        in results
    )

    print_separator()

    print(
        f"🏢 Total Companies: "
        f"{len(results)}",
        flush=True
    )

    print(
        f"🟢 PASS: "
        f"{pass_count}",
        flush=True
    )

    print(
        f"🟡 WARNING: "
        f"{warning_count}",
        flush=True
    )

    print(
        f"🔴 FAIL: "
        f"{fail_count}",
        flush=True
    )

    print(
        f"🟠 LIMITED DATA: "
        f"{limited_count}",
        flush=True
    )

    print(
        f"🔴 Total Company Fail Findings: "
        f"{total_company_failures}",
        flush=True
    )

    print(
        f"🟡 Total Company Warnings: "
        f"{total_company_warnings}",
        flush=True
    )

    if system_findings:

        print(
            "\n🌐 SYSTEM FINDINGS",
            flush=True
        )

        for finding in (
            system_findings
        ):

            severity = finding[
                "severity"
            ]

            if severity == "FAIL":

                icon = "🔴"

            elif severity == "WARN":

                icon = "🟡"

            else:

                icon = "🔵"

            print(
                f"{icon} "
                f"[{finding['code']}] "
                f"{finding['message']}",
                flush=True
            )

    else:

        print(
            "\n"
            "✅ لا توجد مشاكل "
            "System-wide ظاهرة",
            flush=True
        )

    system_fail_count = sum(

        1

        for finding
        in system_findings

        if finding[
            "severity"
        ] == "FAIL"
    )

    if (
        fail_count == 0
        and system_fail_count == 0
    ):

        if (
            warning_count == 0
            and limited_count == 0
        ):

            overall = "PASS"

        else:

            overall = (
                "PASS_WITH_LIMITATIONS"
            )

    else:

        overall = (
            "REVIEW_REQUIRED"
        )

    print_separator()

    print(
        f"🧭 SYSTEM AUDIT RESULT: "
        f"{overall}",
        flush=True
    )

    print(
        "\n"
        "✅ Turning Audit v1.2.1: "
        "State Codes متطابقة مع Turning Engine v2.0.2.",
        flush=True
    )

    print(
        "✅ Base Turning وTurning Engine "
        "مستقلان ولا يعاقب النظام على اختلافهما.",
        flush=True
    )

    print(
        "✅ Turning State Audit: "
        "يتم تدقيق state_code مقابل "
        "Score / Breadth / Confidence.",
        flush=True
    )

    print(
        "✅ Specialized Signal Audit: "
        "Standard / Bank / Insurance / REIT.",
        flush=True
    )

    print(
        "✅ Momentum Boundary القديم تمت إزالته "
        "لأنه لم يكن يمثل خللًا حقيقيًا.",
        flush=True
    )

    print(
        "✅ LIMITED DATA لا يتحول تلقائيًا "
        "إلى System Failure.",
        flush=True
    )

    print(
        "🔒 READ ONLY | "
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

def run_system_audit():

    print_header(
        f"🔬 MASTER SYSTEM AUDIT ENGINE "
        f"v{ENGINE_VERSION}"
    )

    print(
        "🔒 Mode: READ ONLY",
        flush=True
    )

    print(
        "🧠 Turning State Source: "
        "turning_engine_state_code",
        flush=True
    )

    print(
        "🔢 Turning State Map: "
        "v2.0.2",
        flush=True
    )

    print(
        "📡 Signal Audit: "
        "Model-Aware",
        flush=True
    )

    print(
        f"🕐 Started: "
        f"{datetime.now(timezone.utc).isoformat()}",
        flush=True
    )

    stocks = (
        get_active_stocks()
    )

    print(
        f"🏢 Active Companies: "
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
            f"🔍 Audit "
            f"{index}/"
            f"{len(stocks)} | "
            f"{stock['symbol']}",
            flush=True
        )

        try:

            result = (
                audit_stock(
                    stock
                )
            )

        except Exception as error:

            result = {

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

                "latest_period":
                    None,

                "raw_records":
                    0,

                "metric_records":
                    0,

                "period_count":
                    0,

                "limited_data":
                    False,

                "limited_reason":
                    None,

                "decision_score":
                    None,

                "data_quality":
                    None,

                "reliability":
                    None,

                "turning_score":
                    None,

                "turning_state":
                    None,

                "turning_breadth":
                    None,

                "audit_status":
                    "FAIL",

                "audit_score":
                    0,

                "fail_count":
                    1,

                "warn_count":
                    0,

                "info_count":
                    0,

                "findings": [

                    audit_message(
                        "FAIL",
                        "AUDIT_RUNTIME_ERROR",
                        (
                            f"{type(error).__name__}: "
                            f"{error}"
                        )
                    )
                ]
            }

        results.append(
            result
        )

        print_stock_audit(
            result
        )

    system_findings = (
        audit_system_consistency(
            results
        )
    )

    print_final_summary(
        results,
        system_findings
    )


if __name__ == "__main__":

    run_system_audit()
