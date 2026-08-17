import os
import re
import time
from collections import defaultdict
from datetime import datetime
from html import unescape
from html.parser import HTMLParser
from statistics import mean, median, pstdev

import requests
from supabase import create_client


# ============================================================
# DATA SOURCE BENCHMARK v1.1
# READ ONLY
#
# Yahoo (Supabase) vs StockAnalysis candidate source.
#
# v1.1:
# - Model-aware comparison by analysis_model
# - Bank/Insurance are not judged by OCF / FCF / CapEx
# - Detects scale/period anomalies such as ~2x / ~0.5x
# - Detects systematic repeated definition bias
# - Does NOT write to Supabase
# ============================================================


SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_SECRET_KEY = os.environ.get("SUPABASE_SECRET_KEY")

if not SUPABASE_URL:
    raise RuntimeError("SUPABASE_URL is missing")

if not SUPABASE_SECRET_KEY:
    raise RuntimeError("SUPABASE_SECRET_KEY is missing")

supabase = create_client(
    SUPABASE_URL,
    SUPABASE_SECRET_KEY
)


ENGINE_VERSION = "1.1"
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

EXCELLENT_LIMIT = 0.50
GOOD_LIMIT = 2.00
REVIEW_LIMIT = 5.00


# ============================================================
# Yahoo -> Canonical
# ============================================================

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

    "annualTotalLiabilitiesNetMinorityInterest":
        ("annual", "total_liabilities"),
    "quarterlyTotalLiabilitiesNetMinorityInterest":
        ("quarterly", "total_liabilities"),

    "annualStockholdersEquity":
        ("annual", "stockholders_equity"),
    "quarterlyStockholdersEquity":
        ("quarterly", "stockholders_equity"),

    "annualOperatingCashFlow":
        ("annual", "operating_cash_flow"),
    "quarterlyOperatingCashFlow":
        ("quarterly", "operating_cash_flow"),

    "annualCapitalExpenditure":
        ("annual", "capital_expenditure"),
    "quarterlyCapitalExpenditure":
        ("quarterly", "capital_expenditure"),

    "annualFreeCashFlow":
        ("annual", "free_cash_flow"),
    "quarterlyFreeCashFlow":
        ("quarterly", "free_cash_flow"),
}


# ============================================================
# StockAnalysis -> Canonical aliases
# ============================================================

ALIASES = {
    "revenue": [
        "revenue",
        "total revenue",
    ],

    "gross_profit": [
        "gross profit",
    ],

    "operating_income": [
        "operating income",
        "operating profit",
    ],

    "net_income": [
        "net income",
        "net income to common",
        "net income available to common shareholders",
    ],

    "total_assets": [
        "total assets",
    ],

    "total_liabilities": [
        "total liabilities",
    ],

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

    "capital_expenditure": [
        "capital expenditures",
        "capital expenditure",
        "capex",
    ],

    "free_cash_flow": [
        "free cash flow",
    ],
}


# ============================================================
# Model-aware comparison rules
#
# Standard:
# Compare all currently mapped fields.
#
# Bank:
# Do NOT judge provider quality using traditional OCF/FCF/CapEx.
#
# Insurance:
# Same rule for now. Specialized mapping can be expanded later.
# ============================================================

MODEL_COMPARISON_METRICS = {
    "standard": {
        "revenue",
        "gross_profit",
        "operating_income",
        "net_income",
        "total_assets",
        "total_liabilities",
        "stockholders_equity",
        "operating_cash_flow",
        "capital_expenditure",
        "free_cash_flow",
    },

    "bank": {
        "revenue",
        "operating_income",
        "net_income",
        "total_assets",
        "total_liabilities",
        "stockholders_equity",
    },

    "insurance": {
        "revenue",
        "operating_income",
        "net_income",
        "total_assets",
        "total_liabilities",
        "stockholders_equity",
    },
}


# ============================================================
# Helpers
# ============================================================

