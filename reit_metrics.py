import os
from datetime import datetime, timezone
from supabase import create_client


# ============================================================
# REIT METRICS ENGINE v3
#
# YAHOO SAFE MODE
#
# المبادئ:
#
# 1) Yahoo هو المصدر التشغيلي الحالي للـ REIT.
#
# 2) البيانات الناقصة لا تعتبر صفراً.
#
# 3) المؤشر الذي لا يمكن حسابه لا يتم اختلاقه.
#
# 4) QoQ لا يحسب إلا إذا كان الربع السابق زمنياً صالحاً.
#
# 5) YoY لا يحسب إلا إذا وجد نفس الربع تقريباً في العام السابق.
#
# 6) TTM لا يحسب إلا بوجود 4 أرباع متصلة زمنياً.
#
# 7) Q4 يمكن اشتقاقه فقط من:
#       Annual - Q1 - Q2 - Q3
#    عند توفر الثلاثة بشكل موثوق.
#
# 8) نقص الأرباع ينتج:
#       PARTIAL DATA
#    وليس:
#       SYSTEM FAILURE
#
# 9) إضافة Coverage / Availability Flags
#    حتى تستخدمها Data Quality و System Audit لاحقاً.
#
# 10) لا توجد أي محاولة لجلب مصادر رسمية خارج Yahoo.
# ============================================================


SUPABASE_URL = os.environ.get(
    "SUPABASE_URL"
)

SUPABASE_SECRET_KEY = os.environ.get(
    "SUPABASE_SECRET_KEY"
)


if not SUPABASE_URL:
    raise RuntimeError(
        "SUPABASE_URL environment variable is missing"
    )


if not SUPABASE_SECRET_KEY:
    raise RuntimeError(
        "SUPABASE_SECRET_KEY environment variable is missing"
    )


supabase = create_client(
    SUPABASE_URL,
    SUPABASE_SECRET_KEY
)


ENGINE_NAME = "REIT METRICS ENGINE v3 | YAHOO SAFE MODE"


# ============================================================
# Annual -> Quarterly maps
# ============================================================


FLOW_METRIC_MAP = {

    "annualTotalRevenue":
        "quarterlyTotalRevenue",

    "annualOperatingIncome":
        "quarterlyOperatingIncome",

    "annualNetIncome":
        "quarterlyNetIncome",

    "annualOperatingCashFlow":
        "quarterlyOperatingCashFlow",

    "annualFreeCashFlow":
        "quarterlyFreeCashFlow",

    "annualCapitalExpenditure":
        "quarterlyCapitalExpenditure"
}


BALANCE_METRIC_MAP = {

    "annualTotalAssets":
        "quarterlyTotalAssets",

    "annualTotalLiabilitiesNetMinorityInterest":
        "quarterlyTotalLiabilitiesNetMinorityInterest",

    "annualStockholdersEquity":
        "quarterlyStockholdersEquity",

    "annualTotalDebt":
        "quarterlyTotalDebt",

    "annualCashCashEquivalentsAndShortTermInvestments":
        "quarterlyCashCashEquivalentsAndShortTermInvestments",

    "annualCurrentAssets":
        "quarterlyCurrentAssets",

    "annualCurrentLiabilities":
        "quarterlyCurrentLiabilities"
}


# ============================================================
# Required fields
# ============================================================


CURRENT_CORE_FIELDS = [

    "quarterlyTotalRevenue",
    "quarterlyOperatingIncome",
    "quarterlyNetIncome",
    "quarterlyTotalAssets",
    "quarterlyStockholdersEquity",
    "quarterlyTotalDebt"
]


YOY_CORE_FIELDS = [

    "quarterlyTotalRevenue",
    "quarterlyOperatingIncome",
    "quarterlyNetIncome"
]


ANNUAL_CORE_FIELDS = [

    "annualTotalRevenue",
    "annualNetIncome",
    "annualTotalAssets",
    "annualStockholdersEquity"
]


# ============================================================
# Basic helpers
# ============================================================


def safe_number(value):

    if value is None:
        return None

    try:
        return float(
            value
        )

    except (
        TypeError,
        ValueError
    ):
        return None


def safe_divide(
    a,
    b
):

    a = safe_number(
        a
    )

    b = safe_number(
        b
    )


    if (
        a is None
        or b is None
        or b == 0
    ):
        return None


    return a / b


def pct(value):

    value = safe_number(
        value
    )


    if value is None:
        return None


    return value * 100


def growth_rate(
    current,
    previous
):

    current = safe_number(
        current
    )

    previous = safe_number(
        previous
    )


    if (
        current is None
        or previous is None
        or previous == 0
    ):
        return None


    return (
        (
            current
            - previous
        )
        / abs(
            previous
        )
    ) * 100


def difference(
    current,
    previous
):

    current = safe_number(
        current
    )

    previous = safe_number(
        previous
    )


    if (
        current is None
        or previous is None
    ):
        return None


    return (
        current
        - previous
    )


def value(
    data,
    metric
):

    if not data:
        return None


    return safe_number(
        data.get(
            metric
        )
    )


def sum_if_complete(values):

    cleaned = [
        safe_number(
            item
        )
        for item in values
    ]


    if (
        not cleaned
        or any(
            item is None
            for item in cleaned
        )
    ):
        return None


    return sum(
        cleaned
    )


def parse_date(
    date_string
):

    try:

        return datetime.strptime(
            str(
                date_string
            ),
            "%Y-%m-%d"
        ).date()

    except Exception:

        return None


