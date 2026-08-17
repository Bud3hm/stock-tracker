import os
import re
import time
import hashlib
from datetime import datetime, timezone, timedelta
from urllib.parse import urlparse

import requests
from supabase import create_client


# ============================================================
# NEWS DATA PIPELINE v1.0.1
#
# الهدف:
# جلب أخبار الشركات + فلترة الأخبار غير المهمة قبل الحفظ.
#
# DEFAULT MODE:
# TEST / READ ONLY
#
# لا يتم الحفظ إلا إذا:
# NEWS_TEST_MODE=false
#
# التعديلات في v1.0.1:
# - TEST MODE لا يقرأ company_news
# - Yahoo queries تستخدم symbol و symbol code فقط
# - تم إيقاف البحث بالاسم العربي بسبب HTTP 400 من Yahoo
# - Live mode فقط يستخدم Deduplication من company_news
#
# المسار:
# News Source
# -> Relevance Filter
# -> Material Event Classifier
# -> Importance Gate
# -> Deduplication
# -> company_news
#
# Source v1:
# Yahoo Finance Search News
#
# مستقبلًا:
# - Tadawul announcements adapter
# - Company IR adapter
# - Paid provider adapter
# - AI event classifier
#
# مهم:
# - لا يحفظ الأخبار العامة أو حركة السهم اليومية.
# - لا يحفظ الخبر إذا لم يكن حدثًا جوهريًا.
# - لا يستخدم AI في هذه المرحلة.
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

ENGINE_VERSION = "1.0.1"

TEST_MODE = (
    os.environ
    .get(
        "NEWS_TEST_MODE",
        "true"
    )
    .strip()
    .lower()
    in {
        "1",
        "true",
        "yes",
        "on"
    }
)

YAHOO_SEARCH_URL = (
    "https://query1.finance.yahoo.com/"
    "v1/finance/search"
)

REQUEST_TIMEOUT = 20

REQUEST_DELAY_BETWEEN_STOCKS = 0.75

NEWS_LOOKBACK_DAYS = 21

MAX_NEWS_PER_QUERY = 30

MAX_ACCEPTED_PER_STOCK = 10

MIN_RELEVANCE_SCORE = 45.0

MIN_IMPORTANCE_SCORE = 60.0

MAX_TITLE_LENGTH = 500

SOURCE_NAME = "yahoo_news_search"


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 "
        "(Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/131.0 Safari/537.36"
    ),
    "Accept": "application/json,text/plain,*/*",
    "Accept-Language": "en-US,en;q=0.9",
}


# ============================================================
# Event Rules
# ============================================================

EVENT_RULES = {

    "financial_results": {
        "base_score": 72,
        "keywords": [
            "financial results",
            "earnings",
            "quarterly results",
            "annual results",
            "net profit",
            "net income",
            "revenue",
            "profit rises",
            "profit falls",
            "earnings growth",
            "earnings decline",
            "loss",
        ],
    },

    "contract_award": {
        "base_score": 78,
        "keywords": [
            "contract award",
            "awarded contract",
            "wins contract",
            "new contract",
            "signed contract",
            "agreement signed",
            "purchase order",
            "project award",
        ],
    },

    "acquisition_merger": {
        "base_score": 88,
        "keywords": [
            "acquisition",
            "acquire",
            "merger",
            "takeover",
            "buys stake",
            "sells stake",
            "acquires",
        ],
    },

    "capital_action": {
        "base_score": 82,
        "keywords": [
            "capital increase",
            "capital reduction",
            "rights issue",
            "bonus shares",
            "share split",
            "reverse split",
            "share issuance",
        ],
    },

    "dividend": {
        "base_score": 70,
        "keywords": [
            "dividend",
            "cash dividend",
            "dividend distribution",
            "dividend recommendation",
        ],
    },

    "financing_debt": {
        "base_score": 70,
        "keywords": [
            "financing",
            "loan",
            "credit facility",
            "refinancing",
            "sukuk",
            "bond issuance",
            "debt financing",
        ],
    },

    "expansion": {
        "base_score": 74,
        "keywords": [
            "expansion",
            "new plant",
            "new factory",
            "production line",
            "capacity expansion",
            "commercial operation",
            "start production",
        ],
    },

    "management_change": {
        "base_score": 64,
        "keywords": [
            "ceo resigns",
            "ceo appointed",
            "appoints ceo",
            "board appointment",
            "board resignation",
            "management change",
        ],
    },

    "legal_regulatory": {
        "base_score": 80,
        "keywords": [
            "lawsuit",
            "court ruling",
            "fine",
            "penalty",
            "regulatory action",
            "investigation",
            "license suspension",
            "license revoked",
        ],
    },

    "project_status": {
        "base_score": 76,
        "keywords": [
            "project cancelled",
            "project delayed",
            "project suspended",
            "project started",
            "project completed",
            "project completion",
        ],
    },

    "operational_event": {
        "base_score": 74,
        "keywords": [
            "production halt",
            "fire",
            "shutdown",
            "operational disruption",
            "operations resume",
            "production resumes",
        ],
    },

    "guidance": {
        "base_score": 77,
        "keywords": [
            "guidance",
            "raises guidance",
            "cuts guidance",
            "profit warning",
            "financial impact expected",
        ],
    },

    "ownership": {
        "base_score": 66,
        "keywords": [
            "ownership change",
            "major shareholder",
            "stake increase",
            "stake reduction",
            "investor exits",
        ],
    },
}


