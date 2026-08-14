import os
from datetime import datetime, timezone
from supabase import create_client

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_SECRET_KEY = os.environ.get("SUPABASE_SECRET_KEY")

supabase = create_client(
    SUPABASE_URL,
    SUPABASE_SECRET_KEY
)


# ============================================================
# أدوات عامة
# ============================================================

def safe_number(value):

    if value is None:
        return None

    try:
        return float(value)

    except (TypeError, ValueError):
        return None


def clamp(
    value,
    minimum=0.0,
    maximum=100.0
):

    value = safe_number(value)

    if value is None:
        return None

    return max(
        minimum,
        min(
            maximum,
            value
        )
    )


def weighted_average(items):

    total = 0.0
    weight_sum = 0.0

    for item_value, weight in items:

        item_value = safe_number(
            item_value
        )

        weight = safe_number(
            weight
        )

        if (
            item_value is None
            or weight is None
            or weight <= 0
        ):
            continue

        total += (
            item_value
            * weight
        )

        weight_sum += weight

    if weight_sum == 0:
        return None

    return (
        total
        / weight_sum
    )


# ============================================================
# دوال تحويل المؤشرات إلى Score
# ============================================================

def score_growth(value):

    value = safe_number(value)

    if value is None:
        return None

    if value >= 20:
        return 100.0

    if value >= 10:
        return 80.0

    if value >= 0:
        return 60.0

    if value >= -10:
        return 35.0

    return 10.0


def score_margin_change(value):

    value = safe_number(value)

    if value is None:
        return None

    if value >= 3:
        return 100.0

    if value >= 1:
        return 80.0

    if value >= 0:
        return 60.0

    if value >= -2:
        return 35.0

    return 10.0


def score_high_good(
    value,
    excellent,
    good,
    weak
):

    value = safe_number(value)

    if value is None:
        return None

    if value >= excellent:
        return 100.0

    if value >= good:
        return 80.0

    if value >= weak:
        return 55.0

    return 20.0


def score_low_good(
    value,
    excellent,
    acceptable,
    high
):

    value = safe_number(value)

    if value is None:
        return None

    if value <= excellent:
        return 100.0

    if value <= acceptable:
        return 75.0

    if value <= high:
        return 45.0

    return 15.0


def score_cash_conversion(value):

    value = safe_number(value)

    if value is None:
        return None

    if value >= 1.20:
        return 100.0

    if value >= 1.00:
        return 85.0

    if value >= 0.80:
        return 65.0

    if value >= 0.50:
        return 35.0

    return 10.0


def inverse_growth_score(value):

    value = safe_number(value)

    if value is None:
        return None

    return score_growth(
        -value
    )


# ============================================================
# Supabase
# ============================================================

def get_active_stocks():

    response = (
        supabase
        .table("stocks")
        .select(
            "id,"
            "symbol,"
            "company_name,"
            "sector,"
            "analysis_model,"
            "priority,"
            "data_status"
        )
        .eq(
            "is_active",
            True
        )
        .order(
            "priority",
            desc=True
        )
        .order("id")
        .execute()
    )

    return response.data or []


def get_stock_metrics(stock_id):

    response = (
        supabase
        .table(
            "financial_metrics"
        )
        .select(
            "period_end,"
            "metric_name,"
            "metric_value"
        )
        .eq(
            "stock_id",
            stock_id
        )
        .execute()
    )

    return response.data or []


# ============================================================
# تنظيم البيانات
# ============================================================

def organize_metrics(rows):

    periods = {}

    for row in rows:

        period_end = row.get(
            "period_end"
        )

        metric_name = row.get(
            "metric_name"
        )

        metric_value = safe_number(
            row.get(
                "metric_value"
            )
        )

        if (
            not period_end
            or not metric_name
            or metric_value is None
        ):
            continue

        period_end = str(
            period_end
        )

        if period_end not in periods:

            periods[
                period_end
            ] = {}

        periods[
            period_end
        ][
            metric_name
        ] = metric_value

    return periods


