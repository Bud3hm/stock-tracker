import os
from datetime import datetime, timezone
from supabase import create_client


# ============================================================
# REIT METRICS ENGINE
# ============================================================

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_SECRET_KEY = os.environ.get("SUPABASE_SECRET_KEY")

supabase = create_client(
    SUPABASE_URL,
    SUPABASE_SECRET_KEY
)


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


def pct(value):

    if value is None:
        return None

    return value * 100


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


def difference(current, previous):

    current = safe_number(current)
    previous = safe_number(previous)

    if (
        current is None
        or previous is None
    ):
        return None

    return current - previous


def value(data, metric):

    if not data:
        return None

    return safe_number(
        data.get(metric)
    )


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


# ============================================================
# جلب صناديق REIT
# ============================================================

def get_reit_stocks():

    response = (
        supabase
        .table("stocks")
        .select(
            "id,"
            "symbol,"
            "company_name,"
            "analysis_model,"
            "data_status"
        )
        .eq("analysis_model", "reit")
        .execute()
    )

    return response.data or []


# ============================================================
# جلب البيانات المالية
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
# ترتيب البيانات
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

            annual.setdefault(
                period_end,
                {}
            )

            annual[
                period_end
            ][metric] = metric_value

        elif period_type == "3M":

            quarterly.setdefault(
                period_end,
                {}
            )

            quarterly[
                period_end
            ][metric] = metric_value

    return annual, quarterly


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

    for metric_name, metric_value in metrics.items():

        metric_value = safe_number(
            metric_value
        )

        if metric_value is None:
            continue

        records.append(
            {
                "stock_id": stock_id,
                "calculated_at": calculated_at,
                "metric_name": metric_name,
                "metric_value": metric_value,
                "period_end": period_end
            }
        )

    if not records:
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

    return len(records)


# ============================================================
# مؤشرات REIT السنوية
# ============================================================

