import os
from collections import Counter
from datetime import datetime, timezone

from supabase import create_client


# ============================================================
# SYSTEM AUDIT ENGINE v1.1
#
# الهدف:
# تدقيق النظام المالي كاملًا:
#
# 1) stocks
# 2) financial_statements
# 3) financial_metrics
# 4) specialized models
# 5) scoring
# 6) turning point
# 7) data quality
# 8) final decision
#
# المحرك READ ONLY
# لا يكتب أو يعدل أي بيانات
#
# v1.1:
# - التمييز بين SYSTEM FAILURE و LIMITED DATA
# - عدم اعتبار نقص بيانات REIT المعروف فشلًا في النظام
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
# إعدادات
# ============================================================


MODEL_PREFIX = {
    "standard": "q_",
    "bank": "bank_q_",
    "insurance": "insurance_q_",
    "reit": "reit_q_"
}


CORE_ENGINE_METRICS = {

    "scoring": [
        "score_opportunity_score",
        "score_risk_score",
        "score_turning_point_score",
        "score_confidence_score"
    ],

    "turning": [
        "turning_engine_score"
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


RANGE_RULES = {

    "score_opportunity_score": (0, 100),
    "score_risk_score": (0, 100),
    "score_turning_point_score": (0, 100),
    "score_confidence_score": (0, 100),

    "turning_engine_score": (0, 100),

    "data_quality_score": (0, 100),
    "data_freshness_score": (0, 100),
    "data_coverage_score": (0, 100),
    "data_history_score": (0, 100),
    "data_continuity_score": (0, 100),

    "decision_score": (0, 100),
    "decision_confidence": (0, 100),
    "decision_reliability_score": (0, 100),
    "decision_momentum_score": (0, 100)
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


def fmt(value, decimals=2):

    value = safe_number(value)

    if value is None:
        return "N/A"

    return f"{value:.{decimals}f}"


def print_header(title):

    print(
        "\n" + "=" * 88,
        flush=True
    )

    print(
        title,
        flush=True
    )

    print(
        "=" * 88,
        flush=True
    )


def print_separator():

    print(
        "-" * 88,
        flush=True
    )


def audit_message(
    severity,
    code,
    message
):

    return {
        "severity": severity,
        "code": code,
        "message": message
    }


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
            "data_status,"
            "is_active"
        )
        .eq(
            "is_active",
            True
        )
        .order("id")
        .execute()
    )

    return response.data or []


def get_financial_statements(stock_id):

    response = (
        supabase
        .table("financial_statements")
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

    return response.data or []


def get_financial_metrics(stock_id):

    response = (
        supabase
        .table("financial_metrics")
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

    return response.data or []


# ============================================================
# تنظيم financial_metrics
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
# الفترات المالية الخاصة بالنموذج
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
            metric_name.startswith(prefix)
            for metric_name in period_metrics
        ):

            valid.append(
                period_end
            )

    return valid


# ============================================================
# LIMITED DATA DETECTOR
#
# مهم جدًا:
# نقص المصدر لا يعني أن Pipeline معطل.
#
# الراجحي ريت مثال:
# 3 فترات ربعية فقط + ضعف مراجع QoQ/YoY.
# ============================================================


def detect_limited_data(
    periods,
    analysis_model,
    model_periods
):

    if not model_periods:

        return {
            "limited": False,
            "reason": None
        }

    latest_period = model_periods[-1]

    latest = periods.get(
        latest_period,
        {}
    )

    # --------------------------------------------------------
    # REIT
    # --------------------------------------------------------

    if analysis_model == "reit":

        # أقل من 4 أرباع لا يسمح بتاريخ ربعي مكتمل
        if len(model_periods) < 4:

            return {
                "limited": True,
                "reason": (
                    f"REIT history limited: "
                    f"{len(model_periods)} quarterly periods"
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
                "limited": True,
                "reason": (
                    "REIT YoY reference unavailable"
                )
            }

        if (
            qoq_reference is not None
            and qoq_reference <= 0
        ):

            return {
                "limited": True,
                "reason": (
                    "REIT QoQ reference unavailable"
                )
            }

    return {
        "limited": False,
        "reason": None
    }


# ============================================================
# أحدث فترة تحتوي Metric معين
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

    return sorted(matches)[-1]


# ============================================================
# Duplicate detectors
# ============================================================


def find_metric_duplicates(rows):

    counter = Counter()

    for row in rows:

        key = (
            str(
                row.get("period_end")
            ),
            row.get("metric_name")
        )

        counter[key] += 1

    return {
        key: count
        for key, count in counter.items()
        if count > 1
    }


def find_statement_duplicates(rows):

    counter = Counter()

    for row in rows:

        key = (
            row.get("metric"),
            str(
                row.get("period_end")
            ),
            row.get("period_type")
        )

        counter[key] += 1

    return {
        key: count
        for key, count in counter.items()
        if count > 1
    }


# ============================================================
# Financial statements audit
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

    if len(rows) < 20:

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
        find_statement_duplicates(rows)
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
        if not row.get("source")
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
        row.get("period_type")
        for row in rows
        if row.get("period_type")
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
# Metrics structure audit
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
        find_metric_duplicates(rows)
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

    if len(model_periods) < 2:

        findings.append(
            audit_message(
                "WARN",
                "MODEL_SHORT_HISTORY",
                "عدد الفترات الصالحة أقل من فترتين"
            )
        )

    return findings


# ============================================================
# Required model metrics
# ============================================================


def audit_model_metrics(
    periods,
    analysis_model,
    latest_period,
    limited_data=False
):

    findings = []

    required = MODEL_REQUIRED_METRICS.get(
        analysis_model,
        []
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
        for metric_name in required
        if latest.get(metric_name) is None
    ]

    if missing:

        # ----------------------------------------------------
        # إذا المصدر نفسه محدود
        # لا نحول النقص المعروف إلى SYSTEM FAILURE
        # ----------------------------------------------------

        if limited_data:

            severity = "WARN"
            code = "MODEL_REQUIRED_LIMITED_DATA"

        else:

            severity = (
                "FAIL"
                if len(missing)
                >= len(required) / 2
                else "WARN"
            )

            code = "MODEL_REQUIRED_MISSING"

        findings.append(
            audit_message(
                severity,
                code,
                (
                    f"مفقود {len(missing)}/"
                    f"{len(required)} "
                    "من المؤشرات الأساسية: "
                    + ", ".join(missing)
                )
            )
        )

    return findings


# ============================================================
# Engine outputs audit
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
            for metric_name in metrics
            if latest.get(metric_name) is None
        ]

        if not missing:
            continue

        # ----------------------------------------------------
        # في LIMITED DATA:
        # عدم إصدار downstream score قد يكون سلوك حماية صحيح.
        # ----------------------------------------------------

        if limited_data:

            findings.append(
                audit_message(
                    "WARN",
                    "ENGINE_OUTPUT_LIMITED_DATA",
                    (
                        f"{engine_name}: "
                        f"مفقود {len(missing)}/"
                        f"{len(metrics)} بسبب محدودية البيانات: "
                        + ", ".join(missing)
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
                        f"مفقود {len(missing)}/"
                        f"{len(metrics)}: "
                        + ", ".join(missing)
                    )
                )
            )

    return findings


# ============================================================
# Range audit
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
            latest.get(metric_name)
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
                        f"خارج النطاق "
                        f"{minimum}-{maximum}"
                    )
                )
            )

    return findings


