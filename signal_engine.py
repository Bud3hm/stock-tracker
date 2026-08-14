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

MIN_CONFIDENCE_TO_SCORE = 60.0

ENGINE_PREFIX = "engine2_"


# ============================================================
# أدوات مساعدة
# ============================================================

def safe_number(value):

    if value is None:
        return None

    try:
        return float(value)

    except (TypeError, ValueError):
        return None


def clamp(value, minimum, maximum):

    return max(
        minimum,
        min(maximum, value)
    )


def average(values):

    clean = [
        safe_number(value)
        for value in values
        if safe_number(value) is not None
    ]

    if not clean:
        return None

    return sum(clean) / len(clean)


# ============================================================
# جلب المؤشرات المحسوبة
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
# ترتيب المؤشرات حسب الفترة
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
# كائن نتيجة الإشارة
# ============================================================

def new_score_state():

    return {
        "improvement_points": 0.0,
        "risk_points": 0.0,
        "total_weight": 0.0,
        "strong_positive": 0,
        "strong_negative": 0,
        "positive_reasons": [],
        "negative_reasons": []
    }


# ============================================================
# إضافة إشارة
# ============================================================

def add_signal(
    state,
    value,
    weight,
    positive_threshold,
    negative_threshold,
    positive_reason,
    negative_reason,
    inverse=False,
    strong=False
):

    value = safe_number(
        value
    )

    if value is None:
        return

    state[
        "total_weight"
    ] += weight

    if not inverse:

        if value >= positive_threshold:

            state[
                "improvement_points"
            ] += weight

            state[
                "positive_reasons"
            ].append(
                (
                    weight,
                    positive_reason,
                    value
                )
            )

            if strong:
                state[
                    "strong_positive"
                ] += 1

        elif value <= negative_threshold:

            state[
                "risk_points"
            ] += weight

            state[
                "negative_reasons"
            ].append(
                (
                    weight,
                    negative_reason,
                    value
                )
            )

            if strong:
                state[
                    "strong_negative"
                ] += 1

    else:

        if value <= positive_threshold:

            state[
                "improvement_points"
            ] += weight

            state[
                "positive_reasons"
            ].append(
                (
                    weight,
                    positive_reason,
                    value
                )
            )

            if strong:
                state[
                    "strong_positive"
                ] += 1

        elif value >= negative_threshold:

            state[
                "risk_points"
            ] += weight

            state[
                "negative_reasons"
            ].append(
                (
                    weight,
                    negative_reason,
                    value
                )
            )

            if strong:
                state[
                    "strong_negative"
                ] += 1


# ============================================================
# الإشارات الأساسية
#
# YoY أعلى وزنًا من QoQ
# ============================================================

