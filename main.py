import os
import requests
from datetime import datetime
from zoneinfo import ZoneInfo
from threading import Thread
from flask import Flask
from apscheduler.schedulers.background import BackgroundScheduler

app = Flask(__name__)

TICKER_SYMBOL = "2283.SR"
RIYADH_TZ = ZoneInfo("Asia/Riyadh")

YAHOO_URL = (
    f"https://query1.finance.yahoo.com/v8/finance/chart/"
    f"{TICKER_SYMBOL}"
)


def get_stock_data():

    print("🔵 الاتصال بـ Yahoo Chart API...", flush=True)

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

    data = response.json()

    return data


def analyze_market_snapshot():

    now = datetime.now(
        RIYADH_TZ
    ).strftime("%Y-%m-%d %H:%M:%S")

    print("\n" + "=" * 70, flush=True)

    print(
        "📊 اختبار المطاحن الأولى - 2283",
        flush=True
    )

    print(
        f"🕐 توقيت الرياض: {now}",
        flush=True
    )

    print(
        f"🔎 الرمز: {TICKER_SYMBOL}",
        flush=True
    )

    print("=" * 70, flush=True)

    try:

        data = get_stock_data()

        print(
            "🟢 تم استلام البيانات من Yahoo",
            flush=True
        )

        chart = data.get("chart", {})

        result = chart.get("result")

        if not result:

            print(
                "🔴 Yahoo لم يرجع نتيجة للسهم",
                flush=True
            )

            print(
                data,
                flush=True
            )

            return

        result = result[0]

        meta = result.get("meta", {})

        # ---------------------------------------------
        # البيانات الأساسية للسعر
        # ---------------------------------------------

        symbol = meta.get("symbol")

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

        print("\n" + "-" * 60, flush=True)

        print(
            "📌 بيانات السهم",
            flush=True
        )

        print("-" * 60, flush=True)

        print(
            f"🔹 الرمز: {symbol}",
            flush=True
        )

        print(
            f"💰 السعر الحالي: {current_price}",
            flush=True
        )

        print(
            f"📊 الإغلاق السابق: {previous_close}",
            flush=True
        )

        print(
            f"📊 إغلاق الرسم السابق: {chart_previous_close}",
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

        # ---------------------------------------------
        # حساب التغير
        # ---------------------------------------------

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

            print("\n" + "-" * 60)

            print(
                f"📈 التغير: {change:.2f} ريال",
                flush=True
            )

            print(
                f"📈 نسبة التغير: "
                f"{change_percent:.2f}%",
                flush=True
            )

        # ---------------------------------------------
        # آخر شمعة
        # ---------------------------------------------

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

            closes = quote.get(
                "close",
                []
            )

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

            volumes = quote.get(
                "volume",
                []
            )

            # آخر قيمة غير فارغة
            def last_valid(values):

                for value in reversed(values):

                    if value is not None:
                        return value

                return None

            last_close = last_valid(closes)
            last_open = last_valid(opens)
            last_high = last_valid(highs)
            last_low = last_valid(lows)
            last_volume = last_valid(volumes)

            print("\n" + "-" * 60)

            print(
                "🕯️ آخر بيانات دقيقة",
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

        print("\n" + "=" * 70)

        print(
            "🟢🟢🟢 نجح اختبار جلب البيانات 🟢🟢🟢",
            flush=True
        )

        print("=" * 70)

    except Exception as e:

        print("\n" + "=" * 70)

        print(
            "🔴 حدث خطأ",
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

        print("=" * 70)


@app.route("/")
def home():

    return (
        "Saudi Stock Monitor is running - "
        "2283.SR"
    )


def start_scheduler():

    scheduler = BackgroundScheduler(
        timezone=RIYADH_TZ
    )

    scheduler.add_job(
        analyze_market_snapshot,
        "interval",
        minutes=1,
        max_instances=1,
        coalesce=True
    )

    scheduler.start()

    print(
        "🟢 تم تشغيل المجدول",
        flush=True
    )

    print(
        "⏱️ سيتم فحص السهم كل دقيقة",
        flush=True
    )

    # اختبار مباشر عند التشغيل
    analyze_market_snapshot()


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