# ============================================================
# Noise Rules
# ============================================================

NOISE_KEYWORDS = [
    "stock rises",
    "stock falls",
    "shares rise",
    "shares fall",
    "market closes",
    "technical analysis",
    "price target",
    "analyst rating",
    "buy rating",
    "sell rating",
]


# ============================================================
# Importance Boosters
# ============================================================

HIGH_IMPACT_KEYWORDS = [
    "billion",
    "acquisition",
    "merger",
    "capital increase",
    "capital reduction",
    "profit warning",
    "production halt",
]


MEDIUM_IMPACT_KEYWORDS = [
    "million",
    "contract",
    "award",
    "financing",
    "expansion",
    "dividend",
]


# ============================================================
# Helpers
# ============================================================

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


def normalize_text(value):

    if value is None:
        return ""

    text = str(
        value
    ).strip()

    text = re.sub(
        r"\s+",
        " ",
        text
    )

    return text


def normalized_lower(value):

    return (
        normalize_text(
            value
        )
        .lower()
    )


def truncate_text(
    value,
    maximum
):

    value = normalize_text(
        value
    )

    if len(
        value
    ) <= maximum:

        return value

    return (
        value[
            :maximum - 3
        ]
        + "..."
    )


def safe_int(value):

    if value is None:
        return None

    try:
        return int(
            value
        )

    except (
        TypeError,
        ValueError
    ):
        return None


def parse_publish_time(
    value
):

    timestamp = safe_int(
        value
    )

    if timestamp is None:
        return None

    try:

        return (
            datetime.fromtimestamp(
                timestamp,
                tz=timezone.utc
            )
        )

    except (
        OSError,
        OverflowError,
        ValueError
    ):

        return None


def normalize_url(url):

    url = normalize_text(
        url
    )

    if not url:
        return ""

    try:

        parsed = urlparse(
            url
        )

        scheme = (
            parsed.scheme
            or "https"
        )

        netloc = (
            parsed.netloc
            .lower()
        )

        path = (
            parsed.path
            .rstrip("/")
        )

        return (
            f"{scheme}://"
            f"{netloc}"
            f"{path}"
        )

    except Exception:

        return url


def stable_external_id(
    source_name,
    external_id,
    title,
    url
):

    external_id = normalize_text(
        external_id
    )

    if external_id:

        return external_id

    base = (
        f"{source_name}|"
        f"{normalize_url(url)}|"
        f"{normalized_lower(title)}"
    )

    return (
        hashlib.sha256(
            base.encode(
                "utf-8"
            )
        )
        .hexdigest()
    )


