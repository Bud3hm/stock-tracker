import os
import time
import requests
from datetime import datetime
from zoneinfo import ZoneInfo
from supabase import create_client


# ============================================================
# الإعدادات العامة
# ============================================================

RIYADH_TZ = ZoneInfo("Asia/Riyadh")

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_SECRET_KEY = os.environ.get("SUPABASE_SECRET_KEY")

BASE_URL = "https://query1.finance.yahoo.com"
SOURCE_NAME = "yahoo"

# بداية التاريخ: 2020-01-01
FINANCIAL_PERIOD_START = 1577836800

# مهلة بين الشركات لتقليل ضغط الطلبات على Yahoo
REQUEST_DELAY_BETWEEN_COMPANIES = 1.0

# عدد السجلات في كل دفعة حفظ إلى Supabase
UPSERT_BATCH_SIZE = 250


supabase = create_client(
    SUPABASE_URL,
    SUPABASE_SECRET_KEY
)


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
# أنواع البيانات المالية
# سنوي + ربعي
# ============================================================

INCOME_STATEMENT_TYPES = [

    # سنوي
    "annualTotalRevenue",
    "annualCostOfRevenue",
    "annualGrossProfit",
    "annualOperatingIncome",
    "annualPretaxIncome",
    "annualTaxProvision",
    "annualNetIncome",
    "annualBasicEPS",
    "annualDilutedEPS",

    # ربعي
    "quarterlyTotalRevenue",
    "quarterlyCostOfRevenue",
    "quarterlyGrossProfit",
    "quarterlyOperatingIncome",
    "quarterlyPretaxIncome",
    "quarterlyTaxProvision",
    "quarterlyNetIncome",
    "quarterlyBasicEPS",
    "quarterlyDilutedEPS"
]


BALANCE_SHEET_TYPES = [

    # سنوي
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
    "annualRetainedEarnings",

    # ربعي
    "quarterlyTotalAssets",
    "quarterlyCurrentAssets",
    "quarterlyCashCashEquivalentsAndShortTermInvestments",
    "quarterlyAccountsReceivable",
    "quarterlyInventory",
    "quarterlyTotalLiabilitiesNetMinorityInterest",
    "quarterlyCurrentLiabilities",
    "quarterlyTotalDebt",
    "quarterlyShortTermDebt",
    "quarterlyLongTermDebt",
    "quarterlyStockholdersEquity",
    "quarterlyRetainedEarnings"
]


CASH_FLOW_TYPES = [

    # سنوي
    "annualOperatingCashFlow",
    "annualInvestingCashFlow",
    "annualFinancingCashFlow",
    "annualCapitalExpenditure",
    "annualFreeCashFlow",

    # ربعي
    "quarterlyOperatingCashFlow",
    "quarterlyInvestingCashFlow",
    "quarterlyFinancingCashFlow",
    "quarterlyCapitalExpenditure",
    "quarterlyFreeCashFlow"
]


FINANCIAL_GROUPS = [

    {
        "name": "income_statement",
        "title": "📊 قائمة الدخل",
        "types": INCOME_STATEMENT_TYPES
    },

    {
        "name": "balance_sheet",
        "title": "🏦 الميزانية العمومية",
        "types": BALANCE_SHEET_TYPES
    },

    {
        "name": "cash_flow",
        "title": "💵 التدفقات النقدية",
        "types": CASH_FLOW_TYPES
    }
]


# ============================================================
# الاتصال بـ Yahoo
# ============================================================

def yahoo_request(endpoint, retries=3):

    url = f"{BASE_URL}{endpoint}"

    last_error = None

    for attempt in range(1, retries + 1):

        try:

            response = requests.get(
                url,
                headers=HEADERS,
                timeout=20
            )

            print(
                f"HTTP {response.status_code} "
                f"| attempt {attempt}/{retries}",
                flush=True
            )

            if response.status_code == 429:

                wait_seconds = attempt * 5

                print(
                    f"🟠 Yahoo Rate Limit - "
                    f"انتظار {wait_seconds} ثوانٍ",
                    flush=True
                )

                time.sleep(wait_seconds)

                continue

            response.raise_for_status()

            return response.json()

        except Exception as e:

            last_error = e

            if attempt < retries:

                wait_seconds = attempt * 2

                print(
                    f"🟠 إعادة المحاولة بعد "
                    f"{wait_seconds} ثانية...",
                    flush=True
                )

                time.sleep(wait_seconds)

    raise last_error


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

    if not isinstance(reported, dict):
        return None

    if reported.get("raw") is not None:
        return reported.get("raw")

    if reported.get("fmt") is not None:
        return reported.get("fmt")

    return None


