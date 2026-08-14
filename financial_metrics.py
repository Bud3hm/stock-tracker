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
# جلب الشركات المفعلة
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
# جلب البيانات المالية الخام
# ============================================================

def get_financial_data(stock_id):

    response = (
        supabase
        .table("financial_statements")
        .select("*")
        .eq("stock_id", stock_id)
        .execute()
    )

    return response.data or []


# ============================================================
# أدوات الحساب الأساسية
# ============================================================

def safe_number(value):

    if value is None:
        return None

    try:
        return float(value)

    except (TypeError, ValueError):
        return None


def safe_divide(a, b):

    a = safe_number(a)
    b = safe_number(b)

    if (
        a is None
        or b is None
        or b == 0
    ):
        return None

    return a / b


def growth_rate(current, previous):

    current = safe_number(current)
    previous = safe_number(previous)

    if (
        current is None
        or previous is None
        or previous == 0
    ):
        return None

    return (
        (current - previous)
        / abs(previous)
    ) * 100


def pct(value):

    if value is None:
        return None

    return value * 100


def sum_if_complete(values):

    cleaned = [
        safe_number(value)
        for value in values
    ]

    if (
        len(cleaned) != 4
        or any(
            value is None
            for value in cleaned
        )
    ):
        return None

    return sum(cleaned)


def difference(current, previous):

    current = safe_number(current)
    previous = safe_number(previous)

    if (
        current is None
        or previous is None
    ):
        return None

    return current - previous


# ============================================================
# الوصول للمؤشرات داخل الفترة
# ============================================================

def value(data, metric):

    if not data:
        return None

    return safe_number(
        data.get(metric)
    )


# ============================================================
# حفظ المؤشرات
# ============================================================

def save_metrics(
    stock_id,
    period_end,
    metrics
):

    calculated_at = datetime.now(
        timezone.utc
    ).isoformat()

    records = []

    for name, metric_value in metrics.items():

        metric_value = safe_number(
            metric_value
        )

        if metric_value is None:
            continue

        records.append(
            {
                "stock_id": stock_id,
                "calculated_at": calculated_at,
                "metric_name": name,
                "metric_value": metric_value,
                "period_end": period_end
            }
        )

    if not records:

        print(
            f"⚠️ لا توجد مؤشرات قابلة للحفظ "
            f"للفترة {period_end}",
            flush=True
        )

        return 0

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
        f"💾 تم حفظ {len(records)} مؤشر "
        f"للفترة {period_end}",
        flush=True
    )

    return len(records)


# ============================================================
# ترتيب البيانات السنوية والربعية
# ============================================================

def organize_financial_data(rows):

    annual = {}
    quarterly = {}

    for row in rows:

        period_type = row.get(
            "period_type"
        )

        period_end = str(
            row.get("period_end")
        )

        metric = row.get(
            "metric"
        )

        metric_value = safe_number(
            row.get("value")
        )

        if (
            not period_end
            or not metric
            or metric_value is None
        ):
            continue

        if period_type == "12M":

            if period_end not in annual:
                annual[period_end] = {}

            annual[
                period_end
            ][metric] = metric_value

        elif period_type == "3M":

            if period_end not in quarterly:
                quarterly[period_end] = {}

            quarterly[
                period_end
            ][metric] = metric_value

    return annual, quarterly


# ============================================================
# مؤشرات سنوية
# ============================================================