def contains_any(
    text,
    keywords
):

    lowered = normalized_lower(
        text
    )

    return any(
        normalized_lower(
            keyword
        )
        in lowered

        for keyword in keywords
    )


# ============================================================
# Stocks
# ============================================================

def get_active_stocks():

    response = (
        supabase
        .table(
            "stocks"
        )
        .select(
            "id,"
            "symbol,"
            "company_name,"
            "sector,"
            "analysis_model,"
            "priority"
        )
        .eq(
            "is_active",
            True
        )
        .order(
            "priority",
            desc=True
        )
        .order(
            "id"
        )
        .execute()
    )

    return (
        response.data
        or []
    )


# ============================================================
# News Source Adapter
# ============================================================

class NewsSourceAdapter:

    source_name = "unknown"

    def fetch_news(
        self,
        stock
    ):

        raise NotImplementedError


# ============================================================
# Yahoo News Adapter
# ============================================================

class YahooNewsAdapter(
    NewsSourceAdapter
):

    source_name = SOURCE_NAME

    def yahoo_request(
        self,
        query
    ):

        params = {
            "q":
                query,

            "quotesCount":
                0,

            "newsCount":
                MAX_NEWS_PER_QUERY,

            "enableFuzzyQuery":
                "false",

            "quotesQueryId":
                "tss_match_phrase_query",

            "multiQuoteQueryId":
                "multi_quote_single_token_query",

            "newsQueryId":
                "news_cie_vespa",

            "enableCb":
                "true",

            "enableNavLinks":
                "false",

            "enableEnhancedTrivialQuery":
                "true",
        }

        response = requests.get(
            YAHOO_SEARCH_URL,
            params=params,
            headers=HEADERS,
            timeout=REQUEST_TIMEOUT
        )

        print(
            f"🌐 Yahoo News | "
            f"query={query} | "
            f"HTTP {response.status_code}",
            flush=True
        )

        response.raise_for_status()

        return (
            response.json()
        )

    def build_queries(
        self,
        stock
    ):

        symbol = normalize_text(
            stock.get(
                "symbol"
            )
        )

        queries = []

        if symbol:

            queries.append(
                symbol
            )

            symbol_code = (
                symbol
                .split(".")[0]
            )

            if symbol_code:

                queries.append(
                    symbol_code
                )

        return list(
            dict.fromkeys(
                query

                for query in queries

                if query
            )
        )

    def normalize_item(
        self,
        item
    ):

        if not isinstance(
            item,
            dict
        ):

            return None

        title = normalize_text(
            item.get(
                "title"
            )
        )

        if not title:
            return None

        publisher = normalize_text(
            item.get(
                "publisher"
            )
        )

        link = normalize_url(
            item.get(
                "link"
            )
        )

        published_at = parse_publish_time(
            item.get(
                "providerPublishTime"
            )
        )

        external_id = stable_external_id(
            source_name=self.source_name,
            external_id=(
                item.get(
                    "uuid"
                )
                or item.get(
                    "id"
                )
            ),
            title=title,
            url=link
        )

        return {
            "title":
                truncate_text(
                    title,
                    MAX_TITLE_LENGTH
                ),

            "summary":
                None,

            "publisher":
                publisher,

            "source_name":
                self.source_name,

            "source_url":
                link,

            "external_id":
                external_id,

            "published_at":
                published_at,

            "raw_data":
                item,
        }

    def fetch_news(
        self,
        stock
    ):

        all_items = []

        seen_ids = set()

        for query in self.build_queries(
            stock
        ):

            try:

                data = self.yahoo_request(
                    query
                )

                news_items = (
                    data.get(
                        "news",
                        []
                    )
                    if isinstance(
                        data,
                        dict
                    )
                    else []
                )

                for item in news_items:

                    normalized = (
                        self.normalize_item(
                            item
                        )
                    )

                    if not normalized:
                        continue

                    external_id = (
                        normalized[
                            "external_id"
                        ]
                    )

                    if external_id in seen_ids:
                        continue

                    seen_ids.add(
                        external_id
                    )

                    all_items.append(
                        normalized
                    )

            except Exception as error:

                print(
                    f"🟠 Yahoo News Error | "
                    f"{stock.get('symbol')} | "
                    f"query={query} | "
                    f"{type(error).__name__}: "
                    f"{error}",
                    flush=True
                )

        return all_items