def calculate_field_coverage(
    data,
    required_fields
):

    if not required_fields:
        return 0.0


    available = sum(
        1
        for metric in required_fields
        if value(
            data,
            metric
        ) is not None
    )


    return (
        available
        / len(
            required_fields
        )
    ) * 100


# ============================================================
# REIT stocks
# ============================================================


def get_reit_stocks():

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
            "data_status,"
            "is_active"
        )
        .eq(
            "analysis_model",
            "reit"
        )
        .eq(
            "is_active",
            True
        )
        .execute()
    )


    return response.data or []


# ============================================================
# Financial data
# ============================================================


def get_financial_data(
    stock_id
):

    response = (
        supabase
        .table(
            "financial_statements"
        )
        .select(
            "*"
        )
        .eq(
            "stock_id",
            stock_id
        )
        .execute()
    )


    return response.data or []


# ============================================================
# Organize Yahoo financial data
# ============================================================


def organize_financial_data(
    rows
):

    annual = {}
    quarterly = {}


    for row in rows:

        period_type = str(
            row.get(
                "period_type"
            )
            or ""
        ).upper()


        period_end_raw = row.get(
            "period_end"
        )


        if not period_end_raw:
            continue


        period_end = str(
            period_end_raw
        )


        metric = row.get(
            "metric"
        )


        metric_value = safe_number(
            row.get(
                "value"
            )
        )


        if (
            not metric
            or metric_value is None
        ):
            continue


        if period_type == "12M":

            annual.setdefault(
                period_end,
                {}
            )


            annual[
                period_end
            ][
                metric
            ] = metric_value


        elif period_type == "3M":

            quarterly.setdefault(
                period_end,
                {}
            )


            quarterly[
                period_end
            ][
                metric
            ] = metric_value


    return (
        annual,
        quarterly
    )


# ============================================================
# Quarter spacing helpers
# ============================================================


def quarter_gap_days(
    earlier_period,
    later_period
):

    earlier = parse_date(
        earlier_period
    )

    later = parse_date(
        later_period
    )


    if (
        earlier is None
        or later is None
    ):
        return None


    return (
        later
        - earlier
    ).days


def is_valid_quarter_gap(
    earlier_period,
    later_period
):

    gap = quarter_gap_days(
        earlier_period,
        later_period
    )


    if gap is None:
        return False


    # يسمح باختلاف نهايات الأشهر والإجازات
    return (
        60
        <= gap
        <= 125
    )


# ============================================================
# Previous quarter
#
# لا نستخدم السجل السابق بشكل أعمى.
# ============================================================


def find_previous_quarter(
    current_period,
    quarterly
):

    current_date = parse_date(
        current_period
    )


    if current_date is None:
        return (
            None,
            None
        )


    candidates = []


    for period_end in quarterly.keys():

        if period_end == current_period:
            continue


        candidate_date = parse_date(
            period_end
        )


        if candidate_date is None:
            continue


        if candidate_date >= current_date:
            continue


        gap_days = (
            current_date
            - candidate_date
        ).days


        if (
            60
            <= gap_days
            <= 125
        ):

            candidates.append(
                (
                    gap_days,
                    period_end
                )
            )


    if not candidates:

        return (
            None,
            None
        )


    candidates.sort(
        key=lambda item:
            item[
                0
            ]
    )


    best_period = candidates[
        0
    ][
        1
    ]


    return (
        quarterly.get(
            best_period
        ),
        best_period
    )


# ============================================================
# Same quarter last year
# ============================================================


def find_same_quarter_last_year(
    current_period,
    quarterly
):

    current_date = parse_date(
        current_period
    )


    if current_date is None:

        return (
            None,
            None
        )


    target_year = (
        current_date.year
        - 1
    )


    candidates = []


    for period_end in quarterly.keys():

        candidate_date = parse_date(
            period_end
        )


        if candidate_date is None:
            continue


        if candidate_date.year != target_year:
            continue


        month_day_distance = abs(
            (
                candidate_date.month
                * 31
                + candidate_date.day
            )
            -
            (
                current_date.month
                * 31
                + current_date.day
            )
        )


        candidates.append(
            (
                month_day_distance,
                period_end
            )
        )


    if not candidates:

        return (
            None,
            None
        )


    candidates.sort(
        key=lambda item:
            item[
                0
            ]
    )


    distance, best_period = (
        candidates[
            0
        ]
    )


    if distance > 45:

        return (
            None,
            None
        )


    return (
        quarterly.get(
            best_period
        ),
        best_period
    )


# ============================================================
# Q4 synthesis
# ============================================================