def calculate_annual_metrics(
    current,
    previous
):

    revenue = value(
        current,
        "annualTotalRevenue"
    )

    gross_profit = value(
        current,
        "annualGrossProfit"
    )

    operating_income = value(
        current,
        "annualOperatingIncome"
    )

    net_income = value(
        current,
        "annualNetIncome"
    )

    assets = value(
        current,
        "annualTotalAssets"
    )

    equity = value(
        current,
        "annualStockholdersEquity"
    )

    total_debt = value(
        current,
        "annualTotalDebt"
    )

    cash = value(
        current,
        "annualCashCashEquivalentsAndShortTermInvestments"
    )

    current_assets = value(
        current,
        "annualCurrentAssets"
    )

    current_liabilities = value(
        current,
        "annualCurrentLiabilities"
    )

    operating_cash_flow = value(
        current,
        "annualOperatingCashFlow"
    )

    free_cash_flow = value(
        current,
        "annualFreeCashFlow"
    )

    capex = value(
        current,
        "annualCapitalExpenditure"
    )

    previous_revenue = (
        value(
            previous,
            "annualTotalRevenue"
        )
        if previous
        else None
    )

    previous_net_income = (
        value(
            previous,
            "annualNetIncome"
        )
        if previous
        else None
    )

    previous_fcf = (
        value(
            previous,
            "annualFreeCashFlow"
        )
        if previous
        else None
    )

    return {

        "annual_revenue_growth_yoy":
            growth_rate(
                revenue,
                previous_revenue
            ),

        "annual_net_income_growth_yoy":
            growth_rate(
                net_income,
                previous_net_income
            ),

        "annual_fcf_growth_yoy":
            growth_rate(
                free_cash_flow,
                previous_fcf
            ),

        "annual_gross_margin":
            pct(
                safe_divide(
                    gross_profit,
                    revenue
                )
            ),

        "annual_operating_margin":
            pct(
                safe_divide(
                    operating_income,
                    revenue
                )
            ),

        "annual_net_margin":
            pct(
                safe_divide(
                    net_income,
                    revenue
                )
            ),

        "annual_roa":
            pct(
                safe_divide(
                    net_income,
                    assets
                )
            ),

        "annual_roe":
            pct(
                safe_divide(
                    net_income,
                    equity
                )
            ),

        "annual_cash_conversion":
            safe_divide(
                operating_cash_flow,
                net_income
            ),

        "annual_fcf_margin":
            pct(
                safe_divide(
                    free_cash_flow,
                    revenue
                )
            ),

        "annual_debt_to_equity":
            safe_divide(
                total_debt,
                equity
            ),

        "annual_net_debt":
            (
                total_debt - cash
                if (
                    total_debt is not None
                    and cash is not None
                )
                else None
            ),

        "annual_current_ratio":
            safe_divide(
                current_assets,
                current_liabilities
            ),

        "annual_free_cash_flow":
            free_cash_flow,

        "annual_operating_cash_flow":
            operating_cash_flow,

        "annual_capex":
            capex
    }


# ============================================================
# حساب مؤشرات الربع
# ============================================================

