import os
import time
from collections import Counter
from supabase import create_client


# ============================================================
# SIGNAL VALIDATION AUDIT v1.0
#
# الهدف:
#
# التحقق تاريخيًا من Signal Engine 2.2.2
#
# المحرك:
# - READ ONLY
# - لا يحذف
# - لا يعدل
# - لا يكتب في Supabase
#
# الفكرة:
#
# 1) قراءة الإشارة التي أصدرها engine22_
# 2) قراءة البيانات المالية للربع نفسه
# 3) قراءة الربع التالي
# 4) قياس هل تحسنت الأساسيات فعلاً أم تدهورت
# 5) مقارنة اتجاه Signal مع الاتجاه الذي تحقق لاحقًا
#
# مهم:
# هذا Validation للمحرك وليس Score استثماري جديد.
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
# إعدادات
# ============================================================

AUDIT_VERSION = "1.0"

ENGINE_PREFIX = "engine22_"


# ------------------------------------------------------------
# نبدأ بخمس شركات متنوعة
#
# إذا لم توجد إحداها، سيكمل البرنامج بما هو موجود.
# يمكن تغييرها لاحقًا بدون تعديل منطق المحرك.
# ------------------------------------------------------------

DEFAULT_VALIDATION_SYMBOLS = [

    "4030.SR",   # البحري
    "1111.SR",   # مجموعة تداول السعودية
    "7203.SR",   # علم
    "7010.SR",   # STC
    "2283.SR"    # المطاحن الأولى
]


# ------------------------------------------------------------
# الحد الأدنى لقبول Signal تاريخيًا
#
# نفس المنطق المستخدم حاليًا في Signal Engine
# ------------------------------------------------------------

MIN_SIGNAL_CONFIDENCE = 55.0
MIN_HISTORY_SCORE = 40.0
MIN_TREND_RELIABILITY = 35.0


# ------------------------------------------------------------
# الحد الأدنى لتغطية Fundamental Validation
# ------------------------------------------------------------

MIN_FUNDAMENTAL_COVERAGE = 50.0


# ------------------------------------------------------------
# مقدار التغير المطلوب لاعتبار الربع تحسنًا أو تدهورًا
# ------------------------------------------------------------

REALIZED_IMPROVEMENT_THRESHOLD = 5.0
REALIZED_DETERIORATION_THRESHOLD = -5.0


# ============================================================
# أدوات عامة
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


# ============================================================
# Supabase Retry
# ============================================================

def execute_with_retry(
    builder_factory,
    attempts=3,
    delay=2
):

    last_error = None

    for attempt in range(
        1,
        attempts + 1
    ):

        try:

            return (
                builder_factory()
                .execute()
            )

        except Exception as error:

            last_error = error

            if attempt >= attempts:

                raise

            print(
                f"🟡 Supabase retry "
                f"{attempt}/{attempts - 1} | "
                f"{type(error).__name__}",
                flush=True
            )

            time.sleep(
                delay * attempt
            )

    raise last_error


# ============================================================
# جلب الشركات
# ============================================================

def get_active_standard_stocks():

    response = execute_with_retry(
        lambda:
        (
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
            .eq(
                "analysis_model",
                "standard"
            )
            .order(
                "id"
            )
        )
    )

    return (
        response.data
        or []
    )


# ============================================================
# اختيار شركات التدقيق
# ============================================================

def select_validation_stocks():

    stocks = (
        get_active_standard_stocks()
    )

    if not stocks:

        return []

    by_symbol = {

        stock.get(
            "symbol"
        ):
            stock

        for stock in stocks

        if stock.get(
            "symbol"
        )
    }

    selected = []

    for symbol in DEFAULT_VALIDATION_SYMBOLS:

        stock = by_symbol.get(
            symbol
        )

        if stock:

            selected.append(
                stock
            )

    # --------------------------------------------------------
    # إذا نقص العدد عن خمس شركات
    # نكمله من أول الشركات Standard المتوفرة
    # --------------------------------------------------------

    selected_ids = {

        stock[
            "id"
        ]

        for stock in selected
    }

    for stock in stocks:

        if len(
            selected
        ) >= 5:

            break

        if stock[
            "id"
        ] in selected_ids:

            continue

        selected.append(
            stock
        )

        selected_ids.add(
            stock[
                "id"
            ]
        )

    return selected