# ============================================================
# Relevance
# ============================================================

def calculate_relevance_score(
    stock,
    item
):

    title = normalized_lower(
        item.get(
            "title"
        )
    )

    if not title:

        return 0.0

    symbol = normalize_text(
        stock.get(
            "symbol"
        )
    )

    symbol_code = (
        symbol
        .split(".")[0]
        if symbol
        else ""
    )

    score = 0.0

    if (
        symbol
        and normalized_lower(
            symbol
        )
        in title
    ):

        score += 70.0

    if (
        symbol_code
        and symbol_code
        in title
    ):

        score += 45.0

    # Yahoo query matching gives a limited prior.
    score += 15.0

    return min(
        100.0,
        score
    )


# ============================================================
# Event Classification
# ============================================================

def classify_event(
    title
):

    title_lower = normalized_lower(
        title
    )

    matched_events = []

    for event_type, rule in (
        EVENT_RULES.items()
    ):

        matched_keywords = [
            keyword

            for keyword
            in rule[
                "keywords"
            ]

            if normalized_lower(
                keyword
            )
            in title_lower
        ]

        if matched_keywords:

            matched_events.append({
                "event_type":
                    event_type,

                "base_score":
                    float(
                        rule[
                            "base_score"
                        ]
                    ),

                "matched_keywords":
                    matched_keywords,
            })

    if not matched_events:

        return None

    matched_events.sort(
        key=lambda item:
            item[
                "base_score"
            ],
        reverse=True
    )

    return (
        matched_events[0]
    )


# ============================================================
# Noise Filter
# ============================================================

def is_noise_only(
    title,
    event_match
):

    if not contains_any(
        title,
        NOISE_KEYWORDS
    ):

        return False

    if event_match:

        return False

    return True


# ============================================================
# Importance
# ============================================================

def calculate_importance_score(
    title,
    event_match,
    relevance_score
):

    if not event_match:

        return 0.0

    score = float(
        event_match[
            "base_score"
        ]
    )

    if contains_any(
        title,
        HIGH_IMPACT_KEYWORDS
    ):

        score += 12.0

    elif contains_any(
        title,
        MEDIUM_IMPACT_KEYWORDS
    ):

        score += 6.0

    score += (
        max(
            0.0,
            relevance_score
            - MIN_RELEVANCE_SCORE
        )
        * 0.12
    )

    matched_count = len(
        event_match[
            "matched_keywords"
        ]
    )

    if matched_count >= 2:

        score += 4.0

    if matched_count >= 3:

        score += 3.0

    return min(
        100.0,
        score
    )


# ============================================================
# Date Filter
# ============================================================

def is_within_lookback(
    published_at
):

    if published_at is None:
        return False

    cutoff = (
        datetime.now(
            timezone.utc
        )
        - timedelta(
            days=NEWS_LOOKBACK_DAYS
        )
    )

    return (
        published_at
        >= cutoff
    )


# ============================================================
# Existing News / Dedup
# ============================================================

def existing_external_ids(
    stock_id,
    source_name
):

    # في TEST MODE لا نحتاج لمس company_news أصلًا.
    if TEST_MODE:

        return set()

    response = (
        supabase
        .table(
            "company_news"
        )
        .select(
            "external_id"
        )
        .eq(
            "stock_id",
            stock_id
        )
        .eq(
            "source_name",
            source_name
        )
        .execute()
    )

    return {
        row[
            "external_id"
        ]

        for row in (
            response.data
            or []
        )

        if row.get(
            "external_id"
        )
    }


# ============================================================
# Pre-Filter
# ============================================================

