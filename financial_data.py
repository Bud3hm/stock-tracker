import requests
from datetime import datetime
from zoneinfo import ZoneInfo

# ============================================================
# إعدادات
# ============================================================

TICKER_SYMBOL = "2283.SR"

RIYADH_TZ = ZoneInfo("Asia/Riyadh")

BASE_URL = "https://query1.finance.yahoo.com"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 "
        "(Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/131.0 Safari/537.36"
    )
}


# ============================================================
# الاتصال بـ Yahoo
# ============================================================

def yahoo_request(endpoint):

    url = f"{BASE_URL}{endpoint}"

    response = requests.get(
        url,
        headers=HEADERS,
        timeout=15
    )

    print(
        f"HTTP {response.status_code} - {endpoint}",
        flush=True
    )

    response.raise_for_status()

    return response.json()


# ============================================================
# أدوات مساعدة
# ============================================================

def safe_value(value):

    if value is None:
        return None

    if isinstance(value, dict):

        if "raw" in value:
            return value["raw"]

        if "fmt" in value:
            return value["fmt"]

    return value


def format_number(value):

    value = safe_value(value)

    if value is None:
        return "غير متوفر"

    if isinstance(value, (int, float)):

        return f"{value:,.2f}"

    return str(value)


def print_section(title):

    print("\n" + "=" * 75, flush=True)

    print(
        title,
        flush=True
    )

    print("=" * 75, flush=True)


# ============================================================
# البيانات الأساسية للشركة
# ============================================================

def get_company_summary():

    print_section(
        "🏢 البيانات الأساسية للشركة"
    )

    try:

        data = yahoo_request(
            f"/v10/finance/quoteSummary/"
            f"{TICKER_SYMBOL}"
            f"?modules="
            f"price,"
            f"summaryDetail,"
            f"defaultKeyStatistics,"
            f"financialData"
        )

        result = data.get(
            "quoteSummary",
            {}
        ).get(
            "result"
        )

        if not result:

            print(
                "⚠️ لم تصل بيانات الشركة",
                flush=True
            )

            return

        result = result[0]

        # ----------------------------------------------------
        # Price
        # ----------------------------------------------------

        price = result.get(
            "price",
            {}
        )

        print(
            f"الشركة: "
            f"{safe_value(price.get('longName'))}",
            flush=True
        )

        print(
            f"الرمز: "
            f"{safe_value(price.get('symbol'))}",
            flush=True
        )

        print(
            f"العملة: "
            f"{safe_value(price.get('currency'))}",
            flush=True
        )

        print(
            f"السعر الحالي: "
            f"{format_number(price.get('regularMarketPrice'))}",
            flush=True
        )

        print(
            f"القيمة السوقية: "
            f"{format_number(price.get('marketCap'))}",
            flush=True
        )

        # ----------------------------------------------------
        # Summary Detail
        # ----------------------------------------------------

        summary = result.get(
            "summaryDetail",
            {}
        )

        print(
            f"نطاق 52 أسبوع - الأعلى: "
            f"{format_number(summary.get('fiftyTwoWeekHigh'))}",
            flush=True
        )

        print(
            f"نطاق 52 أسبوع - الأدنى: "
            f"{format_number(summary.get('fiftyTwoWeekLow'))}",
            flush=True
        )

        print(
            f"متوسط حجم التداول: "
            f"{format_number(summary.get('averageVolume'))}",
            flush=True
        )

        print(
            f"عائد التوزيعات: "
            f"{format_number(summary.get('dividendYield'))}",
            flush=True
        )

        # ----------------------------------------------------
        # Statistics
        # ----------------------------------------------------

        stats = result.get(
            "defaultKeyStatistics",
            {}
        )

        print(
            f"EPS: "
            f"{format_number(stats.get('trailingEps'))}",
            flush=True
        )

        print(
            f"القيمة الدفترية للسهم: "
            f"{format_number(stats.get('bookValue'))}",
            flush=True
        )

        print(
            f"الأسهم القائمة: "
            f"{format_number(stats.get('sharesOutstanding'))}",
            flush=True
        )

        # ----------------------------------------------------
        # Financial Data
        # ----------------------------------------------------

        financial = result.get(
            "financialData",
            {}
        )

        print(
            f"الإيرادات: "
            f"{format_number(financial.get('totalRevenue'))}",
            flush=True
        )

        print(
            f"صافي هامش الربح: "
            f"{format_number(financial.get('profitMargins'))}",
            flush=True
        )

        print(
            f"ROE: "
            f"{format_number(financial.get('returnOnEquity'))}",
            flush=True
        )

        print(
            f"ROA: "
            f"{format_number(financial.get('returnOnAssets'))}",
            flush=True
        )

        print(
            f"التدفق النقدي التشغيلي: "
            f"{format_number(financial.get('operatingCashflow'))}",
            flush=True
        )

        print(
            f"التدفق النقدي الحر: "
            f"{format_number(financial.get('freeCashflow'))}",
            flush=True
        )

    except Exception as e:

        print(
            f"🔴 خطأ في البيانات الأساسية: "
            f"{type(e).__name__}: {e}",
            flush=True
        )


# ============================================================
# قائمة الدخل
# ============================================================