def safe_number(value):
    if value is None:
        return None

    if isinstance(value, (int, float)):
        return float(value)

    text = (
        str(value)
        .strip()
        .replace(",", "")
        .replace("SAR", "")
        .replace("−", "-")
        .replace("—", "")
        .strip()
    )

    if (
        not text
        or text in {"-", "--", "N/A", "n/a"}
        or "%" in text
    ):
        return None

    multiplier = 1.0

    if text.endswith("T"):
        multiplier, text = 1e12, text[:-1]

    elif text.endswith("B"):
        multiplier, text = 1e9, text[:-1]

    elif text.endswith("M"):
        multiplier, text = 1e6, text[:-1]

    elif text.endswith("K"):
        multiplier, text = 1e3, text[:-1]

    try:
        return float(text) * multiplier

    except (TypeError, ValueError):
        return None


def fmt_money(value):
    value = safe_number(value)

    if value is None:
        return "N/A"

    absolute = abs(value)

    if absolute >= 1e12:
        return f"{value / 1e12:.3f}T"

    if absolute >= 1e9:
        return f"{value / 1e9:.3f}B"

    if absolute >= 1e6:
        return f"{value / 1e6:.3f}M"

    if absolute >= 1e3:
        return f"{value / 1e3:.3f}K"

    return f"{value:.2f}"


def print_header(title):
    print(
        "\n" + "=" * 100,
        flush=True
    )
    print(title, flush=True)
    print("=" * 100, flush=True)


def normalize_label(text):
    text = unescape(
        str(text or "")
    )

    text = re.sub(
        r"\s+",
        " ",
        text
    ).strip().lower()

    return re.sub(
        r"\s+growth$",
        "",
        text
    ).strip()


def canonical_label(label):
    label = normalize_label(label)

    for canonical, aliases in ALIASES.items():
        if label in aliases:
            return canonical

    return None


def period_to_date(label):
    text = (
        str(label or "")
        .replace("’", "'")
        .strip()
    )

    match = re.search(
        r"\b"
        r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)"
        r"\s+'?(\d{2,4})\b",
        text,
        re.I,
    )

    if not match:
        return None

    month_name = match.group(1).title()

    year = int(
        match.group(2)
    )

    if year < 100:
        year += 2000

    month_days = {
        "Jan": (1, 31),
        "Feb": (2, 28),
        "Mar": (3, 31),
        "Apr": (4, 30),
        "May": (5, 31),
        "Jun": (6, 30),
        "Jul": (7, 31),
        "Aug": (8, 31),
        "Sep": (9, 30),
        "Oct": (10, 31),
        "Nov": (11, 30),
        "Dec": (12, 31),
    }

    month, day = month_days[
        month_name
    ]

    if (
        month == 2
        and year % 4 == 0
        and (
            year % 100 != 0
            or year % 400 == 0
        )
    ):
        day = 29

    return (
        f"{year:04d}-"
        f"{month:02d}-"
        f"{day:02d}"
    )


def diff_pct(a, b):
    a = safe_number(a)
    b = safe_number(b)

    if a is None or b is None:
        return None

    return (
        abs(a - b)
        / max(
            abs(a),
            abs(b),
            1.0
        )
        * 100.0
    )


def signed_pct_difference(
    reference,
    candidate
):
    reference = safe_number(
        reference
    )

    candidate = safe_number(
        candidate
    )

    if (
        reference is None
        or candidate is None
        or abs(reference) < 1e-9
    ):
        return None

    return (
        (candidate - reference)
        / abs(reference)
        * 100.0
    )


def ratio_value(
    yahoo,
    stockanalysis
):
    yahoo = safe_number(
        yahoo
    )

    stockanalysis = safe_number(
        stockanalysis
    )

    if (
        yahoo is None
        or stockanalysis is None
        or abs(yahoo) < 1e-9
    ):
        return None

    return (
        stockanalysis
        / yahoo
    )


def status_for(diff):
    if diff is None:
        return "NO_COMPARE"

    if diff <= EXCELLENT_LIMIT:
        return "EXCELLENT"

    if diff <= GOOD_LIMIT:
        return "GOOD"

    if diff <= REVIEW_LIMIT:
        return "REVIEW"

    return "CONFLICT"


