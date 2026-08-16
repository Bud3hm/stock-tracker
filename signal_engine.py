import os
import time
from datetime import datetime, timezone
from supabase import create_client


# ============================================================
# إعداد Supabase
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
# إعدادات المحرك
# ============================================================

ENGINE_VERSION = "2.2.2"

# مهم جدًا:
# لا نغير Prefix لأن المحركات الأخرى تقرأ engine22_
ENGINE_PREFIX = "engine22_"

MIN_DATA_CONFIDENCE = 60.0

MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 2.0


# ============================================================
# النماذج
# ============================================================

SUPPORTED_SIGNAL_MODELS = {
    "standard",
    "reit"
}

SPECIALIZED_MODELS = {
    "bank",
    "insurance"
}


MODEL_QUARTER_PREFIX = {

    "standard":
        "q_",

    "reit":
        "reit_q_",

    "bank":
        "bank_q_",

    "insurance":
        "insurance_q_"
}


MODEL_CONFIDENCE_METRIC = {

    "standard":
        "data_confidence_score",

    "reit":
        "reit_data_confidence_score",

    "bank":
        "bank_data_confidence_score",

    "insurance":
        "insurance_data_confidence_score"
}


# ============================================================
# الوزن النظري الكامل
#
# Standard:
# 27 Growth
# 20 Margins
# 10 Profit Conversion
# 23 Cash Quality
# 13 Balance Sheet
# 7 Working Capital
# = 100
#
# REIT:
# Working Capital غير مطبق
# = 93
# ============================================================

MODEL_TOTAL_WEIGHT = {

    "standard":
        100.0,

    "reit":
        93.0
}


# ============================================================
# REIT -> Generic Aliases
#
# لا نعدل أسماء المؤشرات في Supabase.
# فقط نترجمها داخل Signal Engine.
# ============================================================

REIT_ALIASES = {

    # --------------------------------------------------------
    # Growth
    # --------------------------------------------------------

    "q_revenue_growth_yoy":
        "reit_q_revenue_growth_yoy",

    "q_net_income_growth_yoy":
        "reit_q_net_income_growth_yoy",

    "q_revenue_growth_qoq":
        "reit_q_revenue_growth_qoq",

    "q_net_income_growth_qoq":
        "reit_q_net_income_growth_qoq",

    # --------------------------------------------------------
    # Operating Income
    # --------------------------------------------------------

    "q_operating_income_growth_yoy":
        "reit_q_operating_income_growth_yoy",

    "q_operating_income_growth_qoq":
        "reit_q_operating_income_growth_qoq",

    # --------------------------------------------------------
    # Margins
    # --------------------------------------------------------

    "q_operating_margin_change_yoy":
        "reit_q_operating_margin_change_yoy",

    "q_net_margin_change_yoy":
        "reit_q_net_margin_change_yoy",

    "q_operating_margin_change_qoq":
        "reit_q_operating_margin_change_qoq",

    "q_net_margin_change_qoq":
        "reit_q_net_margin_change_qoq",

    "q_operating_margin":
        "reit_q_operating_margin",

    "q_net_margin":
        "reit_q_net_margin",

    # --------------------------------------------------------
    # Cash
    # --------------------------------------------------------

    "q_cash_conversion":
        "reit_q_cash_conversion",

    "q_ocf_growth_yoy":
        "reit_q_ocf_growth_yoy",

    "q_fcf_growth_yoy":
        "reit_q_fcf_growth_yoy",

    "q_ocf_growth_qoq":
        "reit_q_ocf_growth_qoq",

    "q_fcf_growth_qoq":
        "reit_q_fcf_growth_qoq",

    "ttm_cash_conversion":
        "reit_ttm_cash_conversion",

    "ttm_fcf_margin":
        "reit_ttm_fcf_margin",

    "ttm_net_margin":
        "reit_ttm_net_margin",

    # --------------------------------------------------------
    # Balance Sheet
    # --------------------------------------------------------

    "q_debt_growth_qoq":
        "reit_q_debt_growth_qoq",

    "q_debt_growth_yoy":
        "reit_q_debt_growth_yoy",

    "q_debt_to_equity":
        "reit_q_debt_to_equity",

    "q_debt_to_assets":
        "reit_q_debt_to_assets",

    "q_cash_growth_qoq":
        "reit_q_cash_growth_qoq",

    "q_equity_growth_qoq":
        "reit_q_equity_growth_qoq",

    "q_equity_growth_yoy":
        "reit_q_equity_growth_yoy",

    "q_assets_growth_qoq":
        "reit_q_assets_growth_qoq",

    "q_assets_growth_yoy":
        "reit_q_assets_growth_yoy",

    # --------------------------------------------------------
    # Raw Quarterly Values
    # --------------------------------------------------------

    "q_revenue":
        "reit_q_revenue",

    "q_net_income":
        "reit_q_net_income",

    "q_operating_income":
        "reit_q_operating_income",

    "q_total_assets":
        "reit_q_total_assets",

    "q_total_liabilities":
        "reit_q_total_liabilities",

    "q_equity":
        "reit_q_equity",

    "q_total_debt":
        "reit_q_total_debt",

    "q_cash":
        "reit_q_cash"
}


# ============================================================
# أدوات أساسية
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


def weighted_average(items):

    total_value = 0.0
    total_weight = 0.0

    for value, weight in items:

        value = safe_number(
            value
        )

        weight = safe_number(
            weight
        )

        if (
            value is None
            or weight is None
            or weight <= 0
        ):
            continue

        total_value += (
            value
            * weight
        )

        total_weight += weight

    if total_weight <= 0:
        return None

    return (
        total_value
        / total_weight
    )


def average(values):

    clean = []

    for value in values:

        value = safe_number(
            value
        )

        if value is not None:
            clean.append(
                value
            )

    if not clean:
        return None

    return (
        sum(clean)
        / len(clean)
    )


def fmt(value):

    value = safe_number(
        value
    )

    if value is None:
        return "N/A"

    return f"{value:.2f}"


def print_separator(
    character="=",
    length=72
):

    print(
        character * length,
        flush=True
    )


# ============================================================
# Retry
#
# لحماية GitHub Actions من أخطاء اتصال مؤقتة مثل:
#
# RemoteProtocolError
# Server disconnected
# ============================================================

def execute_with_retry(
    operation,
    description
):

    last_error = None

    for attempt in range(
        1,
        MAX_RETRIES + 1
    ):

        try:

            return operation()

        except Exception as error:

            last_error = error

            if attempt >= MAX_RETRIES:
                break

            wait_seconds = (
                RETRY_DELAY_SECONDS
                * attempt
            )

            print(
                f"🟠 اتصال مؤقت أثناء "
                f"{description} | "
                f"المحاولة "
                f"{attempt}/{MAX_RETRIES} | "
                f"{type(error).__name__}: "
                f"{error}",
                flush=True
            )

            print(
                f"🔁 إعادة المحاولة بعد "
                f"{wait_seconds:.0f} ثانية...",
                flush=True
            )

            time.sleep(
                wait_seconds
            )

    raise last_error


# ============================================================
# جلب الشركات النشطة
# ============================================================

