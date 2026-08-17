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
# SOURCE RECONCILIATION ENGINE v1.1
#
# الهدف:
# فصل جودة "الاتفاق بين المصدرين" عن "تغطية المصادر".
#
# READ ONLY
#
# Source A: Yahoo (Supabase)
# Source B: StockAnalysis
# Official Arbiter: Tadawul / official announcements
#
# v1.1:
# - SINGLE_SOURCE لا يدخل في Agreement Confidence
# - إضافة Dual-Source Agreement Confidence
# - إضافة Source Coverage Score
# - إضافة Reconciliation Risk Score
# - فصل Arbitration Needed عن Definition Conflict known
# - إبقاء Scale / Conflict / Review واضحة
# - لا يكتب أو يعدل أي بيانات
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

ENGINE_VERSION = "1.1"

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
# Thresholds
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
# Model-aware metrics
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


def consensus_candidate(
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

    return (
        yahoo_value
        + stockanalysis_value
    ) / 2.0


# ============================================================
# HTML Parser
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
# Model-aware
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
# Known Definition Rule
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
                "Only one source returned a value."
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

    ratio = (
        ratio_value(
            yahoo_value,
            stockanalysis_value
        )
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
                consensus_candidate(
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
                consensus_candidate(
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
# Metrics for v1.1
# ============================================================

def calculate_dual_source_agreement(
    rows
):

    dual_source = [
        row
        for row in rows
        if (
            row[
                "yahoo"
            ] is not None
            and row[
                "stockanalysis"
            ] is not None
        )
    ]

    if not dual_source:

        return {
            "dual_count":
                0,

            "agreement_confidence":
                0.0,

            "strong_agreement_rate":
                0.0,

            "arbitration_needed":
                0,

            "known_definition_conflicts":
                0,
        }

    weights = {
        "AGREED":
            100.0,

        "AGREED_MINOR_DIFF":
            95.0,

        "REVIEW":
            70.0,

        "CONFLICT":
            20.0,

        "SCALE_ANOMALY":
            10.0,

        "DEFINITION_CONFLICT":
            85.0,
    }

    values = []

    strong_count = 0
    arbitration_needed = 0
    known_definition_conflicts = 0

    for row in dual_source:

        status = row[
            "status"
        ]

        values.append(
            weights.get(
                status,
                0.0
            )
        )

        if status in (
            "AGREED",
            "AGREED_MINOR_DIFF",
            "DEFINITION_CONFLICT"
        ):

            strong_count += 1

        if status in (
            "REVIEW",
            "CONFLICT",
            "SCALE_ANOMALY"
        ):

            arbitration_needed += 1

        if status == "DEFINITION_CONFLICT":

            known_definition_conflicts += 1

    agreement_confidence = (
        mean(
            values
        )
        if values
        else 0.0
    )

    strong_agreement_rate = (
        strong_count
        / len(
            dual_source
        )
        * 100.0
    )

    return {
        "dual_count":
            len(
                dual_source
            ),

        "agreement_confidence":
            agreement_confidence,

        "strong_agreement_rate":
            strong_agreement_rate,

        "arbitration_needed":
            arbitration_needed,

        "known_definition_conflicts":
            known_definition_conflicts,
    }


def calculate_source_coverage(
    rows
):

    if not rows:

        return {
            "total_rows":
                0,

            "dual_source_rows":
                0,

            "single_source_rows":
                0,

            "coverage_score":
                0.0,

            "yahoo_presence":
                0.0,

            "stockanalysis_presence":
                0.0,
        }

    total_rows = len(
        rows
    )

    yahoo_present = sum(
        1
        for row in rows
        if row[
            "yahoo"
        ] is not None
    )

    stockanalysis_present = sum(
        1
        for row in rows
        if row[
            "stockanalysis"
        ] is not None
    )

    dual_source_rows = sum(
        1
        for row in rows
        if (
            row[
                "yahoo"
            ] is not None
            and row[
                "stockanalysis"
            ] is not None
        )
    )

    single_source_rows = sum(
        1
        for row in rows
        if row[
            "status"
        ] == "SINGLE_SOURCE"
    )

    # Coverage Score:
    # dual-source counts fully
    # single-source counts partially
    coverage_score = (
        (
            dual_source_rows
            + single_source_rows
            * 0.50
        )
        / total_rows
        * 100.0
    )

    yahoo_presence = (
        yahoo_present
        / total_rows
        * 100.0
    )

    stockanalysis_presence = (
        stockanalysis_present
        / total_rows
        * 100.0
    )

    return {
        "total_rows":
            total_rows,

        "dual_source_rows":
            dual_source_rows,

        "single_source_rows":
            single_source_rows,

        "coverage_score":
            coverage_score,

        "yahoo_presence":
            yahoo_presence,

        "stockanalysis_presence":
            stockanalysis_presence,
    }


def calculate_reconciliation_risk(
    rows
):

    if not rows:
        return {
            "risk_score":
                100.0,

            "review":
                0,

            "conflict":
                0,

            "scale":
                0,

            "definition":
                0,
        }

    review_count = sum(
        1
        for row in rows
        if row[
            "status"
        ] == "REVIEW"
    )

    conflict_count = sum(
        1
        for row in rows
        if row[
            "status"
        ] == "CONFLICT"
    )

    scale_count = sum(
        1
        for row in rows
        if row[
            "status"
        ] == "SCALE_ANOMALY"
    )

    definition_count = sum(
        1
        for row in rows
        if row[
            "status"
        ] == "DEFINITION_CONFLICT"
    )

    dual_rows = sum(
        1
        for row in rows
        if (
            row[
                "yahoo"
            ] is not None
            and row[
                "stockanalysis"
            ] is not None
        )
    )

    if dual_rows == 0:
        risk_score = 100.0

    else:
        raw_penalty = (
            review_count
            * 0.40
            + conflict_count
            * 1.00
            + scale_count
            * 1.25
            + definition_count
            * 0.10
        )

        risk_score = min(
            100.0,
            raw_penalty
            / dual_rows
            * 100.0
        )

    return {
        "risk_score":
            risk_score,

        "review":
            review_count,

        "conflict":
            conflict_count,

        "scale":
            scale_count,

        "definition":
            definition_count,
    }


# ============================================================
# Repeated bias diagnostics
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

    agreement = (
        calculate_dual_source_agreement(
            rows
        )
    )

    coverage = (
        calculate_source_coverage(
            rows
        )
    )

    risk = (
        calculate_reconciliation_risk(
            rows
        )
    )

    print(
        f"📊 Total Canonical Rows: "
        f"{coverage['total_rows']}",
        flush=True
    )

    print(
        f"🤝 Dual-Source Rows: "
        f"{agreement['dual_count']}",
        flush=True
    )

    print(
        f"🟠 Single-Source Rows: "
        f"{coverage['single_source_rows']}",
        flush=True
    )

    print(
        f"🏆 Dual-Source Agreement Confidence: "
        f"{agreement['agreement_confidence']:.2f}/100",
        flush=True
    )

    print(
        f"✅ Strong Agreement Rate: "
        f"{agreement['strong_agreement_rate']:.2f}%",
        flush=True
    )

    print(
        f"📡 Source Coverage Score: "
        f"{coverage['coverage_score']:.2f}/100",
        flush=True
    )

    print(
        f"🅰️ Yahoo Presence: "
        f"{coverage['yahoo_presence']:.2f}%",
        flush=True
    )

    print(
        f"🅱️ StockAnalysis Presence: "
        f"{coverage['stockanalysis_presence']:.2f}%",
        flush=True
    )

    print(
        f"⚠️ Reconciliation Risk: "
        f"{risk['risk_score']:.2f}/100",
        flush=True
    )

    print(
        f"🏛 Arbitration Needed: "
        f"{agreement['arbitration_needed']}",
        flush=True
    )

    print(
        f"🧬 Known Definition Conflicts: "
        f"{agreement['known_definition_conflicts']}",
        flush=True
    )

    print(
        "\n📋 Status Counts:",
        flush=True
    )

    for status in (
        "AGREED",
        "AGREED_MINOR_DIFF",
        "REVIEW",
        "CONFLICT",
        "SCALE_ANOMALY",
        "DEFINITION_CONFLICT",
        "SINGLE_SOURCE",
        "NO_DATA"
    ):

        print(
            f"- {status}: "
            f"{counts[status]}",
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
                f"Std="
                f"{item['std']:.2f}",
                flush=True
            )

    return {
        "symbol":
            symbol,

        "company_name":
            name,

        "analysis_model":
            model,

        "agreement":
            agreement,

        "coverage":
            coverage,

        "risk":
            risk,

        "counts":
            dict(
                counts
            ),
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
        "🧠 Metrics: Agreement / Coverage / Risk separated",
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

    weighted_agreement = []
    weighted_coverage = []
    weighted_risk = []

    total_dual = 0
    total_rows = 0
    total_single = 0
    total_arbitration = 0
    total_definition = 0

    overall_counts = defaultdict(
        int
    )

    for index, item in enumerate(
        summaries,
        start=1
    ):

        agreement = item[
            "agreement"
        ]

        coverage = item[
            "coverage"
        ]

        risk = item[
            "risk"
        ]

        counts = item[
            "counts"
        ]

        print(
            f"{index:02d}. "
            f"{item['symbol']} | "
            f"{item['company_name']} | "
            f"{item['analysis_model']} | "
            f"Dual="
            f"{agreement['dual_count']} | "
            f"Agreement="
            f"{agreement['agreement_confidence']:.2f} | "
            f"Strong="
            f"{agreement['strong_agreement_rate']:.2f}% | "
            f"Coverage="
            f"{coverage['coverage_score']:.2f} | "
            f"Risk="
            f"{risk['risk_score']:.2f} | "
            f"Arbitration="
            f"{agreement['arbitration_needed']} | "
            f"Definition="
            f"{agreement['known_definition_conflicts']}",
            flush=True
        )

        total_dual += (
            agreement[
                "dual_count"
            ]
        )

        total_rows += (
            coverage[
                "total_rows"
            ]
        )

        total_single += (
            coverage[
                "single_source_rows"
            ]
        )

        total_arbitration += (
            agreement[
                "arbitration_needed"
            ]
        )

        total_definition += (
            agreement[
                "known_definition_conflicts"
            ]
        )

        if agreement[
            "dual_count"
        ] > 0:

            weighted_agreement.extend(
                [
                    agreement[
                        "agreement_confidence"
                    ]
                ]
                * agreement[
                    "dual_count"
                ]
            )

        if coverage[
            "total_rows"
        ] > 0:

            weighted_coverage.extend(
                [
                    coverage[
                        "coverage_score"
                    ]
                ]
                * coverage[
                    "total_rows"
                ]
            )

        if agreement[
            "dual_count"
        ] > 0:

            weighted_risk.extend(
                [
                    risk[
                        "risk_score"
                    ]
                ]
                * agreement[
                    "dual_count"
                ]
            )

        for status, count in (
            counts.items()
        ):

            overall_counts[
                status
            ] += count

    overall_agreement = (
        mean(
            weighted_agreement
        )
        if weighted_agreement
        else 0.0
    )

    overall_coverage = (
        mean(
            weighted_coverage
        )
        if weighted_coverage
        else 0.0
    )

    overall_risk = (
        mean(
            weighted_risk
        )
        if weighted_risk
        else 0.0
    )

    strong_total = (
        overall_counts[
            "AGREED"
        ]
        + overall_counts[
            "AGREED_MINOR_DIFF"
        ]
        + overall_counts[
            "DEFINITION_CONFLICT"
        ]
    )

    overall_strong_rate = (
        strong_total
        / total_dual
        * 100.0
        if total_dual
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
        f"📊 Total Canonical Rows: "
        f"{total_rows}",
        flush=True
    )

    print(
        f"🤝 Total Dual-Source Rows: "
        f"{total_dual}",
        flush=True
    )

    print(
        f"🟠 Total Single-Source Rows: "
        f"{total_single}",
        flush=True
    )

    print(
        f"🏆 Overall Dual-Source Agreement Confidence: "
        f"{overall_agreement:.2f}/100",
        flush=True
    )

    print(
        f"✅ Overall Strong Agreement Rate: "
        f"{overall_strong_rate:.2f}%",
        flush=True
    )

    print(
        f"📡 Overall Source Coverage Score: "
        f"{overall_coverage:.2f}/100",
        flush=True
    )

    print(
        f"⚠️ Overall Reconciliation Risk: "
        f"{overall_risk:.2f}/100",
        flush=True
    )

    print(
        f"🏛 Total Arbitration Needed: "
        f"{total_arbitration}",
        flush=True
    )

    print(
        f"🧬 Known Definition Conflicts: "
        f"{total_definition}",
        flush=True
    )

    print(
        "\n📋 Overall Status Counts:",
        flush=True
    )

    for status in (
        "AGREED",
        "AGREED_MINOR_DIFF",
        "REVIEW",
        "CONFLICT",
        "SCALE_ANOMALY",
        "DEFINITION_CONFLICT",
        "SINGLE_SOURCE",
        "NO_DATA"
    ):

        print(
            f"- {status}: "
            f"{overall_counts[status]}",
            flush=True
        )

    print(
        "\n📌 IMPORTANT:",
        flush=True
    )

    print(
        "- SINGLE_SOURCE لا يخفض Agreement Confidence.",
        flush=True
    )

    print(
        "- Agreement يقيس فقط القيم الموجودة في المصدرين.",
        flush=True
    )

    print(
        "- Coverage يقيس مدى توفر البيانات عبر المصادر.",
        flush=True
    )

    print(
        "- Risk يقيس القيم التي تحتاج Review/Conflict/Scale arbitration.",
        flush=True
    )

    print(
        "- Definition Conflict المعروف لا يعامل كخطأ عشوائي.",
        flush=True
    )

    print(
        "- هذا الملف READ ONLY ولا يكتب أو يعدل أي بيانات.",
        flush=True
    )

    print(
        "- بعد نجاح v1.1 نراجع فقط حالات Arbitration المهمة.",
        flush=True
    )

    print(
        "- بعدها يمكن إقفال مرحلة المصادر مؤقتًا "
        "والانتقال للأخبار والـAI.",
        flush=True
    )

    print(
        "=" * 100,
        flush=True
    )


if __name__ == "__main__":

    run_reconciliation()