# ============================================================
# HTML parser
# ============================================================

class TableParser(HTMLParser):
    def __init__(self):
        super().__init__()

        self.tables = []
        self.table = None
        self.row = None
        self.cell = None

    def handle_starttag(
        self,
        tag,
        attrs
    ):
        tag = tag.lower()

        if (
            tag == "table"
            and self.table is None
        ):
            self.table = []

        elif (
            self.table is not None
            and tag == "tr"
        ):
            self.row = []

        elif (
            self.row is not None
            and tag in ("td", "th")
        ):
            self.cell = []

        elif (
            self.cell is not None
            and tag == "br"
        ):
            self.cell.append(" ")

    def handle_data(
        self,
        data
    ):
        if self.cell is not None:
            self.cell.append(data)

    def handle_endtag(
        self,
        tag
    ):
        tag = tag.lower()

        if (
            self.cell is not None
            and tag in ("td", "th")
        ):
            text = re.sub(
                r"\s+",
                " ",
                unescape(
                    "".join(self.cell)
                )
            ).strip()

            self.row.append(text)
            self.cell = None

        elif (
            self.row is not None
            and tag == "tr"
        ):
            if self.row:
                self.table.append(
                    self.row
                )

            self.row = None

        elif (
            self.table is not None
            and tag == "table"
        ):
            if self.table:
                self.tables.append(
                    self.table
                )

            self.table = None


# ============================================================
# Supabase reads
# ============================================================

def get_test_stocks():
    response = (
        supabase
        .table("stocks")
        .select(
            "id,"
            "symbol,"
            "company_name,"
            "analysis_model,"
            "is_active"
        )
        .in_(
            "symbol",
            TEST_SYMBOLS
        )
        .execute()
    )

    by_symbol = {
        row["symbol"]: row
        for row in (
            response.data
            or []
        )
    }

    return [
        by_symbol[symbol]
        for symbol in TEST_SYMBOLS
        if symbol in by_symbol
    ]


def get_yahoo_rows(stock_id):
    response = (
        supabase
        .table("financial_statements")
        .select(
            "metric,"
            "period_end,"
            "period_type,"
            "value,"
            "currency,"
            "source"
        )
        .eq(
            "stock_id",
            stock_id
        )
        .eq(
            "source",
            "yahoo"
        )
        .execute()
    )

    return (
        response.data
        or []
    )


# ============================================================
# Yahoo canonical
# ============================================================

def build_yahoo(rows):
    output = {}

    for row in rows:
        mapping = YAHOO_MAP.get(
            row.get("metric")
        )

        if not mapping:
            continue

        frequency, metric = mapping

        period = str(
            row.get("period_end")
            or ""
        )

        value = safe_number(
            row.get("value")
        )

        if (
            period
            and value is not None
        ):
            output[
                (
                    frequency,
                    period,
                    metric
                )
            ] = value

    return output


# ============================================================
# StockAnalysis fetch / parse
# ============================================================

def fetch_html(
    symbol,
    page,
    quarterly=False
):
    code = symbol.split(".")[0]

    paths = {
        "income":
            "financials/",

        "balance":
            "financials/balance-sheet/",

        "cash":
            "financials/cash-flow-statement/",
    }

    url = (
        f"{BASE}/"
        f"{code}/"
        f"{paths[page]}"
    )

    if quarterly:
        url += "?p=quarterly"

    response = requests.get(
        url,
        headers=HEADERS,
        timeout=TIMEOUT
    )

    print(
        f"🌐 {symbol} | "
        f"{page} | "
        f"{'quarterly' if quarterly else 'annual'} | "
        f"HTTP {response.status_code}",
        flush=True
    )

    response.raise_for_status()

    return response.text


