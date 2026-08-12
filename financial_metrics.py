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

    return response.data


# ============================================================
# أدوات الحساب
# ============================================================

def safe_divide(a, b):

    if a is None or b is None or b == 0:
        return None

    return a / b


def growth_rate(current, previous):

    if current is None or previous is None or previous == 0:
        return None

    return ((current - previous) / abs(previous)) * 100


# ============================================================
# حفظ المؤشرات في Supabase
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

    for name, value in metrics.items():

        # لا نحفظ المؤشر إذا لم توجد بيانات كافية لحسابه
        if value is None:
            continue

        records.append(
            {
                "stock_id": stock_id,
                "calculated_at": calculated_at,
                "metric_name": name,
                "metric_value": value,
                "period_end": period_end
            }
        )

    if not records:

        print(
            f"⚠️ لا توجد مؤشرات قابلة للحفظ للفترة {period_end}"
        )

        return

    (
        supabase
        .table("financial_metrics")
        .upsert(
            records,
            on_conflict="stock_id,metric_name,period_end"
        )
        .execute()
    )

    print(
        f"💾 Saved {len(records)} metrics "
        f"for {period_end} to Supabase"
    )


# ============================================================
# حساب المؤشرات
# ============================================================

def calculate_metrics(stock_id):

    rows = get_financial_data(
        stock_id
    )

    if not rows:

        print(
            "No financial data found"
        )

        return

    annual = {}

    # ========================================================
    # ترتيب البيانات حسب السنة
    # ========================================================

    for row in rows:

        if row.get("period_type") != "12M":
            continue

        period_end = str(
            row["period_end"]
        )

        year = period_end[:4]

        metric = row["metric"]
        value = row["value"]

        if year not in annual:

            annual[year] = {
                "_period_end": period_end
            }

        annual[year][metric] = value

    years = sorted(
        annual.keys()
    )

    # ========================================================
    # الحساب سنة بسنة
    # ========================================================

    for index, year in enumerate(years):

        data = annual[year]

        period_end = data.get(
            "_period_end"
        )

        revenue = data.get(
            "annualTotalRevenue"
        )

        net_income = data.get(
            "annualNetIncome"
        )

        assets = data.get(
            "annualTotalAssets"
        )

        equity = data.get(
            "annualStockholdersEquity"
        )

        operating_cash_flow = data.get(
            "annualOperatingCashFlow"
        )

        free_cash_flow = data.get(
            "annualFreeCashFlow"
        )

        previous = (
            annual.get(
                years[index - 1]
            )
            if index > 0
            else None
        )

        # ====================================================
        # المؤشرات
        # ====================================================

        revenue_growth = (
            growth_rate(
                revenue,
                previous.get(
                    "annualTotalRevenue"
                )
            )
            if previous
            else None
        )

        net_income_growth = (
            growth_rate(
                net_income,
                previous.get(
                    "annualNetIncome"
                )
            )
            if previous
            else None
        )

        net_margin_raw = safe_divide(
            net_income,
            revenue
        )

        roa_raw = safe_divide(
            net_income,
            assets
        )

        roe_raw = safe_divide(
            net_income,
            equity
        )

        cash_conversion = safe_divide(
            operating_cash_flow,
            net_income
        )

        metrics = {

            "revenue_growth":
                revenue_growth,

            "net_income_growth":
                net_income_growth,

            "net_profit_margin":
                (
                    net_margin_raw * 100
                    if net_margin_raw is not None
                    else None
                ),

            "roa":
                (
                    roa_raw * 100
                    if roa_raw is not None
                    else None
                ),

            "roe":
                (
                    roe_raw * 100
                    if roe_raw is not None
                    else None
                ),

            "cash_conversion":
                cash_conversion,

            "free_cash_flow":
                free_cash_flow
        }

        # ====================================================
        # عرض النتائج
        # ====================================================

        print(
            f"\nYEAR: {year}"
        )

        print(
            f"Period End: {period_end}"
        )

        for name, value in metrics.items():

            print(
                f"{name}: {value}"
            )

        # ====================================================
        # حفظ النتائج
        # ====================================================

        save_metrics(
            stock_id=stock_id,
            period_end=period_end,
            metrics=metrics
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

    calculate_metrics(
        stock_id
    )