def build_synthetic_q4(
    annual,
    quarterly
):

    synthesized_periods = set()


    for annual_date in sorted(
        annual.keys()
    ):

        annual_dt = parse_date(
            annual_date
        )


        if annual_dt is None:
            continue


        year = annual_dt.year


        # Yahoo already provided a 3M entry
        if annual_date in quarterly:

            quarterly[
                annual_date
            ].setdefault(
                "_synthesized",
                0.0
            )

            continue


        same_year_dates = []


        for quarter_date in quarterly.keys():

            quarter_dt = parse_date(
                quarter_date
            )


            if quarter_dt is None:
                continue


            if (
                quarter_dt.year
                == year
                and quarter_dt
                < annual_dt
            ):

                same_year_dates.append(
                    quarter_date
                )


        same_year_dates = sorted(
            same_year_dates
        )


        # يجب أن نجد 3 أرباع فقط قبل نهاية السنة
        if len(
            same_year_dates
        ) < 3:
            continue


        q123_dates = same_year_dates[
            -3:
        ]


        q123_parsed = [
            parse_date(
                item
            )
            for item in q123_dates
        ]


        if any(
            item is None
            for item in q123_parsed
        ):
            continue


        # ====================================================
        # نتأكد أن Q1/Q2/Q3 متسلسلة فعلاً
        # ====================================================

        valid_sequence = True


        for idx in range(
            1,
            len(
                q123_dates
            )
        ):

            if not is_valid_quarter_gap(
                q123_dates[
                    idx - 1
                ],
                q123_dates[
                    idx
                ]
            ):

                valid_sequence = False
                break


        if not valid_sequence:
            continue


        # Q3 -> year end أيضاً يجب أن يكون منطقياً
        q3_to_year_end = quarter_gap_days(
            q123_dates[
                -1
            ],
            annual_date
        )


        if (
            q3_to_year_end is None
            or not (
                60
                <= q3_to_year_end
                <= 125
            )
        ):
            continue


        synthetic = {}

        annual_metrics = annual[
            annual_date
        ]


        # ====================================================
        # Flow metrics
        # ====================================================

        for (
            annual_metric,
            quarterly_metric
        ) in FLOW_METRIC_MAP.items():

            annual_value = value(
                annual_metrics,
                annual_metric
            )


            if annual_value is None:
                continue


            q_values = [

                value(
                    quarterly[
                        quarter_date
                    ],
                    quarterly_metric
                )

                for quarter_date
                in q123_dates
            ]


            q123_sum = sum_if_complete(
                q_values
            )


            if q123_sum is None:
                continue


            synthetic[
                quarterly_metric
            ] = (
                annual_value
                - q123_sum
            )


        # ====================================================
        # Balance sheet snapshot
        # ====================================================

        for (
            annual_metric,
            quarterly_metric
        ) in BALANCE_METRIC_MAP.items():

            annual_value = value(
                annual_metrics,
                annual_metric
            )


            if annual_value is not None:

                synthetic[
                    quarterly_metric
                ] = annual_value


        if not synthetic:
            continue


        synthetic[
            "_synthesized"
        ] = 1.0


        quarterly[
            annual_date
        ] = synthetic


        synthesized_periods.add(
            annual_date
        )


        print(
            f"🧩 Synthetic Q4 built: "
            f"{annual_date} | "
            f"{len(synthetic) - 1} fields",
            flush=True
        )


    return synthesized_periods


# ============================================================
# Save metrics
#
# None is NOT saved.
# This means missing ≠ zero.
# ============================================================


def save_metrics(
    stock_id,
    period_end,
    metrics
):

    calculated_at = datetime.now(
        timezone.utc
    ).isoformat()


    records = []


    for (
        metric_name,
        metric_value
    ) in metrics.items():

        metric_value = safe_number(
            metric_value
        )


        if metric_value is None:
            continue


        records.append({
            "stock_id":
                stock_id,

            "calculated_at":
                calculated_at,

            "metric_name":
                metric_name,

            "metric_value":
                metric_value,

            "period_end":
                period_end
        })


    if not records:
        return 0


    (
        supabase
        .table(
            "financial_metrics"
        )
        .upsert(
            records,
            on_conflict=(
                "stock_id,"
                "metric_name,"
                "period_end"
            )
        )
        .execute()
    )


    return len(
        records
    )


# ============================================================
# Annual metrics
# ============================================================


