import datetime
import os
from threading import Thread
from apscheduler.schedulers.blocking import BlockingScheduler
from flask import Flask
import yahooquery as yq

app = Flask(__name__)

TICKER = "2283.SR"


def analyze_market_snapshot(check_label="رصد موعد"):
    now_ksa = (
        datetime.datetime.utcnow() + datetime.timedelta(hours=3)
    ).strftime("%Y-%m-%d %H:%M:%S")
    current_price = None

    try:
        ticker = yq.Ticker(TICKER)
        price_data = ticker.price
        if isinstance(price_data, dict) and TICKER in price_data:
            data = price_data.get(TICKER, {})
            if isinstance(data, dict):
                current_price = data.get("regularMarketPrice", None)
    except Exception as e:
        print(f"[{now_ksa}] خطأ أثناء جلب السعر: {e}")

    if not current_price or not isinstance(current_price, (int, float)):
        print(f"[{now_ksa}] ⚠️ تعذر جلب السعر اللحظي حالياً.")
        return

    # جلب المؤشرات الأساسية
    try:
        stats = ticker.key_stats.get(TICKER, {})
        eps = stats.get("trailingEps", None)
        book_value = stats.get("bookValue", None)
    except Exception:
        eps, book_value = None, None

    print("\n" + "=" * 50)
    print(f"📌 [المطاحن الأولى - 2283] - [{check_label}]")
    print(f"توقيت الرياض: {now_ksa}")
    print(f"السعر الحالي: {current_price} ريال")

    if book_value and isinstance(book_value, (int, float)):
        price_to_book = current_price / book_value
        print(f"القيمة الدفترية للسهم: {book_value:.2f} ريال")
        print(f"مضاعف القيمة الدفترية اللحظي (P/B): {price_to_book:.2f}x")

    if eps and isinstance(eps, (int, float)) and eps > 0:
        pe_ratio = current_price / eps
        print(f"ربحية السهم (EPS): {eps:.2f} ريال")
        print(f"مكرر الربحية اللحظي (P/E): {pe_ratio:.2f}x")

    print("=" * 50 + "\n")


@app.route("/")
def home():
    # عند فتح رابط الموقع أو زيارته، ينفذ رصد فوري فوراً
    analyze_market_snapshot("رصد مباشر عبر فتح الصفحة")
    return "Saudi Stock Monitor is Active and Running!"


def run_scheduler():
    scheduler = BlockingScheduler()

    # الساعات بتوقيت UTC (من 07:00 إلى 12:00 UTC تعادل 10:00 صباحاً إلى 3:00 عصراً بتوقيت الرياض)
    scheduler.add_job(
        analyze_market_snapshot,
        "cron",
        day_of_week="sun,mon,tue,wed,thu",
        hour="7-11",
        minute="0,15,30,45",
        args=["رصد دوري 15 دقيقة"],
    )
    scheduler.add_job(
        analyze_market_snapshot,
        "cron",
        day_of_week="sun,mon,tue,wed,thu",
        hour="12",
        minute="0",
        args=["رصد إغلاق السوق 3:00 عصراً"],
    )

    # تشغيل قراءة فورية أول ما يشتغل السكربت
    analyze_market_snapshot("رصد التشغيل الأولي")
    scheduler.start()


if __name__ == "__main__":
    t = Thread(target=run_scheduler)
    t.start()
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