def evaluate_current_quarter(metrics):

    state = new_score_state()

    # --------------------------------------------------------
    # الإيرادات YoY
    # --------------------------------------------------------

    add_signal(
        state,
        metrics.get(
            "q_revenue_growth_yoy"
        ),
        weight=12,
        positive_threshold=5,
        negative_threshold=-5,
        positive_reason=(
            "نمو الإيرادات السنوي لنفس الربع جيد"
        ),
        negative_reason=(
            "الإيرادات تتراجع مقارنة بنفس الربع"
        ),
        strong=True
    )

    # --------------------------------------------------------
    # صافي الربح YoY
    # --------------------------------------------------------

    add_signal(
        state,
        metrics.get(
            "q_net_income_growth_yoy"
        ),
        weight=15,
        positive_threshold=8,
        negative_threshold=-8,
        positive_reason=(
            "صافي الربح ينمو بقوة سنويًا"
        ),
        negative_reason=(
            "صافي الربح يتراجع سنويًا"
        ),
        strong=True
    )

    # --------------------------------------------------------
    # الإيرادات QoQ
    # وزن أقل بسبب الموسمية
    # --------------------------------------------------------

    add_signal(
        state,
        metrics.get(
            "q_revenue_growth_qoq"
        ),
        weight=5,
        positive_threshold=4,
        negative_threshold=-7,
        positive_reason=(
            "الإيرادات تتحسن عن الربع السابق"
        ),
        negative_reason=(
            "الإيرادات تتراجع عن الربع السابق"
        )
    )

    # --------------------------------------------------------
    # الربح QoQ
    # --------------------------------------------------------

    add_signal(
        state,
        metrics.get(
            "q_net_income_growth_qoq"
        ),
        weight=6,
        positive_threshold=5,
        negative_threshold=-10,
        positive_reason=(
            "الأرباح تتحسن عن الربع السابق"
        ),
        negative_reason=(
            "الأرباح تراجعت بوضوح عن الربع السابق"
        )
    )

    # --------------------------------------------------------
    # الهامش الإجمالي YoY
    # --------------------------------------------------------

    add_signal(
        state,
        metrics.get(
            "q_gross_margin_change_yoy"
        ),
        weight=7,
        positive_threshold=1,
        negative_threshold=-1.5,
        positive_reason=(
            "الهامش الإجمالي يتحسن سنويًا"
        ),
        negative_reason=(
            "الهامش الإجمالي يتآكل سنويًا"
        ),
        strong=True
    )

    # --------------------------------------------------------
    # الهامش التشغيلي YoY
    # --------------------------------------------------------

    add_signal(
        state,
        metrics.get(
            "q_operating_margin_change_yoy"
        ),
        weight=9,
        positive_threshold=1,
        negative_threshold=-1.5,
        positive_reason=(
            "الهامش التشغيلي يتحسن سنويًا"
        ),
        negative_reason=(
            "الهامش التشغيلي يتراجع سنويًا"
        ),
        strong=True
    )

    # --------------------------------------------------------
    # الهامش الصافي YoY
    # --------------------------------------------------------

    add_signal(
        state,
        metrics.get(
            "q_net_margin_change_yoy"
        ),
        weight=9,
        positive_threshold=1,
        negative_threshold=-1.5,
        positive_reason=(
            "هامش صافي الربح يتحسن سنويًا"
        ),
        negative_reason=(
            "هامش صافي الربح يتراجع سنويًا"
        ),
        strong=True
    )

    # --------------------------------------------------------
    # الهامش التشغيلي QoQ
    # --------------------------------------------------------

    add_signal(
        state,
        metrics.get(
            "q_operating_margin_change_qoq"
        ),
        weight=4,
        positive_threshold=0.75,
        negative_threshold=-1,
        positive_reason=(
            "الهامش التشغيلي يتحسن عن الربع السابق"
        ),
        negative_reason=(
            "الهامش التشغيلي تراجع عن الربع السابق"
        )
    )

    # --------------------------------------------------------
    # التدفق التشغيلي YoY
    # --------------------------------------------------------

    add_signal(
        state,
        metrics.get(
            "q_ocf_growth_yoy"
        ),
        weight=11,
        positive_threshold=8,
        negative_threshold=-15,
        positive_reason=(
            "التدفق النقدي التشغيلي يتحسن سنويًا"
        ),
        negative_reason=(
            "التدفق التشغيلي يتراجع بوضوح"
        ),
        strong=True
    )

    # --------------------------------------------------------
    # FCF YoY
    # --------------------------------------------------------

    add_signal(
        state,
        metrics.get(
            "q_fcf_growth_yoy"
        ),
        weight=10,
        positive_threshold=8,
        negative_threshold=-15,
        positive_reason=(
            "التدفق النقدي الحر يتحسن سنويًا"
        ),
        negative_reason=(
            "التدفق النقدي الحر يتراجع"
        ),
        strong=True
    )

    # --------------------------------------------------------
    # جودة الأرباح
    # --------------------------------------------------------

    add_signal(
        state,
        metrics.get(
            "q_cash_conversion"
        ),
        weight=10,
        positive_threshold=1.0,
        negative_threshold=0.7,
        positive_reason=(
            "تحويل الأرباح إلى نقد قوي"
        ),
        negative_reason=(
            "جودة الأرباح النقدية ضعيفة"
        ),
        strong=True
    )

    # --------------------------------------------------------
    # الدين
    # انخفاضه أفضل
    # --------------------------------------------------------

    add_signal(
        state,
        metrics.get(
            "q_debt_growth_qoq"
        ),
        weight=6,
        positive_threshold=-2,
        negative_threshold=6,
        positive_reason=(
            "الدين يتراجع"
        ),
        negative_reason=(
            "الدين يرتفع بسرعة"
        ),
        inverse=True
    )

    # --------------------------------------------------------
    # السيولة الجارية
    # --------------------------------------------------------

    add_signal(
        state,
        metrics.get(
            "q_current_ratio"
        ),
        weight=6,
        positive_threshold=1.1,
        negative_threshold=0.8,
        positive_reason=(
            "السيولة قصيرة الأجل جيدة"
        ),
        negative_reason=(
            "السيولة قصيرة الأجل ضعيفة"
        )
    )

    # --------------------------------------------------------
    # TTM cash conversion
    # --------------------------------------------------------

    add_signal(
        state,
        metrics.get(
            "ttm_cash_conversion"
        ),
        weight=8,
        positive_threshold=1,
        negative_threshold=0.75,
        positive_reason=(
            "جودة الأرباح خلال آخر 12 شهر جيدة"
        ),
        negative_reason=(
            "الأرباح خلال آخر 12 شهر لا تتحول إلى نقد جيدًا"
        ),
        strong=True
    )

    # --------------------------------------------------------
    # ROE TTM
    # --------------------------------------------------------

    add_signal(
        state,
        metrics.get(
            "ttm_roe"
        ),
        weight=5,
        positive_threshold=15,
        negative_threshold=7,
        positive_reason=(
            "العائد على حقوق المساهمين قوي"
        ),
        negative_reason=(
            "العائد على حقوق المساهمين ضعيف"
        )
    )

    # --------------------------------------------------------
    # FCF Margin TTM
    # --------------------------------------------------------

    add_signal(
        state,
        metrics.get(
            "ttm_fcf_margin"
        ),
        weight=5,
        positive_threshold=10,
        negative_threshold=3,
        positive_reason=(
            "هامش التدفق الحر قوي"
        ),
        negative_reason=(
            "هامش التدفق الحر ضعيف"
        )
    )

    return state


