import os
from datetime import datetime
from zoneinfo import ZoneInfo
from threading import Thread
from flask import Flask
from apscheduler.schedulers.blocking import BlockingScheduler
import yahooquery as yq

app = Flask(__name__)

TICKER_SYMBOL = "2283.SR"
RIYADH_TZ = ZoneInfo("Asia/Riyadh")


def analyze_market_snapshot(check_label="اختبار"):

    now_ksa = datetime.now(RIYADH_TZ).strftime("%Y-%m-%d %H:%M:%S")

    print("\n" + "=" * 70)
    print(f"📊 المطاحن الأولى - 2283")
    print(f"🕐 الوقت: {now_ksa}")
    print(f"🔎 الرمز: {TICKER_SYMBOL}")
    print(f"📌 نوع الفحص: {check_label}")
    print("=" * 70)

    # إنشاء الاتصال
    try:
        ticker = yq.Ticker(TICKER_SYMBOL)
        print("✅ تم الاتصال بـ YahooQuery")
    except Exception as e:
        print(f"❌ فشل الاتصال: {type(e).__name__}: {e}")
        return

    # --------------------------------------------------
    # السعر
    # --------------------------------------------------

    current_price = None

    try:
        print("\n💰 جلب السعر...")

        price_data = ticker.price

        print("📥 بيانات السعر:")
        print(price_data)

        if isinstance(price_data, dict):

            data = price_data.get(TICKER_SYMBOL, {})

            if isinstance(data, dict):

                current_price = data.get("regularMarketPrice")

                if current_price is not None:
                    print(f"✅ السعر الحالي: {current_price} ريال")
                else:
                    print("⚠️ لم يتم العثور على regularMarketPrice")

            else:
                print("❌ بيانات السهم ليست بالشكل المتوقع")

        else:
            print("❌ Yahoo لم يرجع بيانات صحيحة")

    except Exception as e:
        print(f"❌ خطأ السعر: {type(e).__name__}: {e}")

    # --------------------------------------------------
    # Key Stats
    # --------------------------------------------------

    eps = None
    book_value = None

    try:
        print("\n📊 جلب المؤشرات الأساسية...")

        stats_data = ticker.key_stats

        print("📥 Key Stats:")
        print(stats_data)

        if isinstance(stats_data, dict):

            stats = stats_data.get(TICKER_SYMBOL, {})

            if isinstance(stats, dict):

                eps = stats.get("trailingEps")
                book_value = stats.get("bookValue")

                print(f"📌 EPS: {eps}")
                print(f"📌 Book Value: {book_value}")

    except Exception as e:
        print(f"❌ خطأ Key Stats: {type(e).__name__}: {e}")

    # --------------------------------------------------
    # الحسابات
    # --------------------------------------------------

    print("\n🧮 الحسابات:")

    if (
        isinstance(current_price, (int, float))
        and isinstance(eps, (int, float))
        and eps > 0
    ):
        pe = current_price / eps
        print(f"📈 P/E: {pe:.2f}x")
    else:
        print("⚠️ لا يمكن حساب P/E")

    if (
        isinstance(current_price, (int, float))
        and isinstance(book_value, (int, float))
        and book_value > 0
    ):
        pb = current_price / book_value
        print(f"📚 P/B: {pb:.2f}x")
    else:
        print("⚠️ لا يمكن حساب P/B")

    print("\n" + "=" * 70)
    print("✅ انتهى الفحص - الانتظار للفحص القادم بعد دقيقة")
    print("=" * 70 + "\n")


@app.route("/")
def home():

    analyze_market_snapshot("فتح الصفحة")

    return "Saudi Stock Monitor is running."


def run_scheduler():

    scheduler = BlockingScheduler(
        timezone=RIYADH_TZ
    )

    # ================================================
    # فحص كل دقيقة
    # ================================================

    scheduler.add_job(
        analyze_market_snapshot,
        "interval",
        minutes=1,
        args=["فحص كل دقيقة"],
        max_instances=1,
        coalesce=True
    )

    # فحص فوري عند تشغيل السيرفر
    analyze_market_snapshot("تشغيل السيرفر")

    scheduler.start()


if __name__ == "__main__":

    t = Thread(
        target=run_scheduler,
        daemon=True
    )

    t.start()

    port = int(
        os.environ.get("PORT", 10000)
    )

    app.run(
        host="0.0.0.0",
        port=port
    )
