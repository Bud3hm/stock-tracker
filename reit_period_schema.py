# ============================================================
# REIT PERIOD SCHEMA ENGINE v1
# ============================================================
#
# Purpose:
# Define the correct financial-period architecture for Saudi REITs.
#
# IMPORTANT:
# - No Supabase writes
# - No calculations
# - No Yahoo assumptions
# - Generic for ALL Saudi REITs
#
# This module becomes the single source of truth for:
# Q1 / Q2 / Q3 / Q4 / H1 / FY requirements.
# ============================================================


REIT_PERIOD_TYPES = {
    "Q1": {
        "period_class": "quarterly_statement",
        "months": 3,
        "requires_full_income_statement": False,
        "requires_quarterly_statement": True,
        "requires_financial_report": False,
    },

    "Q2": {
        "period_class": "quarterly_statement",
        "months": 3,
        "requires_full_income_statement": False,
        "requires_quarterly_statement": True,
        "requires_financial_report": False,
    },

    "Q3": {
        "period_class": "quarterly_statement",
        "months": 3,
        "requires_full_income_statement": False,
        "requires_quarterly_statement": True,
        "requires_financial_report": False,
    },

    "Q4": {
        "period_class": "quarterly_statement",
        "months": 3,
        "requires_full_income_statement": False,
        "requires_quarterly_statement": True,
        "requires_financial_report": False,
    },

    "H1": {
        "period_class": "semiannual_financial",
        "months": 6,
        "requires_full_income_statement": True,
        "requires_quarterly_statement": False,
        "requires_financial_report": True,
    },

    "FY": {
        "period_class": "annual_financial",
        "months": 12,
        "requires_full_income_statement": True,
        "requires_quarterly_statement": False,
        "requires_financial_report": True,
    },
}


# ============================================================
# OFFICIAL QUARTERLY REIT METRICS
# ============================================================

REIT_QUARTERLY_REQUIRED = [
    "rental_income",
    "total_assets",
    "net_asset_value",
    "nav_per_unit",
    "market_price",
]


REIT_QUARTERLY_IMPORTANT = [
    "total_debt",
    "debt_to_assets",
    "expenses",
    "expenses_to_assets",
    "rental_income_to_market_value",
]


REIT_QUARTERLY_OPTIONAL = [
    "fair_value_assets",
    "fair_value_nav",
    "fair_value_nav_per_unit",
    "occupancy_rate",
    "number_of_properties",
    "number_of_units",
    "distributed_dividends",
    "distribution_percentage",
]


# ============================================================
# H1 / FY FINANCIAL METRICS
# ============================================================

REIT_FINANCIAL_REQUIRED = [
    "total_revenue",
    "net_income",
    "total_assets",
    "total_liabilities",
    "net_assets",
]


REIT_FINANCIAL_IMPORTANT = [
    "operating_income",
    "total_debt",
    "operating_cash_flow",
    "funds_from_operations",
    "total_expenses",
]


REIT_FINANCIAL_OPTIONAL = [
    "free_cash_flow",
    "cash",
    "finance_cost",
    "depreciation",
    "impairment",
]


# ============================================================
# METRIC SOURCE PRIORITY
# ============================================================

REIT_SOURCE_PRIORITY = {
    "quarterly_statement": [
        "saudi_exchange_quarterly_statement",
        "fund_manager_quarterly_statement",
        "secondary_provider",
    ],

    "semiannual_financial": [
        "saudi_exchange_financial_report",
        "fund_manager_financial_report",
        "secondary_provider",
    ],

    "annual_financial": [
        "saudi_exchange_audited_financial_report",
        "fund_manager_audited_financial_report",
        "secondary_provider",
    ],
}


# ============================================================
# METRICS THAT MUST NOT BE FORCED QUARTERLY
# ============================================================

REIT_NOT_REQUIRED_QUARTERLY = [
    "quarterly_net_income",
    "quarterly_operating_income",
    "quarterly_operating_cash_flow",
    "quarterly_free_cash_flow",
]


# ============================================================
# PERIOD IDENTIFICATION
# ============================================================

def identify_reit_period(period_end, report_type=None):
    """
    Determine the logical REIT period.

    report_type should take priority when official metadata exists.
    """

    if report_type:
        normalized = str(report_type).strip().lower()

        if normalized in {
            "q1",
            "quarter1",
            "quarter_1",
        }:
            return "Q1"

        if normalized in {
            "q2",
            "quarter2",
            "quarter_2",
        }:
            return "Q2"

        if normalized in {
            "q3",
            "quarter3",
            "quarter_3",
        }:
            return "Q3"

        if normalized in {
            "q4",
            "quarter4",
            "quarter_4",
        }:
            return "Q4"

        if normalized in {
            "h1",
            "semiannual",
            "semi_annual",
            "half_year",
            "6m",
        }:
            return "H1"

        if normalized in {
            "fy",
            "annual",
            "12m",
            "year",
        }:
            return "FY"

    if not period_end:
        return None

    period_end = str(period_end)

    try:
        month = int(period_end[5:7])
    except (ValueError, IndexError):
        return None

    if month == 3:
        return "Q1"

    if month == 6:
        return "Q2"

    if month == 9:
        return "Q3"

    if month == 12:
        return "Q4"

    return None


# ============================================================
# REQUIRED METRICS BY PERIOD
# ============================================================