# ============================================================
# كشف المخزون والذمم
# ============================================================

def evaluate_working_capital(
    state,
    metrics
):

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

    if (
        revenue_growth is not None
        and inventory_growth is not None
    ):

        state[
            "total_weight"
        ] += 5

        difference_value = (
            inventory_growth
            - revenue_growth
        )

        if difference_value <= 3:

            state[
                "improvement_points"
            ] += 5

            state[
                "positive_reasons"
            ].append(
                (
                    5,
                    "المخزون لا ينمو أسرع من المبيعات بشكل مقلق",
                    difference_value
                )
            )

        elif difference_value >= 12:

            state[
                "risk_points"
            ] += 5

            state[
                "negative_reasons"
            ].append(
                (
                    5,
                    "المخزون يرتفع أسرع من نمو المبيعات",
                    difference_value
                )
            )

    if (
        revenue_growth is not None
        and receivables_growth is not None
    ):

        state[
            "total_weight"
        ] += 5

        difference_value = (
            receivables_growth
            - revenue_growth
        )

        if difference_value <= 3:

            state[
                "improvement_points"
            ] += 5

            state[
                "positive_reasons"
            ].append(
                (
                    5,
                    "الذمم المدينة منضبطة مقابل نمو المبيعات",
                    difference_value
                )
            )

        elif difference_value >= 12:

            state[
                "risk_points"
            ] += 5

            state[
                "negative_reasons"
            ].append(
                (
                    5,
                    "الذمم ترتفع أسرع من المبيعات",
                    difference_value
                )
            )


# ============================================================
# كشف التناقضات
# ============================================================

def evaluate_contradictions(
    state,
    metrics
):

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

    revenue_yoy = safe_number(
        metrics.get(
            "q_revenue_growth_yoy"
        )
    )

    net_margin_yoy = safe_number(
        metrics.get(
            "q_net_margin_change_yoy"
        )
    )

    # --------------------------------------------------------
    # الأرباح ترتفع لكن التدفق ينخفض
    # --------------------------------------------------------

    if (
        net_income_yoy is not None
        and ocf_yoy is not None
        and net_income_yoy > 5
        and ocf_yoy < -10
    ):

        weight = 10

        state[
            "total_weight"
        ] += weight

        state[
            "risk_points"
        ] += weight

        state[
            "strong_negative"
        ] += 1

        state[
            "negative_reasons"
        ].append(
            (
                weight,
                "الأرباح ترتفع لكن التدفق التشغيلي يتراجع",
                ocf_yoy
            )
        )

    # --------------------------------------------------------
    # الإيرادات ترتفع لكن الهامش يتدهور
    # --------------------------------------------------------

    if (
        revenue_yoy is not None
        and net_margin_yoy is not None
        and revenue_yoy > 8
        and net_margin_yoy < -2
    ):

        weight = 8

        state[
            "total_weight"
        ] += weight

        state[
            "risk_points"
        ] += weight

        state[
            "negative_reasons"
        ].append(
            (
                weight,
                "نمو الإيرادات لا يتحول إلى تحسن في هامش الربح",
                net_margin_yoy
            )
        )


# ============================================================
# قياس Momentum عبر الأرباع
# ============================================================