def prefilter_news_item(
    stock,
    item
):

    title = normalize_text(
        item.get(
            "title"
        )
    )

    if not title:

        return {
            "accepted":
                False,

            "reason":
                "EMPTY_TITLE"
        }

    published_at = item.get(
        "published_at"
    )

    if not is_within_lookback(
        published_at
    ):

        return {
            "accepted":
                False,

            "reason":
                "OUTSIDE_LOOKBACK"
        }

    relevance_score = (
        calculate_relevance_score(
            stock,
            item
        )
    )

    if relevance_score < MIN_RELEVANCE_SCORE:

        return {
            "accepted":
                False,

            "reason":
                "LOW_RELEVANCE",

            "relevance_score":
                relevance_score,
        }

    event_match = (
        classify_event(
            title
        )
    )

    if is_noise_only(
        title,
        event_match
    ):

        return {
            "accepted":
                False,

            "reason":
                "MARKET_NOISE",

            "relevance_score":
                relevance_score,
        }

    if not event_match:

        return {
            "accepted":
                False,

            "reason":
                "NO_MATERIAL_EVENT",

            "relevance_score":
                relevance_score,
        }

    importance_score = (
        calculate_importance_score(
            title,
            event_match,
            relevance_score
        )
    )

    if importance_score < MIN_IMPORTANCE_SCORE:

        return {
            "accepted":
                False,

            "reason":
                "LOW_IMPORTANCE",

            "relevance_score":
                relevance_score,

            "importance_score":
                importance_score,

            "event_type":
                event_match[
                    "event_type"
                ],
        }

    return {
        "accepted":
            True,

        "reason":
            "ACCEPTED",

        "relevance_score":
            relevance_score,

        "importance_score":
            importance_score,

        "event_type":
            event_match[
                "event_type"
            ],

        "matched_keywords":
            event_match[
                "matched_keywords"
            ],
    }


# ============================================================
# Save
# ============================================================

def build_news_record(
    stock,
    item,
    decision
):

    published_at = item.get(
        "published_at"
    )

    return {
        "stock_id":
            stock[
                "id"
            ],

        "published_at":
            (
                published_at.isoformat()
                if published_at
                else None
            ),

        "title":
            item[
                "title"
            ],

        "summary":
            item.get(
                "summary"
            ),

        "source_name":
            item[
                "source_name"
            ],

        "source_url":
            item.get(
                "source_url"
            ),

        "external_id":
            item[
                "external_id"
            ],

        "event_type":
            decision[
                "event_type"
            ],

        "importance_score":
            round(
                decision[
                    "importance_score"
                ],
                2
            ),

        "sentiment_score":
            None,

        "ai_processed":
            False,

        "raw_data":
            {
                "publisher":
                    item.get(
                        "publisher"
                    ),

                "relevance_score":
                    round(
                        decision[
                            "relevance_score"
                        ],
                        2
                    ),

                "matched_keywords":
                    decision.get(
                        "matched_keywords",
                        []
                    ),

                "source_payload":
                    item.get(
                        "raw_data"
                    ),
            },
    }


def save_news_records(
    records
):

    if not records:
        return 0

    (
        supabase
        .table(
            "company_news"
        )
        .upsert(
            records,
            on_conflict=(
                "stock_id,"
                "source_name,"
                "external_id"
            )
        )
        .execute()
    )

    return len(
        records
    )


# ============================================================
# Process Stock
# ============================================================