def calculate_quarter_metrics(
    current,
    previous_quarter,
    same_quarter_last_year
):

    revenue = value(
        current,
        "quarterlyTotalRevenue"
    )

    gross_profit = value(
        current,
        "quarterlyGrossProfit"
    )

    operating_income = value(
        current,
        "quarterlyOperatingIncome"
    )

    net_income = value(
        current,
        "quarterlyNetIncome"
    )

    assets = value(
        current,
        "quarterlyTotalAssets"
    )

    equity = value(
        current,
        "quarterlyStockholdersEquity"
    )

    total_debt = value(
        current,
        "quarterlyTotalDebt"
    )

    cash = value(
        current,
        "quarterlyCashCashEquivalentsAndShortTermInvestments"
    )

    current_assets = value(
        current,
        "quarterlyCurrentAssets"
    )

    current_liabilities = value(
        current,
        "quarterlyCurrentLiabilities"
    )

    inventory = value(
        current,
        "quarterlyInventory"
    )

    receivables = value(
        current,
        "quarterlyAccountsReceivable"
    )

    operating_cash_flow = value(
        current,
        "quarterlyOperatingCashFlow"
    )

    free_cash_flow = value(
        current,
        "quarterlyFreeCashFlow"
    )

    capex = value(
        current,
        "quarterlyCapitalExpenditure"
    )

    # ========================================================
    # الربع السابق
    # ========================================================

    prev_revenue = value(
        previous_quarter,
        "quarterlyTotalRevenue"
    )

    prev_net_income = value(
        previous_quarter,
        "quarterlyNetIncome"
    )

    prev_gross_profit = value(
        previous_quarter,
        "quarterlyGrossProfit"
    )

    prev_operating_income = value(
        previous_quarter,
        "quarterlyOperatingIncome"
    )

    prev_debt = value(
        previous_quarter,
        "quarterlyTotalDebt"
    )

    prev_cash = value(
        previous_quarter,
        "quarterlyCashCashEquivalentsAndShortTermInvestments"
    )

    prev_inventory = value(
        previous_quarter,
        "quarterlyInventory"
    )

    prev_receivables = value(
        previous_quarter,
        "quarterlyAccountsReceivable"
    )

    prev_ocf = value(
        previous_quarter,
        "quarterlyOperatingCashFlow"
    )

    prev_fcf = value(
        previous_quarter,
        "quarterlyFreeCashFlow"
    )

    # ========================================================
    # نفس الربع من العام السابق
    # ========================================================

    yoy_revenue = value(
        same_quarter_last_year,
        "quarterlyTotalRevenue"
    )

    yoy_net_income = value(
        same_quarter_last_year,
        "quarterlyNetIncome"
    )

    yoy_gross_profit = value(
        same_quarter_last_year,
        "quarterlyGrossProfit"
    )

    yoy_operating_income = value(
        same_quarter_last_year,
        "quarterlyOperatingIncome"
    )

    yoy_ocf = value(
        same_quarter_last_year,
        "quarterlyOperatingCashFlow"
    )

    yoy_fcf = value(
        same_quarter_last_year,
        "quarterlyFreeCashFlow"
    )

    # ========================================================
    # الهوامش
    # ========================================================

    gross_margin = pct(
        safe_divide(
            gross_profit,
            revenue
        )
    )

    operating_margin = pct(
        safe_divide(
            operating_income,
            revenue
        )
    )

    net_margin = pct(
        safe_divide(
            net_income,
            revenue
        )
    )

    prev_gross_margin = pct(
        safe_divide(
            prev_gross_profit,
            prev_revenue
        )
    )

    prev_operating_margin = pct(
        safe_divide(
            prev_operating_income,
            prev_revenue
        )
    )

    prev_net_margin = pct(
        safe_divide(
            prev_net_income,
            prev_revenue
        )
    )

    yoy_gross_margin = pct(
        safe_divide(
            yoy_gross_profit,
            yoy_revenue
        )
    )

    yoy_operating_margin = pct(
        safe_divide(
            yoy_operating_income,
            yoy_revenue
        )
    )

    yoy_net_margin = pct(
        safe_divide(
            yoy_net_income,
            yoy_revenue
        )
    )

    return {

        # ====================================================
        # QoQ
        # ====================================================

        "q_revenue_growth_qoq":
            growth_rate(
                revenue,
                prev_revenue
            ),

        "q_net_income_growth_qoq":
            growth_rate(
                net_income,
                prev_net_income
            ),

        "q_ocf_growth_qoq":
            growth_rate(
                operating_cash_flow,
                prev_ocf
            ),

        "q_fcf_growth_qoq":
            growth_rate(
                free_cash_flow,
                prev_fcf
            ),

        # ====================================================
        # YoY
        # ====================================================

        "q_revenue_growth_yoy":
            growth_rate(
                revenue,
                yoy_revenue
            ),

        "q_net_income_growth_yoy":
            growth_rate(
                net_income,
                yoy_net_income
            ),

        "q_ocf_growth_yoy":
            growth_rate(
                operating_cash_flow,
                yoy_ocf
            ),

        "q_fcf_growth_yoy":
            growth_rate(
                free_cash_flow,
                yoy_fcf
            ),

        # ====================================================
        # الهوامش
        # ====================================================

        "q_gross_margin":
            gross_margin,

        "q_operating_margin":
            operating_margin,

        "q_net_margin":
            net_margin,

        "q_gross_margin_change_qoq":
            difference(
                gross_margin,
                prev_gross_margin
            ),

        "q_operating_margin_change_qoq":
            difference(
                operating_margin,
                prev_operating_margin
            ),

        "q_net_margin_change_qoq":
            difference(
                net_margin,
                prev_net_margin
            ),

        "q_gross_margin_change_yoy":
            difference(
                gross_margin,
                yoy_gross_margin
            ),

        "q_operating_margin_change_yoy":
            difference(
                operating_margin,
                yoy_operating_margin
            ),

        "q_net_margin_change_yoy":
            difference(
                net_margin,
                yoy_net_margin
            ),

        # ====================================================
        # العائد والكفاءة
        # ====================================================

        "q_roa":
            pct(
                safe_divide(
                    net_income,
                    assets
                )
            ),

        "q_roe":
            pct(
                safe_divide(
                    net_income,
                    equity
                )
            ),

        "q_cash_conversion":
            safe_divide(
                operating_cash_flow,
                net_income
            ),

        "q_fcf_margin":
            pct(
                safe_divide(
                    free_cash_flow,
                    revenue
                )
            ),

        # ====================================================
        # الدين والسيولة
        # ====================================================

        "q_debt_to_equity":
            safe_divide(
                total_debt,
                equity
            ),

        "q_debt_growth_qoq":
            growth_rate(
                total_debt,
                prev_debt
            ),

        "q_net_debt":
            (
                total_debt - cash
                if (
                    total_debt is not None
                    and cash is not None
                )
                else None
            ),

        "q_cash_growth_qoq":
            growth_rate(
                cash,
                prev_cash
            ),

        "q_current_ratio":
            safe_divide(
                current_assets,
                current_liabilities
            ),

        # ====================================================
        # المخزون والذمم
        # ====================================================

        "q_inventory_growth_qoq":
            growth_rate(
                inventory,
                prev_inventory
            ),

        "q_receivables_growth_qoq":
            growth_rate(
                receivables,
                prev_receivables
            ),

        "q_inventory_to_revenue":
            pct(
                safe_divide(
                    inventory,
                    revenue
                )
            ),

        "q_receivables_to_revenue":
            pct(
                safe_divide(
                    receivables,
                    revenue
                )
            ),

        # ====================================================
        # الأرقام الخام
        # ====================================================

        "q_revenue":
            revenue,

        "q_net_income":
            net_income,

        "q_operating_cash_flow":
            operating_cash_flow,

        "q_free_cash_flow":
            free_cash_flow,

        "q_capex":
            capex
    }