# ============================================================
# جلب Financial Metrics مع Pagination
# ============================================================

def get_financial_metrics(
    stock_id
):

    rows = []

    page_size = 1000
    start = 0

    while True:

        end = (
            start
            + page_size
            - 1
        )

        response = execute_with_retry(
            lambda:
            (
                supabase
                .table(
                    "financial_metrics"
                )
                .select(
                    "stock_id,"
                    "period_end,"
                    "metric_name,"
                    "metric_value,"
                    "calculated_at"
                )
                .eq(
                    "stock_id",
                    stock_id
                )
                .range(
                    start,
                    end
                )
            )
        )

        batch = (
            response.data
            or []
        )

        rows.extend(
            batch
        )

        if len(
            batch
        ) < page_size:

            break

        start += page_size

    return rows


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
            period_end is None
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
# تحديد الأرباع Standard
#
# نستبعد الفترات التي تحتوي Engine outputs فقط.
# لا بد من وجود مؤشر مالي فعلي.
# ============================================================

def get_standard_quarter_dates(
    periods
):

    quarter_dates = []

    core_financial_metrics = [

        "q_revenue",
        "q_net_income",
        "q_revenue_growth_yoy",
        "q_net_income_growth_yoy",
        "q_operating_margin",
        "q_net_margin",
        "q_cash_conversion"
    ]

    for (
        period_end,
        metrics
    ) in periods.items():

        has_financial_data = any(

            metric_name in metrics

            for metric_name
            in core_financial_metrics
        )

        if has_financial_data:

            quarter_dates.append(
                period_end
            )

    return sorted(
        quarter_dates
    )


# ============================================================
# تحويل Growth إلى Fundamental Score
#
# هذه الدالة تستخدم فقط في Validation.
# لا تغير Signal Engine.
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
# Score لتغير الهوامش
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
# Score لجودة التحويل النقدي
# ============================================================

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

    if value >= 0.70:
        return 45.0

    if value >= 0.50:
        return 20.0

    return 0.0


# ============================================================
# Fundamental Health Score
#
# هذا ليس Investment Score.
#
# يستخدم فقط لقياس:
# هل تحسنت البيانات الفعلية في الربع التالي أم لا؟
#
# الأوزان:
#
# Revenue YoY          25%
# Net Income YoY       35%
# Operating Margin     15%
# Net Margin           15%
# Cash Conversion      10%
#
# ============================================================

def calculate_fundamental_health(
    metrics
):

    components = []

    available_weight = 0.0
    possible_weight = 100.0

    detail = {}


    # --------------------------------------------------------
    # Revenue Growth
    # --------------------------------------------------------

    value = safe_number(
        metrics.get(
            "q_revenue_growth_yoy"
        )
    )

    score = score_growth(
        value
    )

    if score is not None:

        weight = 25.0

        components.append(
            (
                score,
                weight
            )
        )

        available_weight += weight

        detail[
            "revenue_yoy"
        ] = value


    # --------------------------------------------------------
    # Net Income Growth
    # --------------------------------------------------------

    value = safe_number(
        metrics.get(
            "q_net_income_growth_yoy"
        )
    )

    score = score_growth(
        value
    )

    if score is not None:

        weight = 35.0

        components.append(
            (
                score,
                weight
            )
        )

        available_weight += weight

        detail[
            "net_income_yoy"
        ] = value


    # --------------------------------------------------------
    # Operating Margin Change
    # --------------------------------------------------------

    value = safe_number(
        metrics.get(
            "q_operating_margin_change_yoy"
        )
    )

    score = score_margin_change(
        value
    )

    if score is not None:

        weight = 15.0

        components.append(
            (
                score,
                weight
            )
        )

        available_weight += weight

        detail[
            "operating_margin_yoy"
        ] = value


    # --------------------------------------------------------
    # Net Margin Change
    # --------------------------------------------------------

    value = safe_number(
        metrics.get(
            "q_net_margin_change_yoy"
        )
    )

    score = score_margin_change(
        value
    )

    if score is not None:

        weight = 15.0

        components.append(
            (
                score,
                weight
            )
        )

        available_weight += weight

        detail[
            "net_margin_yoy"
        ] = value


    # --------------------------------------------------------
    # Cash Conversion
    # --------------------------------------------------------

    value = safe_number(
        metrics.get(
            "q_cash_conversion"
        )
    )

    score = score_cash_conversion(
        value
    )

    if score is not None:

        weight = 10.0

        components.append(
            (
                score,
                weight
            )
        )

        available_weight += weight

        detail[
            "cash_conversion"
        ] = value


    if (
        not components
        or available_weight <= 0
    ):

        return None


    weighted_sum = sum(

        score
        * weight

        for (
            score,
            weight
        )
        in components
    )


    health_score = (
        weighted_sum
        / available_weight
    )


    coverage = (
        available_weight
        / possible_weight
    ) * 100


    return {

        "score":
            clamp(
                health_score
            ),

        "coverage":
            clamp(
                coverage
            ),

        "detail":
            detail
    }


