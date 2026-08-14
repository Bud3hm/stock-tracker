import os
from datetime import datetime, timezone
from supabase import create_client


# ============================================================
# إعداد Supabase
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

ENGINE_VERSION = "2.1"
ENGINE_PREFIX = "engine21_"

MIN_DATA_CONFIDENCE = 60.0


# ============================================================
# أدوات أساسية
# ============================================================

def safe_number(value):

    if value is None:
        return None

    try:
        return float(value)

    except (TypeError, ValueError):
        return None


def clamp(value, minimum=0.0, maximum=100.0):

    return max(
        minimum,
        min(
            maximum,
            value
        )
    )


def average(values):

    clean = []

    for value in values:

        number = safe_number(value)

        if number is not None:
            clean.append(number)

    if not clean:
        return None

    return sum(clean) / len(clean)


# ============================================================
# جلب المؤشرات
# ============================================================

def get_financial_metrics(stock_id):

    response = (
        supabase
        .table("financial_metrics")
        .select(
            "stock_id,"
            "period_end,"
            "metric_name,"
            "metric_value"
        )
        .eq("stock_id", stock_id)
        .execute()
    )

    return response.data


# ============================================================
# تنظيم المؤشرات حسب الفترة
# ============================================================

def organize_metrics(rows):

    periods = {}

    for row in rows:

        period_end = str(
            row.get("period_end")
        )

        metric_name = row.get(
            "metric_name"
        )

        metric_value = safe_number(
            row.get("metric_value")
        )

        if (
            not period_end
            or not metric_name
            or metric_value is None
        ):
            continue

        if period_end not in periods:
            periods[period_end] = {}

        periods[
            period_end
        ][
            metric_name
        ] = metric_value

    return periods


# ============================================================
# تحديد الفترات الربعية
# ============================================================

def get_quarter_dates(periods):

    quarter_dates = []

    for period_end, metrics in periods.items():

        if (
            "q_revenue" in metrics
            or "q_net_income" in metrics
            or "data_confidence_score" in metrics
        ):
            quarter_dates.append(
                period_end
            )

    return sorted(
        quarter_dates
    )


# ============================================================
# إنشاء حالة التقييم
# ============================================================

def new_state():

    return {
        "positive_points": 0.0,
        "risk_points": 0.0,
        "available_weight": 0.0,
        "possible_weight": 0.0,

        "strong_positive": 0,
        "strong_negative": 0,

        "positive_reasons": [],
        "negative_reasons": [],

        "component_scores": {}
    }


# ============================================================
# تسجيل نتيجة مجموعة
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

    improvement = clamp(
        improvement
    )

    risk = clamp(
        risk
    )

    coverage = clamp(
        coverage
    )

    usable_weight = (
        weight
        * coverage
        / 100
    )

    state[
        "possible_weight"
    ] += weight

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
        "improvement": improvement,
        "risk": risk,
        "coverage": coverage
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
# تحويل معدل نمو إلى تقييم
# ============================================================

def score_growth(value):

    value = safe_number(
        value
    )

    if value is None:
        return None

    if value >= 25:
        return 100

    if value >= 15:
        return 85

    if value >= 8:
        return 70

    if value >= 3:
        return 60

    if value >= 0:
        return 52

    if value >= -5:
        return 40

    if value >= -10:
        return 25

    if value >= -20:
        return 10

    return 0


# ============================================================
# تقييم تغير الهامش
# القيمة بالنقاط المئوية
# ============================================================

def score_margin_change(value):

    value = safe_number(
        value
    )

    if value is None:
        return None

    if value >= 3:
        return 100

    if value >= 2:
        return 85

    if value >= 1:
        return 70

    if value >= 0:
        return 55

    if value >= -1:
        return 42

    if value >= -2:
        return 25

    if value >= -4:
        return 10

    return 0


# ============================================================
# مجموعة النمو
# YoY أهم من QoQ
# ============================================================