# ============================================================
# حساب TTM
# ============================================================

def calculate_ttm_metrics(
    quarter_dates,
    quarterly,
    index
):

    if index < 3:
        return {}

    last_four_dates = quarter_dates[
        index - 3:index + 1
    ]

    last_four = [
        quarterly[date]
        for date in last_four_dates
    ]

    ttm_revenue = sum_if_complete(
        [
            value(
                q,
                "quarterlyTotalRevenue"
            )
            for q in last_four
        ]
    )

    ttm_gross_profit = sum_if_complete(
        [
            value(
                q,
                "quarterlyGrossProfit"
            )
            for q in last_four
        ]
    )

    ttm_operating_income = sum_if_complete(
        [
            value(
                q,
                "quarterlyOperatingIncome"
            )
            for q in last_four
        ]
    )

    ttm_net_income = sum_if_complete(
        [
            value(
                q,
                "quarterlyNetIncome"
            )
            for q in last_four
        ]
    )

    ttm_ocf = sum_if_complete(
        [
            value(
                q,
                "quarterlyOperatingCashFlow"
            )
            for q in last_four
        ]
    )

    ttm_fcf = sum_if_complete(
        [
            value(
                q,
                "quarterlyFreeCashFlow"
            )
            for q in last_four
        ]
    )

    ttm_capex = sum_if_complete(
        [
            value(
                q,
                "quarterlyCapitalExpenditure"
            )
            for q in last_four
        ]
    )

    latest = last_four[-1]

    latest_assets = value(
        latest,
        "quarterlyTotalAssets"
    )

    latest_equity = value(
        latest,
        "quarterlyStockholdersEquity"
    )

    return {

        "ttm_revenue":
            ttm_revenue,

        "ttm_gross_profit":
            ttm_gross_profit,

        "ttm_operating_income":
            ttm_operating_income,

        "ttm_net_income":
            ttm_net_income,

        "ttm_operating_cash_flow":
            ttm_ocf,

        "ttm_free_cash_flow":
            ttm_fcf,

        "ttm_capex":
            ttm_capex,

        "ttm_gross_margin":
            pct(
                safe_divide(
                    ttm_gross_profit,
                    ttm_revenue
                )
            ),

        "ttm_operating_margin":
            pct(
                safe_divide(
                    ttm_operating_income,
                    ttm_revenue
                )
            ),

        "ttm_net_margin":
            pct(
                safe_divide(
                    ttm_net_income,
                    ttm_revenue
                )
            ),

        "ttm_cash_conversion":
            safe_divide(
                ttm_ocf,
                ttm_net_income
            ),

        "ttm_fcf_margin":
            pct(
                safe_divide(
                    ttm_fcf,
                    ttm_revenue
                )
            ),

        "ttm_roa":
            pct(
                safe_divide(
                    ttm_net_income,
                    latest_assets
                )
            ),

        "ttm_roe":
            pct(
                safe_divide(
                    ttm_net_income,
                    latest_equity
                )
            )
    }