# ============================================================
# استخراج Signal Engine 2.2.2
# ============================================================

def get_signal_values(
    metrics
):

    return {

        "improvement":
            safe_number(
                metrics.get(
                    "engine22_improvement_score"
                )
            ),

        "risk":
            safe_number(
                metrics.get(
                    "engine22_risk_score"
                )
            ),

        "net":
            safe_number(
                metrics.get(
                    "engine22_net_score"
                )
            ),

        "confidence":
            safe_number(
                metrics.get(
                    "engine22_confidence_score"
                )
            ),

        "coverage":
            safe_number(
                metrics.get(
                    "engine22_signal_coverage_score"
                )
            ),

        "history":
            safe_number(
                metrics.get(
                    "engine22_history_sufficiency_score"
                )
            ),

        "trend":
            safe_number(
                metrics.get(
                    "engine22_trend_reliability_score"
                )
            ),

        "acceleration":
            safe_number(
                metrics.get(
                    "engine22_acceleration_score"
                )
            ),

        "persistence":
            safe_number(
                metrics.get(
                    "engine22_persistence_score"
                )
            )
    }


# ============================================================
# تصنيف اتجاه Signal
# ============================================================

def classify_signal_direction(
    signal
):

    net_score = signal.get(
        "net"
    )

    confidence = signal.get(
        "confidence"
    )

    history = signal.get(
        "history"
    )

    trend = signal.get(
        "trend"
    )


    if (
        net_score is None
        or confidence is None
        or history is None
        or trend is None
    ):

        return "NO_SIGNAL"


    if (
        confidence
        < MIN_SIGNAL_CONFIDENCE

        or history
        < MIN_HISTORY_SCORE

        or trend
        < MIN_TREND_RELIABILITY
    ):

        return "INSUFFICIENT"


    if net_score >= 5:

        return "IMPROVING"


    if net_score <= -5:

        return "DETERIORATING"


    return "NEUTRAL"


# ============================================================
# تصنيف ما تحقق فعليًا
# ============================================================

def classify_realized_direction(
    delta
):

    delta = safe_number(
        delta
    )

    if delta is None:

        return "UNKNOWN"


    if (
        delta
        >= REALIZED_IMPROVEMENT_THRESHOLD
    ):

        return "IMPROVING"


    if (
        delta
        <= REALIZED_DETERIORATION_THRESHOLD
    ):

        return "DETERIORATING"


    return "NEUTRAL"


# ============================================================
# Emoji
# ============================================================

def direction_icon(direction):

    mapping = {

        "IMPROVING":
            "🟢",

        "DETERIORATING":
            "🔴",

        "NEUTRAL":
            "⚪",

        "INSUFFICIENT":
            "🟡",

        "NO_SIGNAL":
            "⚫",

        "UNKNOWN":
            "❔"
    }

    return mapping.get(
        direction,
        "❔"
    )


# ============================================================
# مقارنة Signal بالنتيجة الفعلية
# ============================================================

def compare_direction(
    predicted,
    realized
):

    if predicted in [
        "NO_SIGNAL",
        "INSUFFICIENT"
    ]:

        return "SKIPPED"


    if realized == "UNKNOWN":

        return "SKIPPED"


    if predicted == realized:

        return "HIT"


    return "MISS"


# ============================================================
# تحليل شركة واحدة
# ============================================================