def calculate_reit_annual_metrics(
    current,
    previous
):

    revenue = value(
        current,
        "annualTotalRevenue"
    )

    operating_income = value(
        current,
        "annualOperatingIncome"
    )

    net_income = value(
        current,
        "annualNetIncome"
    )

    assets = value(
        current,
        "annualTotalAssets"
    )

    liabilities = value(
        current,
        "annualTotalLiabilitiesNetMinorityInterest"
    )

    equity = value(
        current,
        "annualStockholdersEquity"
    )

    total_debt = value(
        current,
        "annualTotalDebt"
    )

    cash = value(
        current,
        "annualCashCashEquivalentsAndShortTermInvestments"
    )

    operating_cash_flow = value(
        current,
        "annualOperatingCashFlow"
    )

    free_cash_flow = value(
        current,
        "annualFreeCashFlow"
    )


    previous_revenue = (
        value(
            previous,
            "annualTotalRevenue"
        )
        if previous
        else None
    )

    previous_net_income = (
        value(
            previous,
            "annualNetIncome"
        )
        if previous
        else None
    )

    previous_assets = (
        value(
            previous,
            "annualTotalAssets"
        )
        if previous
        else None
    )

    previous_equity = (
        value(
            previous,
            "annualStockholdersEquity"
        )
        if previous
        else None
    )

    previous_debt = (
        value(
            previous,
            "annualTotalDebt"
        )
        if previous
        else None
    )

    previous_ocf = (
        value(
            previous,
            "annualOperatingCashFlow"
        )
        if previous
        else None
    )


    annual_coverage = (
        calculate_field_coverage(
            current,
            ANNUAL_CORE_FIELDS
        )
    )


    return {

        # ----------------------------------------------------
        # Coverage
        # ----------------------------------------------------

        "reit_annual_data_coverage_pct":
            annual_coverage,

        "reit_annual_data_available_flag":
            (
                1.0
                if annual_coverage > 0
                else 0.0
            ),

        "reit_annual_data_complete_flag":
            (
                1.0
                if annual_coverage >= 100
                else 0.0
            ),

        # ----------------------------------------------------
        # Growth
        # ----------------------------------------------------

        "reit_annual_revenue_growth_yoy":
            growth_rate(
                revenue,
                previous_revenue
            ),

        "reit_annual_net_income_growth_yoy":
            growth_rate(
                net_income,
                previous_net_income
            ),

        "reit_annual_assets_growth_yoy":
            growth_rate(
                assets,
                previous_assets
            ),

        "reit_annual_equity_growth_yoy":
            growth_rate(
                equity,
                previous_equity
            ),

        "reit_annual_debt_growth_yoy":
            growth_rate(
                total_debt,
                previous_debt
            ),

        "reit_annual_ocf_growth_yoy":
            growth_rate(
                operating_cash_flow,
                previous_ocf
            ),

        # ----------------------------------------------------
        # Profitability
        # ----------------------------------------------------

        "reit_annual_operating_margin":
            pct(
                safe_divide(
                    operating_income,
                    revenue
                )
            ),

        "reit_annual_net_margin":
            pct(
                safe_divide(
                    net_income,
                    revenue
                )
            ),

        "reit_annual_roa":
            pct(
                safe_divide(
                    net_income,
                    assets
                )
            ),

        "reit_annual_roe":
            pct(
                safe_divide(
                    net_income,
                    equity
                )
            ),

        # ----------------------------------------------------
        # Leverage
        # ----------------------------------------------------

        "reit_annual_debt_to_equity":
            safe_divide(
                total_debt,
                equity
            ),

        "reit_annual_debt_to_assets":
            pct(
                safe_divide(
                    total_debt,
                    assets
                )
            ),

        "reit_annual_liabilities_to_assets":
            pct(
                safe_divide(
                    liabilities,
                    assets
                )
            ),

        "reit_annual_equity_to_assets":
            pct(
                safe_divide(
                    equity,
                    assets
                )
            ),

        "reit_annual_net_debt":
            (
                total_debt
                - cash
                if (
                    total_debt is not None
                    and cash is not None
                )
                else None
            ),

        # ----------------------------------------------------
        # Cash flow
        # ----------------------------------------------------

        "reit_annual_cash_conversion":
            safe_divide(
                operating_cash_flow,
                net_income
            ),

        "reit_annual_fcf_margin":
            pct(
                safe_divide(
                    free_cash_flow,
                    revenue
                )
            ),

        # ----------------------------------------------------
        # Raw annual values
        # ----------------------------------------------------

        "reit_annual_revenue":
            revenue,

        "reit_annual_operating_income":
            operating_income,

        "reit_annual_net_income":
            net_income,

        "reit_annual_total_assets":
            assets,

        "reit_annual_total_liabilities":
            liabilities,

        "reit_annual_equity":
            equity,

        "reit_annual_total_debt":
            total_debt,

        "reit_annual_cash":
            cash,

        "reit_annual_operating_cash_flow":
            operating_cash_flow,

        "reit_annual_free_cash_flow":
            free_cash_flow
    }


# ============================================================
# Quarterly metrics
# ============================================================