def find_latest_period(
    periods,
    analysis_model
):

    prefixes = {

        "standard":
            "q_",

        "bank":
            "bank_q_",

        "insurance":
            "insurance_q_",

        "reit":
            "reit_q_"
    }

    prefix = prefixes.get(
        analysis_model
    )

    if prefix is None:
        return None

    for period_end in sorted(
        periods.keys(),
        reverse=True
    ):

        metrics = periods[
            period_end
        ]

        if any(
            name.startswith(prefix)
            for name in metrics
        ):
            return period_end

    return None


# ============================================================
# Standard
# ============================================================

def score_standard(metrics):

    growth = weighted_average([

        (
            score_growth(
                metrics.get(
                    "q_revenue_growth_yoy"
                )
            ),
            30
        ),

        (
            score_growth(
                metrics.get(
                    "q_net_income_growth_yoy"
                )
            ),
            35
        ),

        (
            score_growth(
                metrics.get(
                    "q_ocf_growth_yoy"
                )
            ),
            15
        ),

        (
            score_growth(
                metrics.get(
                    "q_fcf_growth_yoy"
                )
            ),
            20
        )
    ])

    quality = weighted_average([

        (
            score_margin_change(
                metrics.get(
                    "q_gross_margin_change_yoy"
                )
            ),
            20
        ),

        (
            score_margin_change(
                metrics.get(
                    "q_operating_margin_change_yoy"
                )
            ),
            25
        ),

        (
            score_margin_change(
                metrics.get(
                    "q_net_margin_change_yoy"
                )
            ),
            25
        ),

        (
            score_cash_conversion(
                metrics.get(
                    "q_cash_conversion"
                )
            ),
            30
        )
    ])

    cash = weighted_average([

        (
            score_cash_conversion(
                metrics.get(
                    "q_cash_conversion"
                )
            ),
            40
        ),

        (
            score_growth(
                metrics.get(
                    "q_ocf_growth_yoy"
                )
            ),
            30
        ),

        (
            score_growth(
                metrics.get(
                    "q_fcf_growth_yoy"
                )
            ),
            30
        )
    ])

    balance = weighted_average([

        (
            score_low_good(
                metrics.get(
                    "q_debt_to_equity"
                ),
                excellent=0.50,
                acceptable=1.00,
                high=2.00
            ),
            35
        ),

        (
            score_high_good(
                metrics.get(
                    "q_current_ratio"
                ),
                excellent=1.50,
                good=1.00,
                weak=0.80
            ),
            25
        ),

        (
            inverse_growth_score(
                metrics.get(
                    "q_debt_growth_qoq"
                )
            ),
            20
        ),

        (
            score_growth(
                metrics.get(
                    "q_cash_growth_qoq"
                )
            ),
            20
        )
    ])

    confidence = (
        clamp(
            metrics.get(
                "data_confidence_score"
            )
        )
        or 0.0
    )

    return {

        "growth_score":
            growth,

        "quality_score":
            quality,

        "cash_score":
            cash,

        "balance_score":
            balance,

        "confidence_score":
            confidence
    }


# ============================================================
# Bank
# ============================================================

def score_bank(metrics):

    growth = weighted_average([

        (
            score_growth(
                metrics.get(
                    "bank_q_revenue_growth_yoy"
                )
            ),
            30
        ),

        (
            score_growth(
                metrics.get(
                    "bank_q_net_income_growth_yoy"
                )
            ),
            35
        ),

        (
            score_growth(
                metrics.get(
                    "bank_q_assets_growth_yoy"
                )
            ),
            20
        ),

        (
            score_growth(
                metrics.get(
                    "bank_q_equity_growth_yoy"
                )
            ),
            15
        )
    ])

    quality = weighted_average([

        (
            score_high_good(
                metrics.get(
                    "bank_ttm_roe"
                ),
                excellent=20,
                good=15,
                weak=10
            ),
            45
        ),

        (
            score_high_good(
                metrics.get(
                    "bank_ttm_roa"
                ),
                excellent=2.00,
                good=1.50,
                weak=1.00
            ),
            30
        ),

        (
            score_margin_change(
                metrics.get(
                    "bank_q_profit_margin_change_yoy"
                )
            ),
            25
        )
    ])

    balance = weighted_average([

        (
            score_high_good(
                metrics.get(
                    "bank_q_equity_to_assets"
                ),
                excellent=15,
                good=10,
                weak=7
            ),
            60
        ),

        (
            score_growth(
                metrics.get(
                    "bank_q_equity_growth_yoy"
                )
            ),
            40
        )
    ])

    confidence = (
        clamp(
            metrics.get(
                "bank_data_confidence_score"
            )
        )
        or 0.0
    )

    return {

        "growth_score":
            growth,

        "quality_score":
            quality,

        "cash_score":
            None,

        "balance_score":
            balance,

        "confidence_score":
            confidence
    }