def print_section(title):

    print(
        "\n" + "=" * 80,
        flush=True
    )

    print(
        title,
        flush=True
    )

    print(
        "=" * 80,
        flush=True
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
# تحديث حالة بيانات الشركة
# ============================================================

def update_stock_status(
    stock_id,
    status
):

    try:

        (
            supabase
            .table("stocks")
            .update({
                "data_status": status,
                "updated_at": datetime.now().isoformat()
            })
            .eq("id", stock_id)
            .execute()
        )

    except Exception as e:

        print(
            f"🟠 تعذر تحديث data_status "
            f"لـ stock_id={stock_id}: {e}",
            flush=True
        )


# ============================================================
# استخراج سجلات Timeseries
# ============================================================

def extract_timeseries_rows(
    result,
    stock_id,
    requested_symbol
):

    rows = []

    if not isinstance(result, list):
        return rows

    for item in result:

        if not isinstance(item, dict):
            continue

        meta = item.get("meta", {})

        yahoo_symbol = requested_symbol

        if isinstance(meta, dict):

            meta_symbol = meta.get("symbol")

            if (
                isinstance(meta_symbol, list)
                and meta_symbol
            ):
                yahoo_symbol = meta_symbol[0]

            elif isinstance(meta_symbol, str):
                yahoo_symbol = meta_symbol

        if yahoo_symbol != requested_symbol:

            print(
                f"🟠 تنبيه: Yahoo أعاد الرمز "
                f"{yahoo_symbol} بدل {requested_symbol}",
                flush=True
            )

        for metric, values in item.items():

            if metric in (
                "meta",
                "timestamp"
            ):
                continue

            if not isinstance(values, list):
                continue

            for record in values:

                if not isinstance(record, dict):
                    continue

                period_end = record.get("asOfDate")

                period_type = (
                    record.get("periodType")
                    or "unknown"
                )

                currency = (
                    record.get("currencyCode")
                    or "SAR"
                )

                value = extract_reported_value(
                    record
                )

                if (
                    value is None
                    or not period_end
                ):
                    continue

                rows.append({
                    "stock_id": stock_id,
                    "metric": metric,
                    "period_end": period_end,
                    "period_type": period_type,
                    "value": value,
                    "currency": currency,
                    "source": SOURCE_NAME
                })

    return rows


# ============================================================
# حفظ البيانات دفعات
# ============================================================

def save_financial_rows(rows):

    if not rows:
        return 0

    saved = 0

    for start in range(
        0,
        len(rows),
        UPSERT_BATCH_SIZE
    ):

        batch = rows[
            start:
            start + UPSERT_BATCH_SIZE
        ]

        (
            supabase
            .table("financial_statements")
            .upsert(
                batch,
                on_conflict=(
                    "stock_id,"
                    "metric,"
                    "period_end,"
                    "period_type"
                )
            )
            .execute()
        )

        saved += len(batch)

    return saved


# ============================================================
# جلب مجموعة مالية واحدة
# ============================================================

def fetch_financial_group(
    stock_id,
    symbol,
    group
):

    period_end = int(
        datetime.now().timestamp()
    )

    endpoint = (
        f"/ws/fundamentals-timeseries/"
        f"v1/finance/timeseries/"
        f"{symbol}"
        f"?symbol={symbol}"
        f"&type={','.join(group['types'])}"
        f"&period1={FINANCIAL_PERIOD_START}"
        f"&period2={period_end}"
    )

    print_section(
        f"{group['title']} | {symbol}"
    )

    data = yahoo_request(
        endpoint
    )

    timeseries = data.get(
        "timeseries",
        {}
    )

    if not isinstance(
        timeseries,
        dict
    ):

        raise ValueError(
            "بنية timeseries غير متوقعة"
        )

    result = timeseries.get(
        "result",
        []
    )

    rows = extract_timeseries_rows(
        result=result,
        stock_id=stock_id,
        requested_symbol=symbol
    )

    saved = save_financial_rows(
        rows
    )

    print(
        f"💾 {symbol} | "
        f"{group['name']} | "
        f"تمت معالجة {saved} سجل",
        flush=True
    )

    return saved


# ============================================================
# معالجة شركة واحدة
# ============================================================

def process_stock(stock):

    stock_id = stock["id"]
    symbol = stock["symbol"]

    company_name = (
        stock.get("company_name")
        or symbol
    )

    analysis_model = (
        stock.get("analysis_model")
        or "standard"
    )

    print(
        "\n\n" + "#" * 80,
        flush=True
    )

    print(
        f"🏢 {company_name}",
        flush=True
    )

    print(
        f"📌 Symbol: {symbol}",
        flush=True
    )

    print(
        f"🧠 Analysis Model: "
        f"{analysis_model}",
        flush=True
    )

    print(
        "#" * 80,
        flush=True
    )

    group_success = 0
    group_failures = 0
    total_records = 0

    for group in FINANCIAL_GROUPS:

        try:

            saved = fetch_financial_group(
                stock_id=stock_id,
                symbol=symbol,
                group=group
            )

            if saved > 0:
                group_success += 1

            else:
                group_failures += 1

                print(
                    f"🟠 {symbol} | "
                    f"{group['name']} "
                    f"لم يرجع سجلات",
                    flush=True
                )

            total_records += saved

        except Exception as e:

            group_failures += 1

            print(
                f"🔴 {symbol} | "
                f"{group['name']} | "
                f"{type(e).__name__}: {e}",
                flush=True
            )

    # ========================================================
    # تحديد حالة البيانات
    # ========================================================

    if (
        group_success == len(FINANCIAL_GROUPS)
        and total_records > 0
    ):

        status = "ready"

    elif total_records > 0:

        status = "partial"

    else:

        status = "error"

    update_stock_status(
        stock_id,
        status
    )

    print(
        "\n"
        f"📊 نتيجة {company_name}: "
        f"{status.upper()}",
        flush=True
    )

    print(
        f"💾 إجمالي السجلات المعالجة: "
        f"{total_records}",
        flush=True
    )

    return {
        "stock_id": stock_id,
        "symbol": symbol,
        "company_name": company_name,
        "analysis_model": analysis_model,
        "status": status,
        "records": total_records,
        "group_success": group_success,
        "group_failures": group_failures
    }


# ============================================================
# تشغيل جميع الشركات
# ============================================================

def run_financial_pipeline():

    now = datetime.now(
        RIYADH_TZ
    ).strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    stocks = get_active_stocks()

    print(
        "\n\n" + "#" * 80,
        flush=True
    )

    print(
        "🚀 MULTI-COMPANY FINANCIAL PIPELINE",
        flush=True
    )

    print(
        f"🕐 وقت التشغيل: "
        f"{now} بتوقيت الرياض",
        flush=True
    )

    print(
        f"🏢 عدد الشركات المفعلة: "
        f"{len(stocks)}",
        flush=True
    )

    print(
        "📊 الوضع: سنوي + ربعي",
        flush=True
    )

    print(
        "#" * 80,
        flush=True
    )

    if not stocks:

        print(
            "🔴 لا توجد شركات مفعلة "
            "في جدول stocks",
            flush=True
        )

        return

    results = []

    for index, stock in enumerate(
        stocks,
        start=1
    ):

        print(
            f"\n\n🚦 الشركة "
            f"{index}/{len(stocks)}",
            flush=True
        )

        try:

            result = process_stock(
                stock
            )

            results.append(
                result
            )

        except Exception as e:

            update_stock_status(
                stock["id"],
                "error"
            )

            results.append({
                "stock_id": stock["id"],
                "symbol": stock["symbol"],
                "company_name": (
                    stock.get("company_name")
                    or stock["symbol"]
                ),
                "analysis_model": (
                    stock.get("analysis_model")
                    or "standard"
                ),
                "status": "error",
                "records": 0,
                "group_success": 0,
                "group_failures": 3
            })

            print(
                f"🔴 فشل عام في "
                f"{stock['symbol']}: {e}",
                flush=True
            )

        if index < len(stocks):

            time.sleep(
                REQUEST_DELAY_BETWEEN_COMPANIES
            )

    # ========================================================
    # الملخص النهائي
    # ========================================================

    ready_count = sum(
        1
        for result in results
        if result["status"] == "ready"
    )

    partial_count = sum(
        1
        for result in results
        if result["status"] == "partial"
    )

    error_count = sum(
        1
        for result in results
        if result["status"] == "error"
    )

    total_records = sum(
        result["records"]
        for result in results
    )

    print(
        "\n\n" + "=" * 80,
        flush=True
    )

    print(
        "📊 FINAL FINANCIAL PIPELINE SUMMARY",
        flush=True
    )

    print(
        "=" * 80,
        flush=True
    )

    print(
        f"🏢 Total Companies: "
        f"{len(results)}",
        flush=True
    )

    print(
        f"🟢 Ready: "
        f"{ready_count}",
        flush=True
    )

    print(
        f"🟠 Partial: "
        f"{partial_count}",
        flush=True
    )

    print(
        f"🔴 Error: "
        f"{error_count}",
        flush=True
    )

    print(
        f"💾 Total Records Processed: "
        f"{total_records}",
        flush=True
    )

    print(
        "\n📋 تفاصيل الشركات:",
        flush=True
    )

    for result in results:

        print(
            f"{result['symbol']} | "
            f"{result['company_name']} | "
            f"{result['analysis_model']} | "
            f"{result['status']} | "
            f"{result['records']} records",
            flush=True
        )

    print(
        "=" * 80,
        flush=True
    )


# ============================================================
# توافق مع الاسم القديم
# ============================================================

def run_financial_test():

    run_financial_pipeline()


# ============================================================
# التشغيل
# ============================================================

if __name__ == "__main__":

    run_financial_pipeline()