def evaluate_growth_component(metrics):

    revenue_yoy = safe_number(
        metrics.get(
            "q_revenue_growth_yoy"
        )
    )

    net_income_yoy = safe_number(
        metrics.get(
            "q_net_income_growth_yoy"
        )
    )

    revenue_qoq = safe_number(
        metrics.get(
            "q_revenue_growth_qoq"
        )
    )

    net_income_qoq = safe_number(
        metrics.get(
            "q_net_income_growth_qoq"
        )
    )

    scores = []
    weights = []

    positive_reasons = []
    negative_reasons = []

    # --------------------------------------------------------
    # YoY = الوزن الأساسي
    # --------------------------------------------------------

    if revenue_yoy is not None:

        scores.append(
            score_growth(
                revenue_yoy
            )
        )

        weights.append(
            35
        )

        if revenue_yoy >= 8:

            positive_reasons.append(
                f"نمو الإيرادات YoY جيد "
                f"({revenue_yoy:.2f}%)"
            )

        elif revenue_yoy <= -5:

            negative_reasons.append(
                f"تراجع الإيرادات YoY "
                f"({revenue_yoy:.2f}%)"
            )

    if net_income_yoy is not None:

        scores.append(
            score_growth(
                net_income_yoy
            )
        )

        weights.append(
            40
        )

        if net_income_yoy >= 8:

            positive_reasons.append(
                f"نمو الأرباح YoY قوي "
                f"({net_income_yoy:.2f}%)"
            )

        elif net_income_yoy <= -8:

            negative_reasons.append(
                f"تراجع الأرباح YoY "
                f"({net_income_yoy:.2f}%)"
            )

    # --------------------------------------------------------
    # QoQ = وزن مساند فقط
    # --------------------------------------------------------

    if revenue_qoq is not None:

        scores.append(
            score_growth(
                revenue_qoq
            )
        )

        weights.append(
            10
        )

    if net_income_qoq is not None:

        scores.append(
            score_growth(
                net_income_qoq
            )
        )

        weights.append(
            15
        )

    if not scores:
        return None

    weighted_sum = 0
    total_weight = 0

    for score, weight in zip(
        scores,
        weights
    ):

        weighted_sum += (
            score * weight
        )

        total_weight += weight

    improvement = (
        weighted_sum
        / total_weight
    )

    risk = (
        100
        - improvement
    )

    coverage = (
        total_weight
        / 100
    ) * 100

    return {
        "improvement": improvement,
        "risk": risk,
        "coverage": coverage,
        "positive": positive_reasons,
        "negative": negative_reasons
    }


# ============================================================
# مجموعة الهوامش
#
# تمنع Double Counting
# الهامش الإجمالي + التشغيلي + الصافي
# تعامل كمجموعة واحدة
# ============================================================

def evaluate_margin_component(metrics):

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

    values = []
    weights = []

    positive_reasons = []
    negative_reasons = []

    if gross_yoy is not None:

        values.append(
            score_margin_change(
                gross_yoy
            )
        )

        weights.append(
            25
        )

    if operating_yoy is not None:

        values.append(
            score_margin_change(
                operating_yoy
            )
        )

        weights.append(
            35
        )

    if net_yoy is not None:

        values.append(
            score_margin_change(
                net_yoy
            )
        )

        weights.append(
            30
        )

    if operating_qoq is not None:

        values.append(
            score_margin_change(
                operating_qoq
            )
        )

        weights.append(
            10
        )

    if not values:
        return None

    weighted_sum = 0
    total_weight = 0

    for score, weight in zip(
        values,
        weights
    ):

        weighted_sum += (
            score * weight
        )

        total_weight += weight

    improvement = (
        weighted_sum
        / total_weight
    )

    risk = (
        100
        - improvement
    )

    if (
        operating_yoy is not None
        and operating_yoy >= 1
    ):

        positive_reasons.append(
            f"تحسن الهامش التشغيلي YoY "
            f"({operating_yoy:.2f} نقطة)"
        )

    if (
        net_yoy is not None
        and net_yoy >= 1
    ):

        positive_reasons.append(
            f"تحسن الهامش الصافي YoY "
            f"({net_yoy:.2f} نقطة)"
        )

    if (
        operating_yoy is not None
        and operating_yoy <= -1.5
    ):

        negative_reasons.append(
            f"تآكل الهامش التشغيلي YoY "
            f"({operating_yoy:.2f} نقطة)"
        )

    if (
        net_yoy is not None
        and net_yoy <= -1.5
    ):

        negative_reasons.append(
            f"تآكل الهامش الصافي YoY "
            f"({net_yoy:.2f} نقطة)"
        )

    coverage = (
        total_weight
        / 100
    ) * 100

    return {
        "improvement": improvement,
        "risk": risk,
        "coverage": coverage,
        "positive": positive_reasons,
        "negative": negative_reasons
    }