# ============================================================
# Insurance
# ============================================================

def score_insurance(metrics):

    growth = weighted_average([

        (
            score_growth(
                metrics.get(
                    "insurance_q_revenue_growth_yoy"
                )
            ),
            30
        ),

        (
            score_growth(
                metrics.get(
                    "insurance_q_net_income_growth_yoy"
                )
            ),
            35
        ),

        (
            score_growth(
                metrics.get(
                    "insurance_q_equity_growth_yoy"
                )
            ),
            20
        ),

        (
            score_growth(
                metrics.get(
                    "insurance_q_eps_growth_yoy"
                )
            ),
            15
        )
    ])

    quality = weighted_average([

        (
            score_high_good(
                metrics.get(
                    "insurance_ttm_roe"
                ),
                excellent=20,
                good=15,
                weak=10
            ),
            40
        ),

        (
            score_high_good(
                metrics.get(
                    "insurance_ttm_roa"
                ),
                excellent=4,
                good=2,
                weak=1
            ),
            25
        ),

        (
            score_margin_change(
                metrics.get(
                    "insurance_q_profit_margin_change_yoy"
                )
            ),
            20
        ),

        (
            score_cash_conversion(
                metrics.get(
                    "insurance_ttm_cash_conversion"
                )
            ),
            15
        )
    ])

    cash = weighted_average([

        (
            score_cash_conversion(
                metrics.get(
                    "insurance_ttm_cash_conversion"
                )
            ),
            60
        ),

        (
            score_growth(
                metrics.get(
                    "insurance_q_ocf_growth_yoy"
                )
            ),
            40
        )
    ])

    balance = weighted_average([

        (
            score_high_good(
                metrics.get(
                    "insurance_q_equity_to_assets"
                ),
                excellent=25,
                good=15,
                weak=8
            ),
            70
        ),

        (
            score_growth(
                metrics.get(
                    "insurance_q_equity_growth_yoy"
                )
            ),
            30
        )
    ])

    confidence = (
        clamp(
            metrics.get(
                "insurance_data_confidence_score"
            )
        )
        or 0.0
    )

    return {

        "growth_score":
            growth,

        "quality_score":
            quality,

        "cash_score":
            cash,

        "balance_score":
            balance,

        "confidence_score":
            confidence
    }


# ============================================================
# REIT
# ============================================================

def score_reit(metrics):

    growth = weighted_average([

        (
            score_growth(
                metrics.get(
                    "reit_q_revenue_growth_yoy"
                )
            ),
            30
        ),

        (
            score_growth(
                metrics.get(
                    "reit_q_operating_income_growth_yoy"
                )
            ),
            30
        ),

        (
            score_growth(
                metrics.get(
                    "reit_q_net_income_growth_yoy"
                )
            ),
            25
        ),

        (
            score_growth(
                metrics.get(
                    "reit_q_equity_growth_yoy"
                )
            ),
            15
        )
    ])

    quality = weighted_average([

        (
            score_margin_change(
                metrics.get(
                    "reit_q_operating_margin_change_yoy"
                )
            ),
            35
        ),

        (
            score_margin_change(
                metrics.get(
                    "reit_q_net_margin_change_yoy"
                )
            ),
            25
        ),

        (
            score_cash_conversion(
                metrics.get(
                    "reit_ttm_cash_conversion"
                )
            ),
            40
        )
    ])

    cash = weighted_average([

        (
            score_cash_conversion(
                metrics.get(
                    "reit_ttm_cash_conversion"
                )
            ),
            60
        ),

        (
            score_growth(
                metrics.get(
                    "reit_q_ocf_growth_yoy"
                )
            ),
            40
        )
    ])

    balance = weighted_average([

        (
            score_low_good(
                metrics.get(
                    "reit_q_debt_to_assets"
                ),
                excellent=25,
                acceptable=35,
                high=50
            ),
            60
        ),

        (
            inverse_growth_score(
                metrics.get(
                    "reit_q_debt_growth_yoy"
                )
            ),
            40
        )
    ])

    confidence = (
        clamp(
            metrics.get(
                "reit_data_confidence_score"
            )
        )
        or 0.0
    )

    return {

        "growth_score":
            growth,

        "quality_score":
            quality,

        "cash_score":
            cash,

        "balance_score":
            balance,

        "confidence_score":
            confidence
    }