def calculate_reit_quarter_metrics(
    current,
    previous_quarter,
    same_quarter_last_year
):

    revenue = value(
        current,
        "quarterlyTotalRevenue"
    )

    operating_income = value(
        current,
        "quarterlyOperatingIncome"
    )

    net_income = value(
        current,
        "quarterlyNetIncome"
    )

    assets = value(
        current,
        "quarterlyTotalAssets"
    )

    liabilities = value(
        current,
        "quarterlyTotalLiabilitiesNetMinorityInterest"
    )

    equity = value(
        current,
        "quarterlyStockholdersEquity"
    )

    total_debt = value(
        current,
        "quarterlyTotalDebt"
    )

    cash = value(
        current,
        "quarterlyCashCashEquivalentsAndShortTermInvestments"
    )

    operating_cash_flow = value(
        current,
        "quarterlyOperatingCashFlow"
    )

    free_cash_flow = value(
        current,
        "quarterlyFreeCashFlow"
    )


    prev_revenue = value(
        previous_quarter,
        "quarterlyTotalRevenue"
    )

    prev_operating_income = value(
        previous_quarter,
        "quarterlyOperatingIncome"
    )

    prev_net_income = value(
        previous_quarter,
        "quarterlyNetIncome"
    )

    prev_assets = value(
        previous_quarter,
        "quarterlyTotalAssets"
    )

    prev_equity = value(
        previous_quarter,
        "quarterlyStockholdersEquity"
    )

    prev_debt = value(
        previous_quarter,
        "quarterlyTotalDebt"
    )

    prev_ocf = value(
        previous_quarter,
        "quarterlyOperatingCashFlow"
    )

    prev_fcf = value(
        previous_quarter,
        "quarterlyFreeCashFlow"
    )


    yoy_revenue = value(
        same_quarter_last_year,
        "quarterlyTotalRevenue"
    )

    yoy_operating_income = value(
        same_quarter_last_year,
        "quarterlyOperatingIncome"
    )

    yoy_net_income = value(
        same_quarter_last_year,
        "quarterlyNetIncome"
    )

    yoy_assets = value(
        same_quarter_last_year,
        "quarterlyTotalAssets"
    )

    yoy_equity = value(
        same_quarter_last_year,
        "quarterlyStockholdersEquity"
    )

    yoy_debt = value(
        same_quarter_last_year,
        "quarterlyTotalDebt"
    )

    yoy_ocf = value(
        same_quarter_last_year,
        "quarterlyOperatingCashFlow"
    )

    yoy_fcf = value(
        same_quarter_last_year,
        "quarterlyFreeCashFlow"
    )


    operating_margin = pct(
        safe_divide(
            operating_income,
            revenue
        )
    )

    net_margin = pct(
        safe_divide(
            net_income,
            revenue
        )
    )


    prev_operating_margin = pct(
        safe_divide(
            prev_operating_income,
            prev_revenue
        )
    )

    prev_net_margin = pct(
        safe_divide(
            prev_net_income,
            prev_revenue
        )
    )


    yoy_operating_margin = pct(
        safe_divide(
            yoy_operating_income,
            yoy_revenue
        )
    )

    yoy_net_margin = pct(
        safe_divide(
            yoy_net_income,
            yoy_revenue
        )
    )


    return {

        # ----------------------------------------------------
        # QoQ
        # ----------------------------------------------------

        "reit_q_revenue_growth_qoq":
            growth_rate(
                revenue,
                prev_revenue
            ),

        "reit_q_operating_income_growth_qoq":
            growth_rate(
                operating_income,
                prev_operating_income
            ),

        "reit_q_net_income_growth_qoq":
            growth_rate(
                net_income,
                prev_net_income
            ),

        "reit_q_assets_growth_qoq":
            growth_rate(
                assets,
                prev_assets
            ),

        "reit_q_equity_growth_qoq":
            growth_rate(
                equity,
                prev_equity
            ),

        "reit_q_debt_growth_qoq":
            growth_rate(
                total_debt,
                prev_debt
            ),

        "reit_q_ocf_growth_qoq":
            growth_rate(
                operating_cash_flow,
                prev_ocf
            ),

        "reit_q_fcf_growth_qoq":
            growth_rate(
                free_cash_flow,
                prev_fcf
            ),

        # ----------------------------------------------------
        # YoY
        # ----------------------------------------------------

        "reit_q_revenue_growth_yoy":
            growth_rate(
                revenue,
                yoy_revenue
            ),

        "reit_q_operating_income_growth_yoy":
            growth_rate(
                operating_income,
                yoy_operating_income
            ),

        "reit_q_net_income_growth_yoy":
            growth_rate(
                net_income,
                yoy_net_income
            ),

        "reit_q_assets_growth_yoy":
            growth_rate(
                assets,
                yoy_assets
            ),

        "reit_q_equity_growth_yoy":
            growth_rate(
                equity,
                yoy_equity
            ),

        "reit_q_debt_growth_yoy":
            growth_rate(
                total_debt,
                yoy_debt
            ),

        "reit_q_ocf_growth_yoy":
            growth_rate(
                operating_cash_flow,
                yoy_ocf
            ),

        "reit_q_fcf_growth_yoy":
            growth_rate(
                free_cash_flow,
                yoy_fcf
            ),

        # ----------------------------------------------------
        # Margins
        # ----------------------------------------------------

        "reit_q_operating_margin":
            operating_margin,

        "reit_q_net_margin":
            net_margin,

        "reit_q_operating_margin_change_qoq":
            difference(
                operating_margin,
                prev_operating_margin
            ),

        "reit_q_net_margin_change_qoq":
            difference(
                net_margin,
                prev_net_margin
            ),

        "reit_q_operating_margin_change_yoy":
            difference(
                operating_margin,
                yoy_operating_margin
            ),

        "reit_q_net_margin_change_yoy":
            difference(
                net_margin,
                yoy_net_margin
            ),

        # ----------------------------------------------------
        # Balance sheet
        # ----------------------------------------------------

        "reit_q_debt_to_equity":
            safe_divide(
                total_debt,
                equity
            ),

        "reit_q_debt_to_assets":
            pct(
                safe_divide(
                    total_debt,
                    assets
                )
            ),

        "reit_q_liabilities_to_assets":
            pct(
                safe_divide(
                    liabilities,
                    assets
                )
            ),

        "reit_q_equity_to_assets":
            pct(
                safe_divide(
                    equity,
                    assets
                )
            ),

        "reit_q_net_debt":
            (
                total_debt
                - cash
                if (
                    total_debt is not None
                    and cash is not None
                )
                else None
            ),

        # ----------------------------------------------------
        # Returns
        # ----------------------------------------------------

        "reit_q_roa_annualized":
            pct(
                safe_divide(
                    (
                        net_income * 4
                        if net_income is not None
                        else None
                    ),
                    assets
                )
            ),

        "reit_q_roe_annualized":
            pct(
                safe_divide(
                    (
                        net_income * 4
                        if net_income is not None
                        else None
                    ),
                    equity
                )
            ),

        # ----------------------------------------------------
        # Cash
        # ----------------------------------------------------

        "reit_q_cash_conversion":
            safe_divide(
                operating_cash_flow,
                net_income
            ),

        "reit_q_fcf_margin":
            pct(
                safe_divide(
                    free_cash_flow,
                    revenue
                )
            ),

        # ----------------------------------------------------
        # Raw quarterly
        # ----------------------------------------------------

        "reit_q_revenue":
            revenue,

        "reit_q_operating_income":
            operating_income,

        "reit_q_net_income":
            net_income,

        "reit_q_total_assets":
            assets,

        "reit_q_total_liabilities":
            liabilities,

        "reit_q_equity":
            equity,

        "reit_q_total_debt":
            total_debt,

        "reit_q_cash":
            cash,

        "reit_q_operating_cash_flow":
            operating_cash_flow,

        "reit_q_free_cash_flow":
            free_cash_flow
    }


# ============================================================
# TTM continuity
# ============================================================


def get_valid_ttm_dates(
    quarter_dates,
    index
):

    if index < 3:
        return None


    dates = quarter_dates[
        index - 3:
        index + 1
    ]


    if len(
        dates
    ) != 4:
        return None


    for idx in range(
        1,
        len(
            dates
        )
    ):

        if not is_valid_quarter_gap(
            dates[
                idx - 1
            ],
            dates[
                idx
            ]
        ):

            return None


    return dates


