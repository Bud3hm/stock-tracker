import os
from collections import defaultdict
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

    if value is None:
        return None

    return max(
        minimum,
        min(
            maximum,
            value
        )
    )


def average(values):

    clean = [
        safe_number(v)
        for v in values
        if safe_number(v) is not None
    ]

    if not clean:
        return None

    return sum(clean) / len(clean)


def weighted_average(items):

    weighted_sum = 0.0
    total_weight = 0.0

    for value, weight in items:

        value = safe_number(value)

        if value is None:
            continue

        weighted_sum += (
            value * weight
        )

        total_weight += weight

    if total_weight == 0:
        return None

    return weighted_sum / total_weight


# ============================================================
# تطبيع المؤشرات
# ============================================================

def score_positive_growth(
    value,
    excellent=20,
    good=10,
    neutral=0,
    bad=-10
):

    value = safe_number(value)

    if value is None:
        return None

    if value >= excellent:
        return 100

    if value >= good:
        return 80

    if value >= neutral:
        return 60

    if value >= bad:
        return 35

    return 10


def score_margin_change(value):

    value = safe_number(value)

    if value is None:
        return None

    if value >= 3:
        return 100

    if value >= 1:
        return 80

    if value >= 0:
        return 60

    if value >= -2:
        return 35

    return 10


def score_ratio_high_good(
    value,
    excellent,
    good,
    weak
):

    value = safe_number(value)

    if value is None:
        return None

    if value >= excellent:
        return 100

    if value >= good:
        return 80

    if value >= weak:
        return 55

    return 20


def score_ratio_low_good(
    value,
    excellent,
    acceptable,
    high
):

    value = safe_number(value)

    if value is None:
        return None

    if value <= excellent:
        return 100

    if value <= acceptable:
        return 75

    if value <= high:
        return 45

    return 15


def score_cash_conversion(value):

    value = safe_number(value)

    if value is None:
        return None

    if value >= 1.2:
        return 100

    if value >= 1.0:
        return 85

    if value >= 0.8:
        return 65

    if value >= 0.5:
        return 35

    return 10


def score_confidence(value):

    value = safe_number(value)

    if value is None:
        return 0

    return clamp(value)


# ============================================================
# جلب الشركات
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


# ============================================================
# جلب المؤشرات
# ============================================================

def get_stock_metrics(stock_id):

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
# تحديد أحدث ربع صالح
# ============================================================

def find_latest_period(
    periods,
    analysis_model
):

    dates = sorted(
        periods.keys()
    )

    dates.reverse()

    prefixes = {
        "standard": "q_",
        "bank": "bank_q_",
        "insurance": "insurance_q_",
        "reit": "reit_q_"
    }

    prefix = prefixes.get(
        analysis_model
    )

    for date in dates:

        metrics = periods[
            date
        ]

        if prefix is None:
            continue

        if any(
            name.startswith(prefix)
            for name in metrics.keys()
        ):

            return date

    return None


# ============================================================
# Standard Scoring
# ============================================================

def score_standard(metrics):

    growth_score = weighted_average([
        (
            score_positive_growth(
                metrics.get(
                    "q_revenue_growth_yoy"
                )
            ),
            30
        ),
        (
            score_positive_growth(
                metrics.get(
                    "q_net_income_growth_yoy"
                )
            ),
            35
        ),
        (
            score_positive_growth(
                metrics.get(
                    "q_fcf_growth_yoy"
                )
            ),
            20
        ),
        (
            score_positive_growth(
                metrics.get(
                    "q_ocf_growth_yoy"
                )
            ),
            15
        )
    ])

    quality_score = weighted_average([
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

    cash_score = weighted_average([
        (
            score_cash_conversion(
                metrics.get(
                    "q_cash_conversion"
                )
            ),
            40
        ),
        (
            score_positive_growth(
                metrics.get(
                    "q_ocf_growth_yoy"
                )
            ),
            30
        ),
        (
            score_positive_growth(
                metrics.get(
                    "q_fcf_growth_yoy"
                )
            ),
            30
        )
    ])

    balance_score = weighted_average([
        (
            score_ratio_low_good(
                metrics.get(
                    "q_debt_to_equity"
                ),
                excellent=0.5,
                acceptable=1.0,
                high=2.0
            ),
            35
        ),
        (
            score_ratio_high_good(
                metrics.get(
                    "q_current_ratio"
                ),
                excellent=1.5,
                good=1.0,
                weak=0.8
            ),
            25
        ),
        (
            score_positive_growth(
                -metrics.get(
                    "q_debt_growth_qoq"
                )
                if metrics.get(
                    "q_debt_growth_qoq"
                ) is not None
                else None
            ),
            20
        ),
        (
            score_positive_growth(
                metrics.get(
                    "q_cash_growth_qoq"
                )
            ),
            
