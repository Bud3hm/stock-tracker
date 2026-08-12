import os
from supabase import create_client

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_SECRET_KEY = os.environ.get("SUPABASE_SECRET_KEY")

supabase = create_client(SUPABASE_URL, SUPABASE_SECRET_KEY)


def get_financial_data(stock_id):
    response = (
        supabase
        .table("financial_statements")
        .select("*")
        .eq("stock_id", stock_id)
        .execute()
    )

    return response.data


def safe_divide(a, b):
    if a is None or b is None or b == 0:
        return None

    return a / b


def growth_rate(current, previous):
    if current is None or previous is None or previous == 0:
        return None

    return ((current - previous) / abs(previous)) * 100


def calculate_metrics(stock_id):
    rows = get_financial_data(stock_id)

    if not rows:
        print("No financial data found")
        return

    annual = {}

    for row in rows:
        if row.get("period_type") != "12M":
            continue

        year = str(row["period_end"])[:4]
        metric = row["metric"]
        value = row["value"]

        if year not in annual:
            annual[year] = {}

        annual[year][metric] = value

    years = sorted(annual.keys())

    for index, year in enumerate(years):
        data = annual[year]

        revenue = data.get("annualTotalRevenue")
        net_income = data.get("annualNetIncome")
        assets = data.get("annualTotalAssets")
        equity = data.get("annualStockholdersEquity")
        operating_cash_flow = data.get("annualOperatingCashFlow")
        free_cash_flow = data.get("annualFreeCashFlow")

        previous = annual.get(years[index - 1]) if index > 0 else None

        metrics = {
            "revenue_growth": (
                growth_rate(
                    revenue,
                    previous.get("annualTotalRevenue")
                )
                if previous else None
            ),

            "net_income_growth": (
                growth_rate(
                    net_income,
                    previous.get("annualNetIncome")
                )
                if previous else None
            ),

            "net_profit_margin": (
                safe_divide(net_income, revenue) * 100
                if safe_divide(net_income, revenue) is not None
                else None
            ),

            "roa": (
                safe_divide(net_income, assets) * 100
                if safe_divide(net_income, assets) is not None
                else None
            ),

            "roe": (
                safe_divide(net_income, equity) * 100
                if safe_divide(net_income, equity) is not None
                else None
            ),

            "cash_conversion": (
                safe_divide(operating_cash_flow, net_income)
                if safe_divide(operating_cash_flow, net_income) is not None
                else None
            ),

            "free_cash_flow": free_cash_flow
        }

        print(f"\nYEAR: {year}")

        for name, value in metrics.items():
            print(f"{name}: {value}")


if __name__ == "__main__":
    calculate_metrics(1)