# ============================================================
# Period alignment audit
# ============================================================


def audit_period_alignment(
    periods,
    latest_model_period
):

    findings = []

    important_metrics = [
        "score_opportunity_score",
        "turning_engine_score",
        "data_quality_score",
        "decision_score"
    ]

    for metric_name in important_metrics:

        metric_period = (
            latest_period_for_metric(
                periods,
                metric_name
            )
        )

        if metric_period is None:
            continue

        if metric_period != latest_model_period:

            findings.append(
                audit_message(
                    "FAIL",
                    "PERIOD_MISALIGNMENT",
                    (
                        f"{metric_name} "
                        f"آخر فترة له {metric_period} "
                        f"بينما أحدث فترة مالية "
                        f"{latest_model_period}"
                    )
                )
            )

    return findings


# ============================================================
# Score internal consistency
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

    turning = safe_number(
        latest.get(
            "score_turning_point_score"
        )
    )

    turning_engine = safe_number(
        latest.get(
            "turning_engine_score"
        )
    )

    if (
        turning is not None
        and turning_engine is not None
        and abs(
            turning
            - turning_engine
        ) >= 45
    ):

        findings.append(
            audit_message(
                "WARN",
                "TURNING_SCORE_DIVERGENCE",
                (
                    f"BaseTurning={fmt(turning)} "
                    f"vs EngineTurning="
                    f"{fmt(turning_engine)}"
                )
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
                    f"Opportunity={fmt(opportunity)} "
                    f"و Risk={fmt(risk)} مرتفعان معًا"
                )
            )
        )

    return findings