# ============================================================
# TTM metrics
# ============================================================


def calculate_reit_ttm_metrics(
    quarter_dates,
    quarterly,
    index
):

    dates = get_valid_ttm_dates(
        quarter_dates,
        index
    )


    if dates is None:
        return {}


    quarters = [
        quarterly[
            item
        ]
        for item in dates
    ]


    revenue = sum_if_complete(
        [
            value(
                quarter,
                "quarterlyTotalRevenue"
            )
            for quarter in quarters
        ]
    )


    operating_income = sum_if_complete(
        [
            value(
                quarter,
                "quarterlyOperatingIncome"
            )
            for quarter in quarters
        ]
    )


    net_income = sum_if_complete(
        [
            value(
                quarter,
                "quarterlyNetIncome"
            )
            for quarter in quarters
        ]
    )


    ocf = sum_if_complete(
        [
            value(
                quarter,
                "quarterlyOperatingCashFlow"
            )
            for quarter in quarters
        ]
    )


    fcf = sum_if_complete(
        [
            value(
                quarter,
                "quarterlyFreeCashFlow"
            )
            for quarter in quarters
        ]
    )


    latest = quarters[
        -1
    ]


    assets = value(
        latest,
        "quarterlyTotalAssets"
    )

    equity = value(
        latest,
        "quarterlyStockholdersEquity"
    )

    debt = value(
        latest,
        "quarterlyTotalDebt"
    )


    return {

        "reit_ttm_revenue":
            revenue,

        "reit_ttm_operating_income":
            operating_income,

        "reit_ttm_net_income":
            net_income,

        "reit_ttm_operating_cash_flow":
            ocf,

        "reit_ttm_free_cash_flow":
            fcf,

        "reit_ttm_operating_margin":
            pct(
                safe_divide(
                    operating_income,
                    revenue
                )
            ),

        "reit_ttm_net_margin":
            pct(
                safe_divide(
                    net_income,
                    revenue
                )
            ),

        "reit_ttm_roa":
            pct(
                safe_divide(
                    net_income,
                    assets
                )
            ),

        "reit_ttm_roe":
            pct(
                safe_divide(
                    net_income,
                    equity
                )
            ),

        "reit_ttm_debt_to_equity":
            safe_divide(
                debt,
                equity
            ),

        "reit_ttm_cash_conversion":
            safe_divide(
                ocf,
                net_income
            ),

        "reit_ttm_fcf_margin":
            pct(
                safe_divide(
                    fcf,
                    revenue
                )
            )
    }


# ============================================================
# Data confidence
# ============================================================


def calculate_reit_data_confidence(
    current,
    previous_quarter,
    same_quarter_last_year,
    ttm_ready
):

    current_score = (
        calculate_field_coverage(
            current,
            CURRENT_CORE_FIELDS
        )
    )


    qoq_score = (
        calculate_field_coverage(
            previous_quarter,
            YOY_CORE_FIELDS
        )
        if previous_quarter
        else 0.0
    )


    yoy_score = (
        calculate_field_coverage(
            same_quarter_last_year,
            YOY_CORE_FIELDS
        )
        if same_quarter_last_year
        else 0.0
    )


    ttm_score = (
        100.0
        if ttm_ready
        else 0.0
    )


    # Current data has the highest importance.
    confidence = (
        current_score * 0.55
        + qoq_score * 0.15
        + yoy_score * 0.20
        + ttm_score * 0.10
    )


    return {
        "confidence":
            confidence,

        "current_coverage":
            current_score,

        "qoq_coverage":
            qoq_score,

        "yoy_coverage":
            yoy_score
    }


# ============================================================
# Signal Engine
#
# Important:
# Only available metrics participate.
# Missing data is neutral, not negative.
# ============================================================


def calculate_reit_signal_scores(
    metrics
):

    improvement = 0
    risk = 0
    used = 0


    def evaluate_positive(
        metric_name
    ):

        nonlocal improvement
        nonlocal risk
        nonlocal used


        metric_value = safe_number(
            metrics.get(
                metric_name
            )
        )


        if metric_value is None:
            return


        used += 1


        if metric_value > 0:

            improvement += 1


        elif metric_value < 0:

            risk += 1


    evaluate_positive(
        "reit_q_revenue_growth_yoy"
    )

    evaluate_positive(
        "reit_q_operating_income_growth_yoy"
    )

    evaluate_positive(
        "reit_q_net_income_growth_yoy"
    )

    evaluate_positive(
        "reit_q_equity_growth_yoy"
    )

    evaluate_positive(
        "reit_q_operating_margin_change_yoy"
    )


    debt_growth = safe_number(
        metrics.get(
            "reit_q_debt_growth_yoy"
        )
    )


    if debt_growth is not None:

        used += 1


        if debt_growth <= 0:

            improvement += 1


        elif debt_growth > 15:

            risk += 1


    debt_to_assets = safe_number(
        metrics.get(
            "reit_q_debt_to_assets"
        )
    )


    if debt_to_assets is not None:

        used += 1


        if debt_to_assets <= 35:

            improvement += 1


        elif debt_to_assets >= 50:

            risk += 1


    cash_conversion = safe_number(
        metrics.get(
            "reit_ttm_cash_conversion"
        )
    )


    if cash_conversion is not None:

        used += 1


        if cash_conversion >= 1:

            improvement += 1


        elif cash_conversion < 0.6:

            risk += 1


    if used == 0:

        return {

            "reit_signal_improvement_score":
                None,

            "reit_signal_risk_score":
                None,

            "reit_signal_net_score":
                None,

            "reit_signal_inputs_used":
                0.0
        }


    improvement_score = (
        improvement
        / used
    ) * 100


    risk_score = (
        risk
        / used
    ) * 100


    return {

        "reit_signal_improvement_score":
            improvement_score,

        "reit_signal_risk_score":
            risk_score,

        "reit_signal_net_score":
            improvement_score
            - risk_score,

        "reit_signal_inputs_used":
            float(
                used
            )
    }


