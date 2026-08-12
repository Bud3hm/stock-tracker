import os
import requests

from datetime import datetime
from zoneinfo import ZoneInfo
from threading import Thread

from flask import Flask
from apscheduler.schedulers.background import BackgroundScheduler


app = Flask(__name__)

# ============================================================
# إعدادات السهم
# ============================================================

TICKER_SYMBOL = "2283.SR"

# تثبيت التوقيت على توقيت الرياض
RIYADH_TZ = ZoneInfo("Asia/Riyadh")

# Yahoo Chart API
YAHOO_URL = (
    f"https://query1.finance.yahoo.com/v8/finance/chart/"
    f"{TICKER_SYMBOL}"
)


# ============================================================
# جلب البيانات من Yahoo
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
        YAHOO_URL,
        params=params,
        headers=headers,
        timeout=10
    )

    print(
        f"🟢 Yahoo HTTP Status: {response.status_code}",
        flush=True
    )

    response.raise_for_status()

    return response.json()


# ============================================================
# تحليل وعرض بيانات الرصد
# ============================================================

def analyze_market_snapshot():

    # الوقت الحالي بتوقيت الرياض
    now_ksa = datetime.now(
        RIYADH_TZ
    )

    now_text = now_ksa.strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    print("\n" + "=" * 75, flush=True)

    print(
        "📊 رصد سهم المطاحن الأولى - 2283",
        flush=True
    )

    print(
        f"🕐 وقت الرصد - الرياض: {now_text}",
        flush=True
    )

    print(
        "⏱️ الرصد المجدول: كل 15 دقيقة",
        flush=True
    )

    print(
        f"🔎 الرمز: {TICKER_SYMBOL}",
        flush=True
    )

    print("=" * 75, flush=True)

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

            print(
                data,
                flush=True
            )

            return

        result = result[0]

        meta = result.get(
            "meta",
            {}
        )

        # ====================================================
        # البيانات الحالية
        # ====================================================

        symbol = meta.get(
            "symbol"
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

        print("\n📌 البيانات اللحظية", flush=True)

        print("-" * 60, flush=True)

        print(
            f"🔹 الرمز: {symbol}",
            flush=True
        )

        print(
            f"💰 السعر الحالي: {current_price} ريال",
            flush=True
        )

        print(
            f"📊 الإغلاق السابق: {previous_close} ريال",
            flush=True
        )

        print(
            f"📊 إغلاق الرسم السابق: "
            f"{chart_previous_close} ريال",
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
            f"📡 حالة السوق: {market_state}",
            flush=True
        )

        print(
            f"📋 نوع الأداة: {instrument_type}",
            flush=True
        )

        # ====================================================
        # حساب التغير
        # ====================================================

        if (
            isinstance(current_price, (int, float))
            and isinstance(previous_close, (int, float))
            and previous_close != 0
        ):

            change = (
                current_price -
                previous_close
            )

            change_percent = (
                change /
                previous_close
            ) * 100

            print("\n📈 التغير", flush=True)

            print("-" * 60, flush=True)

            print(
                f"💵 التغير: {change:+.2f} ريال",
                flush=True
            )

            print(
                f"📊 نسبة التغير: "
                f"{change_percent:+.2f}%",
                flush=True
            )

        # ====================================================
        # آخر بيانات دقيقة
        # ====================================================

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

            opens = quote.get(
                "open",
                []
            )

            highs = quote.get(
                "high",
                []
            )

            lows = quote.get(
                "low",
                []
            )

            closes = quote.get(
                "close",
                []
            )

            volumes = quote.get(
                "volume",
                []
            )

            def last_valid(values):

                for value in reversed(values):

                    if value is not None:
                        return value

                return None

            last_open = last_valid(opens)
            last_high = last_valid(highs)
            last_low = last_valid(lows)
            last_close = last_valid(closes)
            last_volume = last_valid(volumes)

            print(
                "\n🕯️ آخر بيانات دقيقة متاحة من Yahoo",
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
                f"حجم التداول: {last_volume}",
                flush=True
            )

        print("\n" + "=" * 75, flush=True)

        print(
            "🟢 تم جلب البيانات بنجاح",
            flush=True
        )

        print(
            f"🕐 انتهاء الرصد: "
            f"{datetime.now(RIYADH_TZ).strftime('%H:%M:%S')} "
            f"بتوقيت الرياض",
            flush=True
        )

        print("=" * 75, flush=True)

    except Exception as e:

        print("\n" + "=" * 75, flush=True)

        print(
            "🔴 حدث خطأ أثناء جلب البيانات",
            flush=True
        )

        print(
            f"نوع الخطأ: {type(e).__name__}",
            flush=True
        )

        print(
            f"التفاصيل: {e}",
            flush=True
        )

        print("=" * 75, flush=True)


# ============================================================
# الصفحة الرئيسية
# ============================================================

@app.route("/")
def home():

    return (
        "Saudi Stock Monitor is running. "
        "Stock: 2283.SR"
    )
# ============================================================
# اختبار البيانات المالية
# ============================================================

@app.route("/financial-test")
def financial_test():

    try:
        from financial_data import run_financial_test

        run_financial_test()

        return (
            "Financial data test completed successfully. "
            "Check Render Logs."
        )

    except Exception as e:

        print(
            f"🔴 Financial test error: "
            f"{type(e).__name__}: {e}",
            flush=True
        )

        return (
            f"Financial test error: "
            f"{type(e).__name__}: {e}"
        ), 500

# ============================================================
# جدولة الرصد
# ============================================================

def start_scheduler():

    scheduler = BackgroundScheduler(
        timezone=RIYADH_TZ
    )

    # --------------------------------------------------------
    # من 10:00 إلى 14:45
    # كل 15 دقيقة
    #
    # الأحد إلى الخميس
    # --------------------------------------------------------

    scheduler.add_job(
        analyze_market_snapshot,
        "cron",
        day_of_week="sun,mon,tue,wed,thu",
        hour="10-14",
        minute="0,15,30,45",
        second=0,
        max_instances=1,
        coalesce=True
    )

    # --------------------------------------------------------
    # الرصد الأخير عند 15:00
    # --------------------------------------------------------

    scheduler.add_job(
        analyze_market_snapshot,
        "cron",
        day_of_week="sun,mon,tue,wed,thu",
        hour=15,
        minute=0,
        second=0,
        max_instances=1,
        coalesce=True
    )

    scheduler.start()

    print("\n" + "=" * 75, flush=True)

    print(
        "🟢 تم تشغيل نظام مراقبة السهم",
        flush=True
    )

    print(
        "📌 السهم: المطاحن الأولى - 2283",
        flush=True
    )

    print(
        "📅 أيام الرصد: الأحد إلى الخميس",
        flush=True
    )

    print(
        "🕙 البداية: 10:00 صباحًا",
        flush=True
    )

    print(
        "🕒 النهاية: 15:00 مساءً",
        flush=True
    )

    print(
        "⏱️ الفاصل: كل 15 دقيقة",
        flush=True
    )

    print(
        "🇸🇦 جميع المواعيد محسوبة بتوقيت Asia/Riyadh",
        flush=True
    )

    print("=" * 75 + "\n", flush=True)


# ============================================================
# تشغيل البرنامج
# ============================================================

if __name__ == "__main__":

    scheduler_thread = Thread(
        target=start_scheduler,
        daemon=True
    )

    scheduler_thread.start()

    port = int(
        os.environ.get(
            "PORT",
            10000
        )
    )

    print(
        f"🟢 تشغيل Flask على المنفذ {port}",
        flush=True
    )

    app.run(
        host="0.0.0.0",
        port=port
    )