def metric_momentum(
    quarter_dates,
    periods,
    index,
    metric_name
):

    if index < 2:
        return None

    dates = quarter_dates[
        index - 2:index + 1
    ]

    values = []

    for date in dates:

        metric_value = safe_number(
            periods[
                date
            ].get(
                metric_name
            )
        )

        if metric_value is None:
            return None

        values.append(
            metric_value
        )

    first_change = (
        values[1]
        - values[0]
    )

    second_change = (
        values[2]
        - values[1]
    )

    # الاتجاه يتحسن باستمرار
    if (
        first_change > 0
        and second_change > 0
    ):

        return 1

    # الاتجاه يتدهور باستمرار
    if (
        first_change < 0
        and second_change < 0
    ):

        return -1

    return 0


# ============================================================
# Momentum Score
# ============================================================

def calculate_momentum(
    quarter_dates,
    periods,
    index
):

    watched_metrics = {
        "q_revenue_growth_yoy": 4,
        "q_net_income_growth_yoy": 5,
        "q_gross_margin": 3,
        "q_operating_margin": 4,
        "q_net_margin": 4,
        "q_cash_conversion": 4,
        "ttm_fcf_margin": 3
    }

    positive = 0.0
    negative = 0.0
    total = 0.0

    for (
        metric_name,
        weight
    ) in watched_metrics.items():

        momentum = metric_momentum(
            quarter_dates,
            periods,
            index,
            metric_name
        )

        if momentum is None:
            continue

        total += weight

        if momentum > 0:
            positive += weight

        elif momentum < 0:
            negative += weight

    if total == 0:

        return {
            "momentum_score": 0.0,
            "momentum_positive": 0.0,
            "momentum_negative": 0.0
        }

    positive_score = (
        positive
        / total
    ) * 100

    negative_score = (
        negative
        / total
    ) * 100

    return {
        "momentum_score":
            positive_score
            - negative_score,

        "momentum_positive":
            positive_score,

        "momentum_negative":
            negative_score
    }


# ============================================================
# قياس استمرارية الاتجاه
# ============================================================

def calculate_consistency(
    quarter_dates,
    periods,
    index
):

    if index < 2:
        return 50.0

    dates = quarter_dates[
        index - 2:index + 1
    ]

    positive_count = 0
    negative_count = 0
    total = 0

    metrics_to_check = [
        "q_revenue_growth_yoy",
        "q_net_income_growth_yoy",
        "q_operating_margin_change_yoy",
        "q_net_margin_change_yoy",
        "q_ocf_growth_yoy",
        "q_fcf_growth_yoy"
    ]

    for metric_name in metrics_to_check:

        values = []

        for date in dates:

            metric_value = safe_number(
                periods[
                    date
                ].get(
                    metric_name
                )
            )

            if metric_value is not None:

                values.append(
                    metric_value
                )

        if len(values) != 3:
            continue

        total += 1

        if all(
            value > 0
            for value in values
        ):

            positive_count += 1

        elif all(
            value < 0
            for value in values
        ):

            negative_count += 1

    if total == 0:
        return 50.0

    raw = (
        (
            positive_count
            - negative_count
        )
        / total
    )

    return clamp(
        50 + (
            raw * 50
        ),
        0,
        100
    )


# ============================================================
# تحويل النقاط إلى Scores
# ============================================================

def finalize_scores(
    state,
    data_confidence,
    momentum,
    consistency
):

    total_weight = state.get(
        "total_weight",
        0
    )

    if total_weight <= 0:

        return {
            "improvement_score": 0.0,
            "risk_score": 0.0,
            "net_score": 0.0,
            "confidence_score": 0.0
        }

    base_improvement = (
        state[
            "improvement_points"
        ]
        / total_weight
    ) * 100

    base_risk = (
        state[
            "risk_points"
        ]
        / total_weight
    ) * 100

    momentum_score = safe_number(
        momentum.get(
            "momentum_score"
        )
    ) or 0

    # Momentum تأثيره محدود
    momentum_adjustment = (
        momentum_score * 0.15
    )

    # consistency فوق 50 إيجابي
    # تحت 50 سلبي
    consistency_adjustment = (
        (
            consistency - 50
        )
        * 0.15
    )

    improvement_score = (
        base_improvement
        + max(
            momentum_adjustment,
            0
        )
        + max(
            consistency_adjustment,
            0
        )
    )

    risk_score = (
        base_risk
        + max(
            -momentum_adjustment,
            0
        )
        + max(
            -consistency_adjustment,
            0
        )
    )

    improvement_score = clamp(
        improvement_score,
        0,
        100
    )

    risk_score = clamp(
        risk_score,
        0,
        100
    )

    net_score = (
        improvement_score
        - risk_score
    )

    data_confidence = safe_number(
        data_confidence
    )

    if data_confidence is None:
        data_confidence = 0

    coverage = clamp(
        total_weight / 130 * 100,
        0,
        100
    )

    confidence_score = (
        data_confidence * 0.70
        + coverage * 0.30
    )

    return {
        "improvement_score":
            improvement_score,

        "risk_score":
            risk_score,

        "net_score":
            net_score,

        "confidence_score":
            confidence_score
    }