# ============================================================
# Calculate one REIT
# ============================================================


def calculate_reit_metrics(
    stock
):

    stock_id = stock[
        "id"
    ]

    symbol = stock[
        "symbol"
    ]

    company_name = (
        stock.get(
            "company_name"
        )
        or symbol
    )


    print(
        "\n"
        + "=" * 78,
        flush=True
    )

    print(
        f"🏢 REIT: "
        f"{symbol} | "
        f"{company_name}",
        flush=True
    )

    print(
        "=" * 78,
        flush=True
    )


    rows = get_financial_data(
        stock_id
    )


    if not rows:

        print(
            "🟡 DATA_INCOMPLETE | "
            "No Yahoo financial data",
            flush=True
        )


        return {

            "status":
                "data_incomplete",

            "metrics":
                0,

            "quarterly_periods":
                0,

            "annual_periods":
                0,

            "synthetic_periods":
                0
        }


    (
        annual,
        quarterly
    ) = organize_financial_data(
        rows
    )


    print(
        f"📅 Raw annual periods: "
        f"{len(annual)}",
        flush=True
    )

    print(
        f"📅 Raw quarterly periods: "
        f"{len(quarterly)}",
        flush=True
    )


    # ========================================================
    # Synthetic Q4
    # ========================================================

    synthesized_periods = (
        build_synthetic_q4(
            annual,
            quarterly
        )
    )


    print(
        f"🧩 Synthetic Q4 periods: "
        f"{len(synthesized_periods)}",
        flush=True
    )


    print(
        f"📅 Final quarterly periods: "
        f"{len(quarterly)}",
        flush=True
    )


    total_saved = 0


    # ========================================================
    # Annual metrics
    # ========================================================

    annual_dates = sorted(
        annual.keys()
    )


    for index, period_end in enumerate(
        annual_dates
    ):

        current = annual[
            period_end
        ]


        previous = (
            annual[
                annual_dates[
                    index - 1
                ]
            ]
            if index > 0
            else None
        )


        metrics = calculate_reit_annual_metrics(
            current,
            previous
        )


        total_saved += save_metrics(
            stock_id,
            period_end,
            metrics
        )


    # ========================================================
    # Quarterly metrics
    # ========================================================

    quarter_dates = sorted(
        quarterly.keys()
    )


    latest_confidence = None

    latest_data_partial = True


    for index, period_end in enumerate(
        quarter_dates
    ):

        current = quarterly[
            period_end
        ]


        (
            previous_quarter,
            previous_quarter_period
        ) = find_previous_quarter(
            period_end,
            quarterly
        )


        (
            same_quarter_last_year,
            yoy_period
        ) = find_same_quarter_last_year(
            period_end,
            quarterly
        )


        metrics = calculate_reit_quarter_metrics(
            current,
            previous_quarter,
            same_quarter_last_year
        )


        # ====================================================
        # TTM
        # ====================================================

        valid_ttm_dates = (
            get_valid_ttm_dates(
                quarter_dates,
                index
            )
        )


        ttm_ready = (
            valid_ttm_dates
            is not None
        )


        if ttm_ready:

            ttm_metrics = (
                calculate_reit_ttm_metrics(
                    quarter_dates,
                    quarterly,
                    index
                )
            )


            metrics.update(
                ttm_metrics
            )


        # ====================================================
        # Provenance / Availability
        # ====================================================

        current_coverage = (
            calculate_field_coverage(
                current,
                CURRENT_CORE_FIELDS
            )
        )


        confidence = (
            calculate_reit_data_confidence(
                current,
                previous_quarter,
                same_quarter_last_year,
                ttm_ready
            )
        )


        metrics[
            "reit_q_synthesized_flag"
        ] = (
            1.0
            if period_end
            in synthesized_periods
            else 0.0
        )


        metrics[
            "reit_q_qoq_reference_available"
        ] = (
            1.0
            if previous_quarter
            else 0.0
        )


        metrics[
            "reit_q_yoy_reference_available"
        ] = (
            1.0
            if same_quarter_last_year
            else 0.0
        )


        metrics[
            "reit_ttm_ready_flag"
        ] = (
            1.0
            if ttm_ready
            else 0.0
        )


        metrics[
            "reit_data_current_coverage_pct"
        ] = current_coverage


        metrics[
            "reit_data_qoq_coverage_pct"
        ] = confidence[
            "qoq_coverage"
        ]


        metrics[
            "reit_data_yoy_coverage_pct"
        ] = confidence[
            "yoy_coverage"
        ]


        metrics[
            "reit_data_confidence_score"
        ] = confidence[
            "confidence"
        ]


        # ----------------------------------------------------
        # Usable means:
        # there is enough current data to analyze something.
        # It does NOT require YoY or TTM.
        # ----------------------------------------------------

        metrics[
            "reit_data_usable_flag"
        ] = (
            1.0
            if current_coverage >= 50
            else 0.0
        )


        # ----------------------------------------------------
        # Partial data is expected and is not a system error.
        # ----------------------------------------------------

        partial_data = (
            current_coverage < 100
            or previous_quarter is None
            or same_quarter_last_year is None
            or not ttm_ready
        )


        metrics[
            "reit_data_partial_flag"
        ] = (
            1.0
            if partial_data
            else 0.0
        )


        # ====================================================
        # Signals
        # ====================================================

        signals = calculate_reit_signal_scores(
            metrics
        )


        metrics.update(
            signals
        )


        total_saved += save_metrics(
            stock_id,
            period_end,
            metrics
        )


        latest_confidence = confidence[
            "confidence"
        ]


        latest_data_partial = partial_data


        print(
            f"📊 {period_end} | "
            f"Synthetic="
            f"{int(metrics['reit_q_synthesized_flag'])} | "
            f"QoQRef="
            f"{previous_quarter_period or 'N/A'} | "
            f"YoYRef="
            f"{yoy_period or 'N/A'} | "
            f"TTM="
            f"{'READY' if ttm_ready else 'N/A'} | "
            f"CurrentCoverage="
            f"{current_coverage:.1f}% | "
            f"Confidence="
            f"{confidence['confidence']:.1f}%",
            flush=True
        )


    # ========================================================
    # Final status
    # ========================================================

    if (
        not annual_dates
        and not quarter_dates
    ):

        final_status = (
            "data_incomplete"
        )


    elif quarter_dates:

        if (
            latest_confidence is not None
            and latest_confidence >= 75
            and not latest_data_partial
        ):

            final_status = (
                "success"
            )

        else:

            final_status = (
                "success_with_limitations"
            )


    else:

        # Annual-only REIT is still analyzable.
        final_status = (
            "success_with_limitations"
        )


    print(
        f"✅ {symbol} | "
        f"{total_saved} REIT metrics saved | "
        f"Status="
        f"{final_status}",
        flush=True
    )


    return {

        "status":
            final_status,

        "metrics":
            total_saved,

        "quarterly_periods":
            len(
                quarter_dates
            ),

        "annual_periods":
            len(
                annual_dates
            ),

        "synthetic_periods":
            len(
                synthesized_periods
            ),

        "latest_confidence":
            latest_confidence
    }