# ============================================================
# درجة اكتمال البيانات
# ============================================================

def calculate_data_confidence(
    current_quarter
):

    required = [

        "quarterlyTotalRevenue",
        "quarterlyGrossProfit",
        "quarterlyOperatingIncome",
        "quarterlyNetIncome",
        "quarterlyTotalAssets",
        "quarterlyStockholdersEquity",
        "quarterlyTotalDebt",
        "quarterlyCurrentAssets",
        "quarterlyCurrentLiabilities",
        "quarterlyOperatingCashFlow",
        "quarterlyFreeCashFlow"
    ]

    available = 0

    for metric in required:

        if value(
            current_quarter,
            metric
        ) is not None:

            available += 1

    return (
        available
        / len(required)
    ) * 100


# ============================================================
# إشارات Legacy
#
# نبقيها الآن للتوافق مع النظام السابق.
# Signal Engine 2.2 هو المحرك الرئيسي الفعلي.
# ============================================================

def calculate_signal_scores(metrics):

    improvement = 0
    risk = 0
    used_signals = 0

    def evaluate(
        metric_name,
        positive_threshold=0,
        negative_threshold=0,
        inverse=False
    ):

        nonlocal improvement
        nonlocal risk
        nonlocal used_signals

        metric_value = metrics.get(
            metric_name
        )

        if metric_value is None:
            return

        used_signals += 1

        if not inverse:

            if metric_value > positive_threshold:
                improvement += 1

            elif metric_value < negative_threshold:
                risk += 1

        else:

            if metric_value < positive_threshold:
                improvement += 1

            elif metric_value > negative_threshold:
                risk += 1

    evaluate(
        "q_revenue_growth_yoy"
    )

    evaluate(
        "q_net_income_growth_yoy"
    )

    evaluate(
        "q_gross_margin_change_yoy"
    )

    evaluate(
        "q_operating_margin_change_yoy"
    )

    evaluate(
        "q_net_margin_change_yoy"
    )

    evaluate(
        "q_ocf_growth_yoy"
    )

    evaluate(
        "q_fcf_growth_yoy"
    )

    evaluate(
        "q_debt_growth_qoq",
        inverse=True
    )

    cash_conversion = metrics.get(
        "q_cash_conversion"
    )

    if cash_conversion is not None:

        used_signals += 1

        if cash_conversion >= 1:
            improvement += 1

        elif cash_conversion < 0.7:
            risk += 1

    current_ratio = metrics.get(
        "q_current_ratio"
    )

    if current_ratio is not None:

        used_signals += 1

        if current_ratio >= 1:
            improvement += 1

        elif current_ratio < 0.8:
            risk += 1

    inventory_growth = metrics.get(
        "q_inventory_growth_qoq"
    )

    revenue_growth = metrics.get(
        "q_revenue_growth_qoq"
    )

    if (
        inventory_growth is not None
        and revenue_growth is not None
    ):

        used_signals += 1

        if (
            inventory_growth
            > revenue_growth + 10
        ):
            risk += 1

        elif (
            inventory_growth
            <= revenue_growth
        ):
            improvement += 1

    receivables_growth = metrics.get(
        "q_receivables_growth_qoq"
    )

    if (
        receivables_growth is not None
        and revenue_growth is not None
    ):

        used_signals += 1

        if (
            receivables_growth
            > revenue_growth + 10
        ):
            risk += 1

        elif (
            receivables_growth
            <= revenue_growth
        ):
            improvement += 1

    if used_signals == 0:

        return {
            "signal_improvement_score": None,
            "signal_risk_score": None,
            "signal_net_score": None
        }

    improvement_score = (
        improvement
        / used_signals
    ) * 100

    risk_score = (
        risk
        / used_signals
    ) * 100

    return {

        "signal_improvement_score":
            improvement_score,

        "signal_risk_score":
            risk_score,

        "signal_net_score":
            (
                improvement_score
                - risk_score
            )
    }


# ============================================================
# حساب شركة Standard واحدة
# ============================================================

