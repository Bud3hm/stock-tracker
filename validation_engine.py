import os
from supabase import create_client


# ============================================================
# VALIDATION ENGINE v1
# الهدف:
# التحقق من منطق Scoring Engine قبل تطوير Turning Point Engine
# ============================================================

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_SECRET_KEY = os.environ.get("SUPABASE_SECRET_KEY")

supabase = create_client(
    SUPABASE_URL,
    SUPABASE_SECRET_KEY
)


# ============================================================
# عينة التحقق
# يمكن تغييرها لاحقًا من GitHub Secrets / ENV
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

        for symbol in env_value.split(",")

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

    except (TypeError, ValueError):

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


def print_separator():

    print(
        "-" * 78,
        flush=True
    )


def print_header(title):

    print(
        "\n"
        + "=" * 78,
        flush=True
    )

    print(
        title,
        flush=True
    )

    print(
        "=" * 78,
        flush=True
    )


# ============================================================
# جلب بيانات الشركات
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

    # نحافظ على ترتيب القائمة الأصلية
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
# جلب المؤشرات
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

    return response.data or []


# ============================================================
# ترتيب المؤشرات حسب الفترة
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
# إيجاد أحدث فترة صالحة لكل نموذج
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
# قراءة درجات Scoring Engine
# ============================================================

def get_score_block(metrics):

    return {

        "growth":
            metrics.get(
                "score_growth_score"
            ),

        "quality":
            metrics.get(
                "score_quality_score"
            ),

        "cash":
            metrics.get(
                "score_cash_score"
            ),

        "balance":
            metrics.get(
                "score_balance_score"
            ),

        "confidence":
            metrics.get(
                "score_confidence_score"
            ),

        "opportunity":
            metrics.get(
                "score_opportunity_score"
            ),

        "risk":
            metrics.get(
                "score_risk_score"
            ),

        "turning":
            metrics.get(
                "score_turning_point_score"
            )
    }


# ============================================================
# تحديد حالة عامة
# ============================================================

