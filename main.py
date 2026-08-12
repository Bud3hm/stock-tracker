import datetime
import os
from threading import Thread
from apscheduler.schedulers.blocking import BlockingScheduler
from flask import Flask
import pandas as pd
import yahooquery as yq

app = Flask(__name__)


@app.route("/")
def home():
    return "Saudi Stock Monitor is Running Successfully!"


TICKER = "2283.SR"


def get_fundamental_benchmarks():
    try:
        ticker = yq.Ticker(TICKER)
        key_stats = ticker.key_stats
        if isinstance(key_stats, dict) and TICKER in key_stats:
            stats = key_stats.get(TICKER, {})
            if isinstance(stats, dict):
                eps = stats.get("trailingEps", None)
                book_value = stats.get("bookValue", None)
                return {"eps": eps, "book_value": book_value}
    except Exception as e:
        print(f"خطأ في جلب المؤشرات المالية الأساسية: {e}")
    return {"eps": None, "book_value": None}


def analyze_market_snapshot(check_label):
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    current_price = None

    try:
        ticker = yq.Ticker(TICKER)
        price_data = ticker.price
        if isinstance(price_data, dict) and TICKER in price_data:
            data = price_data.get(TICKER, {})
            if isinstance(data, dict):
                current_price = data.get("regularMarketPrice", None)
    except Exception as e:
        print(f"[{now}] خطأ أثناء جلب السعر: {e}")

    if not current_price or not isinstance(current_price, (int, float)):
        print(
            f"[{now}] ⚠️ تعذر جلب السعر اللحظي حالياً (قد يكون السوق مغلقاً أو السيرفر مشغول)."
        )
        return

    benchmarks = get_fundamental_benchmarks()
    book_value = benchmarks.get("book_value")
    eps = benchmarks.get("eps")

    print("\n" + "=" * 50)
    print(f"📌 رصد الجلسة - [{check_label}] - الوقت: {now}")
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


def run_scheduler():
    scheduler = BlockingScheduler(timezone="Asia/Riyadh")

    # جدولة كل 15 دقيقة طوال وقت الجلسة من 10:00 صباحاً إلى 02:45 ظهراً
    scheduler.add_job(
        analyze_market_snapshot,
        "cron",
        day_of_week="sun,mon,tue,wed,thu",
        hour="10-14",
        minute="0,15,30,45",
        args=["رصد دوري كل 15 دقيقة"],
    )

    # قراءة تجريبية فورية للتحقق
    analyze_market_snapshot("تشغيل تجريبي للتحقق من المواعيد")
    scheduler.start()


if __name__ == "__main__":
    t = Thread(target=run_scheduler)
    t.start()
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