def process_stock(
    stock,
    adapter
):

    symbol = normalize_text(
        stock.get(
            "symbol"
        )
    )

    company_name = (
        normalize_text(
            stock.get(
                "company_name"
            )
        )
        or symbol
    )

    print_header(
        f"📰 {symbol} | "
        f"{company_name}"
    )

    fetched_items = (
        adapter.fetch_news(
            stock
        )
    )

    print(
        f"📥 Raw Candidate News: "
        f"{len(fetched_items)}",
        flush=True
    )

    existing_ids = (
        existing_external_ids(
            stock[
                "id"
            ],
            adapter.source_name
        )
    )

    accepted = []
    rejected_counts = {}

    local_seen = set()

    for item in fetched_items:

        external_id = item[
            "external_id"
        ]

        if external_id in local_seen:

            rejected_counts[
                "LOCAL_DUPLICATE"
            ] = (
                rejected_counts.get(
                    "LOCAL_DUPLICATE",
                    0
                )
                + 1
            )

            continue

        local_seen.add(
            external_id
        )

        if external_id in existing_ids:

            rejected_counts[
                "ALREADY_STORED"
            ] = (
                rejected_counts.get(
                    "ALREADY_STORED",
                    0
                )
                + 1
            )

            continue

        decision = (
            prefilter_news_item(
                stock,
                item
            )
        )

        if not decision[
            "accepted"
        ]:

            reason = decision[
                "reason"
            ]

            rejected_counts[
                reason
            ] = (
                rejected_counts.get(
                    reason,
                    0
                )
                + 1
            )

            continue

        accepted.append(
            {
                "item":
                    item,

                "decision":
                    decision,
            }
        )

    accepted.sort(
        key=lambda entry: (
            entry[
                "decision"
            ][
                "importance_score"
            ],
            (
                entry[
                    "item"
                ][
                    "published_at"
                ].timestamp()
                if entry[
                    "item"
                ].get(
                    "published_at"
                )
                else 0
            )
        ),
        reverse=True
    )

    accepted = accepted[
        :MAX_ACCEPTED_PER_STOCK
    ]

    print(
        f"✅ Accepted Material Events: "
        f"{len(accepted)}",
        flush=True
    )

    if rejected_counts:

        print(
            "\n🧹 Filtered Out:",
            flush=True
        )

        for reason, count in sorted(
            rejected_counts.items(),
            key=lambda item:
                item[0]
        ):

            print(
                f"- {reason}: "
                f"{count}",
                flush=True
            )

    if accepted:

        print(
            "\n🎯 Accepted Events:",
            flush=True
        )

        for index, entry in enumerate(
            accepted,
            start=1
        ):

            item = entry[
                "item"
            ]

            decision = entry[
                "decision"
            ]

            published_at = (
                item[
                    "published_at"
                ].strftime(
                    "%Y-%m-%d"
                )
                if item.get(
                    "published_at"
                )
                else "N/A"
            )

            print(
                f"{index}. "
                f"[{decision['event_type']}] "
                f"Importance="
                f"{decision['importance_score']:.1f} | "
                f"Relevance="
                f"{decision['relevance_score']:.1f} | "
                f"{published_at} | "
                f"{item['title']}",
                flush=True
            )

    records = [
        build_news_record(
            stock=stock,
            item=entry[
                "item"
            ],
            decision=entry[
                "decision"
            ]
        )

        for entry in accepted
    ]

    saved = 0

    if TEST_MODE:

        print(
            "\n🔒 TEST MODE: "
            "لم يتم حفظ أي خبر.",
            flush=True
        )

    else:

        saved = save_news_records(
            records
        )

        print(
            f"\n💾 Saved Material Events: "
            f"{saved}",
            flush=True
        )

    return {
        "symbol":
            symbol,

        "company_name":
            company_name,

        "raw":
            len(
                fetched_items
            ),

        "accepted":
            len(
                accepted
            ),

        "saved":
            saved,

        "rejected":
            rejected_counts,
    }


# ============================================================
# Run
# ============================================================

