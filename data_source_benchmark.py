import os
import re
import time
from datetime import datetime
from html import unescape
from html.parser import HTMLParser
from statistics import mean

import requests
from supabase import create_client

# ============================================================
# DATA SOURCE BENCHMARK v1.0
# READ ONLY
# Yahoo (Supabase) vs StockAnalysis candidate source.
# Does NOT write to Supabase.
# ============================================================

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_SECRET_KEY = os.environ.get("SUPABASE_SECRET_KEY")

if not SUPABASE_URL:
    raise RuntimeError("SUPABASE_URL is missing")
if not SUPABASE_SECRET_KEY:
    raise RuntimeError("SUPABASE_SECRET_KEY is missing")

supabase = create_client(SUPABASE_URL, SUPABASE_SECRET_KEY)

ENGINE_VERSION = "1.0"
BASE = "https://stockanalysis.com/quote/tadawul"
TIMEOUT = 25
DELAY = 1.0

TEST_SYMBOLS = [
    "2283.SR",  # المطاحن الأولى
    "4030.SR",  # البحري
    "7203.SR",  # علم
    "4190.SR",  # جرير
    "1150.SR",  # مصرف الإنماء
    "8010.SR",  # التعاونية
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

YAHOO_MAP = {
    "annualTotalRevenue": ("annual", "revenue"),
    "quarterlyTotalRevenue": ("quarterly", "revenue"),
    "annualGrossProfit": ("annual", "gross_profit"),
    "quarterlyGrossProfit": ("quarterly", "gross_profit"),
    "annualOperatingIncome": ("annual", "operating_income"),
    "quarterlyOperatingIncome": ("quarterly", "operating_income"),
    "annualNetIncome": ("annual", "net_income"),
    "quarterlyNetIncome": ("quarterly", "net_income"),
    "annualTotalAssets": ("annual", "total_assets"),
    "quarterlyTotalAssets": ("quarterly", "total_assets"),
    "annualTotalLiabilitiesNetMinorityInterest": ("annual", "total_liabilities"),
    "quarterlyTotalLiabilitiesNetMinorityInterest": ("quarterly", "total_liabilities"),
    "annualStockholdersEquity": ("annual", "stockholders_equity"),
    "quarterlyStockholdersEquity": ("quarterly", "stockholders_equity"),
    "annualOperatingCashFlow": ("annual", "operating_cash_flow"),
    "quarterlyOperatingCashFlow": ("quarterly", "operating_cash_flow"),
    "annualCapitalExpenditure": ("annual", "capital_expenditure"),
    "quarterlyCapitalExpenditure": ("quarterly", "capital_expenditure"),
    "annualFreeCashFlow": ("annual", "free_cash_flow"),
    "quarterlyFreeCashFlow": ("quarterly", "free_cash_flow"),
}

ALIASES = {
    "revenue": ["revenue", "total revenue"],
    "gross_profit": ["gross profit"],
    "operating_income": ["operating income", "operating profit"],
    "net_income": [
        "net income",
        "net income to common",
        "net income available to common shareholders",
    ],
    "total_assets": ["total assets"],
    "total_liabilities": ["total liabilities"],
    "stockholders_equity": [
        "shareholders' equity",
        "shareholders equity",
        "stockholders' equity",
        "stockholders equity",
        "total equity",
        "common equity",
    ],
    "operating_cash_flow": [
        "operating cash flow",
        "cash from operating activities",
        "cash flow from operations",
    ],
    "capital_expenditure": ["capital expenditures", "capital expenditure", "capex"],
    "free_cash_flow": ["free cash flow"],
}


def safe_number(value):
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", "").replace("SAR", "")
    text = text.replace("−", "-").replace("—", "").strip()
    if not text or text in {"-", "--", "N/A", "n/a"} or "%" in text:
        return None
    mult = 1.0
    if text.endswith("T"):
        mult, text = 1e12, text[:-1]
    elif text.endswith("B"):
        mult, text = 1e9, text[:-1]
    elif text.endswith("M"):
        mult, text = 1e6, text[:-1]
    elif text.endswith("K"):
        mult, text = 1e3, text[:-1]
    try:
        return float(text) * mult
    except (TypeError, ValueError):
        return None


def fmt_money(value):
    value = safe_number(value)
    if value is None:
        return "N/A"
    a = abs(value)
    if a >= 1e9:
        return f"{value / 1e9:.3f}B"
    if a >= 1e6:
        return f"{value / 1e6:.3f}M"
    if a >= 1e3:
        return f"{value / 1e3:.3f}K"
    return f"{value:.2f}"


def print_header(title):
    print("\n" + "=" * 96, flush=True)
    print(title, flush=True)
    print("=" * 96, flush=True)


def normalize_label(text):
    text = unescape(str(text or ""))
    text = re.sub(r"\s+", " ", text).strip().lower()
    return re.sub(r"\s+growth$", "", text).strip()


def canonical_label(label):
    label = normalize_label(label)
    for canonical, aliases in ALIASES.items():
        if label in aliases:
            return canonical
    return None


def period_to_date(label):
    text = str(label or "").replace("’", "'").strip()
    m = re.search(
        r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+'?(\d{2,4})\b",
        text,
        re.I,
    )
    if not m:
        return None
    mon = m.group(1).title()
    year = int(m.group(2))
    if year < 100:
        year += 2000
    md = {
        "Jan": (1, 31), "Feb": (2, 28), "Mar": (3, 31), "Apr": (4, 30),
        "May": (5, 31), "Jun": (6, 30), "Jul": (7, 31), "Aug": (8, 31),
        "Sep": (9, 30), "Oct": (10, 31), "Nov": (11, 30), "Dec": (12, 31),
    }
    month, day = md[mon]
    if month == 2 and year % 4 == 0 and (year % 100 != 0 or year % 400 == 0):
        day = 29
    return f"{year:04d}-{month:02d}-{day:02d}"


def diff_pct(a, b):
    a, b = safe_number(a), safe_number(b)
    if a is None or b is None:
        return None
    return abs(a - b) / max(abs(a), abs(b), 1.0) * 100.0


def status_for(diff):
    if diff is None:
        return "NO_COMPARE"
    if diff <= 0.5:
        return "EXCELLENT"
    if diff <= 2.0:
        return "GOOD"
    if diff <= 5.0:
        return "REVIEW"
    return "CONFLICT"


class TableParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tables = []
        self.table = None
        self.row = None
        self.cell = None

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag == "table" and self.table is None:
            self.table = []
        elif self.table is not None and tag == "tr":
            self.row = []
        elif self.row is not None and tag in ("td", "th"):
            self.cell = []
        elif self.cell is not None and tag == "br":
            self.cell.append(" ")

    def handle_data(self, data):
        if self.cell is not None:
            self.cell.append(data)

    def handle_endtag(self, tag):
        tag = tag.lower()
        if self.cell is not None and tag in ("td", "th"):
            text = re.sub(r"\s+", " ", unescape("".join(self.cell))).strip()
            self.row.append(text)
            self.cell = None
        elif self.row is not None and tag == "tr":
            if self.row:
                self.table.append(self.row)
            self.row = None
        elif self.table is not None and tag == "table":
            if self.table:
                self.tables.append(self.table)
            self.table = None


def get_test_stocks():
    r = (
        supabase.table("stocks")
        .select("id,symbol,company_name,analysis_model,is_active")
        .in_("symbol", TEST_SYMBOLS)
        .execute()
    )
    by_symbol = {x["symbol"]: x for x in (r.data or [])}
    return [by_symbol[s] for s in TEST_SYMBOLS if s in by_symbol]


def get_yahoo_rows(stock_id):
    r = (
        supabase.table("financial_statements")
        .select("metric,period_end,period_type,value,currency,source")
        .eq("stock_id", stock_id)
        .eq("source", "yahoo")
        .execute()
    )
    return r.data or []


def build_yahoo(rows):
    out = {}
    for row in rows:
        mapping = YAHOO_MAP.get(row.get("metric"))
        if not mapping:
            continue
        frequency, metric = mapping
        period = str(row.get("period_end") or "")
        value = safe_number(row.get("value"))
        if period and value is not None:
            out[(frequency, period, metric)] = value
    return out


def fetch_html(symbol, page, quarterly=False):
    code = symbol.split(".")[0]
    paths = {
        "income": "financials/",
        "balance": "financials/balance-sheet/",
        "cash": "financials/cash-flow-statement/",
    }
    url = f"{BASE}/{code}/{paths[page]}"
    if quarterly:
        url += "?p=quarterly"
    r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    print(
        f"🌐 {symbol} | {page} | {'quarterly' if quarterly else 'annual'} | HTTP {r.status_code}",
        flush=True,
    )
    r.raise_for_status()
    return r.text


def parse_tables(html_text, frequency):
    parser = TableParser()
    parser.feed(html_text)
    lower = re.sub(r"\s+", " ", html_text).lower()
    multiplier = 1e6 if "millions sar" in lower else (1e3 if "thousands sar" in lower else 1.0)
    output = {}

    for table in parser.tables:
        period_cols = []
        for row in table:
            if row and normalize_label(row[0]).startswith("period ending"):
                period_cols = [
                    (idx, period_to_date(label))
                    for idx, label in enumerate(row[1:], start=1)
                ]
                break
        if not period_cols:
            continue

        for row in table:
            if len(row) < 2:
                continue
            metric = canonical_label(row[0])
            if not metric:
                continue
            for idx, period in period_cols:
                if not period or idx >= len(row):
                    continue
                value = safe_number(row[idx])
                if value is not None:
                    output[(frequency, period, metric)] = value * multiplier
    return output


def get_stockanalysis(symbol):
    out = {}
    for frequency, quarterly in (("annual", False), ("quarterly", True)):
        for page in ("income", "balance", "cash"):
            try:
                html_text = fetch_html(symbol, page, quarterly)
                out.update(parse_tables(html_text, frequency))
            except Exception as e:
                print(
                    f"🟠 {symbol} | {page} | {frequency} | {type(e).__name__}: {e}",
                    flush=True,
                )
            time.sleep(0.35)
    return out


def compare(yahoo, sa):
    rows = []
    for key in sorted(set(yahoo) | set(sa)):
        y = yahoo.get(key)
        s = sa.get(key)
        d = diff_pct(y, s)
        rows.append({
            "key": key,
            "yahoo": y,
            "sa": s,
            "diff": d,
            "status": status_for(d),
        })
    return rows


def summarize(rows):
    common = [r for r in rows if r["yahoo"] is not None and r["sa"] is not None]
    counts = {k: sum(1 for r in common if r["status"] == k) for k in ("EXCELLENT", "GOOD", "REVIEW", "CONFLICT")}
    points = {"EXCELLENT": 100, "GOOD": 85, "REVIEW": 55, "CONFLICT": 0}
    score = mean([points[r["status"]] for r in common]) if common else 0.0
    avg_diff = mean([r["diff"] for r in common if r["diff"] is not None]) if common else None
    return common, counts, score, avg_diff


def run():
    print_header(f"🧪 DATA SOURCE BENCHMARK v{ENGINE_VERSION}")
    print("🔒 READ ONLY", flush=True)
    print("🅰️ Yahoo: existing Supabase financial_statements", flush=True)
    print("🅱️ StockAnalysis: candidate source", flush=True)
    print(f"🕐 Started: {datetime.now().isoformat()}", flush=True)

    stocks = get_test_stocks()
    print(f"🏢 Test Companies: {len(stocks)}/{len(TEST_SYMBOLS)}", flush=True)
    if not stocks:
        raise RuntimeError("No test stocks found")

    final = []
    for i, stock in enumerate(stocks, start=1):
        symbol = stock["symbol"]
        name = stock.get("company_name") or symbol
        model = stock.get("analysis_model") or "standard"
        print_header(f"🚦 {i}/{len(stocks)} | {symbol} | {name} | {model}")

        yahoo = build_yahoo(get_yahoo_rows(stock["id"]))
        sa = get_stockanalysis(symbol)
        rows = compare(yahoo, sa)
        common, counts, score, avg_diff = summarize(rows)

        print(f"📦 Yahoo Canonical Values: {len(yahoo)}", flush=True)
        print(f"📦 StockAnalysis Canonical Values: {len(sa)}", flush=True)
        print(f"🤝 Common Comparable Values: {len(common)}", flush=True)
        print(f"🏆 Agreement Score: {score:.2f}/100", flush=True)
        print(f"📏 Average Difference: {avg_diff:.2f}%" if avg_diff is not None else "📏 Average Difference: N/A", flush=True)
        print(
            f"🟢 Excellent={counts['EXCELLENT']} | 🔵 Good={counts['GOOD']} | "
            f"🟡 Review={counts['REVIEW']} | 🔴 Conflict={counts['CONFLICT']}",
            flush=True,
        )

        problems = sorted(
            [r for r in common if r["status"] in ("REVIEW", "CONFLICT")],
            key=lambda r: r["diff"],
            reverse=True,
        )
        if problems:
            print("\n⚠️ أهم الاختلافات:", flush=True)
            for r in problems[:12]:
                frequency, period, metric = r["key"]
                print(
                    f"- {frequency} | {period} | {metric} | "
                    f"Yahoo={fmt_money(r['yahoo'])} | StockAnalysis={fmt_money(r['sa'])} | "
                    f"Diff={r['diff']:.2f}% | {r['status']}",
                    flush=True,
                )
        else:
            print("✅ لا توجد اختلافات كبيرة في القيم المشتركة.", flush=True)

        final.append({
            "symbol": symbol,
            "name": name,
            "model": model,
            "common": len(common),
            "score": score,
            "avg_diff": avg_diff,
            **counts,
        })
        time.sleep(DELAY)

    print_header(f"🏁 DATA SOURCE BENCHMARK v{ENGINE_VERSION} SUMMARY")
    for idx, x in enumerate(final, start=1):
        avg_text = f"{x['avg_diff']:.2f}%" if x["avg_diff"] is not None else "N/A"
        print(
            f"{idx:02d}. {x['symbol']} | {x['name']} | {x['model']} | "
            f"Common={x['common']} | Agreement={x['score']:.2f} | AvgDiff={avg_text} | "
            f"Excellent={x['EXCELLENT']} | Good={x['GOOD']} | Review={x['REVIEW']} | Conflict={x['CONFLICT']}",
            flush=True,
        )

    total_common = sum(x["common"] for x in final)
    weighted = []
    for x in final:
        weighted.extend([x["score"]] * x["common"])
    overall = mean(weighted) if weighted else 0.0

    print("-" * 96, flush=True)
    print(f"🏢 Companies Tested: {len(final)}", flush=True)
    print(f"🤝 Total Comparable Values: {total_common}", flush=True)
    print(f"🏆 Overall Agreement Score: {overall:.2f}/100", flush=True)
    print("\n📌 هذا الاختبار لا يعتمد StockAnalysis كمصدر حقيقة.", flush=True)
    print("📌 بعد نجاحه نأخذ عينة من القيم ونطابقها مع تداول/الإعلانات الرسمية يدويًا أو عبر الويب.", flush=True)
    print("📌 لا يتم حفظ أو تعديل أي بيانات بواسطة هذا الملف.", flush=True)
    print("=" * 96, flush=True)


if __name__ == "__main__":
    run()