def validate_stock(stock):

    stock_id = stock[
        "id"
    ]

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


    print_header(
        f"🔬 VALIDATION | "
        f"{symbol} | "
        f"{company_name}"
    )


    rows = get_financial_metrics(
        stock_id
    )


    print(
        f"📊 Metric Records: "
        f"{len(rows)}",
        flush=True
    )


    if not rows:

        print(
            "🔴 لا توجد Financial Metrics",
            flush=True
        )

        return {

            "symbol":
                symbol,

            "company_name":
                company_name,

            "tests":
                0,

            "hits":
                0,

            "misses":
                0,

            "skipped":
                0,

            "hit_rate":
                None
        }


    periods = organize_metrics(
        rows
    )


    quarter_dates = (
        get_standard_quarter_dates(
            periods
        )
    )


    print(
        f"📅 Financial Quarters: "
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


    if len(
        quarter_dates
    ) < 2:

        print(
            "🟡 لا يوجد عدد أرباع كافٍ "
            "لعمل Forward Validation.",
            flush=True
        )

        return {

            "symbol":
                symbol,

            "company_name":
                company_name,

            "tests":
                0,

            "hits":
                0,

            "misses":
                0,

            "skipped":
                0,

            "hit_rate":
                None
        }


    results = []


    # --------------------------------------------------------
    # لا نختبر آخر ربع
    # لأنه لا يوجد بعده ربع Forward
    # --------------------------------------------------------

    for index in range(
        len(
            quarter_dates
        )
        - 1
    ):

        current_period = (
            quarter_dates[
                index
            ]
        )

        next_period = (
            quarter_dates[
                index + 1
            ]
        )


        current_metrics = periods[
            current_period
        ]

        next_metrics = periods[
            next_period
        ]


        signal = get_signal_values(
            current_metrics
        )


        predicted_direction = (
            classify_signal_direction(
                signal
            )
        )


        current_health = (
            calculate_fundamental_health(
                current_metrics
            )
        )


        next_health = (
            calculate_fundamental_health(
                next_metrics
            )
        )


        realized_direction = "UNKNOWN"
        realized_delta = None


        # ----------------------------------------------------
        # لا نقارن إذا Fundamental Coverage ضعيفة
        # ----------------------------------------------------

        validation_coverage_ok = False


        if (
            current_health
            and next_health
        ):

            current_coverage = (
                current_health[
                    "coverage"
                ]
            )

            next_coverage = (
                next_health[
                    "coverage"
                ]
            )


            if (
                current_coverage
                >= MIN_FUNDAMENTAL_COVERAGE

                and next_coverage
                >= MIN_FUNDAMENTAL_COVERAGE
            ):

                validation_coverage_ok = True


                realized_delta = (

                    next_health[
                        "score"
                    ]

                    -

                    current_health[
                        "score"
                    ]
                )


                realized_direction = (
                    classify_realized_direction(
                        realized_delta
                    )
                )


        comparison = compare_direction(
            predicted_direction,
            realized_direction
        )


        print_separator()


        print(
            f"📅 Signal Period: "
            f"{current_period}",
            flush=True
        )


        print(
            f"➡️ Validation Period: "
            f"{next_period}",
            flush=True
        )


        print(
            f"🧠 Signal Net: "
            f"{fmt(signal['net'])}",
            flush=True
        )


        print(
            f"🎯 Signal Confidence: "
            f"{fmt(signal['confidence'])}",
            flush=True
        )


        print(
            f"🗂️ History: "
            f"{fmt(signal['history'])}",
            flush=True
        )


        print(
            f"🧬 Trend Reliability: "
            f"{fmt(signal['trend'])}",
            flush=True
        )


        print(
            f"{direction_icon(predicted_direction)} "
            f"Predicted: "
            f"{predicted_direction}",
            flush=True
        )


        if current_health:

            print(
                f"📊 Current Fundamental Health: "
                f"{fmt(current_health['score'])} | "
                f"Coverage="
                f"{fmt(current_health['coverage'])}%",
                flush=True
            )

        else:

            print(
                "📊 Current Fundamental Health: N/A",
                flush=True
            )


        if next_health:

            print(
                f"📈 Next Fundamental Health: "
                f"{fmt(next_health['score'])} | "
                f"Coverage="
                f"{fmt(next_health['coverage'])}%",
                flush=True
            )

        else:

            print(
                "📈 Next Fundamental Health: N/A",
                flush=True
            )


        print(
            f"🔄 Realized Change: "
            f"{fmt(realized_delta)}",
            flush=True
        )


        print(
            f"{direction_icon(realized_direction)} "
            f"Realized: "
            f"{realized_direction}",
            flush=True
        )


        if not validation_coverage_ok:

            print(
                "🟡 Validation Coverage غير كافية "
                "لهذه المقارنة.",
                flush=True
            )


        if comparison == "HIT":

            print(
                "✅ RESULT: HIT",
                flush=True
            )

        elif comparison == "MISS":

            print(
                "❌ RESULT: MISS",
                flush=True
            )

        else:

            print(
                "⏭️ RESULT: SKIPPED",
                flush=True
            )


        results.append(
            {

                "signal_period":
                    current_period,

                "validation_period":
                    next_period,

                "predicted":
                    predicted_direction,

                "realized":
                    realized_direction,

                "realized_delta":
                    realized_delta,

                "comparison":
                    comparison
            }
        )


    hits = sum(

        1

        for item in results

        if item[
            "comparison"
        ] == "HIT"
    )


    misses = sum(

        1

        for item in results

        if item[
            "comparison"
        ] == "MISS"
    )


    skipped = sum(

        1

        for item in results

        if item[
            "comparison"
        ] == "SKIPPED"
    )


    valid_tests = (
        hits
        + misses
    )


    hit_rate = (

        (
            hits
            / valid_tests
        )
        * 100

        if valid_tests > 0

        else None
    )


    print_header(
        f"📊 COMPANY VALIDATION SUMMARY | "
        f"{symbol}"
    )


    print(
        f"🧪 Valid Tests: "
        f"{valid_tests}",
        flush=True
    )


    print(
        f"✅ Hits: "
        f"{hits}",
        flush=True
    )


    print(
        f"❌ Misses: "
        f"{misses}",
        flush=True
    )


    print(
        f"⏭️ Skipped: "
        f"{skipped}",
        flush=True
    )


    print(
        f"🎯 Hit Rate: "
        f"{fmt(hit_rate)}%",
        flush=True
    )


    return {

        "symbol":
            symbol,

        "company_name":
            company_name,

        "tests":
            valid_tests,

        "hits":
            hits,

        "misses":
            misses,

        "skipped":
            skipped,

        "hit_rate":
            hit_rate,

        "results":
            results
    }


# ============================================================
# System-wide summary
# ============================================================

def print_master_summary(
    company_results
):

    print_header(
        f"🏆 SIGNAL VALIDATION AUDIT "
        f"{AUDIT_VERSION} MASTER SUMMARY"
    )


    total_tests = sum(

        result[
            "tests"
        ]

        for result in company_results
    )


    total_hits = sum(

        result[
            "hits"
        ]

        for result in company_results
    )


    total_misses = sum(

        result[
            "misses"
        ]

        for result in company_results
    )


    total_skipped = sum(

        result[
            "skipped"
        ]

        for result in company_results
    )


    overall_hit_rate = (

        (
            total_hits
            / total_tests
        )
        * 100

        if total_tests > 0

        else None
    )


    for index, result in enumerate(
        company_results,
        start=1
    ):

        print(
            f"{index:02d}. "
            f"{result['symbol']} | "
            f"{result['company_name']} | "
            f"Tests={result['tests']} | "
            f"Hits={result['hits']} | "
            f"Misses={result['misses']} | "
            f"Skipped={result['skipped']} | "
            f"HitRate={fmt(result['hit_rate'])}%",
            flush=True
        )


    print_separator()


    print(
        f"🏢 Companies Tested: "
        f"{len(company_results)}",
        flush=True
    )


    print(
        f"🧪 Total Valid Tests: "
        f"{total_tests}",
        flush=True
    )


    print(
        f"✅ Total Hits: "
        f"{total_hits}",
        flush=True
    )


    print(
        f"❌ Total Misses: "
        f"{total_misses}",
        flush=True
    )


    print(
        f"⏭️ Total Skipped: "
        f"{total_skipped}",
        flush=True
    )


    print(
        f"🎯 Overall Hit Rate: "
        f"{fmt(overall_hit_rate)}%",
        flush=True
    )


    # --------------------------------------------------------
    # Distribution of predicted directions
    # --------------------------------------------------------

    predicted_counter = Counter()

    realized_counter = Counter()


    for company in company_results:

        for result in company.get(
            "results",
            []
        ):

            predicted_counter[
                result[
                    "predicted"
                ]
            ] += 1

            realized_counter[
                result[
                    "realized"
                ]
            ] += 1


    print(
        "\n🧠 Predicted Direction Distribution:",
        flush=True
    )


    for (
        direction,
        count
    ) in sorted(
        predicted_counter.items()
    ):

        print(
            f"- {direction}: "
            f"{count}",
            flush=True
        )


    print(
        "\n📈 Realized Direction Distribution:",
        flush=True
    )


    for (
        direction,
        count
    ) in sorted(
        realized_counter.items()
    ):

        print(
            f"- {direction}: "
            f"{count}",
            flush=True
        )


    print_separator()


    # --------------------------------------------------------
    # لا نصدر حكم نهائي قوي إذا العينة صغيرة
    # --------------------------------------------------------

    if total_tests < 8:

        final_state = (
            "INSUFFICIENT_VALIDATION_SAMPLE"
        )

        final_text = (
            "العينة التاريخية ما زالت صغيرة "
            "ولا تكفي للحكم النهائي على المحرك."
        )

    elif (
        overall_hit_rate is not None
        and overall_hit_rate >= 70
    ):

        final_state = (
            "STRONG_PRELIMINARY_VALIDATION"
        )

        final_text = (
            "النتيجة الأولية قوية، "
            "لكن يجب توسيع الاختبار "
            "إلى جميع الشركات قبل اعتمادها."
        )

    elif (
        overall_hit_rate is not None
        and overall_hit_rate >= 55
    ):

        final_state = (
            "ACCEPTABLE_PRELIMINARY_VALIDATION"
        )

        final_text = (
            "النتيجة الأولية مقبولة "
            "وتحتاج توسيع العينة "
            "ودراسة حالات الخطأ."
        )

    else:

        final_state = (
            "REVIEW_REQUIRED"
        )

        final_text = (
            "هناك احتمال أن بعض الأوزان "
            "أو الحدود تحتاج مراجعة."
        )


    print(
        f"🧭 VALIDATION RESULT: "
        f"{final_state}",
        flush=True
    )


    print(
        f"📝 {final_text}",
        flush=True
    )


    print(
        "\n🔒 READ ONLY AUDIT | "
        "لم يتم تعديل أو حذف أو حفظ أي بيانات.",
        flush=True
    )


    print(
        "=" * 96,
        flush=True
    )


# ============================================================
# التشغيل
# ============================================================

def run_validation_audit():

    print_header(
        f"🔬 SIGNAL VALIDATION AUDIT v"
        f"{AUDIT_VERSION}"
    )


    print(
        "🔒 Mode: READ ONLY",
        flush=True
    )


    print(
        f"🧠 Engine Prefix: "
        f"{ENGINE_PREFIX}",
        flush=True
    )


    stocks = (
        select_validation_stocks()
    )


    print(
        f"🏢 Validation Companies: "
        f"{len(stocks)}",
        flush=True
    )


    if not stocks:

        print(
            "🔴 لم يتم العثور على شركات "
            "Standard صالحة للتدقيق.",
            flush=True
        )

        return


    print(
        "📋 Companies:",
        flush=True
    )


    for stock in stocks:

        print(
            f"- {stock['symbol']} | "
            f"{stock.get('company_name')}",
            flush=True
        )


    company_results = []


    for index, stock in enumerate(
        stocks,
        start=1
    ):

        print(
            "\n"
            f"🔍 Validation "
            f"{index}/{len(stocks)} | "
            f"{stock['symbol']}",
            flush=True
        )


        try:

            result = validate_stock(
                stock
            )


        except Exception as error:

            print(
                f"🔴 Validation Error | "
                f"{stock.get('symbol')} | "
                f"{type(error).__name__}: "
                f"{error}",
                flush=True
            )


            result = {

                "symbol":
                    stock.get(
                        "symbol"
                    ),

                "company_name":
                    stock.get(
                        "company_name"
                    ),

                "tests":
                    0,

                "hits":
                    0,

                "misses":
                    0,

                "skipped":
                    0,

                "hit_rate":
                    None,

                "results":
                    []
            }


        company_results.append(
            result
        )


    print_master_summary(
        company_results
    )


if __name__ == "__main__":

    run_validation_audit()