def parse_tables(
    html_text,
    frequency
):
    parser = TableParser()

    parser.feed(
        html_text
    )

    lower = re.sub(
        r"\s+",
        " ",
        html_text
    ).lower()

    if "millions sar" in lower:
        multiplier = 1e6

    elif "thousands sar" in lower:
        multiplier = 1e3

    else:
        multiplier = 1.0

    output = {}

    for table in parser.tables:
        period_columns = []

        for row in table:
            if (
                row
                and normalize_label(
                    row[0]
                ).startswith(
                    "period ending"
                )
            ):
                period_columns = [
                    (
                        index,
                        period_to_date(label)
                    )
                    for index, label
                    in enumerate(
                        row[1:],
                        start=1
                    )
                ]
                break

        if not period_columns:
            continue

        for row in table:
            if len(row) < 2:
                continue

            metric = canonical_label(
                row[0]
            )

            if not metric:
                continue

            for index, period in period_columns:
                if (
                    not period
                    or index >= len(row)
                ):
                    continue

                value = safe_number(
                    row[index]
                )

                if value is not None:
                    output[
                        (
                            frequency,
                            period,
                            metric
                        )
                    ] = (
                        value
                        * multiplier
                    )

    return output


def get_stockanalysis(symbol):
    output = {}

    for frequency, quarterly in (
        ("annual", False),
        ("quarterly", True),
    ):
        for page in (
            "income",
            "balance",
            "cash"
        ):
            try:
                html_text = fetch_html(
                    symbol,
                    page,
                    quarterly
                )

                output.update(
                    parse_tables(
                        html_text,
                        frequency
                    )
                )

            except Exception as error:
                print(
                    f"🟠 {symbol} | "
                    f"{page} | "
                    f"{frequency} | "
                    f"{type(error).__name__}: "
                    f"{error}",
                    flush=True
                )

            time.sleep(
                0.35
            )

    return output


# ============================================================
# Model-aware comparison
# ============================================================

def get_allowed_metrics(
    analysis_model
):
    return (
        MODEL_COMPARISON_METRICS.get(
            analysis_model,
            MODEL_COMPARISON_METRICS[
                "standard"
            ]
        )
    )


def compare(
    yahoo,
    stockanalysis,
    analysis_model
):
    rows = []
    excluded = []

    allowed_metrics = (
        get_allowed_metrics(
            analysis_model
        )
    )

    all_keys = sorted(
        set(yahoo)
        | set(stockanalysis)
    )

    for key in all_keys:
        _, _, metric = key

        yahoo_value = yahoo.get(key)
        sa_value = stockanalysis.get(key)

        if metric not in allowed_metrics:
            excluded.append({
                "key": key,
                "yahoo": yahoo_value,
                "sa": sa_value,
            })
            continue

        difference = diff_pct(
            yahoo_value,
            sa_value
        )

        rows.append({
            "key": key,
            "yahoo": yahoo_value,
            "sa": sa_value,
            "diff": difference,
            "signed_diff":
                signed_pct_difference(
                    yahoo_value,
                    sa_value
                ),
            "ratio":
                ratio_value(
                    yahoo_value,
                    sa_value
                ),
            "status":
                status_for(
                    difference
                ),
        })

    return (
        rows,
        excluded
    )


# ============================================================
# Diagnostics
# ============================================================

def detect_scale_anomalies(rows):
    anomalies = []

    target_ratios = [
        0.25,
        0.50,
        2.00,
        4.00,
    ]

    tolerance = 0.03

    for row in rows:
        if row["status"] != "CONFLICT":
            continue

        ratio = row.get("ratio")

        if ratio is None:
            continue

        abs_ratio = abs(ratio)

        for target in target_ratios:
            if (
                abs(
                    abs_ratio
                    - target
                )
                <= target
                * tolerance
            ):
                frequency, period, metric = (
                    row["key"]
                )

                anomalies.append({
                    "frequency": frequency,
                    "period": period,
                    "metric": metric,
                    "ratio": ratio,
                    "target_ratio": target,
                    "yahoo": row["yahoo"],
                    "sa": row["sa"],
                })
                break

    return anomalies


