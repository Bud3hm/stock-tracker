import os
from datetime import datetime, timezone
from supabase import create_client


# ============================================================
# REIT METRICS ENGINE v2
#
# أهم تحسينات v2:
# 1) معالجة غياب Q4 الربعي في Yahoo
# 2) اشتقاق Q4 من Annual - Q1 - Q2 - Q3 عند توفرها
# 3) استخدام Annual balance sheet كـ Q4 snapshot
# 4) مطابقة YoY بالتاريخ الأقرب ضمن هامش زمني
# 5) عدم اختلاق أي بيانات ناقصة
# 6) تسجيل هل الربع مشتق أم أصلي
# ============================================================


SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_SECRET_KEY = os.environ.get("SUPABASE_SECRET_KEY")

supabase = create_client(
    SUPABASE_URL,
    SUPABASE_SECRET_KEY
)


# ============================================================
# خرائط Annual -> Quarterly
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
# أدوات أساسية
# ============================================================

def safe_number(value):

    if value is None:
        return None

    try:
        return float(value)

    except (TypeError, ValueError):
        return None


def safe_divide(a, b):

    a = safe_number(a)
    b = safe_number(b)

    if (
        a is None
        or b is None
        or b == 0
    ):
        return None

    return a / b


def pct(value):

    value = safe_number(value)

    if value is None:
        return None

    return value * 100


def growth_rate(current, previous):

    current = safe_number(current)
    previous = safe_number(previous)

    if (
        current is None
        or previous is None
        or previous == 0
    ):
        return None

    return (
        (current - previous)
        / abs(previous)
    ) * 100


def difference(current, previous):

    current = safe_number(current)
    previous = safe_number(previous)

    if (
        current is None
        or previous is None
    ):
        return None

    return current - previous


def value(data, metric):

    if not data:
        return None

    return safe_number(
        data.get(metric)
    )