def get_required_metrics(period_type):

    if period_type in {
        "Q1",
        "Q2",
        "Q3",
        "Q4",
    }:
        return list(
            REIT_QUARTERLY_REQUIRED
        )

    if period_type in {
        "H1",
        "FY",
    }:
        return list(
            REIT_FINANCIAL_REQUIRED
        )

    return []


def get_important_metrics(period_type):

    if period_type in {
        "Q1",
        "Q2",
        "Q3",
        "Q4",
    }:
        return list(
            REIT_QUARTERLY_IMPORTANT
        )

    if period_type in {
        "H1",
        "FY",
    }:
        return list(
            REIT_FINANCIAL_IMPORTANT
        )

    return []


# ============================================================
# PERIOD VALIDATION
# ============================================================

def validate_reit_period(
    period_type,
    metrics
):

    metrics = metrics or {}

    required = get_required_metrics(
        period_type
    )

    important = get_important_metrics(
        period_type
    )

    required_available = [
        metric
        for metric in required
        if metrics.get(metric) is not None
    ]

    required_missing = [
        metric
        for metric in required
        if metrics.get(metric) is None
    ]

    important_available = [
        metric
        for metric in important
        if metrics.get(metric) is not None
    ]

    important_missing = [
        metric
        for metric in important
        if metrics.get(metric) is None
    ]

    required_coverage = (
        (
            len(required_available)
            / len(required)
        ) * 100
        if required
        else 0.0
    )

    important_coverage = (
        (
            len(important_available)
            / len(important)
        ) * 100
        if important
        else 0.0
    )

    # Required metrics carry most of the quality score.
    quality_score = (
        required_coverage * 0.80
        + important_coverage * 0.20
    )

    if required_coverage == 100:
        status = "READY"

    elif required_coverage >= 60:
        status = "PARTIAL"

    else:
        status = "NOT_READY"

    return {
        "period_type": period_type,

        "status": status,

        "quality_score": round(
            quality_score,
            2
        ),

        "required_coverage": round(
            required_coverage,
            2
        ),

        "important_coverage": round(
            important_coverage,
            2
        ),

        "required_available":
            required_available,

        "required_missing":
            required_missing,

        "important_available":
            important_available,

        "important_missing":
            important_missing,
    }


# ============================================================
# YOY RULES
# ============================================================

def get_valid_yoy_reference(
    current_period_type
):

    mapping = {
        "Q1": "Q1",
        "Q2": "Q2",
        "Q3": "Q3",
        "Q4": "Q4",
        "H1": "H1",
        "FY": "FY",
    }

    return mapping.get(
        current_period_type
    )


def yoy_comparison_allowed(
    current_period_type,
    previous_period_type
):

    if (
        current_period_type is None
        or previous_period_type is None
    ):
        return False

    return (
        current_period_type
        == previous_period_type
    )


# ============================================================
# QUARTERLY INCOME RULES
# ============================================================

def quarterly_income_statement_required(
    period_type
):

    config = REIT_PERIOD_TYPES.get(
        period_type
    )

    if not config:
        return False

    return bool(
        config.get(
            "requires_full_income_statement"
        )
    )


# ============================================================
# SOURCE PRIORITY
# ============================================================

def get_source_priority(
    period_type
):

    config = REIT_PERIOD_TYPES.get(
        period_type
    )

    if not config:
        return []

    period_class = config.get(
        "period_class"
    )

    return list(
        REIT_SOURCE_PRIORITY.get(
            period_class,
            []
        )
    )


# ============================================================
# AUDIT REQUIREMENT BUILDER
# ============================================================

def build_reit_audit_requirements(
    period_type
):

    return {
        "period_type":
            period_type,

        "required_metrics":
            get_required_metrics(
                period_type
            ),

        "important_metrics":
            get_important_metrics(
                period_type
            ),

        "quarterly_income_required":
            quarterly_income_statement_required(
                period_type
            ),

        "valid_yoy_reference":
            get_valid_yoy_reference(
                period_type
            ),

        "source_priority":
            get_source_priority(
                period_type
            ),
    }


# ============================================================
# SELF TEST
# ============================================================

def run_self_test():

    print(
        "\n"
        + "=" * 80
    )

    print(
        "🏢 REIT PERIOD SCHEMA ENGINE v1"
    )

    print(
        "=" * 80
    )

    test_periods = [
        ("2026-03-31", None),
        ("2026-06-30", None),
        ("2026-09-30", None),
        ("2026-12-31", None),
        ("2026-06-30", "H1"),
        ("2026-12-31", "FY"),
    ]

    for period_end, report_type in test_periods:

        period_type = identify_reit_period(
            period_end,
            report_type
        )

        requirements = (
            build_reit_audit_requirements(
                period_type
            )
        )

        print(
            f"\n📅 {period_end}"
            f" | ReportType={report_type}"
            f" | LogicalPeriod={period_type}"
        )

        print(
            "Quarterly Income Required:",
            requirements[
                "quarterly_income_required"
            ]
        )

        print(
            "Required Metrics:",
            ", ".join(
                requirements[
                    "required_metrics"
                ]
            )
        )

        print(
            "Source Priority:",
            " → ".join(
                requirements[
                    "source_priority"
                ]
            )
        )

    print(
        "\n"
        + "=" * 80
    )

    print(
        "✅ REIT PERIOD SCHEMA SELF TEST COMPLETE"
    )

    print(
        "=" * 80
    )


if __name__ == "__main__":
    run_self_test()