# ============================================================
# جودة الأرباح والتدفقات
# ============================================================

def evaluate_cash_quality_component(metrics):

    cash_conversion = safe_number(
        metrics.get(
            "q_cash_conversion"
        )
    )

    ttm_cash_conversion = safe_number(
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

    scores = []
    weights = []

    positive_reasons = []
    negative_reasons = []

    if cash_conversion is not None:

        if cash_conversion >= 1.2:
            score = 100

        elif cash_conversion >= 1:
            score = 85

        elif cash_conversion >= 0.8:
            score = 65

        elif cash_conversion >= 0.7:
            score = 45

        elif cash_conversion >= 0.5:
            score = 20

        else:
            score = 0

        scores.append(
            score
        )

        weights.append(
            25
        )

        if cash_conversion >= 1:

            positive_reasons.append(
                f"تحويل الأرباح إلى نقد جيد "
                f"({cash_conversion:.2f})"
            )

        elif cash_conversion < 0.7:

            negative_reasons.append(
                f"جودة الأرباح النقدية ضعيفة "
                f"({cash_conversion:.2f})"
            )

    if ttm_cash_conversion is not None:

        if ttm_cash_conversion >= 1.2:
            score = 100

        elif ttm_cash_conversion >= 1:
            score = 85

        elif ttm_cash_conversion >= 0.8:
            score = 65

        elif ttm_cash_conversion >= 0.7:
            score = 45

        else:
            score = 15

        scores.append(
            score
        )

        weights.append(
            30
        )

    if ocf_yoy is not None:

        scores.append(
            score_growth(
                ocf_yoy
            )
        )

        weights.append(
            20
        )

    if fcf_yoy is not None:

        scores.append(
            score_growth(
                fcf_yoy
            )
        )

        weights.append(
            15
        )

    if ttm_fcf_margin is not None:

        if ttm_fcf_margin >= 15:
            score = 100

        elif ttm_fcf_margin >= 10:
            score = 80

        elif ttm_fcf_margin >= 5:
            score = 60

        elif ttm_fcf_margin >= 2:
            score = 40

        else:
            score = 20

        scores.append(
            score
        )

        weights.append(
            10
        )

    if not scores:
        return None

    weighted_sum = 0
    total_weight = 0

    for score, weight in zip(
        scores,
        weights
    ):

        weighted_sum += (
            score * weight
        )

        total_weight += weight

    improvement = (
        weighted_sum
        / total_weight
    )

    risk = (
        100
        - improvement
    )

    coverage = (
        total_weight
        / 100
    ) * 100

    return {
        "improvement": improvement,
        "risk": risk,
        "coverage": coverage,
        "positive": positive_reasons,
        "negative": negative_reasons
    }


# ============================================================
# مجموعة المركز المالي
# ============================================================

def evaluate_balance_sheet_component(metrics):

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

    scores = []
    weights = []

    positive_reasons = []
    negative_reasons = []

    if debt_growth is not None:

        if debt_growth <= -8:
            score = 100

        elif debt_growth <= -3:
            score = 85

        elif debt_growth <= 2:
            score = 65

        elif debt_growth <= 6:
            score = 45

        elif debt_growth <= 12:
            score = 25

        else:
            score = 5

        scores.append(
            score
        )

        weights.append(
            30
        )

    if debt_to_equity is not None:

        if debt_to_equity <= 0.5:
            score = 100

        elif debt_to_equity <= 1:
            score = 80

        elif debt_to_equity <= 1.5:
            score = 60

        elif debt_to_equity <= 2:
            score = 35

        else:
            score = 15

        scores.append(
            score
        )

        weights.append(
            25
        )

    if current_ratio is not None:

        if current_ratio >= 1.5:
            score = 100

        elif current_ratio >= 1.2:
            score = 80

        elif current_ratio >= 1:
            score = 65

        elif current_ratio >= 0.8:
            score = 40

        else:
            score = 15

        scores.append(
            score
        )

        weights.append(
            30
        )

    if cash_growth is not None:

        scores.append(
            score_growth(
                cash_growth
            )
        )

        weights.append(
            15
        )

    if not scores:
        return None

    weighted_sum = 0
    total_weight = 0

    for score, weight in zip(
        scores,
        weights
    ):

        weighted_sum += (
            score * weight
        )

        total_weight += weight

    improvement = (
        weighted_sum
        / total_weight
    )

    risk = (
        100
        - improvement
    )

    if (
        debt_growth is not None
        and debt_growth <= -3
    ):

        positive_reasons.append(
            f"الدين ينخفض "
            f"({debt_growth:.2f}% QoQ)"
        )

    if (
        debt_growth is not None
        and debt_growth >= 8
    ):

        negative_reasons.append(
            f"الدين يرتفع بسرعة "
            f"({debt_growth:.2f}% QoQ)"
        )

    if (
        current_ratio is not None
        and current_ratio < 0.8
    ):

        negative_reasons.append(
            f"السيولة الجارية ضعيفة "
            f"({current_ratio:.2f})"
        )

    coverage = (
        total_weight
        / 100
    ) * 100

    return {
        "improvement": improvement,
        "risk": risk,
        "coverage": coverage,
        "positive": positive_reasons,
        "negative": negative_reasons
    }


# ============================================================
# رأس المال العامل
# المخزون + الذمم
# ============================================================

def evaluate_working_capital_component(metrics):

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

    scores = []
    weights = []

    positive_reasons = []
    negative_reasons = []

    if (
        revenue_growth is not None
        and inventory_growth is not None
    ):

        spread = (
            inventory_growth
            - revenue_growth
        )

        if spread <= 0:
            score = 90

        elif spread <= 5:
            score = 70

        elif spread <= 10:
            score = 50

        elif spread <= 20:
            score = 25

        else:
            score = 5

        scores.append(
            score
        )

        weights.append(
            50
        )

        if spread >= 12:

            negative_reasons.append(
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
            score = 90

        elif spread <= 5:
            score = 70

        elif spread <= 10:
            score = 50

        elif spread <= 20:
            score = 25

        else:
            score = 5

        scores.append(
            score
        )

        weights.append(
            50
        )

        if spread >= 12:

            negative_reasons.append(
                f"الذمم تنمو أسرع من الإيرادات "
                f"بـ {spread:.2f} نقطة"
            )

    if not scores:
        return None

    weighted_sum = 0
    total_weight = 0

    for score, weight in zip(
        scores,
        weights
    ):

        weighted_sum += (
            score * weight
        )

        total_weight += weight

    improvement = (
        weighted_sum
        / total_weight
    )

    risk = (
        100
        - improvement
    )

    coverage = (
        total_weight
        / 100
    ) * 100

    return {
        "improvement": improvement,
        "risk": risk,
        "coverage": coverage,
        "positive": positive_reasons,
        "negative": negative_reasons
    }


# ============================================================
# كفاية التاريخ
# ============================================================

def calculate_history_sufficiency(
    quarter_dates,
    periods,
    index
):

    score = 0

    # --------------------------------------------------------
    # عدد الأرباع
    # --------------------------------------------------------

    quarter_count = (
        index + 1
    )

    if quarter_count >= 8:
        score += 40

    elif quarter_count >= 6:
        score += 32

    elif quarter_count >= 4:
        score += 24

    elif quarter_count >= 3:
        score += 16

    elif quarter_count >= 2:
        score += 8

    # --------------------------------------------------------
    # هل توجد بيانات YoY؟
    # --------------------------------------------------------

    current = periods[
        quarter_dates[index]
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

    yoy_ratio = (
        available_yoy
        / len(yoy_metrics)
    )

    score += (
        yoy_ratio * 40
    )

    # --------------------------------------------------------
    # توفر 3 أرباع لقياس الاتجاه
    # --------------------------------------------------------

    if index >= 2:
        score += 20

    return clamp(
        score
    )


# ============================================================
# قياس التسارع
# ============================================================

def calculate_acceleration(
    quarter_dates,
    periods,
    index
):

    if index < 2:

        return {
            "score": 0.0,
            "coverage": 0.0
        }

    watched = [
        "q_revenue_growth_qoq",
        "q_net_income_growth_qoq",
        "q_operating_margin_change_qoq",
        "q_net_margin_change_qoq"
    ]

    acceleration_points = []
    available = 0

    for metric_name in watched:

        values = []

        for date in quarter_dates[
            index - 2:index + 1
        ]:

            metric_value = safe_number(
                periods[
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

        first_change = (
            values[1]
            - values[0]
        )

        second_change = (
            values[2]
            - values[1]
        )

        acceleration = (
            second_change
            - first_change
        )

        acceleration_points.append(
            acceleration
        )

    if not acceleration_points:

        return {
            "score": 0.0,
            "coverage": 0.0
        }

    avg_acceleration = average(
        acceleration_points
    )

    if avg_acceleration >= 10:
        score = 100

    elif avg_acceleration >= 5:
        score = 80

    elif avg_acceleration >= 1:
        score = 65

    elif avg_acceleration >= -1:
        score = 50

    elif avg_acceleration >= -5:
        score = 35

    elif avg_acceleration >= -10:
        score = 20

    else:
        score = 0

    coverage = (
        available
        / len(watched)
    ) * 100

    return {
        "score": score,
        "coverage": coverage
    }


# ============================================================
# قياس الاستمرارية
# ============================================================

def calculate_persistence(
    quarter_dates,
    periods,
    index
):

    if index < 2:

        return {
            "score": 50.0,
            "coverage": 0.0
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

    for metric_name in watched:

        values = []

        for date in quarter_dates[
            index - 2:index + 1
        ]:

            metric_value = safe_number(
                periods[
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
            "score": 50.0,
            "coverage": 0.0
        }

    raw = (
        positive - negative
    ) / available

    score = clamp(
        50 + (
            raw * 50
        )
    )

    coverage = (
        available
        / len(watched)
    ) * 100

    return {
        "score": score,
        "coverage": coverage
    }


# ============================================================
# كشف التناقضات بدون تكرار العقوبة
# ============================================================

def calculate_contradiction_penalty(metrics):

    penalty = 0.0
    reasons = []

    revenue_yoy = safe_number(
        metrics.get(
            "q_revenue_growth_yoy"
        )
    )

    net_income_yoy = safe_number(
        metrics.get(
            "q_net_income_growth_yoy"
        )
    )

    ocf_yoy = safe_number(
        metrics.get(
            "q_ocf_growth_yoy"
        )
    )

    # --------------------------------------------------------
    # الإيرادات تنمو بقوة والأرباح لا تلحق بها
    # --------------------------------------------------------

    if (
        revenue_yoy is not None
        and net_income_yoy is not None
        and revenue_yoy >= 10
        and net_income_yoy
        < revenue_yoy - 10
    ):

        penalty += 8

        reasons.append(
            "نمو الإيرادات لا ينعكس بنفس القوة "
            "على صافي الربح"
        )

    # --------------------------------------------------------
    # الأرباح جيدة لكن التدفق التشغيلي يتراجع بقوة
    # --------------------------------------------------------

    if (
        net_income_yoy is not None
        and ocf_yoy is not None
        and net_income_yoy >= 5
        and ocf_yoy <= -15
    ):

        penalty += 10

        reasons.append(
            "نمو الأرباح غير مدعوم "
            "بالتدفق التشغيلي"
        )

    return {
        "penalty": clamp(
            penalty,
            0,
            20
        ),
        "reasons": reasons
    }


# ============================================================
# التقييم النهائي
# ============================================================

def finalize_engine(
    state,
    data_confidence,
    history,
    acceleration,
    persistence,
    contradiction
):

    available_weight = state[
        "available_weight"
    ]

    possible_weight = state[
        "possible_weight"
    ]

    if available_weight <= 0:

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

    # --------------------------------------------------------
    # عامل التغطية
    #
    # يمنع درجة 60+ من إشارة واحدة فقط
    # --------------------------------------------------------

    coverage_factor = (
        0.30
        + (
            signal_coverage
            / 100
        ) * 0.70
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
    # تأثير الاستمرارية
    # --------------------------------------------------------

    persistence_score = (
        persistence[
            "score"
        ]
    )

    persistence_coverage = (
        persistence[
            "coverage"
        ]
    )

    if persistence_coverage >= 40:

        persistence_adjustment = (
            persistence_score
            - 50
        ) * 0.10

        if persistence_adjustment > 0:

            improvement += (
                persistence_adjustment
            )

        else:

            risk += abs(
                persistence_adjustment
            )

    # --------------------------------------------------------
    # تأثير التسارع
    # --------------------------------------------------------

    acceleration_score = (
        acceleration[
            "score"
        ]
    )

    acceleration_coverage = (
        acceleration[
            "coverage"
        ]
    )

    if acceleration_coverage >= 40:

        acceleration_adjustment = (
            acceleration_score
            - 50
        ) * 0.10

        if acceleration_adjustment > 0:

            improvement += (
                acceleration_adjustment
            )

        else:

            risk += abs(
                acceleration_adjustment
            )

    # --------------------------------------------------------
    # عقوبة التناقض
    # --------------------------------------------------------

    contradiction_penalty = (
        contradiction[
            "penalty"
        ]
    )

    risk += contradiction_penalty

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
        or 0
    )

    # --------------------------------------------------------
    # Confidence الحقيقي
    #
    # Data Quality ≠ Signal Confidence
    # --------------------------------------------------------

    confidence = (
        data_confidence * 0.40
        + signal_coverage * 0.30
        + history * 0.30
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

        "acceleration_score":
            acceleration_score,

        "acceleration_coverage":
            acceleration_coverage,

        "persistence_score":
            persistence_score,

        "persistence_coverage":
            persistence_coverage,

        "contradiction_penalty":
            contradiction_penalty
    }


# ============================================================
# تفسير النتيجة
# ============================================================

def classify_result(
    scores
):

    net_score = scores[
        "net_score"
    ]

    confidence = scores[
        "confidence_score"
    ]

    history = scores[
        "history_sufficiency_score"
    ]

    if (
        confidence < 55
        or history < 40
    ):
        return (
            "INSUFFICIENT_HISTORY",
            "التاريخ غير كافٍ لحكم قوي"
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
# حفظ النتائج
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
        return

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

    print(
        f"💾 تم حفظ Signal Engine "
        f"{ENGINE_VERSION} | {period_end}",
        flush=True
    )


# ============================================================
# طباعة الأسباب
# ============================================================

def print_reasons(
    state,
    contradiction
):

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

    for _, component, reason in positive[:5]:

        print(
            f"- [{component}] {reason}",
            flush=True
        )

    print(
        "\n🔴 أسباب الخطر:",
        flush=True
    )

    if (
        not negative
        and not contradiction["reasons"]
    ):

        print(
            "- لا توجد إشارة خطر قوية",
            flush=True
        )

    for _, component, reason in negative[:5]:

        print(
            f"- [{component}] {reason}",
            flush=True
        )

    for reason in contradiction[
        "reasons"
    ]:

        print(
            f"- [contradiction] {reason}",
            flush=True
        )


# ============================================================
# تشغيل المحرك
# ============================================================

def run_signal_engine(stock_id):

    rows = get_financial_metrics(
        stock_id
    )

    if not rows:

        print(
            "🔴 لا توجد Financial Metrics",
            flush=True
        )

        return

    periods = organize_metrics(
        rows
    )

    quarter_dates = get_quarter_dates(
        periods
    )

    if not quarter_dates:

        print(
            "🔴 لا توجد أرباع للتحليل",
            flush=True
        )

        return

    print(
        "\n"
        "============================================================",
        flush=True
    )

    print(
        "🧠 SIGNAL ENGINE 2.1",
        flush=True
    )

    print(
        "============================================================",
        flush=True
    )

    for index, period_end in enumerate(
        quarter_dates
    ):

        metrics = periods[
            period_end
        ]

        data_confidence = safe_number(
            metrics.get(
                "data_confidence_score"
            )
        )

        if (
            data_confidence is None
            or data_confidence
            < MIN_DATA_CONFIDENCE
        ):

            print(
                f"\n⚠️ تجاهل {period_end} "
                f"بسبب انخفاض جودة البيانات",
                flush=True
            )

            continue

        state = new_state()

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
                weight=30,
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
        # Margins
        # ====================================================

        component = (
            evaluate_margin_component(
                metrics
            )
        )

        if component:

            add_component(
                state,
                "margins",
                weight=22,
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
        # Cash quality
        # ====================================================

        component = (
            evaluate_cash_quality_component(
                metrics
            )
        )

        if component:

            add_component(
                state,
                "cash_quality",
                weight=25,
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
        # Balance sheet
        # ====================================================

        component = (
            evaluate_balance_sheet_component(
                metrics
            )
        )

        if component:

            add_component(
                state,
                "balance_sheet",
                weight=15,
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
        # Working capital
        # ====================================================

        component = (
            evaluate_working_capital_component(
                metrics
            )
        )

        if component:

            add_component(
                state,
                "working_capital",
                weight=8,
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
        # History
        # ====================================================

        history = (
            calculate_history_sufficiency(
                quarter_dates,
                periods,
                index
            )
        )

        # ====================================================
        # Acceleration
        # ====================================================

        acceleration = (
            calculate_acceleration(
                quarter_dates,
                periods,
                index
            )
        )

        # ====================================================
        # Persistence
        # ====================================================

        persistence = (
            calculate_persistence(
                quarter_dates,
                periods,
                index
            )
        )

        # ====================================================
        # Contradictions
        # ====================================================

        contradiction = (
            calculate_contradiction_penalty(
                metrics
            )
        )

        scores = finalize_engine(
            state,
            data_confidence,
            history,
            acceleration,
            persistence,
            contradiction
        )

        if not scores:
            continue

        status_code, status_text = (
            classify_result(
                scores
            )
        )

        print(
            f"\n📅 الفترة: {period_end}",
            flush=True
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
            f"🗂️ History Sufficiency: "
            f"{scores['history_sufficiency_score']:.2f}",
            flush=True
        )

        print(
            f"🚀 Acceleration: "
            f"{scores['acceleration_score']:.2f}",
            flush=True
        )

        print(
            f"🔁 Persistence: "
            f"{scores['persistence_score']:.2f}",
            flush=True
        )

        print(
            f"⚠️ Contradiction Penalty: "
            f"{scores['contradiction_penalty']:.2f}",
            flush=True
        )

        print(
            f"🧭 الحالة: "
            f"{status_code} | "
            f"{status_text}",
            flush=True
        )

        print_reasons(
            state,
            contradiction
        )

        save_engine_metrics(
            stock_id,
            period_end,
            scores
        )


# ============================================================
# التشغيل
# ============================================================

if __name__ == "__main__":

    stock_id = int(
        os.environ.get(
            "STOCK_ID",
            "1"
        )
    )

    run_signal_engine(
        stock_id
    )
