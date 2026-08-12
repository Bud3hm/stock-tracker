import os
from datetime import datetime
from zoneinfo import ZoneInfo
from threading import Thread
from concurrent.futures import ThreadPoolExecutor, TimeoutError

from flask import Flask
from apscheduler.schedulers.background import BackgroundScheduler
import yahooquery as yq


app = Flask(__name__)

TICKER_SYMBOL = "2283.SR"
RIYADH_TZ = ZoneInfo("Asia/Riyadh")


def get_yahoo_data():

    print("🔵 بدأ الاتصال بـ YahooQuery...", flush=True)

    ticker = yq.Ticker(TICKER_SYMBOL)

    print("🟢 تم إنشاء Ticker بنجاح", flush=True)

    print("🔵 الآن نحاول جلب السعر...", flush=True)

    price_data = ticker.price

    print("🟢 تم استلام بيانات السعر", flush=True)

    return price_data


def analyze_market_snapshot():

    now = datetime.now(RIYADH_TZ).strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    print("\n" + "=" * 70, flush=True)
    print("📊 اختبار المطاحن الأولى - 2283", flush=True)
    print(f"🕐 توقيت الرياض: {now}", flush=True)
    print(f"🔎 الرمز: {TICKER_SYMBOL}", flush=True)
    print("=" * 70, flush=True)

    # --------------------------------------------------
    # محاولة Yahoo بمهلة 10 ثوانٍ
    # --------------------------------------------------

    try:

        with ThreadPoolExecutor(max_workers=1) as executor:

            future = executor.submit(get_yahoo_data)

            try:

                price_data = future.result(timeout=10)

            except TimeoutError:

                print(
                    "🔴 YahooQuery لم يستجب خلال 10 ثوانٍ",
                    flush=True
                )

                return

        # --------------------------------------------------
        # عرض البيانات الخام
        # --------------------------------------------------

        print("\n📥 البيانات التي وصلت من Yahoo:", flush=True)
        print(price_data, flush=True)

        if not isinstance(price_data, dict):

            print(
                "🔴 Yahoo لم يرجع Dictionary",
                flush=True
            )

            return

        data = price_data.get(TICKER_SYMBOL)

        if not data:

            print(
                f"🔴 لم نجد {TICKER_SYMBOL} داخل البيانات",
                flush=True
            )

            print(
                f"المفاتيح الموجودة: {list(price_data.keys())}",
                flush=True
            )

            return

        # --------------------------------------------------
        # السعر
        # --------------------------------------------------

        current_price = data.get(
            "regularMarketPrice"
        )

        previous_close = data.get(
            "regularMarketPreviousClose"
        )

        market_state = data.get(
            "marketState"
        )

        currency = data.get(
            "currency"
        )

        print("\n" + "-" * 50, flush=True)
        print("📌 بيانات السهم", flush=True)
        print("-" * 50, flush=True)

        print(
            f"💰 السعر الحالي: {current_price}",
            flush=True
        )

        print(
            f"📊 إغلاق سابق: {previous_close}",
            flush=True
        )

        print(
            f"🏦 حالة السوق: {market_state}",
            flush=True
        )

        print(
            f"💵 العملة: {currency}",
            flush=True
        )

        print("-" * 50, flush=True)

        if (
            isinstance(current_price, (int, float))
            and isinstance(previous_close, (int, float))
            and previous_close != 0
        ):

            change = current_price - previous_close

            change_percent = (
                change / previous_close
            ) * 100

            print(
                f"📈 التغير: {change:.2f} ريال",
                flush=True
            )

            print(
                f"📈 نسبة التغير: {change_percent:.2f}%",
                flush=True
            )

        print(
            "\n🟢 انتهى الفحص بنجاح",
            flush=True
        )

    except Exception as e:

        print(
            "\n🔴 حدث خطأ:",
            flush=True
        )

        print(
            f"نوع الخطأ: {type(e).__name__}",
            flush=True
        )

        print(
            f"تفاصيل الخطأ: {e}",
            flush=True
        )


@app.route("/")
def home():

    return """
    Saudi Stock Monitor is running.
    Stock: 2283.SR
    """


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
        "🟢 تم تشغيل المجدول - فحص كل دقيقة",
        flush=True
    )

    # أول فحص مباشرة
    analyze_market_snapshot()


if __name__ == "__main__":

    # تشغيل المجدول في Thread منفصل
    scheduler_thread = Thread(
        target=start_scheduler,
        daemon=True
    )

    scheduler_thread.start()

    port = int(
        os.environ.get("PORT", 10000)
    )

    print(
        f"🟢 تشغيل Flask على المنفذ {port}",
        flush=True
    )

    app.run(
        host="0.0.0.0",
        port=port
    )
