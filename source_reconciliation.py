import os
import re
import time
from collections import defaultdict
from datetime import datetime
from html import unescape
from html.parser import HTMLParser
from statistics import median, pstdev

import requests
from supabase import create_client


# ============================================================
# SOURCE RECONCILIATION ENGINE v1.0
#
# الهدف:
# بناء طبقة مستقلة بين مصادر البيانات والمحركات التحليلية.
#
# READ ONLY
#
# المرحلة الحالية:
# - Source A: Yahoo (من financial_statements في Supabase)
# - Source B: StockAnalysis
# - Official Arbiter: تداول/الإعلانات الرسمية (خارج هذا الملف)
#
# المخرجات:
# - AGREED
# - AGREED_MINOR_DIFF
# - REVIEW
# - CONFLICT
# - SCALE_ANOMALY
# - DEFINITION_CONFLICT
# - SINGLE_SOURCE
# - NO_DATA
#
# مهم:
# - لا يكتب أو يعدل أي بيانات في Supabase.
# - لا يغير financial_data.py.
# - لا يغير أي Engine حالي.
# - قابل مستقبلًا لإضافة Paid Provider Adapter.
# ============================================================


# ============================================================
# Supabase
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


# ============================================================
# Settings
# ============================================================

ENGINE_VERSION = "1.0"

STOCKANALYSIS_BASE = (
    "https://stockanalysis.com/quote/tadawul"
)

REQUEST_TIMEOUT = 25
REQUEST_DELAY = 0.35

TEST_SYMBOLS = [
    "2283.SR",
    "4030.SR",
    "7203.SR",
    "4190.SR",
    "1150.SR",
    "8010.SR",
]


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


# ============================================================
# Reconciliation thresholds
# ============================================================

AGREED_LIMIT = 0.50
MINOR_DIFF_LIMIT = 2.00
REVIEW_LIMIT = 5.00

SCALE_TARGETS = [
    0.25,
    0.50,
    2.00,
    4.00,
]

SCALE_TOLERANCE = 0.03


# ============================================================
# Yahoo Mapping
# ============================================================