def detect_systematic_bias(rows):
    grouped = defaultdict(list)

    for row in rows:
        if (
            row["yahoo"] is None
            or row["sa"] is None
            or row["signed_diff"] is None
            or row["ratio"] is None
        ):
            continue

        _, _, metric = row["key"]

        grouped[
            metric
        ].append(
            row
        )

    findings = []

    for metric, metric_rows in (
        grouped.items()
    ):
        if len(metric_rows) < 4:
            continue

        signed_diffs = [
            row["signed_diff"]
            for row in metric_rows
        ]

        ratios = [
            row["ratio"]
            for row in metric_rows
        ]

        med_diff = median(
            signed_diffs
        )

        med_ratio = median(
            ratios
        )

        std_diff = (
            pstdev(
                signed_diffs
            )
            if len(
                signed_diffs
            ) > 1
            else 0.0
        )

        same_direction = (
            all(
                value > 0
                for value in signed_diffs
            )
            or all(
                value < 0
                for value in signed_diffs
            )
        )

        if (
            abs(med_diff) >= 2.0
            and same_direction
            and std_diff <= max(
                3.0,
                abs(med_diff)
                * 0.60
            )
        ):
            findings.append({
                "metric": metric,
                "periods":
                    len(metric_rows),
                "median_signed_diff":
                    med_diff,
                "median_ratio":
                    med_ratio,
                "std_diff":
                    std_diff,
            })

    return sorted(
        findings,
        key=lambda item:
            abs(
                item[
                    "median_signed_diff"
                ]
            ),
        reverse=True
    )


# ============================================================
# Summary
# ============================================================

def summarize(rows):
    common = [
        row
        for row in rows
        if (
            row["yahoo"] is not None
            and row["sa"] is not None
        )
    ]

    counts = {
        status:
            sum(
                1
                for row in common
                if row["status"] == status
            )
        for status in (
            "EXCELLENT",
            "GOOD",
            "REVIEW",
            "CONFLICT"
        )
    }

    points = {
        "EXCELLENT": 100,
        "GOOD": 85,
        "REVIEW": 55,
        "CONFLICT": 0,
    }

    score = (
        mean(
            [
                points[
                    row[
                        "status"
                    ]
                ]
                for row in common
            ]
        )
        if common
        else 0.0
    )

    valid_diffs = [
        row["diff"]
        for row in common
        if row["diff"] is not None
    ]

    avg_diff = (
        mean(
            valid_diffs
        )
        if valid_diffs
        else None
    )

    return (
        common,
        counts,
        score,
        avg_diff
    )


# ============================================================
# Print Diagnostics
# ============================================================

def print_scale_anomalies(
    anomalies
):
    if not anomalies:
        return

    print(
        "\n🧮 SCALE / PERIOD ANOMALY FLAGS:",
        flush=True
    )

    for item in anomalies[:10]:
        print(
            f"- {item['frequency']} | "
            f"{item['period']} | "
            f"{item['metric']} | "
            f"Yahoo="
            f"{fmt_money(item['yahoo'])} | "
            f"StockAnalysis="
            f"{fmt_money(item['sa'])} | "
            f"Ratio="
            f"{item['ratio']:.3f}x "
            f"(near "
            f"{item['target_ratio']:.2f}x) | "
            "قد يكون Scale / Period / "
            "Column Mapping",
            flush=True
        )


def print_systematic_bias(
    findings
):
    if not findings:
        return

    print(
        "\n🧬 SYSTEMATIC DEFINITION BIAS FLAGS:",
        flush=True
    )

    for item in findings[:10]:
        direction = (
            "أعلى"
            if item[
                "median_signed_diff"
            ] > 0
            else "أقل"
        )

        print(
            f"- {item['metric']} | "
            f"{item['periods']} فترات | "
            f"StockAnalysis {direction} "
            f"من Yahoo بوسيط "
            f"{abs(item['median_signed_diff']):.2f}% | "
            f"MedianRatio="
            f"{item['median_ratio']:.4f}x | "
            f"Std="
            f"{item['std_diff']:.2f} | "
            "يرجح Definition/Mapping مختلف",
            flush=True
        )


# ============================================================
# Run
# ============================================================