# ============================================================
# Run all REITs
# ============================================================


def run_reit_metrics():

    print(
        "\n"
        + "#" * 78,
        flush=True
    )


    print(
        f"🏢 {ENGINE_NAME}",
        flush=True
    )


    print(
        "#" * 78,
        flush=True
    )


    print(
        "📡 Primary data source: Yahoo Finance",
        flush=True
    )


    print(
        "🛡 Missing REIT data = limitation, not failure",
        flush=True
    )


    stocks = get_reit_stocks()


    print(
        f"🏢 Total active REITs: "
        f"{len(stocks)}",
        flush=True
    )


    success = 0

    limited = 0

    incomplete = 0

    errors = 0

    total_metrics = 0

    details = []


    for stock in stocks:

        try:

            result = calculate_reit_metrics(
                stock
            )


            status = result[
                "status"
            ]


            count = result[
                "metrics"
            ]


            total_metrics += count


            if status == "success":

                success += 1


            elif status == "success_with_limitations":

                limited += 1


            elif status == "data_incomplete":

                incomplete += 1


            details.append(
                (
                    stock[
                        "symbol"
                    ],
                    status,
                    count,
                    result.get(
                        "annual_periods",
                        0
                    ),
                    result.get(
                        "quarterly_periods",
                        0
                    ),
                    result.get(
                        "synthetic_periods",
                        0
                    ),
                    result.get(
                        "latest_confidence"
                    )
                )
            )


        except Exception as error:

            errors += 1


            details.append(
                (
                    stock[
                        "symbol"
                    ],
                    "error",
                    0,
                    0,
                    0,
                    0,
                    None
                )
            )


            print(
                f"🔴 "
                f"{stock['symbol']} | "
                f"{type(error).__name__}: "
                f"{error}",
                flush=True
            )


    # ========================================================
    # Summary
    # ========================================================

    print(
        "\n"
        + "=" * 78,
        flush=True
    )


    print(
        "📋 FINAL REIT METRICS SUMMARY v3",
        flush=True
    )


    print(
        "=" * 78,
        flush=True
    )


    print(
        f"🏢 Total REITs: "
        f"{len(stocks)}",
        flush=True
    )


    print(
        f"🟢 Full Success: "
        f"{success}",
        flush=True
    )


    print(
        f"🟡 Success With Limitations: "
        f"{limited}",
        flush=True
    )


    print(
        f"🟠 Data Incomplete: "
        f"{incomplete}",
        flush=True
    )


    print(
        f"🔴 System Errors: "
        f"{errors}",
        flush=True
    )


    print(
        f"💾 Total REIT Metrics Saved: "
        f"{total_metrics}",
        flush=True
    )


    print(
        "\n📋 REITs:",
        flush=True
    )


    for (
        symbol,
        status,
        count,
        annual_count,
        quarterly_count,
        synthetic_count,
        confidence
    ) in details:

        confidence_text = (
            f"{confidence:.1f}%"
            if confidence is not None
            else "N/A"
        )


        print(
            f"{symbol} | "
            f"{status} | "
            f"{count} metrics | "
            f"Annual={annual_count} | "
            f"Quarters={quarterly_count} | "
            f"SyntheticQ4={synthetic_count} | "
            f"Confidence={confidence_text}",
            flush=True
        )


    print(
        "=" * 78,
        flush=True
    )


# ============================================================
# START
# ============================================================


if __name__ == "__main__":

    run_reit_metrics()