def run_news_pipeline():

    print_header(
        f"📰 NEWS DATA PIPELINE "
        f"v{ENGINE_VERSION}"
    )

    print(
        f"🔒 TEST MODE: "
        f"{TEST_MODE}",
        flush=True
    )

    print(
        f"📅 Lookback: "
        f"{NEWS_LOOKBACK_DAYS} days",
        flush=True
    )

    print(
        f"🎯 Minimum Relevance: "
        f"{MIN_RELEVANCE_SCORE}",
        flush=True
    )

    print(
        f"⭐ Minimum Importance: "
        f"{MIN_IMPORTANCE_SCORE}",
        flush=True
    )

    print(
        f"🗄️ Save Target: "
        f"company_news",
        flush=True
    )

    print(
        f"🕐 Started: "
        f"{datetime.now(timezone.utc).isoformat()}",
        flush=True
    )

    stocks = (
        get_active_stocks()
    )

    print(
        f"🏢 Active Companies: "
        f"{len(stocks)}",
        flush=True
    )

    if not stocks:

        print(
            "🔴 No active stocks found.",
            flush=True
        )

        return

    adapter = (
        YahooNewsAdapter()
    )

    results = []

    for index, stock in enumerate(
        stocks,
        start=1
    ):

        print(
            "\n"
            f"🚦 Company "
            f"{index}/{len(stocks)} | "
            f"{stock.get('symbol')}",
            flush=True
        )

        try:

            result = process_stock(
                stock,
                adapter
            )

            results.append(
                result
            )

        except Exception as error:

            print(
                f"🔴 NEWS ERROR | "
                f"{stock.get('symbol')} | "
                f"{type(error).__name__}: "
                f"{error}",
                flush=True
            )

            results.append({
                "symbol":
                    stock.get(
                        "symbol"
                    ),

                "company_name":
                    stock.get(
                        "company_name"
                    ),

                "raw":
                    0,

                "accepted":
                    0,

                "saved":
                    0,

                "rejected":
                    {
                        "ERROR":
                            1
                    },
            })

        if index < len(
            stocks
        ):

            time.sleep(
                REQUEST_DELAY_BETWEEN_STOCKS
            )

    # ========================================================
    # Final Summary
    # ========================================================

    total_raw = sum(
        item[
            "raw"
        ]
        for item in results
    )

    total_accepted = sum(
        item[
            "accepted"
        ]
        for item in results
    )

    total_saved = sum(
        item[
            "saved"
        ]
        for item in results
    )

    aggregate_rejections = {}

    for result in results:

        for reason, count in (
            result[
                "rejected"
            ].items()
        ):

            aggregate_rejections[
                reason
            ] = (
                aggregate_rejections.get(
                    reason,
                    0
                )
                + count
            )

    print_header(
        f"🏁 NEWS DATA PIPELINE "
        f"v{ENGINE_VERSION} SUMMARY"
    )

    print(
        f"🏢 Companies Processed: "
        f"{len(results)}",
        flush=True
    )

    print(
        f"📥 Raw Candidates: "
        f"{total_raw}",
        flush=True
    )

    print(
        f"✅ Accepted Material Events: "
        f"{total_accepted}",
        flush=True
    )

    print(
        f"💾 Saved Events: "
        f"{total_saved}",
        flush=True
    )

    if total_raw > 0:

        acceptance_rate = (
            total_accepted
            / total_raw
            * 100.0
        )

    else:

        acceptance_rate = 0.0

    print(
        f"🧹 Acceptance Rate: "
        f"{acceptance_rate:.2f}%",
        flush=True
    )

    if aggregate_rejections:

        print(
            "\n📋 Rejection Summary:",
            flush=True
        )

        for reason, count in sorted(
            aggregate_rejections.items(),
            key=lambda item:
                (
                    -item[1],
                    item[0]
                )
        ):

            print(
                f"- {reason}: "
                f"{count}",
                flush=True
            )

    print(
        "\n📌 IMPORTANT:",
        flush=True
    )

    print(
        "- Yahoo query uses symbol and symbol code only.",
        flush=True
    )

    print(
        "- Arabic company-name query is disabled in v1.0.1.",
        flush=True
    )

    print(
        "- TEST MODE does not read or write company_news.",
        flush=True
    )

    print(
        "- الأخبار غير الجوهرية لا تُحفظ.",
        flush=True
    )

    print(
        "- الأخبار المكررة لا تُحفظ.",
        flush=True
    )

    print(
        "- Sentiment لم يتم حسابه بعد.",
        flush=True
    )

    print(
        "- AI سيحلل الخبر المقبول لاحقًا.",
        flush=True
    )

    print(
        "- يمكن إضافة أي News Provider جديد "
        "كـ Adapter مستقل.",
        flush=True
    )

    print(
        "=" * 100,
        flush=True
    )


# ============================================================
# Start
# ============================================================

if __name__ == "__main__":

    run_news_pipeline()