# ============================================================
# Data Quality consistency
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
                    f"DataQuality={fmt(quality)} "
                    f"مع Freshness={fmt(freshness)}"
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
                    f"DataQuality={fmt(quality)} "
                    f"مع Coverage={fmt(coverage)}"
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
                    f"Freshness={fmt(freshness)} "
                    f"مع MarketLag={fmt(market_lag)}"
                )
            )
        )

    return findings


# ============================================================
# Decision logic audit
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
        latest.get("decision_score")
    )

    risk = safe_number(
        latest.get("score_risk_score")
    )

    opportunity = safe_number(
        latest.get("score_opportunity_score")
    )

    turning = safe_number(
        latest.get("turning_engine_score")
    )

    data_quality = safe_number(
        latest.get("data_quality_score")
    )

    freshness = safe_number(
        latest.get("data_freshness_score")
    )

    coverage = safe_number(
        latest.get("data_coverage_score")
    )

    reliability = safe_number(
        latest.get(
            "decision_reliability_score"
        )
    )

    momentum = safe_number(
        latest.get(
            "decision_momentum_score"
        )
    )

    market_lag = safe_number(
        latest.get(
            "data_market_lag_days"
        )
    )

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
                    f"Decision={fmt(decision)} مرتفع "
                    f"مع DataQuality={fmt(data_quality)}"
                )
            )
        )

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
                    f"Decision={fmt(decision)} مرتفع "
                    f"مع Freshness={fmt(freshness)}"
                )
            )
        )

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
                    f"Decision={fmt(decision)} "
                    f"مع MarketLag="
                    f"{fmt(market_lag)} يوم"
                )
            )
        )

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
                    f"Decision={fmt(decision)} "
                    f"مع Risk={fmt(risk)}"
                )
            )
        )

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
                    f"Decision={fmt(decision)} "
                    f"مع Opportunity="
                    f"{fmt(opportunity)}"
                )
            )
        )

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
                    f"Decision={fmt(decision)} "
                    f"مع Reliability="
                    f"{fmt(reliability)}"
                )
            )
        )

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
                    f"Decision={fmt(decision)} "
                    f"مع Coverage="
                    f"{fmt(coverage)}"
                )
            )
        )

    if (
        momentum is not None
        and (
            momentum <= 10
            or momentum >= 92
        )
    ):

        findings.append(
            audit_message(
                "INFO",
                "MOMENTUM_BOUNDARY",
                (
                    "Momentum على حد النظام: "
                    f"{fmt(momentum)}"
                )
            )
        )

    if (
        turning is not None
        and turning >= 80
        and decision is not None
        and decision < 45
    ):

        findings.append(
            audit_message(
                "INFO",
                "TURNING_DECISION_DIVERGENCE",
                (
                    f"Turning={fmt(turning)} مرتفع "
                    f"لكن Decision="
                    f"{fmt(decision)} منخفض"
                )
            )
        )

    return findings


# ============================================================
# تحديد حالة Audit
# ============================================================


def classify_audit(findings):

    fail_count = sum(
        1
        for finding in findings
        if finding["severity"] == "FAIL"
    )

    warn_count = sum(
        1
        for finding in findings
        if finding["severity"] == "WARN"
    )

    info_count = sum(
        1
        for finding in findings
        if finding["severity"] == "INFO"
    )

    if fail_count > 0:
        status = "FAIL"

    elif warn_count > 0:
        status = "WARNING"

    else:
        status = "PASS"

    score = 100.0

    score -= fail_count * 25
    score -= warn_count * 8
    score -= info_count * 1

    score = max(
        0.0,
        score
    )

    return {
        "status": status,
        "audit_score": score,
        "fail_count": fail_count,
        "warn_count": warn_count,
        "info_count": info_count
    }


# ============================================================
# تحليل شركة واحدة
# ============================================================