def calculate_reit_annual_metrics(
    current,
    previous
):

    revenue = value(
        current,
        "annualTotalRevenue"
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

    liabilities = value(
        current,
        "annualTotalLiabilitiesNetMinorityInterest"
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

    operating_cash_flow = value(
        current,
        "annualOperatingCashFlow"
    )

    free_cash_flow = value(
        current,
        "annualFreeCashFlow"
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

    previous_assets = (
        value(
            previous,
            "annualTotalAssets"
        )
        if previous
        else None
    )

    previous_equity = (
        value(
            previous,
            "annualStockholdersEquity"
        )
        if previous
        else None
    )

    previous_debt = (
        value(
            previous,
            "annualTotalDebt"
        )
        if previous
        else None
    )

    previous_ocf = (
        value(
            previous,
            "annualOperatingCashFlow"
        )
        if previous
        else None
    )

    return {

        "reit_annual_revenue_growth_yoy":
            growth_rate(
                revenue,
                previous_revenue
            ),

        "reit_annual_net_income_growth_yoy":
            growth_rate(
                net_income,
                previous_net_income
            ),

        "reit_annual_assets_growth_yoy":
            growth_rate(
                assets,
                previous_assets
            ),

        "reit_annual_equity_growth_yoy":
            growth_rate(
                equity,
                previous_equity
            ),

        "reit_annual_debt_growth_yoy":
            growth_rate(
                total_debt,
                previous_debt
            ),

        "reit_annual_ocf_growth_yoy":
            growth_rate(
                operating_cash_flow,
                previous_ocf
            ),

        "reit_annual_operating_margin":
            pct(
                safe_divide(
                    operating_income,
                    revenue
                )
            ),

        "reit_annual_net_margin":
            pct(
                safe_divide(
                    net_income,
                    revenue
                )
            ),

        "reit_annual_roa":
            pct(
                safe_divide(
                    net_income,
                    assets
                )
            ),

        "reit_annual_roe":
            pct(
                safe_divide(
                    net_income,
                    equity
                )
            ),

        "reit_annual_debt_to_equity":
            safe_divide(
                total_debt,
                equity
            ),

        "reit_annual_debt_to_assets":
            pct(
                safe_divide(
                    total_debt,
                    assets
                )
            ),

        "reit_annual_liabilities_to_assets":
            pct(
                safe_divide(
                    liabilities,
                    assets
                )
            ),

        "reit_annual_equity_to_assets":
            pct(
                safe_divide(
                    equity,
                    assets
                )
            ),

        "reit_annual_net_debt":
            (
                total_debt - cash
                if (
                    total_debt is not None
                    and cash is not None
                )
                else None
            ),

        "reit_annual_cash_conversion":
            safe_divide(
                operating_cash_flow,
                net_income
            ),

        "reit_annual_fcf_margin":
            pct(
                safe_divide(
                    free_cash_flow,
                    revenue
                )
            ),

        "reit_annual_revenue":
            revenue,

        "reit_annual_operating_income":
            operating_income,

        "reit_annual_net_income":
            net_income,

        "reit_annual_total_assets":
            assets,

        "reit_annual_total_liabilities":
            liabilities,

        "reit_annual_equity":
            equity,

        "reit_annual_total_debt":
            total_debt,

        "reit_annual_cash":
            cash,

        "reit_annual_operating_cash_flow":
            operating_cash_flow,

        "reit_annual_free_cash_flow":
            free_cash_flow
    }


# ============================================================
# مؤشرات REIT الربعية
# ============================================================

def calculate_reit_quarter_metrics(
    current,
    previous_quarter,
    same_quarter_last_year
):

    revenue = value(
        current,
        "quarterlyTotalRevenue"
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

    liabilities = value(
        current,
        "quarterlyTotalLiabilitiesNetMinorityInterest"
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

    operating_cash_flow = value(
        current,
        "quarterlyOperatingCashFlow"
    )

    free_cash_flow = value(
        current,
        "quarterlyFreeCashFlow"
    )

    # ========================================================
    # السابق
    # ========================================================

    prev_revenue = value(
        previous_quarter,
        "quarterlyTotalRevenue"
    )

    prev_operating_income = value(
        previous_quarter,
        "quarterlyOperatingIncome"
    )

    prev_net_income = value(
        previous_quarter,
        "quarterlyNetIncome"
    )

    prev_assets = value(
        previous_quarter,
        "quarterlyTotalAssets"
    )

    prev_equity = value(
        previous_quarter,
        "quarterlyStockholdersEquity"
    )

    prev_debt = value(
        previous_quarter,
        "quarterlyTotalDebt"
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
    # نفس الربع العام السابق
    # ========================================================

    yoy_revenue = value(
        same_quarter_last_year,
        "quarterlyTotalRevenue"
    )

    yoy_operating_income = value(
        same_quarter_last_year,
        "quarterlyOperatingIncome"
    )

    yoy_net_income = value(
        same_quarter_last_year,
        "quarterlyNetIncome"
    )

    yoy_assets = value(
        same_quarter_last_year,
        "quarterlyTotalAssets"
    )

    yoy_equity = value(
        same_quarter_last_year,
        "quarterlyStockholdersEquity"
    )

    yoy_debt = value(
        same_quarter_last_year,
        "quarterlyTotalDebt"
    )

    yoy_ocf = value(
        same_quarter_last_year,
        "quarterlyOperatingCashFlow"
    )

    yoy_fcf = value(
        same_quarter_last_year,
        "quarterlyFreeCashFlow"
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

        "reit_q_revenue_growth_qoq":
            growth_rate(
                revenue,
                prev_revenue
            ),

        "reit_q_operating_income_growth_qoq":
            growth_rate(
                operating_income,
                prev_operating_income
            ),

        "reit_q_net_income_growth_qoq":
            growth_rate(
                net_income,
                prev_net_income
            ),

        "reit_q_assets_growth_qoq":
            growth_rate(
                assets,
                prev_assets
            ),

        "reit_q_equity_growth_qoq":
            growth_rate(
                equity,
                prev_equity
            ),

        "reit_q_debt_growth_qoq":
            growth_rate(
                total_debt,
                prev_debt
            ),

        "reit_q_ocf_growth_qoq":
            growth_rate(
                operating_cash_flow,
                prev_ocf
            ),

        "reit_q_fcf_growth_qoq":
            growth_rate(
                free_cash_flow,
                prev_fcf
            ),

        # ====================================================
        # YoY
        # ====================================================

        "reit_q_revenue_growth_yoy":
            growth_rate(
                revenue,
                yoy_revenue
            ),

        "reit_q_operating_income_growth_yoy":
            growth_rate(
                operating_income,
                yoy_operating_income
            ),

        "reit_q_net_income_growth_yoy":
            growth_rate(
                net_income,
                yoy_net_income
            ),

        "reit_q_assets_growth_yoy":
            growth_rate(
                assets,
                yoy_assets
            ),

        "reit_q_equity_growth_yoy":
            growth_rate(
                equity,
                yoy_equity
            ),

        "reit_q_debt_growth_yoy":
            growth_rate(
                total_debt,
                yoy_debt
            ),

        "reit_q_ocf_growth_yoy":
            growth_rate(
                operating_cash_flow,
                yoy_ocf
            ),

        "reit_q_fcf_growth_yoy":
            growth_rate(
                free_cash_flow,
                yoy_fcf
            ),

        # ====================================================
        # الهوامش
        # ====================================================

        "reit_q_operating_margin":
            operating_margin,

        "reit_q_net_margin":
            net_margin,

        "reit_q_operating_margin_change_qoq":
            difference(
                operating_margin,
                prev_operating_margin
            ),

        "reit_q_net_margin_change_qoq":
            difference(
                net_margin,
                prev_net_margin
            ),

        "reit_q_operating_margin_change_yoy":
            difference(
                operating_margin,
                yoy_operating_margin
            ),

        "reit_q_net_margin_change_yoy":
            difference(
                net_margin,
                yoy_net_margin
            ),

        # ====================================================
        # الهيكل المالي
        # ====================================================

        "reit_q_debt_to_equity":
            safe_divide(
                total_debt,
                equity
            ),

        "reit_q_debt_to_assets":
            pct(
                safe_divide(
                    total_debt,
                    assets
                )
            ),

        "reit_q_liabilities_to_assets":
            pct(
                safe_divide(
                    liabilities,
                    assets
                )
            ),

        "reit_q_equity_to_assets":
            pct(
                safe_divide(
                    equity,
                    assets
                )
            ),

        "reit_q_net_debt":
            (
                total_debt - cash
                if (
                    total_debt is not None
                    and cash is not None
                )
                else None
            ),

        # ====================================================
        # العوائد والتدفقات
        # ====================================================

        "reit_q_roa_annualized":
            pct(
                safe_divide(
                    (
                        net_income * 4
                        if net_income is not None
                        else None
                    ),
                    assets
                )
            ),

        "reit_q_roe_annualized":
            pct(
                safe_divide(
                    (
                        net_income * 4
                        if net_income is not None
                        else None
                    ),
                    equity
                )
            ),

        "reit_q_cash_conversion":
            safe_divide(
                operating_cash_flow,
                net_income
            ),

        "reit_q_fcf_margin":
            pct(
                safe_divide(
                    free_cash_flow,
                    revenue
                )
            ),

        # ====================================================
        # خام
        # ====================================================

        "reit_q_revenue":
            revenue,

        "reit_q_operating_income":
            operating_income,

        "reit_q_net_income":
            net_income,

        "reit_q_total_assets":
            assets,

        "reit_q_total_liabilities":
            liabilities,

        "reit_q_equity":
            equity,

        "reit_q_total_debt":
            total_debt,

        "reit_q_cash":
            cash,

        "reit_q_operating_cash_flow":
            operating_cash_flow,

        "reit_q_free_cash_flow":
            free_cash_flow
    }


# ============================================================
# TTM
# ============================================================

def calculate_reit_ttm_metrics(
    quarter_dates,
    quarterly,
    index
):

    if index < 3:
        return {}

    dates = quarter_dates[
        index - 3:index + 1
    ]

    quarters = [
        quarterly[date]
        for date in dates
    ]

    revenue = sum_if_complete(
        [
            value(
                q,
                "quarterlyTotalRevenue"
            )
            for q in quarters
        ]
    )

    operating_income = sum_if_complete(
        [
            value(
                q,
                "quarterlyOperatingIncome"
            )
            for q in quarters
        ]
    )

    net_income = sum_if_complete(
        [
            value(
                q,
                "quarterlyNetIncome"
            )
            for q in quarters
        ]
    )

    ocf = sum_if_complete(
        [
            value(
                q,
                "quarterlyOperatingCashFlow"
            )
            for q in quarters
        ]
    )

    fcf = sum_if_complete(
        [
            value(
                q,
                "quarterlyFreeCashFlow"
            )
            for q in quarters
        ]
    )

    latest = quarters[-1]

    assets = value(
        latest,
        "quarterlyTotalAssets"
    )

    equity = value(
        latest,
        "quarterlyStockholdersEquity"
    )

    debt = value(
        latest,
        "quarterlyTotalDebt"
    )

    return {

        "reit_ttm_revenue":
            revenue,

        "reit_ttm_operating_income":
            operating_income,

        "reit_ttm_net_income":
            net_income,

        "reit_ttm_operating_cash_flow":
            ocf,

        "reit_ttm_free_cash_flow":
            fcf,

        "reit_ttm_operating_margin":
            pct(
                safe_divide(
                    operating_income,
                    revenue
                )
            ),

        "reit_ttm_net_margin":
            pct(
                safe_divide(
                    net_income,
                    revenue
                )
            ),

        "reit_ttm_roa":
            pct(
                safe_divide(
                    net_income,
                    assets
                )
            ),

        "reit_ttm_roe":
            pct(
                safe_divide(
                    net_income,
                    equity
                )
            ),

        "reit_ttm_debt_to_equity":
            safe_divide(
                debt,
                equity
            ),

        "reit_ttm_cash_conversion":
            safe_divide(
                ocf,
                net_income
            ),

        "reit_ttm_fcf_margin":
            pct(
                safe_divide(
                    fcf,
                    revenue
                )
            )
    }


# ============================================================
# ثقة البيانات
# ============================================================

def calculate_reit_data_confidence(
    current
):

    required = [

        "quarterlyTotalRevenue",
        "quarterlyOperatingIncome",
        "quarterlyNetIncome",
        "quarterlyTotalAssets",
        "quarterlyStockholdersEquity",
        "quarterlyTotalDebt"
    ]

    available = 0

    for metric in required:

        if value(
            current,
            metric
        ) is not None:

            available += 1

    return (
        available
        / len(required)
    ) * 100


# ============================================================
# REIT Signal Engine v1
# ============================================================

def calculate_reit_signal_scores(
    metrics
):

    improvement = 0
    risk = 0
    used = 0

    def evaluate_positive(metric_name):

        nonlocal improvement
        nonlocal risk
        nonlocal used

        metric_value = metrics.get(
            metric_name
        )

        if metric_value is None:
            return

        used += 1

        if metric_value > 0:
            improvement += 1

        elif metric_value < 0:
            risk += 1

    evaluate_positive(
        "reit_q_revenue_growth_yoy"
    )

    evaluate_positive(
        "reit_q_operating_income_growth_yoy"
    )

    evaluate_positive(
        "reit_q_net_income_growth_yoy"
    )

    evaluate_positive(
        "reit_q_equity_growth_yoy"
    )

    evaluate_positive(
        "reit_q_operating_margin_change_yoy"
    )

    debt_growth = metrics.get(
        "reit_q_debt_growth_yoy"
    )

    if debt_growth is not None:

        used += 1

        if debt_growth <= 0:
            improvement += 1

        elif debt_growth > 15:
            risk += 1

    debt_to_assets = metrics.get(
        "reit_q_debt_to_assets"
    )

    if debt_to_assets is not None:

        used += 1

        if debt_to_assets <= 35:
            improvement += 1

        elif debt_to_assets >= 50:
            risk += 1

    cash_conversion = metrics.get(
        "reit_ttm_cash_conversion"
    )

    if cash_conversion is not None:

        used += 1

        if cash_conversion >= 1:
            improvement += 1

        elif cash_conversion < 0.6:
            risk += 1

    if used == 0:

        return {
            "reit_signal_improvement_score":
                None,

            "reit_signal_risk_score":
                None,

            "reit_signal_net_score":
                None
        }

    improvement_score = (
        improvement / used
    ) * 100

    risk_score = (
        risk / used
    ) * 100

    return {

        "reit_signal_improvement_score":
            improvement_score,

        "reit_signal_risk_score":
            risk_score,

        "reit_signal_net_score":
            improvement_score
            - risk_score
    }


# ============================================================
# تشغيل REIT واحد
# ============================================================

def calculate_reit_metrics(stock):

    stock_id = stock["id"]

    symbol = stock["symbol"]

    company_name = (
        stock.get("company_name")
        or symbol
    )

    print(
        "\n"
        + "=" * 70,
        flush=True
    )

    print(
        f"🏢 REIT: "
        f"{symbol} | {company_name}",
        flush=True
    )

    print(
        "=" * 70,
        flush=True
    )

    rows = get_financial_data(
        stock_id
    )

    if not rows:

        print(
            "⚠️ No financial data",
            flush=True
        )

        return {
            "status": "no_data",
            "metrics": 0
        }

    annual, quarterly = (
        organize_financial_data(
            rows
        )
    )

    total_saved = 0

    # ========================================================
    # سنوي
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
            calculate_reit_annual_metrics(
                current,
                previous
            )
        )

        total_saved += save_metrics(
            stock_id,
            period_end,
            metrics
        )

    # ========================================================
    # ربعي
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

        metrics = (
            calculate_reit_quarter_metrics(
                current,
                previous_quarter,
                same_quarter_last_year
            )
        )

        ttm_metrics = (
            calculate_reit_ttm_metrics(
                quarter_dates,
                quarterly,
                index
            )
        )

        metrics.update(
            ttm_metrics
        )

        metrics[
            "reit_data_confidence_score"
        ] = calculate_reit_data_confidence(
            current
        )

        signals = (
            calculate_reit_signal_scores(
                metrics
            )
        )

        metrics.update(
            signals
        )

        total_saved += save_metrics(
            stock_id,
            period_end,
            metrics
        )

    print(
        f"✅ {symbol} | "
        f"{total_saved} REIT metrics saved",
        flush=True
    )

    return {
        "status": "success",
        "metrics": total_saved
    }


# ============================================================
# تشغيل جميع صناديق REIT
# ============================================================

def run_reit_metrics():

    print(
        "\n"
        + "#" * 70,
        flush=True
    )

    print(
        "🏢 REIT METRICS ENGINE",
        flush=True
    )

    print(
        "#" * 70,
        flush=True
    )

    stocks = get_reit_stocks()

    print(
        f"🏢 Total REITs: "
        f"{len(stocks)}",
        flush=True
    )

    success = 0
    no_data = 0
    errors = 0
    total_metrics = 0

    details = []

    for stock in stocks:

        try:

            result = (
                calculate_reit_metrics(
                    stock
                )
            )

            status = result[
                "status"
            ]

            count = result[
                "metrics"
            ]

            total_metrics += count

            if status == "success":
                success += 1

            elif status == "no_data":
                no_data += 1

            details.append(
                (
                    stock["symbol"],
                    status,
                    count
                )
            )

        except Exception as e:

            errors += 1

            details.append(
                (
                    stock["symbol"],
                    "error",
                    0
                )
            )

            print(
                f"🔴 {stock['symbol']} | "
                f"{type(e).__name__}: {e}",
                flush=True
            )

    print(
        "\n"
        + "=" * 70,
        flush=True
    )

    print(
        "📋 FINAL REIT METRICS SUMMARY",
        flush=True
    )

    print(
        "=" * 70,
        flush=True
    )

    print(
        f"🏢 Total REITs: "
        f"{len(stocks)}",
        flush=True
    )

    print(
        f"🟢 Success: "
        f"{success}",
        flush=True
    )

    print(
        f"🟡 No Data: "
        f"{no_data}",
        flush=True
    )

    print(
        f"🔴 Errors: "
        f"{errors}",
        flush=True
    )

    print(
        f"💾 Total REIT Metrics Saved: "
        f"{total_metrics}",
        flush=True
    )

    print(
        "\n📋 REITs:",
        flush=True
    )

    for symbol, status, count in details:

        print(
            f"{symbol} | "
            f"{status} | "
            f"{count} metrics",
            flush=True
        )

    print(
        "=" * 70,
        flush=True
    )


# ============================================================
# START
# ============================================================

if __name__ == "__main__":

    run_reit_metrics()
