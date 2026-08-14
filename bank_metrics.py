import os
from datetime import datetime, timezone
from supabase import create_client


# ============================================================
# BANK METRICS ENGINE
# نموذج المؤشرات المالية المتخصص للبنوك
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

    if a is None or b is None or b == 0:
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

    if current is None or previous is None:
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
        safe_number(v)
        for v in values
    ]

    if (
        len(cleaned) != 4
        or any(v is None for v in cleaned)
    ):
        return None

    return sum(cleaned)


# ============================================================
# جلب الشركات البنكية
# ============================================================

def get_bank_stocks():

    response = (
        supabase
        .table("stocks")
        .select(
            "id,symbol,company_name,"
            "analysis_model,data_status"
        )
        .eq("analysis_model", "bank")
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

        period_type = row.get("period_type")
        period_end = str(row.get("period_end"))
        metric = row.get("metric")

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

            annual[period_end][
                metric
            ] = metric_value

        elif period_type == "3M":

            quarterly.setdefault(
                period_end,
                {}
            )

            quarterly[period_end][
                metric
            ] = metric_value

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
# المؤشرات السنوية للبنوك
# ============================================================

def calculate_bank_annual_metrics(
    current,
    previous
):

    revenue = value(
        current,
        "annualTotalRevenue"
    )

    net_income = value(
        current,
        "annualNetIncome"
    )

    pretax_income = value(
        current,
        "annualPretaxIncome"
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

    cash = value(
        current,
        "annualCashCashEquivalentsAndShortTermInvestments"
    )

    basic_eps = value(
        current,
        "annualBasicEPS"
    )

    diluted_eps = value(
        current,
        "annualDilutedEPS"
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

    previous_eps = (
        value(
            previous,
            "annualDilutedEPS"
        )
        if previous
        else None
    )

    average_assets = None

    if (
        assets is not None
        and previous_assets is not None
    ):
        average_assets = (
            assets + previous_assets
        ) / 2

    elif assets is not None:
        average_assets = assets

    average_equity = None

    if (
        equity is not None
        and previous_equity is not None
    ):
        average_equity = (
            equity + previous_equity
        ) / 2

    elif equity is not None:
        average_equity = equity

    metrics = {

        # نمو الأعمال
        "bank_annual_revenue_growth_yoy":
            growth_rate(
                revenue,
                previous_revenue
            ),

        "bank_annual_net_income_growth_yoy":
            growth_rate(
                net_income,
                previous_net_income
            ),

        "bank_annual_eps_growth_yoy":
            growth_rate(
                diluted_eps,
                previous_eps
            ),

        "bank_annual_assets_growth_yoy":
            growth_rate(
                assets,
                previous_assets
            ),

        "bank_annual_equity_growth_yoy":
            growth_rate(
                equity,
                previous_equity
            ),

        # الربحية
        "bank_annual_profit_margin":
            pct(
                safe_divide(
                    net_income,
                    revenue
                )
            ),

        "bank_annual_pretax_margin":
            pct(
                safe_divide(
                    pretax_income,
                    revenue
                )
            ),

        # ROA للبنك
        "bank_annual_roa":
            pct(
                safe_divide(
                    net_income,
                    average_assets
                )
            ),

        # ROE للبنك
        "bank_annual_roe":
            pct(
                safe_divide(
                    net_income,
                    average_equity
                )
            ),

        # هيكل رأس المال
        "bank_annual_equity_to_assets":
            pct(
                safe_divide(
                    equity,
                    assets
                )
            ),

        "bank_annual_liabilities_to_assets":
            pct(
                safe_divide(
                    liabilities,
                    assets
                )
            ),

        # أرقام أساسية
        "bank_annual_revenue":
            revenue,

        "bank_annual_net_income":
            net_income,

        "bank_annual_total_assets":
            assets,

        "bank_annual_total_liabilities":
            liabilities,

        "bank_annual_equity":
            equity,

        "bank_annual_cash":
            cash,

        "bank_annual_basic_eps":
            basic_eps,

        "bank_annual_diluted_eps":
            diluted_eps
    }

    return metrics


# ============================================================
# المؤشرات الربعية للبنوك
# ============================================================

def calculate_bank_quarter_metrics(
    current,
    previous_quarter,
    same_quarter_last_year
):

    revenue = value(
        current,
        "quarterlyTotalRevenue"
    )

    net_income = value(
        current,
        "quarterlyNetIncome"
    )

    pretax_income = value(
        current,
        "quarterlyPretaxIncome"
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

    cash = value(
        current,
        "quarterlyCashCashEquivalentsAndShortTermInvestments"
    )

    basic_eps = value(
        current,
        "quarterlyBasicEPS"
    )

    diluted_eps = value(
        current,
        "quarterlyDilutedEPS"
    )

    # الربع السابق
    prev_revenue = value(
        previous_quarter,
        "quarterlyTotalRevenue"
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

    prev_cash = value(
        previous_quarter,
        "quarterlyCashCashEquivalentsAndShortTermInvestments"
    )

    # نفس الربع العام السابق
    yoy_revenue = value(
        same_quarter_last_year,
        "quarterlyTotalRevenue"
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

    yoy_eps = value(
        same_quarter_last_year,
        "quarterlyDilutedEPS"
    )

    profit_margin = pct(
        safe_divide(
            net_income,
            revenue
        )
    )

    prev_profit_margin = pct(
        safe_divide(
            prev_net_income,
            prev_revenue
        )
    )

    yoy_profit_margin = pct(
        safe_divide(
            yoy_net_income,
            yoy_revenue
        )
    )

    metrics = {

        # QoQ
        "bank_q_revenue_growth_qoq":
            growth_rate(
                revenue,
                prev_revenue
            ),

        "bank_q_net_income_growth_qoq":
            growth_rate(
                net_income,
                prev_net_income
            ),

        "bank_q_assets_growth_qoq":
            growth_rate(
                assets,
                prev_assets
            ),

        "bank_q_equity_growth_qoq":
            growth_rate(
                equity,
                prev_equity
            ),

        "bank_q_cash_growth_qoq":
            growth_rate(
                cash,
                prev_cash
            ),

        # YoY
        "bank_q_revenue_growth_yoy":
            growth_rate(
                revenue,
                yoy_revenue
            ),

        "bank_q_net_income_growth_yoy":
            growth_rate(
                net_income,
                yoy_net_income
            ),

        "bank_q_assets_growth_yoy":
            growth_rate(
                assets,
                yoy_assets
            ),

        "bank_q_equity_growth_yoy":
            growth_rate(
                equity,
                yoy_equity
            ),

        "bank_q_eps_growth_yoy":
            growth_rate(
                diluted_eps,
                yoy_eps
            ),

        # الربحية
        "bank_q_profit_margin":
            profit_margin,

        "bank_q_profit_margin_change_qoq":
            difference(
                profit_margin,
                prev_profit_margin
            ),

        "bank_q_profit_margin_change_yoy":
            difference(
                profit_margin,
                yoy_profit_margin
            ),

        "bank_q_pretax_margin":
            pct(
                safe_divide(
                    pretax_income,
                    revenue
                )
            ),

        # عوائد البنك
        # يتم تحويل الربع إلى معدل سنوي تقريبي ×4
        "bank_q_roa_annualized":
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

        "bank_q_roe_annualized":
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

        # رأس المال
        "bank_q_equity_to_assets":
            pct(
                safe_divide(
                    equity,
                    assets
                )
            ),

        "bank_q_liabilities_to_assets":
            pct(
                safe_divide(
                    liabilities,
                    assets
                )
            ),

        # أرقام خام
        "bank_q_revenue":
            revenue,

        "bank_q_net_income":
            net_income,

        "bank_q_total_assets":
            assets,

        "bank_q_total_liabilities":
            liabilities,

        "bank_q_equity":
            equity,

        "bank_q_cash":
            cash,

        "bank_q_basic_eps":
            basic_eps,

        "bank_q_diluted_eps":
            diluted_eps
    }

    return metrics


# ============================================================
# TTM للبنوك
# ============================================================

def calculate_bank_ttm_metrics(
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
        quarterly[d]
        for d in dates
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

    net_income = sum_if_complete(
        [
            value(
                q,
                "quarterlyNetIncome"
            )
            for q in quarters
        ]
    )

    pretax_income = sum_if_complete(
        [
            value(
                q,
                "quarterlyPretaxIncome"
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

    metrics = {

        "bank_ttm_revenue":
            revenue,

        "bank_ttm_net_income":
            net_income,

        "bank_ttm_profit_margin":
            pct(
                safe_divide(
                    net_income,
                    revenue
                )
            ),

        "bank_ttm_pretax_margin":
            pct(
                safe_divide(
                    pretax_income,
                    revenue
                )
            ),

        "bank_ttm_roa":
            pct(
                safe_divide(
                    net_income,
                    assets
                )
            ),

        "bank_ttm_roe":
            pct(
                safe_divide(
                    net_income,
                    equity
                )
            )
    }

    return metrics


# ============================================================
# درجة اكتمال بيانات البنك
# ============================================================

def calculate_bank_data_confidence(
    current
):

    required = [

        "quarterlyTotalRevenue",
        "quarterlyNetIncome",
        "quarterlyPretaxIncome",
        "quarterlyTotalAssets",
        "quarterlyTotalLiabilitiesNetMinorityInterest",
        "quarterlyStockholdersEquity"
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
# Bank Signal Engine V1
# ============================================================

def calculate_bank_signal_scores(
    metrics
):

    improvement = 0
    risk = 0
    used = 0

    def positive(metric_name):

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

    positive(
        "bank_q_revenue_growth_yoy"
    )

    positive(
        "bank_q_net_income_growth_yoy"
    )

    positive(
        "bank_q_assets_growth_yoy"
    )

    positive(
        "bank_q_equity_growth_yoy"
    )

    positive(
        "bank_q_profit_margin_change_yoy"
    )

    roe = metrics.get(
        "bank_ttm_roe"
    )

    if roe is not None:

        used += 1

        if roe >= 12:
            improvement += 1

        elif roe < 8:
            risk += 1

    roa = metrics.get(
        "bank_ttm_roa"
    )

    if roa is not None:

        used += 1

        if roa >= 1.5:
            improvement += 1

        elif roa < 0.8:
            risk += 1

    equity_assets = metrics.get(
        "bank_q_equity_to_assets"
    )

    if equity_assets is not None:

        used += 1

        if equity_assets >= 10:
            improvement += 1

        elif equity_assets < 7:
            risk += 1

    if used == 0:

        return {
            "bank_signal_improvement_score": None,
            "bank_signal_risk_score": None,
            "bank_signal_net_score": None
        }

    improvement_score = (
        improvement / used
    ) * 100

    risk_score = (
        risk / used
    ) * 100

    return {

        "bank_signal_improvement_score":
            improvement_score,

        "bank_signal_risk_score":
            risk_score,

        "bank_signal_net_score":
            improvement_score
            - risk_score
    }


# ============================================================
# تشغيل بنك واحد
# ============================================================

def calculate_bank_metrics(stock):

    stock_id = stock["id"]
    symbol = stock["symbol"]
    company_name = stock.get(
        "company_name"
    )

    print(
        "\n"
        + "=" * 70,
        flush=True
    )

    print(
        f"🏦 BANK: {symbol} | {company_name}",
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

    # --------------------------------------------------------
    # Annual
    # --------------------------------------------------------

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
                annual_dates[index - 1]
            ]
            if index > 0
            else None
        )

        metrics = (
            calculate_bank_annual_metrics(
                current,
                previous
            )
        )

        saved = save_metrics(
            stock_id,
            period_end,
            metrics
        )

        total_saved += saved

    # --------------------------------------------------------
    # Quarterly
    # --------------------------------------------------------

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
                quarter_dates[index - 1]
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
            calculate_bank_quarter_metrics(
                current,
                previous_quarter,
                same_quarter_last_year
            )
        )

        ttm_metrics = (
            calculate_bank_ttm_metrics(
                quarter_dates,
                quarterly,
                index
            )
        )

        metrics.update(
            ttm_metrics
        )

        metrics[
            "bank_data_confidence_score"
        ] = calculate_bank_data_confidence(
            current
        )

        signals = (
            calculate_bank_signal_scores(
                metrics
            )
        )

        metrics.update(
            signals
        )

        saved = save_metrics(
            stock_id,
            period_end,
            metrics
        )

        total_saved += saved

    print(
        f"✅ {symbol} | "
        f"{total_saved} bank metrics saved",
        flush=True
    )

    return {
        "status": "success",
        "metrics": total_saved
    }


# ============================================================
# التشغيل الرئيسي لجميع البنوك
# ============================================================

def run_bank_metrics():

    print(
        "\n"
        + "#" * 70,
        flush=True
    )

    print(
        "🏦 BANK METRICS ENGINE",
        flush=True
    )

    print(
        "#" * 70,
        flush=True
    )

    banks = get_bank_stocks()

    print(
        f"🏦 Total Banks: {len(banks)}",
        flush=True
    )

    success = 0
    no_data = 0
    errors = 0
    total_metrics = 0

    details = []

    for stock in banks:

        try:

            result = calculate_bank_metrics(
                stock
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
        "📋 FINAL BANK METRICS SUMMARY",
        flush=True
    )

    print(
        "=" * 70,
        flush=True
    )

    print(
        f"🏦 Total Banks: {len(banks)}",
        flush=True
    )

    print(
        f"🟢 Success: {success}",
        flush=True
    )

    print(
        f"🟡 No Data: {no_data}",
        flush=True
    )

    print(
        f"🔴 Errors: {errors}",
        flush=True
    )

    print(
        f"💾 Total Bank Metrics Saved: "
        f"{total_metrics}",
        flush=True
    )

    print(
        "\n📋 Banks:",
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

    run_bank_metrics()