def calculate_standard_metrics(stock):

    stock_id = stock["id"]

    symbol = stock["symbol"]

    company_name = (
        stock.get("company_name")
        or symbol
    )

    print(
        "\n\n"
        "############################################################",
        flush=True
    )

    print(
        f"🧮 STANDARD METRICS | "
        f"{company_name} | {symbol}",
        flush=True
    )

    print(
        "############################################################",
        flush=True
    )

    rows = get_financial_data(
        stock_id
    )

    if not rows:

        print(
            f"⚠️ لا توجد بيانات مالية لـ "
            f"{symbol}",
            flush=True
        )

        return {
            "status": "no_data",
            "saved_metrics": 0
        }

    annual, quarterly = (
        organize_financial_data(
            rows
        )
    )

    total_saved = 0

    # ========================================================
    # السنوي
    # ========================================================

    annual_dates = sorted(
        annual.keys()
    )

    for index, period_end in enumerate(
        annual_dates
    ):

        current = annual[
            period_end
        ]

        previous = (
            annual[
                annual_dates[
                    index - 1
                ]
            ]
            if index > 0
            else None
        )

        metrics = (
            calculate_annual_metrics(
                current,
                previous
            )
        )

        print(
            f"\n📅 ANNUAL: "
            f"{period_end}",
            flush=True
        )

        total_saved += save_metrics(
            stock_id,
            period_end,
            metrics
        )

    # ========================================================
    # الربعي
    # ========================================================

    quarter_dates = sorted(
        quarterly.keys()
    )

    for index, period_end in enumerate(
        quarter_dates
    ):

        current = quarterly[
            period_end
        ]

        previous_quarter = (
            quarterly[
                quarter_dates[
                    index - 1
                ]
            ]
            if index > 0
            else None
        )

        current_date = datetime.strptime(
            period_end,
            "%Y-%m-%d"
        )

        prior_year_date = (
            f"{current_date.year - 1}-"
            f"{current_date.month:02d}-"
            f"{current_date.day:02d}"
        )

        same_quarter_last_year = (
            quarterly.get(
                prior_year_date
            )
        )

        quarter_metrics = (
            calculate_quarter_metrics(
                current,
                previous_quarter,
                same_quarter_last_year
            )
        )

        ttm_metrics = (
            calculate_ttm_metrics(
                quarter_dates,
                quarterly,
                index
            )
        )

        all_metrics = {}

        all_metrics.update(
            quarter_metrics
        )

        all_metrics.update(
            ttm_metrics
        )

        all_metrics[
            "data_confidence_score"
        ] = calculate_data_confidence(
            current
        )

        legacy_signals = (
            calculate_signal_scores(
                all_metrics
            )
        )

        all_metrics.update(
            legacy_signals
        )

        print(
            f"\n📊 QUARTER: "
            f"{period_end}",
            flush=True
        )

        print(
            f"🎯 Data Confidence: "
            f"{all_metrics.get('data_confidence_score')}",
            flush=True
        )

        total_saved += save_metrics(
            stock_id,
            period_end,
            all_metrics
        )

    print(
        f"\n🟢 انتهت مؤشرات {symbol} "
        f"| Saved Metrics: {total_saved}",
        flush=True
    )

    return {
        "status": "success",
        "saved_metrics": total_saved
    }


# ============================================================
# Router حسب نموذج التحليل
# ============================================================

def calculate_metrics_for_stock(stock):

    model = (
        stock.get("analysis_model")
        or "standard"
    )

    symbol = stock["symbol"]

    company_name = (
        stock.get("company_name")
        or symbol
    )

    if model == "standard":

        return calculate_standard_metrics(
            stock
        )

    if model == "bank":

        print(
            "\n"
            f"🏦 {company_name} | {symbol}\n"
            "⏭️ تم تجاوز الحساب Standard.\n"
            "السبب: البنك يحتاج Bank Metrics Engine متخصص.",
            flush=True
        )

        return {
            "status": "special_model_pending",
            "saved_metrics": 0
        }

    if model == "insurance":

        print(
            "\n"
            f"🛡️ {company_name} | {symbol}\n"
            "⏭️ تم تجاوز الحساب Standard.\n"
            "السبب: شركة التأمين تحتاج Insurance Metrics Engine متخصص.",
            flush=True
        )

        return {
            "status": "special_model_pending",
            "saved_metrics": 0
        }

    if model == "reit":

        print(
            "\n"
            f"🏢 {company_name} | {symbol}\n"
            "⏭️ تم تجاوز الحساب Standard.\n"
            "السبب: REIT يحتاج REIT Metrics Engine متخصص.",
            flush=True
        )

        return {
            "status": "special_model_pending",
            "saved_metrics": 0
        }

    print(
        f"🔴 نموذج تحليل غير معروف: "
        f"{model} | {symbol}",
        flush=True
    )

    return {
        "status": "unknown_model",
        "saved_metrics": 0
    }


