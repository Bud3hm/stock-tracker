import requests
from datetime import datetime
from zoneinfo import ZoneInfo


# ============================================================
# الإعدادات
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


def extract_reported_value(record):

    if not isinstance(record, dict):
        return None

    reported = record.get("reportedValue")

    if isinstance(reported, dict):

        if reported.get("raw") is not None:
            return reported.get("raw")

        if reported.get("fmt") is not None:
            return reported.get("fmt")

    return None


def format_number(value):

    value = safe_value(value)

    if value is None:
        return "غير متوفر"

    if isinstance(value, (int, float)):

        if abs(value) >= 1_000_000_000:
            return f"{value / 1_000_000_000:,.3f} مليار"

        if abs(value) >= 1_000_000:
            return f"{value / 1_000_000:,.3f} مليون"

        return f"{value:,.2f}"

    return str(value)


def print_section(title):

    print("\n" + "=" * 80, flush=True)
    print(title, flush=True)
    print("=" * 80, flush=True)


# ============================================================
# طباعة بيانات Timeseries
# ============================================================

def print_timeseries_result(result):

    if not isinstance(result, list) or not result:

        print(
            "⚠️ لا توجد بيانات",
            flush=True
        )

        return

    for item in result:

        if not isinstance(item, dict):
            continue

        meta = item.get("meta", {})

        symbol = TICKER_SYMBOL

        if isinstance(meta, dict):

            meta_symbol = meta.get("symbol")

            if isinstance(meta_symbol, list) and meta_symbol:
                symbol = meta_symbol[0]

            elif isinstance(meta_symbol, str):
                symbol = meta_symbol

        for key, values in item.items():

            if key in ("meta", "timestamp"):
                continue

            if not isinstance(values, list):
                continue

            print(
                "\n----------------------------------------------",
                flush=True
            )

            print(
                f"📌 المؤشر: {key}",
                flush=True
            )

            print(
                f"🔹 الرمز: {symbol}",
                flush=True
            )

            for record in values:

                if not isinstance(record, dict):
                    continue

                date = record.get(
                    "asOfDate",
                    "غير معروف"
                )

                period_type = record.get(
                    "periodType",
                    "غير معروف"
                )

                currency = record.get(
                    "currencyCode",
                    ""
                )

                value = extract_reported_value(
                    record
                )

                print(
                    f"{date} | "
                    f"{period_type} | "
                    f"{format_number(value)} "
                    f"{currency}",
                    flush=True
                )


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

        quote_summary = data.get(
            "quoteSummary",
            {}
        )

        if not isinstance(
            quote_summary,
            dict
        ):
            print(
                "⚠️ بنية quoteSummary غير متوقعة",
                flush=True
            )
            return

        result = quote_summary.get(
            "result"
        )

        if not result:

            print(
                "⚠️ لم تصل بيانات الشركة الأساسية",
                flush=True
            )

            return

        result = result[0]

        if not isinstance(result, dict):
            return

        price = result.get(
            "price",
            {}
        )

        if not isinstance(price, dict):
            price = {}

        summary = result.get(
            "summaryDetail",
            {}
        )

        if not isinstance(summary, dict):
            summary = {}

        stats = result.get(
            "defaultKeyStatistics",
            {}
        )

        if not isinstance(stats, dict):
            stats = {}

        financial = result.get(
            "financialData",
            {}
        )

        if not isinstance(financial, dict):
            financial = {}

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

        print(
            f"أعلى 52 أسبوع: "
            f"{format_number(summary.get('fiftyTwoWeekHigh'))}",
            flush=True
        )

        print(
            f"أدنى 52 أسبوع: "
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

        print(
            f"الإيرادات TTM: "
            f"{format_number(financial.get('totalRevenue'))}",
            flush=True
        )

        print(
            f"هامش صافي الربح: "
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
            f"🔴 خطأ البيانات الأساسية: "
            f"{type(e).__name__}: {e}",
            flush=True
        )


# ============================================================
# قائمة الدخل السنوية
# ============================================================

def get_income_statement():

    print_section(
        "📊 قائمة الدخل السنوية"
    )

    try:

        types = [
            "annualTotalRevenue",
            "annualCostOfRevenue",
            "annualGrossProfit",
            "annualOperatingIncome",
            "annualPretaxIncome",
            "annualTaxProvision",
            "annualNetIncome",
            "annualBasicEPS",
            "annualDilutedEPS"
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

        timeseries = data.get(
            "timeseries",
            {}
        )

        if not isinstance(
            timeseries,
            dict
        ):

            print(
                "⚠️ timeseries غير متوقعة",
                flush=True
            )
            return

        result = timeseries.get(
            "result",
            []
        )

        print_timeseries_result(
            result
        )

    except Exception as e:

        print(
            f"🔴 خطأ قائمة الدخل: "
            f"{type(e).__name__}: {e}",
            flush=True
        )


# ============================================================
# الميزانية السنوية
# ============================================================

def get_balance_sheet():

    print_section(
        "🏦 الميزانية العمومية السنوية"
    )

    try:

        types = [
            "annualTotalAssets",
            "annualCurrentAssets",
            "annualCashCashEquivalentsAndShortTermInvestments",
            "annualAccountsReceivable",
            "annualInventory",
            "annualTotalLiabilitiesNetMinorityInterest",
            "annualCurrentLiabilities",
            "annualTotalDebt",
            "annualShortTermDebt",
            "annualLongTermDebt",
            "annualStockholdersEquity",
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

        timeseries = data.get(
            "timeseries",
            {}
        )

        if not isinstance(
            timeseries,
            dict
        ):
            print(
                "⚠️ timeseries غير متوقعة",
                flush=True
            )
            return

        result = timeseries.get(
            "result",
            []
        )

        print_timeseries_result(
            result
        )

    except Exception as e:

        print(
            f"🔴 خطأ الميزانية: "
            f"{type(e).__name__}: {e}",
            flush=True
        )


# ============================================================
# التدفقات النقدية السنوية
# ============================================================

def get_cash_flow():

    print_section(
        "💵 التدفقات النقدية السنوية"
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

        timeseries = data.get(
            "timeseries",
            {}
        )

        if not isinstance(
            timeseries,
            dict
        ):
            print(
                "⚠️ timeseries غير متوقعة",
                flush=True
            )
            return

        result = timeseries.get(
            "result",
            []
        )

        print_timeseries_result(
            result
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

    print(
        "\n\n" + "#" * 80,
        flush=True
    )

    print(
        "🧪 اختبار حزمة البيانات المالية",
        flush=True
    )

    print(
        f"🕐 وقت الاختبار: "
        f"{now} بتوقيت الرياض",
        flush=True
    )

    print(
        f"📌 السهم: "
        f"{TICKER_SYMBOL}",
        flush=True
    )

    print(
        "#" * 80,
        flush=True
    )

    get_company_summary()
    get_income_statement()
    get_balance_sheet()
    get_cash_flow()

    print(
        "\n" + "#" * 80,
        flush=True
    )

    print(
        "🟢 انتهى اختبار حزمة البيانات المالية",
        flush=True
    )

    print(
        "#" * 80,
        flush=True
    )


if __name__ == "__main__":

    run_financial_test()