def run():
    print_header(
        f"🧪 DATA SOURCE BENCHMARK "
        f"v{ENGINE_VERSION}"
    )

    print(
        "🔒 READ ONLY",
        flush=True
    )

    print(
        "🅰️ Yahoo: existing Supabase "
        "financial_statements",
        flush=True
    )

    print(
        "🅱️ StockAnalysis: candidate source",
        flush=True
    )

    print(
        "🧠 Benchmark Mode: MODEL-AWARE",
        flush=True
    )

    print(
        f"🕐 Started: "
        f"{datetime.now().isoformat()}",
        flush=True
    )

    stocks = get_test_stocks()

    print(
        f"🏢 Test Companies: "
        f"{len(stocks)}/"
        f"{len(TEST_SYMBOLS)}",
        flush=True
    )

    if not stocks:
        raise RuntimeError(
            "No test stocks found"
        )

    final = []

    for index, stock in enumerate(
        stocks,
        start=1
    ):
        symbol = stock["symbol"]

        name = (
            stock.get(
                "company_name"
            )
            or symbol
        )

        model = (
            stock.get(
                "analysis_model"
            )
            or "standard"
        )

        print_header(
            f"🚦 {index}/{len(stocks)} | "
            f"{symbol} | "
            f"{name} | "
            f"{model}"
        )

        allowed_metrics = (
            get_allowed_metrics(
                model
            )
        )

        print(
            "📋 Model Comparison Metrics: "
            + ", ".join(
                sorted(
                    allowed_metrics
                )
            ),
            flush=True
        )

        yahoo = build_yahoo(
            get_yahoo_rows(
                stock["id"]
            )
        )

        stockanalysis = (
            get_stockanalysis(
                symbol
            )
        )

        rows, excluded = compare(
            yahoo,
            stockanalysis,
            model
        )

        common, counts, score, avg_diff = (
            summarize(
                rows
            )
        )

        scale_anomalies = (
            detect_scale_anomalies(
                common
            )
        )

        systematic_bias = (
            detect_systematic_bias(
                common
            )
        )

        print(
            f"📦 Yahoo Canonical Values: "
            f"{len(yahoo)}",
            flush=True
        )

        print(
            f"📦 StockAnalysis Canonical Values: "
            f"{len(stockanalysis)}",
            flush=True
        )

        print(
            f"🧹 Model-Excluded Values: "
            f"{len(excluded)}",
            flush=True
        )

        print(
            f"🤝 Common Comparable Values: "
            f"{len(common)}",
            flush=True
        )

        print(
            f"🏆 Agreement Score: "
            f"{score:.2f}/100",
            flush=True
        )

        if avg_diff is not None:
            print(
                f"📏 Average Difference: "
                f"{avg_diff:.2f}%",
                flush=True
            )
        else:
            print(
                "📏 Average Difference: N/A",
                flush=True
            )

        print(
            f"🟢 Excellent="
            f"{counts['EXCELLENT']} | "
            f"🔵 Good="
            f"{counts['GOOD']} | "
            f"🟡 Review="
            f"{counts['REVIEW']} | "
            f"🔴 Conflict="
            f"{counts['CONFLICT']}",
            flush=True
        )

        problems = sorted(
            [
                row
                for row in common
                if row["status"] in (
                    "REVIEW",
                    "CONFLICT"
                )
            ],
            key=lambda row:
                (
                    row["diff"]
                    if row["diff"] is not None
                    else -1
                ),
            reverse=True
        )

        if problems:
            print(
                "\n⚠️ أهم الاختلافات:",
                flush=True
            )

            for row in problems[:12]:
                frequency, period, metric = (
                    row["key"]
                )

                print(
                    f"- {frequency} | "
                    f"{period} | "
                    f"{metric} | "
                    f"Yahoo="
                    f"{fmt_money(row['yahoo'])} | "
                    f"StockAnalysis="
                    f"{fmt_money(row['sa'])} | "
                    f"Diff="
                    f"{row['diff']:.2f}% | "
                    f"{row['status']}",
                    flush=True
                )
        else:
            print(
                "✅ لا توجد اختلافات كبيرة "
                "في القيم المشتركة.",
                flush=True
            )

        print_scale_anomalies(
            scale_anomalies
        )

        print_systematic_bias(
            systematic_bias
        )

        final.append({
            "symbol": symbol,
            "name": name,
            "model": model,
            "common": len(common),
            "excluded": len(excluded),
            "score": score,
            "avg_diff": avg_diff,
            "scale_flags":
                len(scale_anomalies),
            "bias_flags":
                len(systematic_bias),
            **counts,
        })

        time.sleep(
            DELAY
        )

    print_header(
        f"🏁 DATA SOURCE BENCHMARK "
        f"v{ENGINE_VERSION} SUMMARY"
    )

    for index, item in enumerate(
        final,
        start=1
    ):
        avg_text = (
            f"{item['avg_diff']:.2f}%"
            if item["avg_diff"] is not None
            else "N/A"
        )

        print(
            f"{index:02d}. "
            f"{item['symbol']} | "
            f"{item['name']} | "
            f"{item['model']} | "
            f"Common="
            f"{item['common']} | "
            f"Excluded="
            f"{item['excluded']} | "
            f"Agreement="
            f"{item['score']:.2f} | "
            f"AvgDiff="
            f"{avg_text} | "
            f"Excellent="
            f"{item['EXCELLENT']} | "
            f"Good="
            f"{item['GOOD']} | "
            f"Review="
            f"{item['REVIEW']} | "
            f"Conflict="
            f"{item['CONFLICT']} | "
            f"ScaleFlags="
            f"{item['scale_flags']} | "
            f"BiasFlags="
            f"{item['bias_flags']}",
            flush=True
        )

    total_common = sum(
        item["common"]
        for item in final
    )

    total_excluded = sum(
        item["excluded"]
        for item in final
    )

    total_conflicts = sum(
        item["CONFLICT"]
        for item in final
    )

    weighted_scores = []

    for item in final:
        weighted_scores.extend(
            [item["score"]]
            * item["common"]
        )

    overall = (
        mean(
            weighted_scores
        )
        if weighted_scores
        else 0.0
    )

    print(
        "-" * 100,
        flush=True
    )

    print(
        f"🏢 Companies Tested: "
        f"{len(final)}",
        flush=True
    )

    print(
        f"🤝 Total Comparable Values: "
        f"{total_common}",
        flush=True
    )

    print(
        f"🧹 Total Model-Excluded Values: "
        f"{total_excluded}",
        flush=True
    )

    print(
        f"🔴 Total Conflicts: "
        f"{total_conflicts}",
        flush=True
    )

    print(
        f"🏆 Overall Model-Aware "
        f"Agreement Score: "
        f"{overall:.2f}/100",
        flush=True
    )

    print(
        "\n📌 تفسير v1.1:",
        flush=True
    )

    print(
        "- Standard يقارن "
        "Income + Balance + Cash Flow.",
        flush=True
    )

    print(
        "- Bank لا يُحكم عليه عبر "
        "OCF / FCF / CapEx التقليدية.",
        flush=True
    )

    print(
        "- Insurance لا يُحكم عليه عبر "
        "OCF / FCF / CapEx التقليدية.",
        flush=True
    )

    print(
        "- Scale Flags تبحث عن "
        "2x / 0.5x ونحوها قبل اتهام المصدر.",
        flush=True
    )

    print(
        "- Bias Flags تبحث عن فرق ثابت "
        "قد يكون Definition/Mapping.",
        flush=True
    )

    print(
        "- StockAnalysis لا يصبح "
        "Source B معتمدًا من هذا الاختبار وحده.",
        flush=True
    )

    print(
        "- الخطوة التالية بعد نجاح v1.1: "
        "مطابقة عينة مع تداول/الإعلانات الرسمية.",
        flush=True
    )

    print(
        "- لا يتم حفظ أو تعديل أي بيانات.",
        flush=True
    )

    print(
        "=" * 100,
        flush=True
    )


if __name__ == "__main__":
    run()