# ============================================================
# تشغيل جميع الشركات
# ============================================================

def run_metrics_pipeline():

    stocks = get_active_stocks()

    print(
        "\n\n"
        "============================================================",
        flush=True
    )

    print(
        "🧮 MULTI-COMPANY FINANCIAL METRICS PIPELINE",
        flush=True
    )

    print(
        "============================================================",
        flush=True
    )

    print(
        f"🏢 Active Stocks: "
        f"{len(stocks)}",
        flush=True
    )

    if not stocks:

        print(
            "🔴 لا توجد شركات مفعلة",
            flush=True
        )

        return

    results = []

    for index, stock in enumerate(
        stocks,
        start=1
    ):

        print(
            "\n"
            "------------------------------------------------------------",
            flush=True
        )

        print(
            f"🚦 Company "
            f"{index}/{len(stocks)} "
            f"| {stock['symbol']}",
            flush=True
        )

        try:

            result = (
                calculate_metrics_for_stock(
                    stock
                )
            )

        except Exception as e:

            print(
                f"🔴 فشل حساب مؤشرات "
                f"{stock['symbol']} | "
                f"{type(e).__name__}: {e}",
                flush=True
            )

            result = {
                "status": "error",
                "saved_metrics": 0
            }

        results.append({
            "symbol":
                stock["symbol"],

            "company_name":
                stock.get(
                    "company_name"
                ),

            "analysis_model":
                stock.get(
                    "analysis_model"
                )
                or "standard",

            "status":
                result[
                    "status"
                ],

            "saved_metrics":
                result[
                    "saved_metrics"
                ]
        })

    # ========================================================
    # الملخص
    # ========================================================

    success_count = sum(
        1
        for item in results
        if item["status"] == "success"
    )

    special_count = sum(
        1
        for item in results
        if item["status"] == "special_model_pending"
    )

    no_data_count = sum(
        1
        for item in results
        if item["status"] == "no_data"
    )

    error_count = sum(
        1
        for item in results
        if item["status"] in (
            "error",
            "unknown_model"
        )
    )

    total_saved = sum(
        item["saved_metrics"]
        for item in results
    )

    print(
        "\n\n"
        "============================================================",
        flush=True
    )

    print(
        "📊 FINAL METRICS SUMMARY",
        flush=True
    )

    print(
        "============================================================",
        flush=True
    )

    print(
        f"🟢 Standard Success: "
        f"{success_count}",
        flush=True
    )

    print(
        f"🧠 Specialized Pending: "
        f"{special_count}",
        flush=True
    )

    print(
        f"🟠 No Data: "
        f"{no_data_count}",
        flush=True
    )

    print(
        f"🔴 Errors: "
        f"{error_count}",
        flush=True
    )

    print(
        f"💾 Total Metrics Saved: "
        f"{total_saved}",
        flush=True
    )

    print(
        "\n📋 Companies:",
        flush=True
    )

    for item in results:

        print(
            f"{item['symbol']} | "
            f"{item['analysis_model']} | "
            f"{item['status']} | "
            f"{item['saved_metrics']} metrics",
            flush=True
        )

    print(
        "============================================================",
        flush=True
    )


# ============================================================
# توافق مع الاستدعاء القديم
# ============================================================

def calculate_metrics(stock_id):

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
        .eq("id", stock_id)
        .limit(1)
        .execute()
    )

    if not response.data:

        print(
            f"🔴 stock_id={stock_id} "
            f"غير موجود",
            flush=True
        )

        return

    calculate_metrics_for_stock(
        response.data[0]
    )


# ============================================================
# التشغيل
# ============================================================

if __name__ == "__main__":

    run_metrics_pipeline()
