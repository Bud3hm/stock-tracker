import os
import requests
from datetime import datetime
from zoneinfo import ZoneInfo

from flask import Flask
from supabase import create_client


# ============================================================
# إعداد التطبيق
# ============================================================

app = Flask(__name__)


# ============================================================
# الإعدادات العامة
# ============================================================

TICKER_SYMBOL = os.environ.get(
    "TICKER_SYMBOL",
    "2283.SR"
)

RIYADH_TZ = ZoneInfo(
    "Asia/Riyadh"
)

SUPABASE_URL = os.environ.get(
    "SUPABASE_URL"
)

SUPABASE_SECRET_KEY = os.environ.get(
    "SUPABASE_SECRET_KEY"
)

supabase = create_client(
    SUPABASE_URL,
    SUPABASE_SECRET_KEY
)


# ============================================================
# رابط Yahoo
# ============================================================

def get_yahoo_url():

    return (
        "https://query1.finance.yahoo.com/"
        "v8/finance/chart/"
        f"{TICKER_SYMBOL}"
    )


# ============================================================
# جلب stock_id من Supabase
# ============================================================

def get_stock_id(symbol):

    try:

        response = (
            supabase
            .table("stocks")
            .select("id")
            .eq("symbol", symbol)
            .limit(1)
            .execute()
        )

        if response.data:

            return response.data[0]["id"]

    except Exception as e:

        print(
            f"🔴 خطأ جلب stock_id: {e}",
            flush=True
        )

    return None


# ============================================================
# جلب بيانات السعر من Yahoo
# ============================================================

def get_stock_data():

    print(
        "🔵 بدء جلب البيانات من Yahoo...",
        flush=True
    )

    params = {
        "range": "1d",
        "interval": "1m",
        "includePrePost": "false"
    }

    headers = {
        "User-Agent": (
            "Mozilla/5.0 "
            "(Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 "
            "(KHTML, like Gecko) "
            "Chrome/131.0 Safari/537.36"
        )
    }

    response = requests.get(
        get_yahoo_url(),
        params=params,
        headers=headers,
        timeout=10
    )

    print(
        f"🟢 Yahoo HTTP Status: "
        f"{response.status_code}",
        flush=True
    )

    response.raise_for_status()

    return response.json()


# ============================================================
# آخر قيمة صحيحة
# ============================================================

def last_valid(values):

    if not values:
        return None

    for value in reversed(values):

        if value is not None:
            return value

    return None


# ============================================================
# تحليل وحفظ رصد واحد
# ============================================================