# ============================================================
# الدرجات النهائية
# ============================================================

def calculate_final_scores(
    components
):

    growth = components.get(
        "growth_score"
    )

    quality = components.get(
        "quality_score"
    )

    cash = components.get(
        "cash_score"
    )

    balance = components.get(
        "balance_score"
    )

    confidence = (
        safe_number(
            components.get(
                "confidence_score"
            )
        )
        or 0.0
    )

    opportunity_raw = weighted_average([

        (
            growth,
            35
        ),

        (
            quality,
            30
        ),

        (
            cash,
            20
        ),

        (
            balance,
            15
        )
    ])

    risk_raw = weighted_average([

        (
            (
                100 - quality
                if quality is not None
                else None
            ),
            40
        ),

        (
            (
                100 - cash
                if cash is not None
                else None
            ),
            30
        ),

        (
            (
                100 - balance
                if balance is not None
                else None
            ),
            30
        )
    ])

    turning_raw = weighted_average([

        (
            growth,
            45
        ),

        (
            quality,
            35
        ),

        (
            (
                cash
                if cash is not None
                else 50.0
            ),
            20
        )
    ])

    confidence_factor = (
        0.50
        + (
            clamp(
                confidence
            )
            / 200.0
        )
    )

    opportunity = (
        opportunity_raw
        * confidence_factor
        if opportunity_raw is not None
        else None
    )

    turning_point = (
        turning_raw
        * confidence_factor
        if turning_raw is not None
        else None
    )

    return {

        "opportunity_score":
            clamp(
                opportunity
            ),

        "risk_score":
            clamp(
                risk_raw
            ),

        "turning_point_score":
            clamp(
                turning_point
            )
    }


# ============================================================
# حفظ Scoring
# ============================================================

def save_scoring_metrics(
    stock_id,
    period_end,
    scores
):

    calculated_at = datetime.now(
        timezone.utc
    ).isoformat()

    records = []

    for metric_name, metric_value in (
        scores.items()
    ):

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
                f"score_{metric_name}",

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

    return len(records)


# ============================================================
# شركة واحدة
# ============================================================

def score_stock(stock):

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

    analysis_model = (
        stock.get(
            "analysis_model"
        )
        or "standard"
    )

    rows = get_stock_metrics(
        stock_id
    )

    periods = organize_metrics(
        rows
    )

    latest_period = find_latest_period(
        periods,
        analysis_model
    )

    if latest_period is None:

        return {

            "symbol":
                symbol,

            "company_name":
                company_name,

            "analysis_model":
                analysis_model,

            "status":
                "no_period"
        }

    metrics = periods[
        latest_period
    ]

    if analysis_model == "standard":

        components = score_standard(
            metrics
        )

    elif analysis_model == "bank":

        components = score_bank(
            metrics
        )

    elif analysis_model == "insurance":

        components = score_insurance(
            metrics
        )

    elif analysis_model == "reit":

        components = score_reit(
            metrics
        )

    else:

        return {

            "symbol":
                symbol,

            "company_name":
                company_name,

            "analysis_model":
                analysis_model,

            "status":
                "unknown_model"
        }

    final_scores = calculate_final_scores(
        components
    )

    all_scores = {}

    all_scores.update(
        components
    )

    all_scores.update(
        final_scores
    )

    saved = save_scoring_metrics(
        stock_id,
        latest_period,
        all_scores
    )

    return {

        "symbol":
            symbol,

        "company_name":
            company_name,

        "analysis_model":
            analysis_model,

        "status":
            "success",

        "period_end":
            latest_period,

        "saved":
            saved,

        "growth":
            all_scores.get(
                "growth_score"
            ),

        "quality":
            all_scores.get(
                "quality_score"
            ),

        "cash":
            all_scores.get(
                "cash_score"
            ),

        "balance":
            all_scores.get(
                "balance_score"
            ),

        "opportunity":
            all_scores.get(
                "opportunity_score"
            ),

        "risk":
            all_scores.get(
                "risk_score"
            ),

        "turning_point":
            all_scores.get(
                "turning_point_score"
            ),

        "confidence":
            all_scores.get(
                "confidence_score"
            )
    }