YAHOO_MAP = {
    "annualTotalRevenue":
        ("annual", "revenue"),

    "quarterlyTotalRevenue":
        ("quarterly", "revenue"),

    "annualGrossProfit":
        ("annual", "gross_profit"),

    "quarterlyGrossProfit":
        ("quarterly", "gross_profit"),

    "annualOperatingIncome":
        ("annual", "operating_income"),

    "quarterlyOperatingIncome":
        ("quarterly", "operating_income"),

    "annualNetIncome":
        ("annual", "net_income"),

    "quarterlyNetIncome":
        ("quarterly", "net_income"),

    "annualTotalAssets":
        ("annual", "total_assets"),

    "quarterlyTotalAssets":
        ("quarterly", "total_assets"),

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
# StockAnalysis aliases
# ============================================================

STOCKANALYSIS_ALIASES = {
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
# Model-aware allowed metrics
# ============================================================

MODEL_METRICS = {
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
# Known Definition Rules
#
# مؤقتًا هذه ليست "تصحيح أرقام".
# فقط تساعد النظام على التمييز بين Conflict عشوائي
# وفرق متكرر قد يكون Definition/Mapping.
#
# البحري مثال:
# StockAnalysis Equity أعلى بصورة منهجية ~5-7%.
# ============================================================

KNOWN_DEFINITION_RULES = {
    "4030.SR": {
        "stockholders_equity": {
            "min_signed_diff": 4.0,
            "max_signed_diff": 8.0,
            "preferred_source": "yahoo",
            "reason": (
                "Recurring equity definition difference; "
                "Yahoo matched Tadawul shareholders' equity "
                "after minority interests in prior verification."
            ),
        }
    }
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
        or text in {
            "-",
            "--",
            "N/A",
            "n/a"
        }
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
        "\n"
        + "=" * 100,
        flush=True
    )

    print(
        title,
        flush=True
    )

    print(
        "=" * 100,
        flush=True
    )


def normalize_label(text):

    text = unescape(
        str(
            text
            or ""
        )
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

    label = normalize_label(
        label
    )

    for canonical, aliases in (
        STOCKANALYSIS_ALIASES.items()
    ):

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

    month_name = (
        match.group(1)
        .title()
    )

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

    month, day = (
        month_days[
            month_name
        ]
    )

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


def difference_percent(
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
    ):
        return None

    return (
        abs(
            reference
            - candidate
        )
        / max(
            abs(reference),
            abs(candidate),
            1.0
        )
        * 100.0
    )


def signed_difference_percent(
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
        (
            candidate
            - reference
        )
        / abs(reference)
        * 100.0
    )


def ratio_value(
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
        candidate
        / reference
    )


def is_scale_anomaly(ratio):

    ratio = safe_number(
        ratio
    )

    if ratio is None:
        return (
            False,
            None
        )

    absolute_ratio = abs(
        ratio
    )

    for target in SCALE_TARGETS:

        if (
            abs(
                absolute_ratio
                - target
            )
            <= target
            * SCALE_TOLERANCE
        ):
            return (
                True,
                target
            )

    return (
        False,
        None
    )


def canonical_candidate(
    yahoo_value,
    stockanalysis_value
):

    yahoo_value = safe_number(
        yahoo_value
    )

    stockanalysis_value = safe_number(
        stockanalysis_value
    )

    if (
        yahoo_value is None
        and stockanalysis_value is None
    ):
        return None

    if yahoo_value is None:
        return stockanalysis_value

    if stockanalysis_value is None:
        return yahoo_value

    # عند الاتفاق نأخذ المتوسط فقط كـ Candidate تشخيصي.
    # لا يتم حفظه أو استخدامه في المحركات حاليًا.
    return (
        yahoo_value
        + stockanalysis_value
    ) / 2.0


# ============================================================
# Minimal HTML parser
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
            and tag in (
                "td",
                "th"
            )
        ):

            self.cell = []

        elif (
            self.cell is not None
            and tag == "br"
        ):

            self.cell.append(
                " "
            )

    def handle_data(
        self,
        data
    ):

        if self.cell is not None:

            self.cell.append(
                data
            )

    def handle_endtag(
        self,
        tag
    ):

        tag = tag.lower()

        if (
            self.cell is not None
            and tag in (
                "td",
                "th"
            )
        ):

            text = re.sub(
                r"\s+",
                " ",
                unescape(
                    "".join(
                        self.cell
                    )
                )
            ).strip()

            self.row.append(
                text
            )

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
# Source Adapter Base
# ============================================================

class SourceAdapter:

    source_name = "unknown"

    def get_canonical(
        self,
        stock
    ):

        raise NotImplementedError


# ============================================================
# Yahoo Adapter
# ============================================================

class YahooAdapter(
    SourceAdapter
):

    source_name = "yahoo"

    def get_rows(
        self,
        stock_id
    ):

        response = (
            supabase
            .table(
                "financial_statements"
            )
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

    def get_canonical(
        self,
        stock
    ):

        rows = self.get_rows(
            stock[
                "id"
            ]
        )

        output = {}

        for row in rows:

            mapping = (
                YAHOO_MAP.get(
                    row.get(
                        "metric"
                    )
                )
            )

            if not mapping:
                continue

            frequency, metric = (
                mapping
            )

            period_end = str(
                row.get(
                    "period_end"
                )
                or ""
            )

            value = safe_number(
                row.get(
                    "value"
                )
            )

            if (
                period_end
                and value is not None
            ):

                output[
                    (
                        frequency,
                        period_end,
                        metric
                    )
                ] = value

        return output


# ============================================================
# StockAnalysis Adapter
# ============================================================

class StockAnalysisAdapter(
    SourceAdapter
):

    source_name = "stockanalysis"

    def fetch_html(
        self,
        symbol,
        page,
        quarterly=False
    ):

        code = (
            symbol
            .split(".")[0]
        )

        paths = {
            "income":
                "financials/",

            "balance":
                "financials/balance-sheet/",

            "cash":
                "financials/cash-flow-statement/",
        }

        url = (
            f"{STOCKANALYSIS_BASE}/"
            f"{code}/"
            f"{paths[page]}"
        )

        if quarterly:
            url += "?p=quarterly"

        response = requests.get(
            url,
            headers=HEADERS,
            timeout=REQUEST_TIMEOUT
        )

        print(
            f"🌐 StockAnalysis | "
            f"{symbol} | "
            f"{page} | "
            f"{'quarterly' if quarterly else 'annual'} | "
            f"HTTP {response.status_code}",
            flush=True
        )

        response.raise_for_status()

        return response.text

    def parse_tables(
        self,
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
                            period_to_date(
                                label
                            )
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

                for (
                    index,
                    period_end
                ) in period_columns:

                    if (
                        not period_end
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
                                period_end,
                                metric
                            )
                        ] = (
                            value
                            * multiplier
                        )

        return output

    def get_canonical(
        self,
        stock
    ):

        symbol = stock[
            "symbol"
        ]

        output = {}

        for (
            frequency,
            quarterly
        ) in (
            (
                "annual",
                False
            ),
            (
                "quarterly",
                True
            ),
        ):

            for page in (
                "income",
                "balance",
                "cash"
            ):

                try:

                    html_text = (
                        self.fetch_html(
                            symbol,
                            page,
                            quarterly
                        )
                    )

                    output.update(
                        self.parse_tables(
                            html_text,
                            frequency
                        )
                    )

                except Exception as error:

                    print(
                        f"🟠 StockAnalysis | "
                        f"{symbol} | "
                        f"{page} | "
                        f"{frequency} | "
                        f"{type(error).__name__}: "
                        f"{error}",
                        flush=True
                    )

                time.sleep(
                    REQUEST_DELAY
                )

        return output


# ============================================================
# Stocks
# ============================================================

def get_test_stocks():

    response = (
        supabase
        .table(
            "stocks"
        )
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
        row[
            "symbol"
        ]:
            row

        for row in (
            response.data
            or []
        )
    }

    return [
        by_symbol[
            symbol
        ]

        for symbol in TEST_SYMBOLS

        if symbol in by_symbol
    ]


# ============================================================
# Model-aware metrics
# ============================================================

def allowed_metrics(
    analysis_model
):

    return (
        MODEL_METRICS.get(
            analysis_model,
            MODEL_METRICS[
                "standard"
            ]
        )
    )


# ============================================================
# Definition rule
# ============================================================

def get_definition_rule(
    symbol,
    metric,
    signed_diff
):

    rules = (
        KNOWN_DEFINITION_RULES.get(
            symbol,
            {}
        )
    )

    rule = (
        rules.get(
            metric
        )
    )

    if not rule:
        return None

    if signed_diff is None:
        return None

    minimum = safe_number(
        rule.get(
            "min_signed_diff"
        )
    )

    maximum = safe_number(
        rule.get(
            "max_signed_diff"
        )
    )

    if (
        minimum is None
        or maximum is None
    ):
        return None

    if (
        minimum
        <= signed_diff
        <= maximum
    ):
        return rule

    return None


# ============================================================
# Reconciliation
# ============================================================

def reconcile_value(
    symbol,
    metric,
    yahoo_value,
    stockanalysis_value
):

    yahoo_value = safe_number(
        yahoo_value
    )

    stockanalysis_value = safe_number(
        stockanalysis_value
    )

    if (
        yahoo_value is None
        and stockanalysis_value is None
    ):

        return {
            "status":
                "NO_DATA",

            "confidence":
                0.0,

            "canonical_candidate":
                None,

            "preferred_source":
                None,

            "difference_pct":
                None,

            "reason":
                "No source returned a value."
        }

    if (
        yahoo_value is None
        or stockanalysis_value is None
    ):

        available_source = (
            "yahoo"
            if yahoo_value is not None
            else "stockanalysis"
        )

        available_value = (
            yahoo_value
            if yahoo_value is not None
            else stockanalysis_value
        )

        return {
            "status":
                "SINGLE_SOURCE",

            "confidence":
                55.0,

            "canonical_candidate":
                available_value,

            "preferred_source":
                available_source,

            "difference_pct":
                None,

            "reason":
                (
                    "Only one source returned a value."
                )
        }

    difference = (
        difference_percent(
            yahoo_value,
            stockanalysis_value
        )
    )

    signed_diff = (
        signed_difference_percent(
            yahoo_value,
            stockanalysis_value
        )
    )

    ratio = ratio_value(
        yahoo_value,
        stockanalysis_value
    )

    scale_flag, scale_target = (
        is_scale_anomaly(
            ratio
        )
    )

    if scale_flag:

        return {
            "status":
                "SCALE_ANOMALY",

            "confidence":
                20.0,

            "canonical_candidate":
                None,

            "preferred_source":
                None,

            "difference_pct":
                difference,

            "ratio":
                ratio,

            "reason":
                (
                    f"Source ratio is near "
                    f"{scale_target:.2f}x; "
                    "requires period/scale verification."
                )
        }

    definition_rule = (
        get_definition_rule(
            symbol,
            metric,
            signed_diff
        )
    )

    if definition_rule:

        preferred_source = (
            definition_rule[
                "preferred_source"
            ]
        )

        canonical_value = (
            yahoo_value
            if preferred_source == "yahoo"
            else stockanalysis_value
        )

        return {
            "status":
                "DEFINITION_CONFLICT",

            "confidence":
                85.0,

            "canonical_candidate":
                canonical_value,

            "preferred_source":
                preferred_source,

            "difference_pct":
                difference,

            "ratio":
                ratio,

            "reason":
                definition_rule[
                    "reason"
                ]
        }

    if difference <= AGREED_LIMIT:

        return {
            "status":
                "AGREED",

            "confidence":
                99.0,

            "canonical_candidate":
                canonical_candidate(
                    yahoo_value,
                    stockanalysis_value
                ),

            "preferred_source":
                "consensus",

            "difference_pct":
                difference,

            "ratio":
                ratio,

            "reason":
                "Sources agree within 0.5%."
        }

    if difference <= MINOR_DIFF_LIMIT:

        return {
            "status":
                "AGREED_MINOR_DIFF",

            "confidence":
                94.0,

            "canonical_candidate":
                canonical_candidate(
                    yahoo_value,
                    stockanalysis_value
                ),

            "preferred_source":
                "consensus",

            "difference_pct":
                difference,

            "ratio":
                ratio,

            "reason":
                "Minor difference within 2%."
        }

    if difference <= REVIEW_LIMIT:

        return {
            "status":
                "REVIEW",

            "confidence":
                75.0,

            "canonical_candidate":
                None,

            "preferred_source":
                None,

            "difference_pct":
                difference,

            "ratio":
                ratio,

            "reason":
                "Difference between 2% and 5%."
        }

    return {
        "status":
            "CONFLICT",

        "confidence":
            35.0,

        "canonical_candidate":
            None,

        "preferred_source":
            None,

        "difference_pct":
            difference,

        "ratio":
            ratio,

        "reason":
            "Difference exceeds 5%."
    }


# ============================================================
# Detect repeated definition bias
# ============================================================

def detect_repeated_bias(
    rows
):

    grouped = defaultdict(
        list
    )

    for row in rows:

        if (
            row[
                "yahoo"
            ] is None
            or row[
                "stockanalysis"
            ] is None
        ):
            continue

        signed_diff = (
            signed_difference_percent(
                row[
                    "yahoo"
                ],
                row[
                    "stockanalysis"
                ]
            )
        )

        if signed_diff is None:
            continue

        grouped[
            row[
                "metric"
            ]
        ].append(
            signed_diff
        )

    output = []

    for metric, values in (
        grouped.items()
    ):

        if len(
            values
        ) < 4:
            continue

        med = median(
            values
        )

        std = (
            pstdev(
                values
            )
            if len(
                values
            ) > 1
            else 0.0
        )

        same_direction = (
            all(
                value > 0
                for value in values
            )
            or all(
                value < 0
                for value in values
            )
        )

        if (
            abs(med) >= 2.0
            and same_direction
            and std <= max(
                3.0,
                abs(med)
                * 0.60
            )
        ):

            output.append({
                "metric":
                    metric,

                "periods":
                    len(values),

                "median_signed_diff":
                    med,

                "std":
                    std,
            })

    return sorted(
        output,
        key=lambda item:
            abs(
                item[
                    "median_signed_diff"
                ]
            ),
        reverse=True
    )


# ============================================================
# Company reconciliation
# ============================================================

def reconcile_stock(
    stock,
    yahoo_data,
    stockanalysis_data
):

    analysis_model = (
        stock.get(
            "analysis_model"
        )
        or "standard"
    )

    symbol = stock[
        "symbol"
    ]

    allowed = (
        allowed_metrics(
            analysis_model
        )
    )

    rows = []

    all_keys = sorted(
        set(
            yahoo_data
        )
        | set(
            stockanalysis_data
        )
    )

    for key in all_keys:

        frequency, period_end, metric = (
            key
        )

        if metric not in allowed:
            continue

        yahoo_value = (
            yahoo_data.get(
                key
            )
        )

        stockanalysis_value = (
            stockanalysis_data.get(
                key
            )
        )

        result = (
            reconcile_value(
                symbol=symbol,
                metric=metric,
                yahoo_value=yahoo_value,
                stockanalysis_value=stockanalysis_value
            )
        )

        rows.append({
            "frequency":
                frequency,

            "period_end":
                period_end,

            "metric":
                metric,

            "yahoo":
                yahoo_value,

            "stockanalysis":
                stockanalysis_value,

            **result
        })

    return rows


# ============================================================
# Print
# ============================================================

def print_stock_result(
    stock,
    rows
):

    symbol = stock[
        "symbol"
    ]

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
        f"🔎 {symbol} | "
        f"{name} | "
        f"{model}"
    )

    counts = defaultdict(
        int
    )

    for row in rows:

        counts[
            row[
                "status"
            ]
        ] += 1

    comparable = [
        row
        for row in rows
        if row[
            "status"
        ] != "NO_DATA"
    ]

    avg_confidence = (
        sum(
            row[
                "confidence"
            ]
            for row in comparable
        )
        / len(
            comparable
        )
        if comparable
        else 0.0
    )

    print(
        f"📊 Reconciled Values: "
        f"{len(rows)}",
        flush=True
    )

    print(
        f"🛡 Average Reconciliation Confidence: "
        f"{avg_confidence:.2f}",
        flush=True
    )

    print(
        f"🟢 AGREED: "
        f"{counts['AGREED']}",
        flush=True
    )

    print(
        f"🔵 AGREED_MINOR_DIFF: "
        f"{counts['AGREED_MINOR_DIFF']}",
        flush=True
    )

    print(
        f"🟡 REVIEW: "
        f"{counts['REVIEW']}",
        flush=True
    )

    print(
        f"🔴 CONFLICT: "
        f"{counts['CONFLICT']}",
        flush=True
    )

    print(
        f"🧮 SCALE_ANOMALY: "
        f"{counts['SCALE_ANOMALY']}",
        flush=True
    )

    print(
        f"🧬 DEFINITION_CONFLICT: "
        f"{counts['DEFINITION_CONFLICT']}",
        flush=True
    )

    print(
        f"🟠 SINGLE_SOURCE: "
        f"{counts['SINGLE_SOURCE']}",
        flush=True
    )

    problem_rows = [
        row
        for row in rows
        if row[
            "status"
        ] in (
            "REVIEW",
            "CONFLICT",
            "SCALE_ANOMALY",
            "DEFINITION_CONFLICT"
        )
    ]

    if problem_rows:

        print(
            "\n⚠️ Key Reconciliation Findings:",
            flush=True
        )

        for row in problem_rows[:15]:

            print(
                f"- {row['frequency']} | "
                f"{row['period_end']} | "
                f"{row['metric']} | "
                f"Yahoo="
                f"{fmt_money(row['yahoo'])} | "
                f"StockAnalysis="
                f"{fmt_money(row['stockanalysis'])} | "
                f"Status="
                f"{row['status']} | "
                f"Confidence="
                f"{row['confidence']:.0f} | "
                f"{row['reason']}",
                flush=True
            )

    repeated_bias = (
        detect_repeated_bias(
            rows
        )
    )

    if repeated_bias:

        print(
            "\n🧬 Repeated Bias Candidates:",
            flush=True
        )

        for item in repeated_bias[:10]:

            direction = (
                "higher"
                if item[
                    "median_signed_diff"
                ] > 0
                else "lower"
            )

            print(
                f"- {item['metric']} | "
                f"{item['periods']} periods | "
                f"StockAnalysis {direction} "
                f"by median "
                f"{abs(item['median_signed_diff']):.2f}% | "
                f"Std={item['std']:.2f}",
                flush=True
            )

    return {
        "symbol":
            symbol,

        "company_name":
            name,

        "analysis_model":
            model,

        "rows":
            len(rows),

        "avg_confidence":
            avg_confidence,

        "counts":
            dict(
                counts
            )
    }


# ============================================================
# Run
# ============================================================

def run_reconciliation():

    print_header(
        f"🧩 SOURCE RECONCILIATION ENGINE "
        f"v{ENGINE_VERSION}"
    )

    print(
        "🔒 Mode: READ ONLY",
        flush=True
    )

    print(
        "🅰️ Source A: Yahoo",
        flush=True
    )

    print(
        "🅱️ Source B: StockAnalysis",
        flush=True
    )

    print(
        "🏛 Official Arbiter: Tadawul "
        "(external/manual verification when needed)",
        flush=True
    )

    print(
        f"🕐 Started: "
        f"{datetime.now().isoformat()}",
        flush=True
    )

    stocks = (
        get_test_stocks()
    )

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

    yahoo_adapter = (
        YahooAdapter()
    )

    stockanalysis_adapter = (
        StockAnalysisAdapter()
    )

    summaries = []

    for index, stock in enumerate(
        stocks,
        start=1
    ):

        print(
            "\n"
            f"🚦 Reconciliation "
            f"{index}/{len(stocks)} | "
            f"{stock['symbol']}",
            flush=True
        )

        yahoo_data = (
            yahoo_adapter.get_canonical(
                stock
            )
        )

        stockanalysis_data = (
            stockanalysis_adapter.get_canonical(
                stock
            )
        )

        rows = (
            reconcile_stock(
                stock=stock,
                yahoo_data=yahoo_data,
                stockanalysis_data=stockanalysis_data
            )
        )

        summary = (
            print_stock_result(
                stock,
                rows
            )
        )

        summaries.append(
            summary
        )

    # ========================================================
    # Final Summary
    # ========================================================

    print_header(
        f"🏁 SOURCE RECONCILIATION ENGINE "
        f"v{ENGINE_VERSION} SUMMARY"
    )

    total_rows = 0
    total_confidence = 0.0

    overall_counts = defaultdict(
        int
    )

    for index, item in enumerate(
        summaries,
        start=1
    ):

        counts = item[
            "counts"
        ]

        print(
            f"{index:02d}. "
            f"{item['symbol']} | "
            f"{item['company_name']} | "
            f"{item['analysis_model']} | "
            f"Rows={item['rows']} | "
            f"AvgConfidence="
            f"{item['avg_confidence']:.2f} | "
            f"Agreed="
            f"{counts.get('AGREED', 0)} | "
            f"Minor="
            f"{counts.get('AGREED_MINOR_DIFF', 0)} | "
            f"Review="
            f"{counts.get('REVIEW', 0)} | "
            f"Conflict="
            f"{counts.get('CONFLICT', 0)} | "
            f"Scale="
            f"{counts.get('SCALE_ANOMALY', 0)} | "
            f"Definition="
            f"{counts.get('DEFINITION_CONFLICT', 0)}",
            flush=True
        )

        total_rows += (
            item[
                "rows"
            ]
        )

        total_confidence += (
            item[
                "avg_confidence"
            ]
            * item[
                "rows"
            ]
        )

        for status, count in (
            counts.items()
        ):

            overall_counts[
                status
            ] += count

    overall_confidence = (
        total_confidence
        / total_rows
        if total_rows
        else 0.0
    )

    print(
        "-" * 100,
        flush=True
    )

    print(
        f"🏢 Companies Tested: "
        f"{len(summaries)}",
        flush=True
    )

    print(
        f"📊 Total Reconciled Rows: "
        f"{total_rows}",
        flush=True
    )

    print(
        f"🛡 Overall Reconciliation Confidence: "
        f"{overall_confidence:.2f}",
        flush=True
    )

    print(
        f"🟢 AGREED: "
        f"{overall_counts['AGREED']}",
        flush=True
    )

    print(
        f"🔵 AGREED_MINOR_DIFF: "
        f"{overall_counts['AGREED_MINOR_DIFF']}",
        flush=True
    )

    print(
        f"🟡 REVIEW: "
        f"{overall_counts['REVIEW']}",
        flush=True
    )

    print(
        f"🔴 CONFLICT: "
        f"{overall_counts['CONFLICT']}",
        flush=True
    )

    print(
        f"🧮 SCALE_ANOMALY: "
        f"{overall_counts['SCALE_ANOMALY']}",
        flush=True
    )

    print(
        f"🧬 DEFINITION_CONFLICT: "
        f"{overall_counts['DEFINITION_CONFLICT']}",
        flush=True
    )

    print(
        f"🟠 SINGLE_SOURCE: "
        f"{overall_counts['SINGLE_SOURCE']}",
        flush=True
    )

    print(
        "\n📌 IMPORTANT:",
        flush=True
    )

    print(
        "- هذا الملف لا يكتب أو يعدل أي بيانات.",
        flush=True
    )

    print(
        "- Canonical Candidate هنا تشخيصي فقط.",
        flush=True
    )

    print(
        "- REVIEW / CONFLICT / SCALE_ANOMALY "
        "لا تدخل المحركات الحالية.",
        flush=True
    )

    print(
        "- بعد نجاح هذه المرحلة يمكن إنشاء "
        "canonical_financials أو طبقة مصدر موحدة.",
        flush=True
    )

    print(
        "- أي مزود مدفوع مستقبلًا يضاف كـ Adapter "
        "بدون تغيير المحركات التحليلية.",
        flush=True
    )

    print(
        "=" * 100,
        flush=True
    )


if __name__ == "__main__":

    run_reconciliation()
