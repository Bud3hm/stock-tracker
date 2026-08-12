import datetime
import os
from threading import Thread
from apscheduler.schedulers.blocking import BlockingScheduler
from flask import Flask
import pandas as pd
import yahooquery as yq

# خادم ويب بسيط لتشغيل الخطة المجانية على Render
app = Flask(__name__)


@app.route("/")
def home():
    return "Saudi Stock Monitor is Running Successfully!"


TICKER = "2283.SR"


def get_fundamental_benchmarks():
    ticker = yq.Ticker(TICKER)
    key_stats = ticker.key_stats.get(TICKER, {})
    eps = key_stats.get("trailingEps", None)
    book_value = key_stats.get("bookValue", None)
    return {"eps": eps, "book_value": book_value}


def analyze_market_snapshot(check_label):
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ticker = yq.Ticker(TICKER)
    price_data = ticker.price.get(TICKER, {})
    current_price = price_data.get("regularMarketPrice", None)

    if not current_price:
        print(f"[{now}] تعذر جلب السعر اللحظي.")
        return

    benchmarks = get_fundamental_benchmarks()
    book_value = benchmarks.get("book_value")
    eps = benchmarks.get("eps")

    print("\n" + "=" * 50)
    print(f"📌 رصد الجلسة - [{check_label}] - الوقت: {now}")
    print(f"السعر الحالي: {current_price} ريال")

    if book_value:
        price_to_book = current_price / book_value
        print(f"القيمة الدفترية للسهم: {book_value:.2f} ريال")
        print(f"مضاعف القيمة الدفترية اللحظي (P/B): {price_to_book:.2f}x")

    if eps and eps > 0:
        pe_ratio = current_price / eps
        print(f"ربحية السهم (EPS): {eps:.2f} ريال")
        print(f"مكرر الربحية اللحظي (P/E): {pe_ratio:.2f}x")

    print("=" * 50 + "\n")


def run_scheduler():
    scheduler = BlockingScheduler(timezone="Asia/Riyadh")
    # التوقيت: 11:00 صباحاً | 12:30 ظهراً | 02:00 ظهراً
    scheduler.add_job(
        analyze_market_snapshot,
        "cron",
        day_of_week="sun,mon,tue,wed,thu",
        hour=11,
        minute=0,
        args=["بعد بداية الجلسة بساعة"],
    )
    scheduler.add_job(
        analyze_market_snapshot,
        "cron",
        day_of_week="sun,mon,tue,wed,thu",
        hour=12,
        minute=30,
        args=["منتصف الجلسة"],
    )
    scheduler.add_job(
        analyze_market_snapshot,
        "cron",
        day_of_week="sun,mon,tue,wed,thu",
        hour=14,
        minute=0,
        args=["قبل نهاية الجلسة بساعة"],
    )
    analyze_market_snapshot("تشغيل تجريبي أول عند الإطلاق")
    scheduler.start()


if __name__ == "__main__":
    t = Thread(target=run_scheduler)
    t.start()
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