def get_income_statement():

    print_section(
        "📊 قائمة الدخل"
    )

    try:

        data = yahoo_request(
            f"/ws/fundamentals-timeseries/v1/finance/"
            f"timeseries/{TICKER_SYMBOL}"
            f"?symbol={TICKER_SYMBOL}"
            f"&type="
            f"annualTotalRevenue,"
            f"annualCostOfRevenue,"
            f"annualGrossProfit,"
            f"annualOperatingIncome,"
            f"annualPretaxIncome,"
            f"annualTaxProvision,"
            f"annualNetIncome,"
            f"annualDilutedEPS,"
            f"annualBasicEPS"
            f"&period1=1577836800"
            f"&period2=1893456000"
        )

        result = data.get(
            "timeseries",
            {}
        ).get(
            "result",
            []
        )

        if not result:

            print(
                "⚠️ لا توجد بيانات قائمة دخل",
                flush=True
            )

            return

        for item in result:

            print("\n-----------------------------------")

            print(
                f"الفترة: "
                f"{item.get('meta', {}).get('symbol', TICKER_SYMBOL)}"
            )

            for key, values in item.items():

                if key == "meta":
                    continue

                if isinstance(values, list):

                    for record in values:

                        date = record.get(
                            "asOfDate",
                            "غير معروف"
                        )

                        value = record.get(
                            key
                        )

                        print(
                            f"{key} | "
                            f"{date} | "
                            f"{format_number(value)}",
                            flush=True
                        )

    except Exception as e:

        print(
            f"🔴 خطأ قائمة الدخل: "
            f"{type(e).__name__}: {e}",
            flush=True
        )


# ============================================================
# الميزانية العمومية
# ============================================================

def get_balance_sheet():

    print_section(
        "🏦 الميزانية العمومية"
    )

    try:

        types = [
            "annualTotalAssets",
            "annualTotalLiabilitiesNetMinorityInterest",
            "annualStockholdersEquity",
            "annualCashCashEquivalentsAndShortTermInvestments",
            "annualInventory",
            "annualAccountsReceivable",
            "annualCurrentAssets",
            "annualCurrentLiabilities",
            "annualTotalDebt",
            "annualLongTermDebt",
            "annualShortTermDebt",
            "annualRetainedEarnings"
        ]

        endpoint = (
            f"/ws/fundamentals-timeseries/v1/finance/"
            f"timeseries/{TICKER_SYMBOL}"
            f"?symbol={TICKER_SYMBOL}"
            f"&type={','.join(types)}"
            f"&period1=1577836800"
            f"&period2=1893456000"
        )

        data = yahoo_request(endpoint)

        result = data.get(
            "timeseries",
            {}
        ).get(
            "result",
            []
        )

        if not result:

            print(
                "⚠️ لا توجد بيانات ميزانية",
                flush=True
            )

            return

        for item in result:

            for key, values in item.items():

                if key == "meta":
                    continue

                if isinstance(values, list):

                    for record in values:

                        print(
                            f"{key} | "
                            f"{record.get('asOfDate')} | "
                            f"{format_number(record.get(key))}",
                            flush=True
                        )

    except Exception as e:

        print(
            f"🔴 خطأ الميزانية: "
            f"{type(e).__name__}: {e}",
            flush=True
        )


# ============================================================
# التدفقات النقدية
# ============================================================

def get_cash_flow():

    print_section(
        "💵 التدفقات النقدية"
    )

    try:

        types = [
            "annualOperatingCashFlow",
            "annualInvestingCashFlow",
            "annualFinancingCashFlow",
            "annualCapitalExpenditure",
            "annualFreeCashFlow"
        ]

        endpoint = (
            f"/ws/fundamentals-timeseries/v1/finance/"
            f"timeseries/{TICKER_SYMBOL}"
            f"?symbol={TICKER_SYMBOL}"
            f"&type={','.join(types)}"
            f"&period1=1577836800"
            f"&period2=1893456000"
        )

        data = yahoo_request(endpoint)

        result = data.get(
            "timeseries",
            {}
        ).get(
            "result",
            []
        )

        if not result:

            print(
                "⚠️ لا توجد بيانات تدفقات نقدية",
                flush=True
            )

            return

        for item in result:

            for key, values in item.items():

                if key == "meta":
                    continue

                if isinstance(values, list):

                    for record in values:

                        print(
                            f"{key} | "
                            f"{record.get('asOfDate')} | "
                            f"{format_number(record.get(key))}",
                            flush=True
                        )

    except Exception as e:

        print(
            f"🔴 خطأ التدفقات النقدية: "
            f"{type(e).__name__}: {e}",
            flush=True
        )


# ============================================================
# التشغيل
# ============================================================

def run_financial_test():

    now = datetime.now(
        RIYADH_TZ
    ).strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    print("\n\n" + "#" * 75)

    print(
        "🧪 اختبار حزمة البيانات المالية",
        flush=True
    )

    print(
        f"🕐 وقت الاختبار: {now} بتوقيت الرياض",
        flush=True
    )

    print(
        f"📌 السهم: {TICKER_SYMBOL}",
        flush=True
    )

    print("#" * 75)

    # 1
    get_company_summary()

    # 2
    get_income_statement()

    # 3
    get_balance_sheet()

    # 4
    get_cash_flow()

    print("\n" + "#" * 75)

    print(
        "🟢 انتهى اختبار حزمة البيانات المالية",
        flush=True
    )

    print("#" * 75 + "\n")


if __name__ == "__main__":

    run_financial_test()