def get_active_stocks():

    def operation():

        response = (
            supabase
            .table(
                "stocks"
            )
            .select(
                "id,"
                "symbol,"
                "company_name,"
                "analysis_model,"
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

    return execute_with_retry(
        operation,
        "جلب الشركات النشطة"
    )


# ============================================================
# جلب معلومات شركة
# ============================================================

def get_stock_info(stock_id):

    def operation():

        response = (
            supabase
            .table(
                "stocks"
            )
            .select(
                "id,"
                "symbol,"
                "company_name,"
                "analysis_model,"
                "data_status,"
                "is_active"
            )
            .eq(
                "id",
                stock_id
            )
            .limit(1)
            .execute()
        )

        rows = (
            response.data
            or []
        )

        if not rows:
            return None

        return rows[0]

    return execute_with_retry(
        operation,
        f"جلب Stock ID {stock_id}"
    )


# ============================================================
# جلب المؤشرات
# ============================================================

def get_financial_metrics(stock_id):

    def operation():

        response = (
            supabase
            .table(
                "financial_metrics"
            )
            .select(
                "stock_id,"
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

    return execute_with_retry(
        operation,
        f"جلب Financial Metrics للشركة {stock_id}"
    )


# ============================================================
# تنظيم المؤشرات
# ============================================================

def organize_metrics(rows):

    periods = {}

    for row in rows:

        period_end_raw = row.get(
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
            period_end_raw is None
            or not metric_name
            or metric_value is None
        ):
            continue

        period_end = str(
            period_end_raw
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
# Normalization
# ============================================================

def normalize_metrics(
    metrics,
    analysis_model
):

    normalized = dict(
        metrics
    )

    if analysis_model == "standard":

        return normalized

    if analysis_model == "reit":

        for (
            generic_name,
            reit_name
        ) in REIT_ALIASES.items():

            metric_value = safe_number(
                metrics.get(
                    reit_name
                )
            )

            if metric_value is not None:

                normalized[
                    generic_name
                ] = metric_value

        reit_confidence = safe_number(
            metrics.get(
                "reit_data_confidence_score"
            )
        )

        if reit_confidence is not None:

            normalized[
                "data_confidence_score"
            ] = reit_confidence

        return normalized

    return normalized


# ============================================================
# تحديد الأرباع
# ============================================================

def get_quarter_dates(
    periods,
    analysis_model
):

    prefix = MODEL_QUARTER_PREFIX.get(
        analysis_model
    )

    if not prefix:
        return []

    quarter_dates = []

    for period_end, metrics in periods.items():

        has_model_metric = any(
            metric_name.startswith(
                prefix
            )
            for metric_name in metrics
        )

        if has_model_metric:

            quarter_dates.append(
                period_end
            )

    return sorted(
        set(
            quarter_dates
        )
    )


# ============================================================
# Data Confidence
# ============================================================

def get_data_confidence(
    metrics,
    analysis_model
):

    metric_name = (
        MODEL_CONFIDENCE_METRIC.get(
            analysis_model
        )
    )

    if metric_name:

        value = safe_number(
            metrics.get(
                metric_name
            )
        )

        if value is not None:
            return value

    return safe_number(
        metrics.get(
            "data_confidence_score"
        )
    )


# ============================================================
# State
# ============================================================

def new_state(
    total_possible_weight
):

    return {

        "positive_points":
            0.0,

        "risk_points":
            0.0,

        "available_weight":
            0.0,

        # مهم:
        # هذا الآن الوزن النظري الكامل للنموذج
        # وليس فقط Components التي ظهرت.
        "possible_weight":
            total_possible_weight,

        "positive_reasons":
            [],

        "negative_reasons":
            [],

        "component_scores":
            {}
    }


# ============================================================
# إضافة Component
# ============================================================

def add_component(
    state,
    name,
    weight,
    improvement,
    risk,
    coverage,
    positive_reasons=None,
    negative_reasons=None
):

    weight = safe_number(
        weight
    )

    improvement = clamp(
        improvement
    )

    risk = clamp(
        risk
    )

    coverage = clamp(
        coverage
    )

    if (
        weight is None
        or weight <= 0
        or improvement is None
        or risk is None
        or coverage is None
    ):
        return

    usable_weight = (
        weight
        * coverage
        / 100
    )

    state[
        "available_weight"
    ] += usable_weight

    state[
        "positive_points"
    ] += (
        usable_weight
        * improvement
        / 100
    )

    state[
        "risk_points"
    ] += (
        usable_weight
        * risk
        / 100
    )

    state[
        "component_scores"
    ][name] = {

        "improvement":
            improvement,

        "risk":
            risk,

        "coverage":
            coverage,

        "weight":
            weight,

        "usable_weight":
            usable_weight
    }

    if positive_reasons:

        for reason in positive_reasons:

            state[
                "positive_reasons"
            ].append(
                (
                    weight,
                    name,
                    reason
                )
            )

    if negative_reasons:

        for reason in negative_reasons:

            state[
                "negative_reasons"
            ].append(
                (
                    weight,
                    name,
                    reason
                )
            )


# ============================================================
# Growth Score
# ============================================================

def score_growth(value):

    value = safe_number(
        value
    )

    if value is None:
        return None

    if value >= 25:
        return 100.0

    if value >= 15:
        return 85.0

    if value >= 8:
        return 70.0

    if value >= 3:
        return 60.0

    if value >= 0:
        return 52.0

    if value >= -5:
        return 40.0

    if value >= -10:
        return 25.0

    if value >= -20:
        return 10.0

    return 0.0


# ============================================================
# Margin Change Score
# ============================================================

def score_margin_change(value):

    value = safe_number(
        value
    )

    if value is None:
        return None

    if value >= 3:
        return 100.0

    if value >= 2:
        return 85.0

    if value >= 1:
        return 70.0

    if value >= 0:
        return 55.0

    if value >= -1:
        return 42.0

    if value >= -2:
        return 25.0

    if value >= -4:
        return 10.0

    return 0.0


# ============================================================
# Growth Component
# ============================================================

def evaluate_growth_component(metrics):

    revenue_yoy = safe_number(
        metrics.get(
            "q_revenue_growth_yoy"
        )
    )

    profit_yoy = safe_number(
        metrics.get(
            "q_net_income_growth_yoy"
        )
    )

    revenue_qoq = safe_number(
        metrics.get(
            "q_revenue_growth_qoq"
        )
    )

    profit_qoq = safe_number(
        metrics.get(
            "q_net_income_growth_qoq"
        )
    )

    items = []

    positive = []
    negative = []

    possible = 100.0
    available = 0.0

    if revenue_yoy is not None:

        items.append(
            (
                score_growth(
                    revenue_yoy
                ),
                35
            )
        )

        available += 35

        if revenue_yoy >= 8:

            positive.append(
                f"نمو الإيرادات YoY جيد "
                f"({revenue_yoy:.2f}%)"
            )

        elif revenue_yoy <= -5:

            negative.append(
                f"الإيرادات تتراجع YoY "
                f"({revenue_yoy:.2f}%)"
            )

    if profit_yoy is not None:

        items.append(
            (
                score_growth(
                    profit_yoy
                ),
                45
            )
        )

        available += 45

        if profit_yoy >= 8:

            positive.append(
                f"نمو صافي الربح YoY قوي "
                f"({profit_yoy:.2f}%)"
            )

        elif profit_yoy <= -8:

            negative.append(
                f"صافي الربح يتراجع YoY "
                f"({profit_yoy:.2f}%)"
            )

    if revenue_qoq is not None:

        items.append(
            (
                score_growth(
                    revenue_qoq
                ),
                8
            )
        )

        available += 8

    if profit_qoq is not None:

        items.append(
            (
                score_growth(
                    profit_qoq
                ),
                12
            )
        )

        available += 12

    score = weighted_average(
        items
    )

    if score is None:
        return None

    return {

        "improvement":
            score,

        "risk":
            100.0 - score,

        "coverage":
            (
                available
                / possible
            ) * 100,

        "positive":
            positive,

        "negative":
            negative
    }


# ============================================================
# Margin Pressure
# ============================================================

def evaluate_margin_pressure(metrics):

    gross_yoy = safe_number(
        metrics.get(
            "q_gross_margin_change_yoy"
        )
    )

    operating_yoy = safe_number(
        metrics.get(
            "q_operating_margin_change_yoy"
        )
    )

    net_yoy = safe_number(
        metrics.get(
            "q_net_margin_change_yoy"
        )
    )

    operating_qoq = safe_number(
        metrics.get(
            "q_operating_margin_change_qoq"
        )
    )

    items = []

    available = 0.0
    possible = 100.0

    positive = []
    negative = []

    if gross_yoy is not None:

        items.append(
            (
                score_margin_change(
                    gross_yoy
                ),
                25
            )
        )

        available += 25

    if operating_yoy is not None:

        items.append(
            (
                score_margin_change(
                    operating_yoy
                ),
                35
            )
        )

        available += 35

    if net_yoy is not None:

        items.append(
            (
                score_margin_change(
                    net_yoy
                ),
                30
            )
        )

        available += 30

    if operating_qoq is not None:

        items.append(
            (
                score_margin_change(
                    operating_qoq
                ),
                10
            )
        )

        available += 10

    score = weighted_average(
        items
    )

    if score is None:
        return None

    pressure_values = []

    for margin_change in [
        gross_yoy,
        operating_yoy,
        net_yoy
    ]:

        if margin_change is not None:

            pressure_values.append(
                min(
                    margin_change,
                    0
                )
            )

    pressure_average = average(
        pressure_values
    )

    if pressure_average is None:
        pressure_average = 0.0

    pressure_magnitude = abs(
        min(
            pressure_average,
            0
        )
    )

    cascade_pressure = 0.0

    if (
        gross_yoy is not None
        and operating_yoy is not None
        and net_yoy is not None
        and net_yoy < operating_yoy
        and operating_yoy < gross_yoy
        and net_yoy < 0
    ):

        cascade_pressure = min(
            abs(
                net_yoy
                - gross_yoy
            ),
            10
        )

    if (
        operating_yoy is not None
        and operating_yoy >= 1
    ):

        positive.append(
            f"الهامش التشغيلي يتحسن YoY "
            f"({operating_yoy:.2f} نقطة)"
        )

    if (
        net_yoy is not None
        and net_yoy >= 1
    ):

        positive.append(
            f"الهامش الصافي يتحسن YoY "
            f"({net_yoy:.2f} نقطة)"
        )

    if pressure_magnitude >= 1.5:

        negative.append(
            f"ضغط جماعي على الهوامش "
            f"بمتوسط "
            f"{pressure_magnitude:.2f} نقطة"
        )

    if cascade_pressure >= 1:

        negative.append(
            "الضغط يزداد من الهامش الإجمالي "
            "إلى التشغيلي ثم الصافي"
        )

    pressure_penalty = min(
        (
            pressure_magnitude
            * 4
        )
        +
        (
            cascade_pressure
            * 2
        ),
        20
    )

    risk = clamp(
        100.0
        - score
        + pressure_penalty
    )

    improvement = clamp(
        score
        - (
            pressure_penalty
            * 0.4
        )
    )

    return {

        "improvement":
            improvement,

        "risk":
            risk,

        "coverage":
            (
                available
                / possible
            ) * 100,

        "positive":
            positive,

        "negative":
            negative,

        "pressure_score":
            clamp(
                pressure_penalty
                * 5
            )
    }


# ============================================================
# Profit Conversion Gap
# ============================================================

def evaluate_profit_conversion_gap(metrics):

    revenue_yoy = safe_number(
        metrics.get(
            "q_revenue_growth_yoy"
        )
    )

    profit_yoy = safe_number(
        metrics.get(
            "q_net_income_growth_yoy"
        )
    )

    if (
        revenue_yoy is None
        or profit_yoy is None
    ):
        return None

    gap = (
        revenue_yoy
        - profit_yoy
    )

    positive = []
    negative = []

    if gap <= -10:

        score = 100.0

        positive.append(
            f"الأرباح تنمو أسرع بكثير "
            f"من الإيرادات "
            f"(Gap {gap:.2f})"
        )

    elif gap <= -3:

        score = 85.0

        positive.append(
            "الأرباح تنمو أسرع من الإيرادات"
        )

    elif gap <= 5:

        score = 70.0

    elif gap <= 10:

        score = 55.0

    elif gap <= 15:

        score = 40.0

    elif gap <= 25:

        score = 20.0

        negative.append(
            f"نمو المبيعات لا يتحول بالكامل "
            f"إلى الأرباح "
            f"(Gap {gap:.2f} نقطة)"
        )

    else:

        score = 5.0

        negative.append(
            f"فجوة كبيرة جدًا بين نمو "
            f"الإيرادات والأرباح "
            f"({gap:.2f} نقطة)"
        )

    return {

        "improvement":
            score,

        "risk":
            100.0 - score,

        "coverage":
            100.0,

        "positive":
            positive,

        "negative":
            negative,

        "gap":
            gap
    }


# ============================================================
# Cash Quality
# ============================================================

def evaluate_cash_quality(metrics):

    q_conversion = safe_number(
        metrics.get(
            "q_cash_conversion"
        )
    )

    ttm_conversion = safe_number(
        metrics.get(
            "ttm_cash_conversion"
        )
    )

    ocf_yoy = safe_number(
        metrics.get(
            "q_ocf_growth_yoy"
        )
    )

    fcf_yoy = safe_number(
        metrics.get(
            "q_fcf_growth_yoy"
        )
    )

    ttm_fcf_margin = safe_number(
        metrics.get(
            "ttm_fcf_margin"
        )
    )

    items = []

    available = 0.0
    possible = 100.0

    positive = []
    negative = []

    if q_conversion is not None:

        if q_conversion >= 1.2:
            score = 100.0

        elif q_conversion >= 1:
            score = 85.0

        elif q_conversion >= 0.8:
            score = 65.0

        elif q_conversion >= 0.7:
            score = 45.0

        elif q_conversion >= 0.5:
            score = 20.0

        else:
            score = 0.0

        items.append(
            (
                score,
                25
            )
        )

        available += 25

        if q_conversion >= 1:

            positive.append(
                f"تحويل الأرباح الربعية "
                f"إلى نقد جيد "
                f"({q_conversion:.2f})"
            )

        elif q_conversion < 0.7:

            negative.append(
                f"جودة الأرباح النقدية ضعيفة "
                f"({q_conversion:.2f})"
            )

    if ttm_conversion is not None:

        if ttm_conversion >= 1.2:
            score = 100.0

        elif ttm_conversion >= 1:
            score = 85.0

        elif ttm_conversion >= 0.8:
            score = 65.0

        elif ttm_conversion >= 0.7:
            score = 45.0

        else:
            score = 15.0

        items.append(
            (
                score,
                30
            )
        )

        available += 30

    if ocf_yoy is not None:

        items.append(
            (
                score_growth(
                    ocf_yoy
                ),
                20
            )
        )

        available += 20

    if fcf_yoy is not None:

        items.append(
            (
                score_growth(
                    fcf_yoy
                ),
                15
            )
        )

        available += 15

    if ttm_fcf_margin is not None:

        if ttm_fcf_margin >= 15:
            score = 100.0

        elif ttm_fcf_margin >= 10:
            score = 80.0

        elif ttm_fcf_margin >= 5:
            score = 60.0

        elif ttm_fcf_margin >= 2:
            score = 40.0

        else:
            score = 20.0

        items.append(
            (
                score,
                10
            )
        )

        available += 10

    score = weighted_average(
        items
    )

    if score is None:
        return None

    return {

        "improvement":
            score,

        "risk":
            100.0 - score,

        "coverage":
            (
                available
                / possible
            ) * 100,

        "positive":
            positive,

        "negative":
            negative
    }


# ============================================================
# Balance Sheet
# ============================================================

def evaluate_balance_sheet(metrics):

    debt_growth = safe_number(
        metrics.get(
            "q_debt_growth_qoq"
        )
    )

    debt_to_equity = safe_number(
        metrics.get(
            "q_debt_to_equity"
        )
    )

    current_ratio = safe_number(
        metrics.get(
            "q_current_ratio"
        )
    )

    cash_growth = safe_number(
        metrics.get(
            "q_cash_growth_qoq"
        )
    )

    items = []

    available = 0.0
    possible = 100.0

    positive = []
    negative = []

    if debt_growth is not None:

        if debt_growth <= -8:
            score = 100.0

        elif debt_growth <= -3:
            score = 85.0

        elif debt_growth <= 2:
            score = 65.0

        elif debt_growth <= 6:
            score = 45.0

        elif debt_growth <= 12:
            score = 25.0

        else:
            score = 5.0

        items.append(
            (
                score,
                30
            )
        )

        available += 30

        if debt_growth <= -3:

            positive.append(
                f"الدين ينخفض "
                f"({debt_growth:.2f}% QoQ)"
            )

        elif debt_growth >= 8:

            negative.append(
                f"الدين يرتفع بسرعة "
                f"({debt_growth:.2f}% QoQ)"
            )

    if debt_to_equity is not None:

        if debt_to_equity <= 0.5:
            score = 100.0

        elif debt_to_equity <= 1:
            score = 80.0

        elif debt_to_equity <= 1.5:
            score = 60.0

        elif debt_to_equity <= 2:
            score = 35.0

        else:
            score = 15.0

        items.append(
            (
                score,
                25
            )
        )

        available += 25

    if current_ratio is not None:

        if current_ratio >= 1.5:
            score = 100.0

        elif current_ratio >= 1.2:
            score = 80.0

        elif current_ratio >= 1:
            score = 65.0

        elif current_ratio >= 0.8:
            score = 40.0

        else:
            score = 15.0

        items.append(
            (
                score,
                30
            )
        )

        available += 30

        if current_ratio < 0.8:

            negative.append(
                f"السيولة الجارية ضعيفة "
                f"({current_ratio:.2f})"
            )

    if cash_growth is not None:

        items.append(
            (
                score_growth(
                    cash_growth
                ),
                15
            )
        )

        available += 15

    score = weighted_average(
        items
    )

    if score is None:
        return None

    return {

        "improvement":
            score,

        "risk":
            100.0 - score,

        "coverage":
            (
                available
                / possible
            ) * 100,

        "positive":
            positive,

        "negative":
            negative
    }


# ============================================================
# Working Capital
#
# Standard فقط
# ============================================================

def evaluate_working_capital(metrics):

    revenue_growth = safe_number(
        metrics.get(
            "q_revenue_growth_qoq"
        )
    )

    inventory_growth = safe_number(
        metrics.get(
            "q_inventory_growth_qoq"
        )
    )

    receivables_growth = safe_number(
        metrics.get(
            "q_receivables_growth_qoq"
        )
    )

    items = []

    available = 0.0
    possible = 100.0

    positive = []
    negative = []

    if (
        revenue_growth is not None
        and inventory_growth is not None
    ):

        spread = (
            inventory_growth
            - revenue_growth
        )

        if spread <= 0:
            score = 90.0

        elif spread <= 5:
            score = 70.0

        elif spread <= 10:
            score = 50.0

        elif spread <= 20:
            score = 25.0

        else:
            score = 5.0

        items.append(
            (
                score,
                50
            )
        )

        available += 50

        if spread >= 12:

            negative.append(
                f"المخزون ينمو أسرع من الإيرادات "
                f"بـ {spread:.2f} نقطة"
            )

    if (
        revenue_growth is not None
        and receivables_growth is not None
    ):

        spread = (
            receivables_growth
            - revenue_growth
        )

        if spread <= 0:
            score = 90.0

        elif spread <= 5:
            score = 70.0

        elif spread <= 10:
            score = 50.0

        elif spread <= 20:
            score = 25.0

        else:
            score = 5.0

        items.append(
            (
                score,
                50
            )
        )

        available += 50

        if spread >= 12:

            negative.append(
                f"الذمم تنمو أسرع من الإيرادات "
                f"بـ {spread:.2f} نقطة"
            )

    score = weighted_average(
        items
    )

    if score is None:
        return None

    return {

        "improvement":
            score,

        "risk":
            100.0 - score,

        "coverage":
            (
                available
                / possible
            ) * 100,

        "positive":
            positive,

        "negative":
            negative
    }


# ============================================================
# Historical Sufficiency
# ============================================================

def calculate_history_sufficiency(
    quarter_dates,
    normalized_periods,
    index
):

    quarter_count = (
        index + 1
    )

    score = 0.0

    if quarter_count >= 12:
        score += 50

    elif quarter_count >= 8:
        score += 42

    elif quarter_count >= 6:
        score += 34

    elif quarter_count >= 4:
        score += 25

    elif quarter_count >= 3:
        score += 17

    elif quarter_count >= 2:
        score += 8

    current = normalized_periods[
        quarter_dates[
            index
        ]
    ]

    yoy_metrics = [

        "q_revenue_growth_yoy",
        "q_net_income_growth_yoy",
        "q_operating_margin_change_yoy",
        "q_net_margin_change_yoy",
        "q_ocf_growth_yoy",
        "q_fcf_growth_yoy"
    ]

    available_yoy = 0

    for metric_name in yoy_metrics:

        if safe_number(
            current.get(
                metric_name
            )
        ) is not None:

            available_yoy += 1

    score += (
        available_yoy
        / len(
            yoy_metrics
        )
    ) * 35

    if index >= 2:

        score += 15

    return clamp(
        score
    )


# ============================================================
# Trend Reliability
# ============================================================

def calculate_trend_reliability(
    quarter_dates,
    normalized_periods,
    index
):

    if index < 2:

        return {

            "score":
                20.0,

            "available_series":
                0
        }

    watched = [

        "q_revenue_growth_yoy",
        "q_net_income_growth_yoy",
        "q_operating_margin_change_yoy",
        "q_net_margin_change_yoy",
        "q_cash_conversion",
        "ttm_net_margin",
        "ttm_fcf_margin"
    ]

    available_series = 0
    stable_series = 0

    dates = quarter_dates[
        max(
            0,
            index - 2
        ):
        index + 1
    ]

    for metric_name in watched:

        values = []

        for date in dates:

            metric_value = safe_number(
                normalized_periods[
                    date
                ].get(
                    metric_name
                )
            )

            if metric_value is not None:

                values.append(
                    metric_value
                )

        if len(
            values
        ) < 2:

            continue

        available_series += 1

        last_move = abs(
            values[-1]
            - values[-2]
        )

        historical_range = (
            max(values)
            - min(values)
        )

        if (
            historical_range == 0
            or last_move
            <= (
                historical_range
                * 1.25
            )
        ):

            stable_series += 1

    if available_series == 0:

        return {

            "score":
                20.0,

            "available_series":
                0
        }

    reliability = (
        stable_series
        / available_series
    ) * 100

    history_factor = min(
        (
            index + 1
        ) / 8,
        1
    )

    reliability = (

        reliability
        * 0.70

        + (
            history_factor
            * 100
        )
        * 0.30
    )

    return {

        "score":
            clamp(
                reliability
            ),

        "available_series":
            available_series
    }


# ============================================================
# Acceleration
# ============================================================

def calculate_acceleration(
    quarter_dates,
    normalized_periods,
    index
):

    if index < 2:

        return {

            "score":
                50.0,

            "coverage":
                0.0,

            "reliability":
                0.0
        }

    yoy_metrics = [

        "q_revenue_growth_yoy",
        "q_net_income_growth_yoy",
        "q_operating_margin_change_yoy",
        "q_net_margin_change_yoy"
    ]

    qoq_fallback = [

        "q_revenue_growth_qoq",
        "q_net_income_growth_qoq"
    ]

    accelerations = []

    yoy_available = 0

    dates = quarter_dates[
        index - 2:
        index + 1
    ]

    for metric_name in yoy_metrics:

        values = []

        for date in dates:

            metric_value = safe_number(
                normalized_periods[
                    date
                ].get(
                    metric_name
                )
            )

            if metric_value is None:

                values = []
                break

            values.append(
                metric_value
            )

        if len(values) != 3:
            continue

        yoy_available += 1

        first_delta = (
            values[1]
            - values[0]
        )

        second_delta = (
            values[2]
            - values[1]
        )

        accelerations.append(
            second_delta
            - first_delta
        )

    fallback_available = 0

    if yoy_available == 0:

        for metric_name in qoq_fallback:

            values = []

            for date in dates:

                metric_value = safe_number(
                    normalized_periods[
                        date
                    ].get(
                        metric_name
                    )
                )

                if metric_value is None:

                    values = []
                    break

                values.append(
                    metric_value
                )

            if len(values) != 3:
                continue

            fallback_available += 1

            first_delta = (
                values[1]
                - values[0]
            )

            second_delta = (
                values[2]
                - values[1]
            )

            accelerations.append(
                (
                    second_delta
                    - first_delta
                )
                * 0.35
            )

    if not accelerations:

        return {

            "score":
                50.0,

            "coverage":
                0.0,

            "reliability":
                0.0
        }

    acceleration_value = average(
        accelerations
    )

    if acceleration_value >= 12:
        raw_score = 90.0

    elif acceleration_value >= 6:
        raw_score = 78.0

    elif acceleration_value >= 2:
        raw_score = 65.0

    elif acceleration_value >= -2:
        raw_score = 50.0

    elif acceleration_value >= -6:
        raw_score = 35.0

    elif acceleration_value >= -12:
        raw_score = 22.0

    else:
        raw_score = 10.0

    if yoy_available > 0:

        coverage = (
            yoy_available
            / len(
                yoy_metrics
            )
        ) * 100

        reliability = (
            50
            + (
                coverage
                * 0.5
            )
        )

    else:

        coverage = (
            fallback_available
            / len(
                qoq_fallback
            )
        ) * 40

        reliability = min(
            coverage,
            40
        )

    adjusted_score = (
        50
        + (
            raw_score
            - 50
        )
        * (
            reliability
            / 100
        )
    )

    return {

        "score":
            clamp(
                adjusted_score
            ),

        "coverage":
            clamp(
                coverage
            ),

        "reliability":
            clamp(
                reliability
            )
    }


# ============================================================
# Persistence
# ============================================================

def calculate_persistence(
    quarter_dates,
    normalized_periods,
    index
):

    if index < 2:

        return {

            "score":
                50.0,

            "coverage":
                0.0
        }

    watched = [

        "q_revenue_growth_qoq",
        "q_net_income_growth_qoq",
        "q_operating_margin_change_qoq",
        "q_net_margin_change_qoq",
        "q_cash_conversion"
    ]

    positive = 0
    negative = 0
    available = 0

    dates = quarter_dates[
        index - 2:
        index + 1
    ]

    for metric_name in watched:

        values = []

        for date in dates:

            metric_value = safe_number(
                normalized_periods[
                    date
                ].get(
                    metric_name
                )
            )

            if metric_value is None:

                values = []
                break

            values.append(
                metric_value
            )

        if len(values) != 3:
            continue

        available += 1

        if all(
            value > 0
            for value in values
        ):

            positive += 1

        elif all(
            value < 0
            for value in values
        ):

            negative += 1

    if available == 0:

        return {

            "score":
                50.0,

            "coverage":
                0.0
        }

    raw = (
        positive
        - negative
    ) / available

    return {

        "score":
            clamp(
                50
                + (
                    raw
                    * 50
                )
            ),

        "coverage":
            (
                available
                / len(
                    watched
                )
            ) * 100
    }


# ============================================================
# Finalize
# ============================================================

def finalize_engine(
    state,
    data_confidence,
    history,
    trend_reliability,
    acceleration,
    persistence,
    margin_pressure_score,
    profit_gap
):

    available_weight = safe_number(
        state.get(
            "available_weight"
        )
    )

    possible_weight = safe_number(
        state.get(
            "possible_weight"
        )
    )

    if (
        available_weight is None
        or possible_weight is None
        or available_weight <= 0
        or possible_weight <= 0
    ):
        return None

    raw_improvement = (
        state[
            "positive_points"
        ]
        / available_weight
    ) * 100

    raw_risk = (
        state[
            "risk_points"
        ]
        / available_weight
    ) * 100

    signal_coverage = (
        available_weight
        / possible_weight
    ) * 100

    signal_coverage = clamp(
        signal_coverage
    )

    # --------------------------------------------------------
    # نقص التغطية يخفض قوة النتيجة
    # --------------------------------------------------------

    coverage_factor = (
        0.30
        + (
            signal_coverage
            / 100
        )
        * 0.70
    )

    improvement = (
        raw_improvement
        * coverage_factor
    )

    risk = (
        raw_risk
        * coverage_factor
    )

    # --------------------------------------------------------
    # Persistence
    # --------------------------------------------------------

    if (
        persistence[
            "coverage"
        ] >= 40
    ):

        adjustment = (
            persistence[
                "score"
            ]
            - 50
        ) * 0.08

        if adjustment > 0:

            improvement += adjustment

        else:

            risk += abs(
                adjustment
            )

    # --------------------------------------------------------
    # Acceleration
    # --------------------------------------------------------

    if (
        acceleration[
            "coverage"
        ] >= 30
    ):

        acceleration_effect = (
            acceleration[
                "score"
            ]
            - 50
        ) * 0.08

        acceleration_effect *= (
            acceleration[
                "reliability"
            ]
            / 100
        )

        if acceleration_effect > 0:

            improvement += (
                acceleration_effect
            )

        else:

            risk += abs(
                acceleration_effect
            )

    improvement = clamp(
        improvement
    )

    risk = clamp(
        risk
    )

    net_score = (
        improvement
        - risk
    )

    data_confidence = (
        safe_number(
            data_confidence
        )
        or 0.0
    )

    history = (
        safe_number(
            history
        )
        or 0.0
    )

    trend_reliability = (
        safe_number(
            trend_reliability
        )
        or 0.0
    )

    confidence = (

        data_confidence
        * 0.30

        + signal_coverage
        * 0.25

        + history
        * 0.25

        + trend_reliability
        * 0.20
    )

    confidence = clamp(
        confidence
    )

    return {

        "improvement_score":
            improvement,

        "risk_score":
            risk,

        "net_score":
            net_score,

        "confidence_score":
            confidence,

        "signal_coverage_score":
            signal_coverage,

        "history_sufficiency_score":
            history,

        "trend_reliability_score":
            trend_reliability,

        "acceleration_score":
            acceleration[
                "score"
            ],

        "acceleration_coverage":
            acceleration[
                "coverage"
            ],

        "acceleration_reliability":
            acceleration[
                "reliability"
            ],

        "persistence_score":
            persistence[
                "score"
            ],

        "persistence_coverage":
            persistence[
                "coverage"
            ],

        "margin_pressure_score":
            margin_pressure_score,

        "profit_conversion_gap":
            profit_gap
    }


# ============================================================
# Classification
# ============================================================

def classify_result(scores):

    net_score = scores[
        "net_score"
    ]

    confidence = scores[
        "confidence_score"
    ]

    history = scores[
        "history_sufficiency_score"
    ]

    reliability = scores[
        "trend_reliability_score"
    ]

    if (
        confidence < 55
        or history < 40
        or reliability < 35
    ):

        return (
            "INSUFFICIENT_HISTORY",
            "التاريخ أو موثوقية الاتجاه غير كافية"
        )

    if net_score >= 45:

        return (
            "STRONG_IMPROVEMENT",
            "تحسن قوي ومتعدد الإشارات"
        )

    if net_score >= 20:

        return (
            "IMPROVING",
            "اتجاه تحسن واضح"
        )

    if net_score >= 5:

        return (
            "EARLY_IMPROVEMENT",
            "إشارات تحسن مبكرة"
        )

    if net_score > -5:

        return (
            "NEUTRAL",
            "الصورة متوازنة"
        )

    if net_score > -20:

        return (
            "EARLY_RISK",
            "إشارات تدهور مبكرة"
        )

    if net_score > -45:

        return (
            "DETERIORATING",
            "اتجاه تدهور واضح"
        )

    return (
        "HIGH_RISK",
        "تدهور قوي ومتعدد الإشارات"
    )


# ============================================================
# Save
# ============================================================

def save_engine_metrics(
    stock_id,
    period_end,
    values
):

    calculated_at = datetime.now(
        timezone.utc
    ).isoformat()

    records = []

    for name, metric_value in values.items():

        metric_value = safe_number(
            metric_value
        )

        if metric_value is None:
            continue

        records.append(
            {

                "stock_id":
                    stock_id,

                "calculated_at":
                    calculated_at,

                "metric_name":
                    f"{ENGINE_PREFIX}{name}",

                "metric_value":
                    metric_value,

                "period_end":
                    period_end
            }
        )

    if not records:
        return 0

    def operation():

        return (
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

    execute_with_retry(
        operation,
        (
            f"حفظ Signal Metrics | "
            f"Stock={stock_id} | "
            f"Period={period_end}"
        )
    )

    print(
        f"💾 تم حفظ Signal Engine "
        f"{ENGINE_VERSION} | "
        f"{period_end}",
        flush=True
    )

    return len(
        records
    )


# ============================================================
# Reasons
# ============================================================

def print_reasons(state):

    positive = sorted(
        state[
            "positive_reasons"
        ],
        key=lambda item: item[0],
        reverse=True
    )

    negative = sorted(
        state[
            "negative_reasons"
        ],
        key=lambda item: item[0],
        reverse=True
    )

    print(
        "\n🟢 أسباب التحسن:",
        flush=True
    )

    if not positive:

        print(
            "- لا توجد إشارة إيجابية قوية",
            flush=True
        )

    for _, component, reason in positive[:6]:

        print(
            f"- [{component}] "
            f"{reason}",
            flush=True
        )

    print(
        "\n🔴 أسباب الخطر:",
        flush=True
    )

    if not negative:

        print(
            "- لا توجد إشارة خطر قوية",
            flush=True
        )

    for _, component, reason in negative[:6]:

        print(
            f"- [{component}] "
            f"{reason}",
            flush=True
        )


# ============================================================
# تشغيل شركة واحدة
# ============================================================

def run_signal_engine(
    stock_id,
    stock_info=None
):

    stock = (
        stock_info
        if stock_info is not None
        else get_stock_info(
            stock_id
        )
    )

    if not stock:

        print(
            f"🔴 Stock ID {stock_id} "
            "غير موجود في جدول stocks",
            flush=True
        )

        return {

            "stock_id":
                stock_id,

            "status":
                "NOT_FOUND",

            "evaluated_periods":
                0,

            "limited_periods":
                0,

            "metrics_saved":
                0
        }

    symbol = (
        stock.get(
            "symbol"
        )
        or str(
            stock_id
        )
    )

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

    data_status = (
        stock.get(
            "data_status"
        )
        or "UNKNOWN"
    )

    print(
        "\n"
        + "=" * 72,
        flush=True
    )

    print(
        f"🧠 SIGNAL ENGINE "
        f"{ENGINE_VERSION}",
        flush=True
    )

    print(
        f"🏢 {symbol} | "
        f"{company_name}",
        flush=True
    )

    print(
        f"🧩 Analysis Model: "
        f"{analysis_model}",
        flush=True
    )

    print(
        f"🗄️ Data Status: "
        f"{data_status}",
        flush=True
    )

    print_separator()

    # --------------------------------------------------------
    # Bank / Insurance
    # --------------------------------------------------------

    if analysis_model in SPECIALIZED_MODELS:

        print(
            f"🟡 {analysis_model.upper()} "
            "له طبيعة مالية متخصصة.",
            flush=True
        )

        print(
            "⏭️ لن يتم إجباره على "
            "Standard Signal Logic.",
            flush=True
        )

        return {

            "stock_id":
                stock_id,

            "symbol":
                symbol,

            "company_name":
                company_name,

            "analysis_model":
                analysis_model,

            "status":
                "SPECIALIZED_MODEL_SKIPPED",

            "evaluated_periods":
                0,

            "limited_periods":
                0,

            "metrics_saved":
                0
        }

    if analysis_model not in SUPPORTED_SIGNAL_MODELS:

        print(
            f"🔴 Analysis Model غير مدعوم: "
            f"{analysis_model}",
            flush=True
        )

        return {

            "stock_id":
                stock_id,

            "symbol":
                symbol,

            "company_name":
                company_name,

            "analysis_model":
                analysis_model,

            "status":
                "UNSUPPORTED_MODEL",

            "evaluated_periods":
                0,

            "limited_periods":
                0,

            "metrics_saved":
                0
        }

    rows = get_financial_metrics(
        stock_id
    )

    if not rows:

        print(
            "🔴 لا توجد Financial Metrics",
            flush=True
        )

        return {

            "stock_id":
                stock_id,

            "symbol":
                symbol,

            "company_name":
                company_name,

            "analysis_model":
                analysis_model,

            "status":
                "NO_METRICS",

            "evaluated_periods":
                0,

            "limited_periods":
                0,

            "metrics_saved":
                0
        }

    periods = organize_metrics(
        rows
    )

    quarter_dates = get_quarter_dates(
        periods,
        analysis_model
    )

    if not quarter_dates:

        prefix = MODEL_QUARTER_PREFIX.get(
            analysis_model
        )

        print(
            "🔴 لم يتم العثور على فترات "
            "ربعية صالحة "
            f"بـ Prefix: {prefix}",
            flush=True
        )

        return {

            "stock_id":
                stock_id,

            "symbol":
                symbol,

            "company_name":
                company_name,

            "analysis_model":
                analysis_model,

            "status":
                "NO_QUARTERS",

            "evaluated_periods":
                0,

            "limited_periods":
                0,

            "metrics_saved":
                0
        }

    print(
        f"📅 Quarterly Periods Found: "
        f"{len(quarter_dates)}",
        flush=True
    )

    print(
        "📅 "
        + ", ".join(
            quarter_dates
        ),
        flush=True
    )

    normalized_periods = {}

    for period_end in quarter_dates:

        normalized_periods[
            period_end
        ] = normalize_metrics(
            periods[
                period_end
            ],
            analysis_model
        )

    evaluated_periods = 0
    limited_periods = 0
    total_saved = 0

    total_possible_weight = (
        MODEL_TOTAL_WEIGHT[
            analysis_model
        ]
    )

    for index, period_end in enumerate(
        quarter_dates
    ):

        raw_metrics = periods[
            period_end
        ]

        metrics = normalized_periods[
            period_end
        ]

        data_confidence = (
            get_data_confidence(
                raw_metrics,
                analysis_model
            )
        )

        print(
            "\n"
            + "-" * 72,
            flush=True
        )

        print(
            f"📅 الفترة: "
            f"{period_end}",
            flush=True
        )

        print(
            f"🎯 Data Confidence: "
            f"{fmt(data_confidence)}",
            flush=True
        )

        if data_confidence is None:

            limited_periods += 1

            print(
                "🟡 LIMITED DATA | "
                "Data Confidence غير متوفرة.",
                flush=True
            )

            print(
                "⏭️ لن يصدر Signal Score.",
                flush=True
            )

            continue

        if (
            data_confidence
            < MIN_DATA_CONFIDENCE
        ):

            limited_periods += 1

            print(
                f"🟡 LIMITED DATA | "
                f"Confidence="
                f"{data_confidence:.2f}% "
                f"أقل من الحد "
                f"{MIN_DATA_CONFIDENCE:.2f}%",
                flush=True
            )

            print(
                "⏭️ لن يصدر Signal Score "
                "حتى لا نعطي نتيجة مضللة.",
                flush=True
            )

            continue

        state = new_state(
            total_possible_weight
        )

        margin_pressure_score = 0.0
        profit_gap_value = 0.0

        # ====================================================
        # Growth
        # ====================================================

        component = (
            evaluate_growth_component(
                metrics
            )
        )

        if component:

            add_component(
                state,
                "growth",
                weight=27,
                improvement=component[
                    "improvement"
                ],
                risk=component[
                    "risk"
                ],
                coverage=component[
                    "coverage"
                ],
                positive_reasons=component[
                    "positive"
                ],
                negative_reasons=component[
                    "negative"
                ]
            )

        # ====================================================
        # Margin Pressure
        # ====================================================

        component = (
            evaluate_margin_pressure(
                metrics
            )
        )

        if component:

            margin_pressure_score = (
                component[
                    "pressure_score"
                ]
            )

            add_component(
                state,
                "margin_pressure",
                weight=20,
                improvement=component[
                    "improvement"
                ],
                risk=component[
                    "risk"
                ],
                coverage=component[
                    "coverage"
                ],
                positive_reasons=component[
                    "positive"
                ],
                negative_reasons=component[
                    "negative"
                ]
            )

        # ====================================================
        # Profit Conversion
        # ====================================================

        component = (
            evaluate_profit_conversion_gap(
                metrics
            )
        )

        if component:

            profit_gap_value = (
                component[
                    "gap"
                ]
            )

            add_component(
                state,
                "profit_conversion",
                weight=10,
                improvement=component[
                    "improvement"
                ],
                risk=component[
                    "risk"
                ],
                coverage=component[
                    "coverage"
                ],
                positive_reasons=component[
                    "positive"
                ],
                negative_reasons=component[
                    "negative"
                ]
            )

        # ====================================================
        # Cash Quality
        # ====================================================

        component = (
            evaluate_cash_quality(
                metrics
            )
        )

        if component:

            add_component(
                state,
                "cash_quality",
                weight=23,
                improvement=component[
                    "improvement"
                ],
                risk=component[
                    "risk"
                ],
                coverage=component[
                    "coverage"
                ],
                positive_reasons=component[
                    "positive"
                ],
                negative_reasons=component[
                    "negative"
                ]
            )

        # ====================================================
        # Balance Sheet
        # ====================================================

        component = (
            evaluate_balance_sheet(
                metrics
            )
        )

        if component:

            add_component(
                state,
                "balance_sheet",
                weight=13,
                improvement=component[
                    "improvement"
                ],
                risk=component[
                    "risk"
                ],
                coverage=component[
                    "coverage"
                ],
                positive_reasons=component[
                    "positive"
                ],
                negative_reasons=component[
                    "negative"
                ]
            )

        # ====================================================
        # Working Capital
        # Standard فقط
        # ====================================================

        if analysis_model == "standard":

            component = (
                evaluate_working_capital(
                    metrics
                )
            )

            if component:

                add_component(
                    state,
                    "working_capital",
                    weight=7,
                    improvement=component[
                        "improvement"
                    ],
                    risk=component[
                        "risk"
                    ],
                    coverage=component[
                        "coverage"
                    ],
                    positive_reasons=component[
                        "positive"
                    ],
                    negative_reasons=component[
                        "negative"
                    ]
                )

        # ====================================================
        # Historical Layer
        # ====================================================

        history = (
            calculate_history_sufficiency(
                quarter_dates,
                normalized_periods,
                index
            )
        )

        trend = (
            calculate_trend_reliability(
                quarter_dates,
                normalized_periods,
                index
            )
        )

        acceleration = (
            calculate_acceleration(
                quarter_dates,
                normalized_periods,
                index
            )
        )

        persistence = (
            calculate_persistence(
                quarter_dates,
                normalized_periods,
                index
            )
        )

        scores = finalize_engine(
            state,
            data_confidence,
            history,
            trend[
                "score"
            ],
            acceleration,
            persistence,
            margin_pressure_score,
            profit_gap_value
        )

        if not scores:

            limited_periods += 1

            print(
                "🟡 LIMITED DATA | "
                "لا توجد Components مالية "
                "كافية للحساب.",
                flush=True
            )

            continue

        evaluated_periods += 1

        (
            status_code,
            status_text
        ) = classify_result(
            scores
        )

        print(
            f"🟢 Improvement: "
            f"{scores['improvement_score']:.2f}",
            flush=True
        )

        print(
            f"🔴 Risk: "
            f"{scores['risk_score']:.2f}",
            flush=True
        )

        print(
            f"⚖️ Net: "
            f"{scores['net_score']:.2f}",
            flush=True
        )

        print(
            f"🎯 Confidence: "
            f"{scores['confidence_score']:.2f}",
            flush=True
        )

        print(
            f"📡 Signal Coverage: "
            f"{scores['signal_coverage_score']:.2f}",
            flush=True
        )

        print(
            f"🗂️ History: "
            f"{scores['history_sufficiency_score']:.2f}",
            flush=True
        )

        print(
            f"🧬 Trend Reliability: "
            f"{scores['trend_reliability_score']:.2f}",
            flush=True
        )

        print(
            f"🚀 Acceleration: "
            f"{scores['acceleration_score']:.2f}",
            flush=True
        )

        print(
            f"🎚️ Acceleration Reliability: "
            f"{scores['acceleration_reliability']:.2f}",
            flush=True
        )

        print(
            f"🔁 Persistence: "
            f"{scores['persistence_score']:.2f}",
            flush=True
        )

        print(
            f"📉 Margin Pressure: "
            f"{scores['margin_pressure_score']:.2f}",
            flush=True
        )

        print(
            f"💰 Profit Conversion Gap: "
            f"{scores['profit_conversion_gap']:.2f}",
            flush=True
        )

        print(
            f"🧭 الحالة: "
            f"{status_code} | "
            f"{status_text}",
            flush=True
        )

        print_reasons(
            state
        )

        total_saved += (
            save_engine_metrics(
                stock_id,
                period_end,
                scores
            )
        )

    # ========================================================
    # Company Summary
    # ========================================================

    print(
        "\n"
        + "=" * 72,
        flush=True
    )

    print(
        f"📊 SIGNAL ENGINE "
        f"{ENGINE_VERSION} SUMMARY",
        flush=True
    )

    print_separator()

    print(
        f"🏢 {symbol} | "
        f"{company_name}",
        flush=True
    )

    print(
        f"🧩 Model: "
        f"{analysis_model}",
        flush=True
    )

    print(
        f"📅 Quarterly Periods Found: "
        f"{len(quarter_dates)}",
        flush=True
    )

    print(
        f"🟢 Evaluated Periods: "
        f"{evaluated_periods}",
        flush=True
    )

    print(
        f"🟡 Limited Periods: "
        f"{limited_periods}",
        flush=True
    )

    print(
        f"💾 Metrics Saved: "
        f"{total_saved}",
        flush=True
    )

    if (
        analysis_model == "reit"
        and evaluated_periods == 0
    ):

        print(
            "🟡 REIT DATA STATUS: "
            "البيانات الربعية موجودة، "
            "لكنها غير كافية حاليًا "
            "لإصدار Signal موثوق.",
            flush=True
        )

        print(
            "✅ هذا نقص من مصدر البيانات "
            "وليس خطأ في Signal Engine.",
            flush=True
        )

    print_separator()

    if evaluated_periods > 0:

        final_status = "EVALUATED"

    elif limited_periods > 0:

        final_status = "LIMITED_DATA"

    else:

        final_status = "NO_EVALUATION"

    return {

        "stock_id":
            stock_id,

        "symbol":
            symbol,

        "company_name":
            company_name,

        "analysis_model":
            analysis_model,

        "status":
            final_status,

        "quarterly_periods":
            len(
                quarter_dates
            ),

        "evaluated_periods":
            evaluated_periods,

        "limited_periods":
            limited_periods,

        "metrics_saved":
            total_saved
    }


# ============================================================
# تشغيل جميع الشركات النشطة
# ============================================================

def run_all_active_stocks():

    stocks = get_active_stocks()

    print(
        "\n"
        + "=" * 88,
        flush=True
    )

    print(
        f"🌐 SIGNAL ENGINE "
        f"{ENGINE_VERSION} | "
        f"ALL ACTIVE COMPANIES",
        flush=True
    )

    print(
        f"🏢 Active Companies: "
        f"{len(stocks)}",
        flush=True
    )

    print(
        "=" * 88,
        flush=True
    )

    results = []

    for index, stock in enumerate(
        stocks,
        start=1
    ):

        stock_id = stock.get(
            "id"
        )

        symbol = (
            stock.get(
                "symbol"
            )
            or stock_id
        )

        print(
            "\n"
            + "#" * 88,
            flush=True
        )

        print(
            f"🔍 Company "
            f"{index}/{len(stocks)} | "
            f"{symbol}",
            flush=True
        )

        print(
            "#" * 88,
            flush=True
        )

        try:

            result = run_signal_engine(
                stock_id,
                stock_info=stock
            )

        except Exception as error:

            print(
                f"🔴 فشل Signal Engine "
                f"للشركة {symbol}",
                flush=True
            )

            print(
                f"🔴 "
                f"{type(error).__name__}: "
                f"{error}",
                flush=True
            )

            result = {

                "stock_id":
                    stock_id,

                "symbol":
                    symbol,

                "company_name":
                    stock.get(
                        "company_name"
                    ),

                "analysis_model":
                    stock.get(
                        "analysis_model"
                    ),

                "status":
                    "ERROR",

                "quarterly_periods":
                    0,

                "evaluated_periods":
                    0,

                "limited_periods":
                    0,

                "metrics_saved":
                    0
            }

        results.append(
            result
        )

    # ========================================================
    # Master Summary
    # ========================================================

    print(
        "\n"
        + "=" * 88,
        flush=True
    )

    print(
        f"🏆 SIGNAL ENGINE "
        f"{ENGINE_VERSION} "
        f"MASTER SUMMARY",
        flush=True
    )

    print(
        "=" * 88,
        flush=True
    )

    for index, result in enumerate(
        results,
        start=1
    ):

        print(
            f"{index:02d}. "
            f"{result.get('symbol')} | "
            f"{result.get('analysis_model')} | "
            f"Status="
            f"{result.get('status')} | "
            f"Periods="
            f"{result.get('quarterly_periods', 0)} | "
            f"Evaluated="
            f"{result.get('evaluated_periods', 0)} | "
            f"Limited="
            f"{result.get('limited_periods', 0)} | "
            f"Saved="
            f"{result.get('metrics_saved', 0)}",
            flush=True
        )

    evaluated_companies = sum(

        1
        for result in results
        if result.get(
            "status"
        ) == "EVALUATED"
    )

    limited_companies = sum(

        1
        for result in results
        if result.get(
            "status"
        ) == "LIMITED_DATA"
    )

    specialized_companies = sum(

        1
        for result in results
        if result.get(
            "status"
        ) == "SPECIALIZED_MODEL_SKIPPED"
    )

    error_companies = sum(

        1
        for result in results
        if result.get(
            "status"
        ) == "ERROR"
    )

    unsupported_companies = sum(

        1
        for result in results
        if result.get(
            "status"
        ) == "UNSUPPORTED_MODEL"
    )

    total_saved = sum(

        result.get(
            "metrics_saved",
            0
        )
        for result in results
    )

    print(
        "-" * 88,
        flush=True
    )

    print(
        f"🏢 Total Companies: "
        f"{len(results)}",
        flush=True
    )

    print(
        f"🟢 Evaluated Companies: "
        f"{evaluated_companies}",
        flush=True
    )

    print(
        f"🟡 Limited Data Companies: "
        f"{limited_companies}",
        flush=True
    )

    print(
        f"🧩 Specialized Models Skipped: "
        f"{specialized_companies}",
        flush=True
    )

    print(
        f"🟠 Unsupported Models: "
        f"{unsupported_companies}",
        flush=True
    )

    print(
        f"🔴 Errors: "
        f"{error_companies}",
        flush=True
    )

    print(
        f"💾 Total Metrics Saved: "
        f"{total_saved}",
        flush=True
    )

    if error_companies == 0:

        print(
            "✅ Batch completed without "
            "runtime errors.",
            flush=True
        )

    else:

        print(
            "⚠️ Batch completed with "
            f"{error_companies} runtime errors.",
            flush=True
        )

    print(
        "=" * 88,
        flush=True
    )


# ============================================================
# START
#
# طرق التشغيل:
#
# 1) شركة واحدة:
#    STOCK_ID=1
#
# 2) جميع الشركات:
#    STOCK_ID=ALL
#
# أو:
#    RUN_ALL_STOCKS=true
#
# إذا لم يوجد STOCK_ID أصلًا:
# سيعمل على جميع الشركات النشطة.
# ============================================================

if __name__ == "__main__":

    stock_id_raw = os.environ.get(
        "STOCK_ID"
    )

    run_all_raw = (
        os.environ.get(
            "RUN_ALL_STOCKS",
            ""
        )
        .strip()
        .lower()
    )

    run_all = (
        run_all_raw
        in {
            "1",
            "true",
            "yes",
            "y",
            "all"
        }
    )

    if stock_id_raw is not None:

        stock_id_raw = (
            stock_id_raw
            .strip()
        )

    if (
        run_all
        or not stock_id_raw
        or stock_id_raw.upper() == "ALL"
    ):

        run_all_active_stocks()

    else:

        try:

            stock_id = int(
                stock_id_raw
            )

        except ValueError:

            raise RuntimeError(
                "STOCK_ID يجب أن يكون رقمًا "
                "أو القيمة ALL"
            )

        run_signal_engine(
            stock_id
        )