def classify_score(
    opportunity,
    risk,
    turning,
    confidence
):

    opportunity = safe_number(
        opportunity
    )

    risk = safe_number(
        risk
    )

    turning = safe_number(
        turning
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
        and turning is not None
        and turning >= 70
    ):

        return (
            "STRONG",
            "جودة مرتفعة مع فرصة وتحول قويين"
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
# STANDARD
# ============================================================

def validate_standard(
    latest,
    previous
):

    reasons_positive = []
    reasons_risk = []
    contradictions = []

    revenue_yoy = latest.get(
        "q_revenue_growth_yoy"
    )

    profit_yoy = latest.get(
        "q_net_income_growth_yoy"
    )

    ocf_yoy = latest.get(
        "q_ocf_growth_yoy"
    )

    fcf_yoy = latest.get(
        "q_fcf_growth_yoy"
    )

    gross_margin_yoy = latest.get(
        "q_gross_margin_change_yoy"
    )

    operating_margin_yoy = latest.get(
        "q_operating_margin_change_yoy"
    )

    net_margin_yoy = latest.get(
        "q_net_margin_change_yoy"
    )

    cash_conversion = latest.get(
        "q_cash_conversion"
    )

    debt_growth = latest.get(
        "q_debt_growth_qoq"
    )

    current_ratio = latest.get(
        "q_current_ratio"
    )

    receivables_growth = latest.get(
        "q_receivables_growth_qoq"
    )

    inventory_growth = latest.get(
        "q_inventory_growth_qoq"
    )

    revenue_qoq = latest.get(
        "q_revenue_growth_qoq"
    )

    # --------------------------------------------------------
    # تحسن
    # --------------------------------------------------------

    if (
        revenue_yoy is not None
        and revenue_yoy >= 10
    ):

        reasons_positive.append(
            f"نمو الإيرادات YoY قوي "
            f"({signed_fmt(revenue_yoy)}%)"
        )

    if (
        profit_yoy is not None
        and profit_yoy >= 10
    ):

        reasons_positive.append(
            f"نمو صافي الربح YoY قوي "
            f"({signed_fmt(profit_yoy)}%)"
        )

    if (
        fcf_yoy is not None
        and fcf_yoy >= 10
    ):

        reasons_positive.append(
            f"التدفق النقدي الحر يتحسن "
            f"({signed_fmt(fcf_yoy)}%)"
        )

    if (
        cash_conversion is not None
        and cash_conversion >= 1
    ):

        reasons_positive.append(
            f"تحويل الأرباح إلى نقد جيد "
            f"({fmt(cash_conversion)})"
        )

    if (
        operating_margin_yoy is not None
        and operating_margin_yoy > 1
    ):

        reasons_positive.append(
            f"الهامش التشغيلي يتحسن "
            f"({signed_fmt(operating_margin_yoy)} نقطة)"
        )

    # --------------------------------------------------------
    # مخاطر
    # --------------------------------------------------------

    if (
        gross_margin_yoy is not None
        and gross_margin_yoy <= -2
    ):

        reasons_risk.append(
            f"تآكل الهامش الإجمالي "
            f"({signed_fmt(gross_margin_yoy)} نقطة)"
        )

    if (
        operating_margin_yoy is not None
        and operating_margin_yoy <= -2
    ):

        reasons_risk.append(
            f"تآكل الهامش التشغيلي "
            f"({signed_fmt(operating_margin_yoy)} نقطة)"
        )

    if (
        net_margin_yoy is not None
        and net_margin_yoy <= -2
    ):

        reasons_risk.append(
            f"تآكل هامش صافي الربح "
            f"({signed_fmt(net_margin_yoy)} نقطة)"
        )

    if (
        cash_conversion is not None
        and cash_conversion < 0.70
    ):

        reasons_risk.append(
            f"تحويل الأرباح إلى نقد ضعيف "
            f"({fmt(cash_conversion)})"
        )

    if (
        debt_growth is not None
        and debt_growth > 15
    ):

        reasons_risk.append(
            f"الدين يرتفع سريعًا QoQ "
            f"({signed_fmt(debt_growth)}%)"
        )

    if (
        current_ratio is not None
        and current_ratio < 0.80
    ):

        reasons_risk.append(
            f"السيولة الجارية ضعيفة "
            f"({fmt(current_ratio)})"
        )

    if (
        receivables_growth is not None
        and revenue_qoq is not None
        and receivables_growth
        > revenue_qoq + 10
    ):

        reasons_risk.append(
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

        reasons_risk.append(
            f"المخزون ينمو أسرع من المبيعات "
            f"بفارق "
            f"{fmt(inventory_growth - revenue_qoq)} نقطة"
        )

    # --------------------------------------------------------
    # تناقضات
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
        reasons_positive,
        reasons_risk,
        contradictions
    )


# ============================================================
# BANK
# ============================================================

def validate_bank(
    latest,
    previous
):

    positives = []
    risks = []
    contradictions = []

    revenue = latest.get(
        "bank_q_revenue_growth_yoy"
    )

    profit = latest.get(
        "bank_q_net_income_growth_yoy"
    )

    assets = latest.get(
        "bank_q_assets_growth_yoy"
    )

    equity = latest.get(
        "bank_q_equity_growth_yoy"
    )

    roe = latest.get(
        "bank_ttm_roe"
    )

    roa = latest.get(
        "bank_ttm_roa"
    )

    equity_assets = latest.get(
        "bank_q_equity_to_assets"
    )

    margin_change = latest.get(
        "bank_q_profit_margin_change_yoy"
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
# INSURANCE
# ============================================================

def validate_insurance(
    latest,
    previous
):

    positives = []
    risks = []
    contradictions = []

    revenue = latest.get(
        "insurance_q_revenue_growth_yoy"
    )

    profit = latest.get(
        "insurance_q_net_income_growth_yoy"
    )

    roe = latest.get(
        "insurance_ttm_roe"
    )

    roa = latest.get(
        "insurance_ttm_roa"
    )

    cash_conversion = latest.get(
        "insurance_ttm_cash_conversion"
    )

    equity_growth = latest.get(
        "insurance_q_equity_growth_yoy"
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


# ============================================================
# REIT
# ============================================================

def validate_reit(
    latest,
    previous
):

    positives = []
    risks = []
    contradictions = []

    revenue = latest.get(
        "reit_q_revenue_growth_yoy"
    )

    operating_income = latest.get(
        "reit_q_operating_income_growth_yoy"
    )

    net_income = latest.get(
        "reit_q_net_income_growth_yoy"
    )

    debt_assets = latest.get(
        "reit_q_debt_to_assets"
    )

    debt_growth = latest.get(
        "reit_q_debt_growth_yoy"
    )

    cash_conversion = latest.get(
        "reit_ttm_cash_conversion"
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
# مقارنة Score بالفترة السابقة
# ============================================================

def score_change(
    latest_scores,
    previous_metrics
):

    if not previous_metrics:

        return {}

    previous_scores = get_score_block(
        previous_metrics
    )

    changes = {}

    for key in [

        "growth",
        "quality",
        "cash",
        "balance",
        "opportunity",
        "risk",
        "turning"

    ]:

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
                current - previous
            )

    return changes


# ============================================================
# تحليل شركة واحدة
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

    state, state_description = classify_score(

        scores.get(
            "opportunity"
        ),

        scores.get(
            "risk"
        ),

        scores.get(
            "turning"
        ),

        scores.get(
            "confidence"
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

    print_separator()

    print(
        "🎯 SCORING COMPONENTS",
        flush=True
    )

    print(
        f"Growth:      "
        f"{fmt(scores.get('growth'))}",
        flush=True
    )

    print(
        f"Quality:     "
        f"{fmt(scores.get('quality'))}",
        flush=True
    )

    print(
        f"Cash:        "
        f"{fmt(scores.get('cash'))}",
        flush=True
    )

    print(
        f"Balance:     "
        f"{fmt(scores.get('balance'))}",
        flush=True
    )

    print(
        f"Opportunity: "
        f"{fmt(scores.get('opportunity'))}",
        flush=True
    )

    print(
        f"Risk:        "
        f"{fmt(scores.get('risk'))}",
        flush=True
    )

    print(
        f"Turning:     "
        f"{fmt(scores.get('turning'))}",
        flush=True
    )

    print(
        f"Confidence:  "
        f"{fmt(scores.get('confidence'))}",
        flush=True
    )

    # ========================================================
    # أسباب كل نموذج
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
    # تغير الدرجة
    # ========================================================

    changes = score_change(
        scores,
        previous
    )

    print_separator()

    print(
        "🚀 SCORE MOMENTUM",
        flush=True
    )

    if not changes:

        print(
            "لا توجد مقارنة سابقة",
            flush=True
        )

    else:

        print(
            f"Opportunity Δ: "
            f"{signed_fmt(changes.get('opportunity'))}",
            flush=True
        )

        print(
            f"Risk Δ:        "
            f"{signed_fmt(changes.get('risk'))}",
            flush=True
        )

        print(
            f"Turning Δ:     "
            f"{signed_fmt(changes.get('turning'))}",
            flush=True
        )

        print(
            f"Growth Δ:      "
            f"{signed_fmt(changes.get('growth'))}",
            flush=True
        )

        print(
            f"Quality Δ:     "
            f"{signed_fmt(changes.get('quality'))}",
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

        "turning":
            safe_number(
                scores.get(
                    "turning"
                )
            ),

        "confidence":
            safe_number(
                scores.get(
                    "confidence"
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
            )
    }


# ============================================================
# ملخص نهائي
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
        "📋 VALIDATION SUMMARY"
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
            f"Opportunity={fmt(result['opportunity'])} | "
            f"Risk={fmt(result['risk'])} | "
            f"Turning={fmt(result['turning'])} | "
            f"+Signals={result['positive_count']} | "
            f"-Signals={result['risk_count']} | "
            f"Contradictions="
            f"{result['contradiction_count']}",

            flush=True
        )

    print(
        "\n"
        "⚠️ ملاحظة: Confidence في النسخة الحالية "
        "يعبر أساسًا عن اكتمال البيانات المستخدمة، "
        "وليس ضمانًا لصحة المصدر أو دقة التنبؤ.",
        flush=True
    )

    print(
        "=" * 78,
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
        "🧪 VALIDATION ENGINE v1"
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