def sum_if_complete(values):

    cleaned = [
        safe_number(item)
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

    return sum(cleaned)


def parse_date(date_string):

    try:
        return datetime.strptime(
            str(date_string),
            "%Y-%m-%d"
        ).date()

    except Exception:
        return None


# ============================================================
# جلب صناديق REIT
# ============================================================

def get_reit_stocks():

    response = (
        supabase
        .table("stocks")
        .select(
            "id,"
            "symbol,"
            "company_name,"
            "analysis_model,"
            "data_status"
        )
        .eq(
            "analysis_model",
            "reit"
        )
        .execute()
    )

    return response.data or []


# ============================================================
# جلب البيانات المالية
# ============================================================

def get_financial_data(stock_id):

    response = (
        supabase
        .table("financial_statements")
        .select("*")
        .eq(
            "stock_id",
            stock_id
        )
        .execute()
    )

    return response.data or []


# ============================================================
# ترتيب البيانات
# ============================================================

def organize_financial_data(rows):

    annual = {}
    quarterly = {}

    for row in rows:

        period_type = str(
            row.get("period_type") or ""
        )

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
            row.get("value")
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
# اشتقاق Q4 من Annual عند غياب الربع الرابع
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

        # ----------------------------------------------------
        # إذا كان لدينا بالفعل Quarterly في نفس تاريخ السنة
        # فلا نعيد بناء الربع
        # ----------------------------------------------------

        if annual_date in quarterly:

            quarterly[
                annual_date
            ].setdefault(
                "_synthesized",
                0.0
            )

            continue

        # ----------------------------------------------------
        # نبحث عن الأرباع الموجودة في نفس السنة قبل نهاية السنة
        # ----------------------------------------------------

        same_year_dates = []

        for quarter_date in quarterly.keys():

            quarter_dt = parse_date(
                quarter_date
            )

            if quarter_dt is None:
                continue

            if (
                quarter_dt.year == year
                and quarter_dt < annual_dt
            ):

                same_year_dates.append(
                    quarter_date
                )

        same_year_dates = sorted(
            same_year_dates
        )

        # لا نشتق Q4 إلا بوجود 3 أرباع فعلية كاملة
        if len(same_year_dates) < 3:
            continue

        q123_dates = same_year_dates[-3:]

        # نتأكد أنها بالفعل منتشرة خلال السنة
        q123_parsed = [
            parse_date(item)
            for item in q123_dates
        ]

        if any(
            item is None
            for item in q123_parsed
        ):
            continue

        # يجب أن تغطي تقريبًا Q1/Q2/Q3 لا ثلاثة سجلات متقاربة
        span_days = (
            q123_parsed[-1]
            - q123_parsed[0]
        ).days

        if span_days < 150:
            continue

        synthetic = {}

        annual_metrics = annual[
            annual_date
        ]

        # ====================================================
        # FLOW METRICS
        # Annual - Q1 - Q2 - Q3 = Q4
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
        # BALANCE SHEET METRICS
        # Annual year-end = Q4 year-end snapshot
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

        # نحتاج قيمة مالية واحدة على الأقل حتى نسجل الربع
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
# إيجاد نفس الربع في العام السابق
#
# نستخدم أقرب تاريخ للهدف ضمن 45 يومًا.
# لا نستخدم ربعًا مختلفًا بعيدًا.
# ============================================================

def find_same_quarter_last_year(
    current_period,
    quarterly
):

    current_date = parse_date(
        current_period
    )

    if current_date is None:
        return None, None

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

        # فرق الأيام الموسمي بين التاريخين
        month_day_distance = abs(
            (
                candidate_date.month * 31
                + candidate_date.day
            )
            -
            (
                current_date.month * 31
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
        return None, None

    candidates.sort(
        key=lambda item: item[0]
    )

    distance, best_period = (
        candidates[0]
    )

    # لا نقبل مقارنة بعيدة زمنيًا
    if distance > 45:
        return None, None

    return (
        quarterly.get(
            best_period
        ),
        best_period
    )


# ============================================================
# حفظ المؤشرات
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

        records.append(
            {
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
            }
        )

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
# مؤشرات REIT السنوية
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

    return {

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
                total_debt - cash
                if (
                    total_debt is not None
                    and cash is not None
                )
                else None
            ),

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
# مؤشرات REIT الربعية
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
                total_debt - cash
                if (
                    total_debt is not None
                    and cash is not None
                )
                else None
            ),

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
# TTM
# ============================================================

def calculate_reit_ttm_metrics(
    quarter_dates,
    quarterly,
    index
):

    if index < 3:
        return {}

    dates = quarter_dates[
        index - 3:index + 1
    ]

    quarters = [
        quarterly[item]
        for item in dates
    ]

    revenue = sum_if_complete(
        [
            value(
                q,
                "quarterlyTotalRevenue"
            )
            for q in quarters
        ]
    )

    operating_income = sum_if_complete(
        [
            value(
                q,
                "quarterlyOperatingIncome"
            )
            for q in quarters
        ]
    )

    net_income = sum_if_complete(
        [
            value(
                q,
                "quarterlyNetIncome"
            )
            for q in quarters
        ]
    )

    ocf = sum_if_complete(
        [
            value(
                q,
                "quarterlyOperatingCashFlow"
            )
            for q in quarters
        ]
    )

    fcf = sum_if_complete(
        [
            value(
                q,
                "quarterlyFreeCashFlow"
            )
            for q in quarters
        ]
    )

    latest = quarters[-1]

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
# ثقة بيانات REIT
# ============================================================

def calculate_reit_data_confidence(
    current,
    same_quarter_last_year
):

    current_required = [
        "quarterlyTotalRevenue",
        "quarterlyOperatingIncome",
        "quarterlyNetIncome",
        "quarterlyTotalAssets",
        "quarterlyStockholdersEquity",
        "quarterlyTotalDebt"
    ]

    current_available = sum(
        1
        for metric in current_required
        if value(
            current,
            metric
        ) is not None
    )

    current_score = (
        current_available
        / len(current_required)
    ) * 100

    # YoY reference is also part of confidence
    yoy_required = [
        "quarterlyTotalRevenue",
        "quarterlyOperatingIncome",
        "quarterlyNetIncome"
    ]

    yoy_available = sum(
        1
        for metric in yoy_required
        if value(
            same_quarter_last_year,
            metric
        ) is not None
    )

    yoy_score = (
        yoy_available
        / len(yoy_required)
    ) * 100

    return (
        current_score * 0.70
        + yoy_score * 0.30
    )


# ============================================================
# Signal Engine
# ============================================================

def calculate_reit_signal_scores(
    metrics
):

    improvement = 0
    risk = 0
    used = 0

    def evaluate_positive(metric_name):

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
                None
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
            - risk_score
    }


# ============================================================
# تشغيل REIT واحد
# ============================================================

def calculate_reit_metrics(stock):

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
        + "=" * 72,
        flush=True
    )

    print(
        f"🏢 REIT: "
        f"{symbol} | "
        f"{company_name}",
        flush=True
    )

    print(
        "=" * 72,
        flush=True
    )

    rows = get_financial_data(
        stock_id
    )

    if not rows:

        print(
            "⚠️ No financial data",
            flush=True
        )

        return {
            "status":
                "no_data",

            "metrics":
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
    # إصلاح فجوات Q4
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
    # Annual
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

        metrics = (
            calculate_reit_annual_metrics(
                current,
                previous
            )
        )

        total_saved += save_metrics(
            stock_id,
            period_end,
            metrics
        )

    # ========================================================
    # Quarterly
    # ========================================================

    quarter_dates = sorted(
        quarterly.keys()
    )

    for index, period_end in enumerate(
        quarter_dates
    ):

        current = quarterly[
            period_end
        ]

        previous_quarter = (
            quarterly[
                quarter_dates[
                    index - 1
                ]
            ]
            if index > 0
            else None
        )

        (
            same_quarter_last_year,
            yoy_period
        ) = find_same_quarter_last_year(
            period_end,
            quarterly
        )

        metrics = (
            calculate_reit_quarter_metrics(
                current,
                previous_quarter,
                same_quarter_last_year
            )
        )

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

        # ----------------------------------------------------
        # Provenance / quality flags
        # ----------------------------------------------------

        metrics[
            "reit_q_synthesized_flag"
        ] = (
            1.0
            if period_end
            in synthesized_periods
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
            "reit_data_confidence_score"
        ] = calculate_reit_data_confidence(
            current,
            same_quarter_last_year
        )

        signals = (
            calculate_reit_signal_scores(
                metrics
            )
        )

        metrics.update(
            signals
        )

        total_saved += save_metrics(
            stock_id,
            period_end,
            metrics
        )

        print(
            f"📊 {period_end} | "
            f"Synthetic="
            f"{int(metrics['reit_q_synthesized_flag'])} | "
            f"YoYRef="
            f"{yoy_period or 'N/A'} | "
            f"Confidence="
            f"{metrics['reit_data_confidence_score']:.2f}",
            flush=True
        )

    print(
        f"✅ {symbol} | "
        f"{total_saved} REIT metrics saved",
        flush=True
    )

    return {
        "status":
            "success",

        "metrics":
            total_saved,

        "quarterly_periods":
            len(quarter_dates),

        "synthetic_periods":
            len(synthesized_periods)
    }


# ============================================================
# تشغيل جميع REIT
# ============================================================

def run_reit_metrics():

    print(
        "\n"
        + "#" * 72,
        flush=True
    )

    print(
        "🏢 REIT METRICS ENGINE v2",
        flush=True
    )

    print(
        "#" * 72,
        flush=True
    )

    stocks = get_reit_stocks()

    print(
        f"🏢 Total REITs: "
        f"{len(stocks)}",
        flush=True
    )

    success = 0
    no_data = 0
    errors = 0
    total_metrics = 0

    details = []

    for stock in stocks:

        try:

            result = (
                calculate_reit_metrics(
                    stock
                )
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

            elif status == "no_data":

                no_data += 1

            details.append(
                (
                    stock["symbol"],
                    status,
                    count,
                    result.get(
                        "quarterly_periods",
                        0
                    ),
                    result.get(
                        "synthetic_periods",
                        0
                    )
                )
            )

        except Exception as error:

            errors += 1

            details.append(
                (
                    stock["symbol"],
                    "error",
                    0,
                    0,
                    0
                )
            )

            print(
                f"🔴 "
                f"{stock['symbol']} | "
                f"{type(error).__name__}: "
                f"{error}",
                flush=True
            )

    print(
        "\n"
        + "=" * 72,
        flush=True
    )

    print(
        "📋 FINAL REIT METRICS SUMMARY v2",
        flush=True
    )

    print(
        "=" * 72,
        flush=True
    )

    print(
        f"🏢 Total REITs: "
        f"{len(stocks)}",
        flush=True
    )

    print(
        f"🟢 Success: "
        f"{success}",
        flush=True
    )

    print(
        f"🟡 No Data: "
        f"{no_data}",
        flush=True
    )

    print(
        f"🔴 Errors: "
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
        quarterly_count,
        synthetic_count
    ) in details:

        print(
            f"{symbol} | "
            f"{status} | "
            f"{count} metrics | "
            f"Quarters={quarterly_count} | "
            f"SyntheticQ4={synthetic_count}",
            flush=True
        )

    print(
        "=" * 72,
        flush=True
    )


# ============================================================
# START
# ============================================================

if __name__ == "__main__":

    run_reit_metrics()