def analyze_market_snapshot():

    now_ksa = datetime.now(
        RIYADH_TZ
    )

    now_text = now_ksa.strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    print(
        "\n" + "=" * 75,
        flush=True
    )

    print(
        f"📊 رصد السهم - {TICKER_SYMBOL}",
        flush=True
    )

    print(
        f"🕐 وقت الرصد - الرياض: "
        f"{now_text}",
        flush=True
    )

    print(
        "=" * 75,
        flush=True
    )

    try:

        data = get_stock_data()

        chart = data.get(
            "chart",
            {}
        )

        result = chart.get(
            "result"
        )

        if not result:

            print(
                "🔴 Yahoo لم يرجع بيانات للسهم",
                flush=True
            )

            return

        result = result[0]

        meta = result.get(
            "meta",
            {}
        )

        symbol = (
            meta.get("symbol")
            or TICKER_SYMBOL
        )

        current_price = meta.get(
            "regularMarketPrice"
        )

        previous_close = meta.get(
            "previousClose"
        )

        chart_previous_close = meta.get(
            "chartPreviousClose"
        )

        currency = meta.get(
            "currency"
        )

        exchange = meta.get(
            "exchangeName"
        )

        market_state = meta.get(
            "marketState"
        )

        instrument_type = meta.get(
            "instrumentType"
        )

        print(
            "\n📌 البيانات اللحظية",
            flush=True
        )

        print(
            "-" * 60,
            flush=True
        )

        print(
            f"🔹 الرمز: {symbol}",
            flush=True
        )

        print(
            f"💰 السعر الحالي: "
            f"{current_price}",
            flush=True
        )

        print(
            f"📊 الإغلاق السابق: "
            f"{previous_close}",
            flush=True
        )

        print(
            f"📊 إغلاق الرسم السابق: "
            f"{chart_previous_close}",
            flush=True
        )

        print(
            f"💵 العملة: {currency}",
            flush=True
        )

        print(
            f"🏦 السوق: {exchange}",
            flush=True
        )

        print(
            f"📡 حالة السوق: "
            f"{market_state}",
            flush=True
        )

        print(
            f"📋 نوع الأداة: "
            f"{instrument_type}",
            flush=True
        )

        # ====================================================
        # حساب التغير
        # ====================================================

        change_value = None
        change_percent = None

        if (
            isinstance(
                current_price,
                (int, float)
            )
            and isinstance(
                previous_close,
                (int, float)
            )
            and previous_close != 0
        ):

            change_value = (
                current_price
                - previous_close
            )

            change_percent = (
                change_value
                / previous_close
            ) * 100

            print(
                "\n📈 التغير",
                flush=True
            )

            print(
                "-" * 60,
                flush=True
            )

            print(
                f"💵 التغير: "
                f"{change_value:+.2f}",
                flush=True
            )

            print(
                f"📊 نسبة التغير: "
                f"{change_percent:+.2f}%",
                flush=True
            )

        # ====================================================
        # بيانات آخر دقيقة
        # ====================================================

        last_open = None
        last_high = None
        last_low = None
        last_close = None
        last_volume = None

        timestamps = result.get(
            "timestamp",
            []
        )

        indicators = result.get(
            "indicators",
            {}
        )

        quotes = indicators.get(
            "quote",
            []
        )

        if timestamps and quotes:

            quote = quotes[0]

            last_open = last_valid(
                quote.get(
                    "open",
                    []
                )
            )

            last_high = last_valid(
                quote.get(
                    "high",
                    []
                )
            )

            last_low = last_valid(
                quote.get(
                    "low",
                    []
                )
            )

            last_close = last_valid(
                quote.get(
                    "close",
                    []
                )
            )

            last_volume = last_valid(
                quote.get(
                    "volume",
                    []
                )
            )

            print(
                "\n🕯️ آخر بيانات دقيقة متاحة",
                flush=True
            )

            print(
                "-" * 60,
                flush=True
            )

            print(
                f"فتح: {last_open}",
                flush=True
            )

            print(
                f"أعلى: {last_high}",
                flush=True
            )

            print(
                f"أدنى: {last_low}",
                flush=True
            )

            print(
                f"إغلاق: {last_close}",
                flush=True
            )

            print(
                f"حجم التداول: "
                f"{last_volume}",
                flush=True
            )

        # ====================================================
        # التأكد من وجود السهم
        # ====================================================

        stock_id = get_stock_id(
            symbol
        )

        if stock_id is None:

            print(
                f"🔴 السهم {symbol} "
                f"غير موجود في جدول stocks",
                flush=True
            )

            return

        if current_price is None:

            print(
                "🔴 لا يوجد سعر صالح للحفظ",
                flush=True
            )

            return

        # ====================================================
        # تجهيز السجل
        # ====================================================

        price_record = {

            "stock_id":
                stock_id,

            "captured_at":
                now_ksa.isoformat(),

            "price":
                current_price,

            "previous_close":
                previous_close,

            "change_value":
                change_value,

            "change_percent":
                change_percent,

            "open_price":
                last_open,

            "high_price":
                last_high,

            "low_price":
                last_low,

            "close_price":
                last_close,

            "volume":
                last_volume,

            "market_state":
                market_state,

            "source":
                "yahoo"
        }

        # ====================================================
        # الحفظ
        # ====================================================

        (
            supabase
            .table("price_history")
            .insert(price_record)
            .execute()
        )

        print(
            "💾 تم حفظ الرصد في Supabase",
            flush=True
        )

        print(
            "🟢 انتهى الرصد بنجاح",
            flush=True
        )

        print(
            f"🕐 وقت الانتهاء: "
            f"{datetime.now(RIYADH_TZ).strftime('%H:%M:%S')}",
            flush=True
        )

        print(
            "=" * 75,
            flush=True
        )

    except Exception as e:

        print(
            "\n" + "=" * 75,
            flush=True
        )

        print(
            "🔴 حدث خطأ أثناء الرصد",
            flush=True
        )

        print(
            f"نوع الخطأ: "
            f"{type(e).__name__}",
            flush=True
        )

        print(
            f"التفاصيل: {e}",
            flush=True
        )

        print(
            "=" * 75,
            flush=True
        )

        raise


# ============================================================
# صفحة Render الرئيسية
# ============================================================

@app.route("/")
def home():

    return (
        "Saudi Stock Monitor is running. "
        f"Stock: {TICKER_SYMBOL}"
    )


# ============================================================
# تشغيل Flask فقط
# الجدولة أصبحت مسؤولية GitHub Actions
# ============================================================

if __name__ == "__main__":

    port = int(
        os.environ.get(
            "PORT",
            10000
        )
    )

    print(
        f"🟢 تشغيل Flask على المنفذ "
        f"{port}",
        flush=True
    )

    app.run(
        host="0.0.0.0",
        port=port
    )