# ============================================================
# تنسيق النتائج
# ============================================================

def fmt(value):

    value = safe_number(
        value
    )

    if value is None:
        return "N/A"

    return f"{value:.2f}"


# ============================================================
# التشغيل الرئيسي
# ============================================================

def run_scoring_engine():

    stocks = get_active_stocks()

    print(
        "\n"
        + "=" * 80,
        flush=True
    )

    print(
        "🎯 SCORING ENGINE v1.1",
        flush=True
    )

    print(
        "=" * 80,
        flush=True
    )

    print(
        f"🏢 Total Stocks: "
        f"{len(stocks)}",
        flush=True
    )

    results = []

    for index, stock in enumerate(
        stocks,
        start=1
    ):

        print(
            f"\n🚦 Scoring "
            f"{index}/{len(stocks)} | "
            f"{stock['symbol']}",
            flush=True
        )

        try:

            result = score_stock(
                stock
            )

        except Exception as error:

            result = {

                "symbol":
                    stock[
                        "symbol"
                    ],

                "company_name":
                    stock.get(
                        "company_name"
                    ),

                "analysis_model":
                    stock.get(
                        "analysis_model"
                    ),

                "status":
                    "error",

                "error":
                    str(error)
            }

            print(
                f"🔴 "
                f"{stock['symbol']} | "
                f"{type(error).__name__}: "
                f"{error}",
                flush=True
            )

        results.append(
            result
        )

    successful = [

        result

        for result in results

        if result.get(
            "status"
        ) == "success"
    ]

    successful.sort(

        key=lambda result: (

            safe_number(
                result.get(
                    "opportunity"
                )
            )

            if safe_number(
                result.get(
                    "opportunity"
                )
            ) is not None

            else -1
        ),

        reverse=True
    )

    print(
        "\n"
        + "=" * 80,
        flush=True
    )

    print(
        "🏆 OPPORTUNITY RANKING",
        flush=True
    )

    print(
        "=" * 80,
        flush=True
    )

    for rank, result in enumerate(
        successful,
        start=1
    ):

        print(

            f"{rank:02d}. "
            f"{result['symbol']} | "
            f"{result['company_name']} | "
            f"{result['analysis_model']} | "
            f"Opportunity="
            f"{fmt(result.get('opportunity'))} | "
            f"Risk="
            f"{fmt(result.get('risk'))} | "
            f"Turning="
            f"{fmt(result.get('turning_point'))} | "
            f"Confidence="
            f"{fmt(result.get('confidence'))}",

            flush=True
        )

    failures = [

        result

        for result in results

        if result.get(
            "status"
        ) != "success"
    ]

    print(
        "\n"
        + "=" * 80,
        flush=True
    )

    print(
        "📊 SCORING SUMMARY",
        flush=True
    )

    print(
        "=" * 80,
        flush=True
    )

    print(
        f"🟢 Success: "
        f"{len(successful)}",
        flush=True
    )

    print(
        f"🔴 Failed/Skipped: "
        f"{len(failures)}",
        flush=True
    )

    if failures:

        print(
            "\n⚠️ Failed / Skipped:",
            flush=True
        )

        for result in failures:

            print(

                f"{result.get('symbol')} | "
                f"{result.get('analysis_model')} | "
                f"{result.get('status')} | "
                f"{result.get('error', '')}",

                flush=True
            )

    print(
        "=" * 80,
        flush=True
    )


if __name__ == "__main__":

    run_scoring_engine()