# ============================================================
# حفظ نتائج المحرك
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
        f"💾 تم حفظ نتائج Signal Engine "
        f"للفترة {period_end}",
        flush=True
    )


# ============================================================
# طباعة أهم الأسباب
# ============================================================

def print_top_reasons(
    state,
    limit=5
):

    positive = sorted(
        state[
            "positive_reasons"
        ],
        key=lambda x: x[0],
        reverse=True
    )

    negative = sorted(
        state[
            "negative_reasons"
        ],
        key=lambda x: x[0],
        reverse=True
    )

    print(
        "\n🟢 أقوى إشارات التحسن:",
        flush=True
    )

    if not positive:

        print(
            "- لا توجد إشارة قوية",
            flush=True
        )

    for (
        weight,
        reason,
        value
    ) in positive[:limit]:

        print(
            f"- {reason} "
            f"| القيمة: {value:.2f} "
            f"| الوزن: {weight}",
            flush=True
        )

    print(
        "\n🔴 أقوى إشارات الخطر:",
        flush=True
    )

    if not negative:

        print(
            "- لا توجد إشارة قوية",
            flush=True
        )

    for (
        weight,
        reason,
        value
    ) in negative[:limit]:

        print(
            f"- {reason} "
            f"| القيمة: {value:.2f} "
            f"| الوزن: {weight}",
            flush=True
        )


# ============================================================
# تشغيل Signal Engine
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
            "🔴 لا توجد بيانات ربعية للتحليل",
            flush=True
        )

        return

    print(
        "\n"
        "============================================================",
        flush=True
    )

    print(
        "🧠 SIGNAL ENGINE 2.0",
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
            < MIN_CONFIDENCE_TO_SCORE
        ):

            print(
                f"\n⚠️ تجاهل {period_end} "
                f"بسبب انخفاض جودة البيانات",
                flush=True
            )

            continue

        state = evaluate_current_quarter(
            metrics
        )

        evaluate_working_capital(
            state,
            metrics
        )

        evaluate_contradictions(
            state,
            metrics
        )

        momentum = calculate_momentum(
            quarter_dates,
            periods,
            index
        )

        consistency = calculate_consistency(
            quarter_dates,
            periods,
            index
        )

        scores = finalize_scores(
            state,
            data_confidence,
            momentum,
            consistency
        )

        engine_values = {

            "improvement_score":
                scores[
                    "improvement_score"
                ],

            "risk_score":
                scores[
                    "risk_score"
                ],

            "net_score":
                scores[
                    "net_score"
                ],

            "confidence_score":
                scores[
                    "confidence_score"
                ],

            "momentum_score":
                momentum[
                    "momentum_score"
                ],

            "momentum_positive":
                momentum[
                    "momentum_positive"
                ],

            "momentum_negative":
                momentum[
                    "momentum_negative"
                ],

            "consistency_score":
                consistency,

            "strong_positive_count":
                state[
                    "strong_positive"
                ],

            "strong_negative_count":
                state[
                    "strong_negative"
                ]
        }

        print(
            f"\n📅 الفترة: {period_end}",
            flush=True
        )

        print(
            f"🟢 Improvement Score: "
            f"{engine_values['improvement_score']:.2f}",
            flush=True
        )

        print(
            f"🔴 Risk Score: "
            f"{engine_values['risk_score']:.2f}",
            flush=True
        )

        print(
            f"⚖️ Net Score: "
            f"{engine_values['net_score']:.2f}",
            flush=True
        )

        print(
            f"🚀 Momentum: "
            f"{engine_values['momentum_score']:.2f}",
            flush=True
        )

        print(
            f"🔁 Consistency: "
            f"{engine_values['consistency_score']:.2f}",
            flush=True
        )

        print(
            f"🎯 Confidence: "
            f"{engine_values['confidence_score']:.2f}",
            flush=True
        )

        print_top_reasons(
            state
        )

        save_engine_metrics(
            stock_id,
            period_end,
            engine_values
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