def audit_stock(stock):

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

    limited_data = limited_info[
        "limited"
    ]

    limited_reason = limited_info[
        "reason"
    ]

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
                limited_data=limited_data
            )
        )

        findings.extend(
            audit_engine_outputs(
                periods,
                latest_period,
                limited_data=limited_data
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
                latest_period
            )
        )

        findings.extend(
            audit_score_logic(
                periods,
                latest_period
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

    return {

        "symbol": symbol,
        "company_name": company_name,
        "analysis_model": analysis_model,

        "latest_period": latest_period,

        "raw_records": len(raw_rows),
        "metric_records": len(metric_rows),
        "period_count": len(model_periods),

        "limited_data": limited_data,
        "limited_reason": limited_reason,

        "decision_score": safe_number(
            latest_values.get(
                "decision_score"
            )
        ),

        "data_quality": safe_number(
            latest_values.get(
                "data_quality_score"
            )
        ),

        "reliability": safe_number(
            latest_values.get(
                "decision_reliability_score"
            )
        ),

        "audit_status": classification[
            "status"
        ],

        "audit_score": classification[
            "audit_score"
        ],

        "fail_count": classification[
            "fail_count"
        ],

        "warn_count": classification[
            "warn_count"
        ],

        "info_count": classification[
            "info_count"
        ],

        "findings": findings
    }


# ============================================================
# طباعة شركة
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

    if result["limited_data"]:

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

    if not result["findings"]:

        print(
            "\n✅ لا توجد ملاحظات تدقيق",
            flush=True
        )

        return

    print(
        "\n📋 FINDINGS",
        flush=True
    )

    for finding in result["findings"]:

        severity = finding["severity"]

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
# System-wide audit
# ============================================================


def audit_system_consistency(results):

    findings = []

    symbols = [
        result["symbol"]
        for result in results
    ]

    duplicate_symbols = [
        symbol
        for symbol, count
        in Counter(symbols).items()
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
        result["decision_score"]
        for result in results
        if result["decision_score"] is not None
    ]

    if decision_values:

        high_count = sum(
            1
            for value in decision_values
            if value >= 80
        )

        if (
            high_count
            > len(decision_values) * 0.50
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
            for value in decision_values
            if value == 0
        )

        if (
            zero_count
            > len(decision_values) * 0.50
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
        result["latest_period"]
        for result in results
        if result["latest_period"]
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
# Final summary
# ============================================================


def print_final_summary(
    results,
    system_findings
):

    print_header(
        "🏆 MASTER SYSTEM AUDIT SUMMARY v1.1"
    )

    sorted_results = sorted(
        results,
        key=lambda item: (
            item["audit_score"],
            item["symbol"]
        )
    )

    for index, result in enumerate(
        sorted_results,
        start=1
    ):

        data_mode = (
            "LIMITED"
            if result["limited_data"]
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
            f"DataQuality={fmt(result['data_quality'])}",
            flush=True
        )

    pass_count = sum(
        1
        for result in results
        if result["audit_status"] == "PASS"
    )

    warning_count = sum(
        1
        for result in results
        if result["audit_status"] == "WARNING"
    )

    fail_count = sum(
        1
        for result in results
        if result["audit_status"] == "FAIL"
    )

    limited_count = sum(
        1
        for result in results
        if result["limited_data"]
    )

    total_company_failures = sum(
        result["fail_count"]
        for result in results
    )

    total_company_warnings = sum(
        result["warn_count"]
        for result in results
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

        for finding in system_findings:

            severity = finding["severity"]

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
            "\n✅ لا توجد مشاكل System-wide ظاهرة",
            flush=True
        )

    system_fail_count = sum(
        1
        for finding in system_findings
        if finding["severity"] == "FAIL"
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

            overall = "PASS_WITH_LIMITATIONS"

    else:

        overall = "REVIEW_REQUIRED"

    print_separator()

    print(
        f"🧭 SYSTEM AUDIT RESULT: "
        f"{overall}",
        flush=True
    )

    print(
        "=" * 88,
        flush=True
    )


# ============================================================
# التشغيل
# ============================================================


def run_system_audit():

    print_header(
        "🔬 MASTER SYSTEM AUDIT ENGINE v1.1"
    )

    print(
        "🔒 Mode: READ ONLY",
        flush=True
    )

    print(
        f"🕐 Started: "
        f"{datetime.now(timezone.utc).isoformat()}",
        flush=True
    )

    stocks = get_active_stocks()

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
            f"{index}/{len(stocks)} | "
            f"{stock['symbol']}",
            flush=True
        )

        try:

            result = audit_stock(
                stock
            )

        except Exception as error:

            result = {

                "symbol": stock.get(
                    "symbol"
                ),

                "company_name": stock.get(
                    "company_name"
                ),

                "analysis_model": stock.get(
                    "analysis_model"
                ),

                "latest_period": None,

                "raw_records": 0,
                "metric_records": 0,
                "period_count": 0,

                "limited_data": False,
                "limited_reason": None,

                "decision_score": None,
                "data_quality": None,
                "reliability": None,

                "audit_status": "FAIL",
                "audit_score": 0,

                "fail_count": 1,
                "warn_count": 0,
                "info_count": 0,

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
