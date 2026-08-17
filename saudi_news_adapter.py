import re
import time
import hashlib
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from html import unescape
from xml.etree import ElementTree as ET

import requests


# ============================================================
# SAUDI NEWS ADAPTER v0.4.1
#
# READ ONLY / TEST ONLY
#
# v0.4.1:
# - يحتفظ بكل منطق v0.4
# - يضيف Retry + Exponential Backoff لـ Google News RSS
# - يقلل ضغط الطلبات
# - يميز SOURCE_UNAVAILABLE عن NO_NEWS
# - لا يعتبر 503 = صفر أخبار
# - لا يكتب إلى Supabase
# ============================================================


ENGINE_VERSION = "0.4.2"

TIMEOUT = 25

REQUEST_DELAY = 1.25
RETRY_ATTEMPTS = 3
RETRY_BASE_WAIT = 3

NEWS_LOOKBACK_DAYS = 21

MAX_ITEMS_PER_QUERY = 40
MAX_PRINT_PER_COMPANY = 12

MIN_RELEVANCE_SCORE = 45.0
MIN_IMPORTANCE_SCORE = 60.0

TADAWUL_URL = (
    "https://www.saudiexchange.sa/wps/portal/saudiexchange/"
    "newsandreports/issuer-news/issuer-announcements?locale=en"
)

ARGAAM_HOME = "https://www.argaam.com/"

GOOGLE_NEWS_RSS = "https://news.google.com/rss/search"


# ============================================================
# Test Companies
# ============================================================

TEST_COMPANIES = [
    {
        "symbol": "7203.SR",
        "code": "7203",
        "name_en": "Elm Company",
        "name_ar": "علم",
        "aliases": [
            "elm company",
            "elm",
            "شركة علم",
            "علم",
        ],
    },
    {
        "symbol": "4190.SR",
        "code": "4190",
        "name_en": "Jarir Marketing",
        "name_ar": "جرير",
        "aliases": [
            "jarir marketing",
            "jarir",
            "مكتبة جرير",
            "جرير",
        ],
    },
    {
        "symbol": "1810.SR",
        "code": "1810",
        "name_en": "Seera Group",
        "name_ar": "سيرا",
        "aliases": [
            "seera group",
            "seera",
            "مجموعة سيرا",
            "سيرا",
        ],
    },
]


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 "
        "(Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/131.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "application/rss+xml;q=0.9,*/*;q=0.8"
    ),
    "Accept-Language": "ar,en-US;q=0.9,en;q=0.8",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
}


# ============================================================
# Noise Rules
# ============================================================

NON_NEWS_TITLE_PATTERNS = [
    r"\brevenue breakdown\b",
    r"\bfinancial statements\b",
    r"\bnumber of employees\b",
    r"\bemployee count\b",
    r"\bheadcount data\b",
    r"\bstock price\b",
    r"\bshare price\b",
    r"\btechnical analysis\b",
    r"\bprice target\b",
    r"\bvaluation\b",
    r"\bhistorical data\b",
    r"\bcompany profile\b",
]


# ============================================================
# v0.4.2 - Pre-event rejection rules
# Reject previews, expectations and analyst/commentary pieces
# BEFORE material-event classification.
# ============================================================

PRE_EVENT_REJECT_PATTERNS = [
    r"\bwhat to expect\b",
    r"\bahead of .* earnings\b",
    r"\bahead of .* results\b",
    r"\bearnings preview\b",
    r"\bresults preview\b",
    r"\bpreviewing .* earnings\b",
    r"\bpreviewing .* results\b",
    r"\bexpected to report\b",
    r"\bexpected earnings\b",
    r"\bearnings expectations\b",
    r"\banalyst expects?\b",
    r"\banalysts expect\b",
    r"\banalyst forecast\b",
    r"\banalyst forecasts\b",
    r"\banalyst estimates?\b",
    r"\bconsensus estimate\b",
    r"\bconsensus estimates\b",
    r"\bforecast ahead of\b",
    r"\bshould you buy\b",
    r"\bis .* a buy\b",
    r"\bstock looks\b",
]

# Explicit precedence prevents a generic financial keyword such as
# "Q2" or "results" from overriding a more specific event.
EVENT_TYPE_PRIORITY = {
    "acquisition_merger": 120,
    "capital_action": 115,
    "contract_award": 110,
    "legal_regulatory": 105,
    "operational_event": 100,
    "project_status": 95,
    "dividend": 92,
    "management_change": 90,
    "financing_debt": 88,
    "expansion": 86,
    "ownership": 84,
    "guidance": 82,
    "growth_strategy": 80,
    "financial_results": 70,
}


# ============================================================
# Material Event Rules
# ============================================================

EVENT_RULES = {

    "financial_results": {
        "base_score": 72,
        "keywords": [
            "financial results",
            "earnings",
            "quarterly results",
            "annual results",
            "q1",
            "q2",
            "q3",
            "q4",
            "net profit",
            "net income",
            "revenue",
            "profit rises",
            "profit falls",
            "earnings growth",
            "earnings decline",
            "loss",
            "results",
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
            "pays sar",
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
            "opens new",
            "open new",
            "new showroom",
            "new store",
            "new bookstore",
            "branch",
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

    "growth_strategy": {
        "base_score": 68,
        "keywords": [
            "drives growth",
            "growth strategy",
            "career gains pending",
            "investment",
            "invests sar",
            "growth as",
        ],
    },
}


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
    "showroom",
    "store",
    "branch",
    "earnings",
    "results",
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


def clean_text(value):

    value = unescape(
        str(
            value
            or ""
        )
    )

    value = re.sub(
        r"\s+",
        " ",
        value
    )

    return value.strip()


def normalized_lower(value):

    return clean_text(
        value
    ).lower()


def make_external_id(
    source,
    title,
    url
):

    base = (
        f"{source}|"
        f"{clean_text(title)}|"
        f"{clean_text(url)}"
    )

    return hashlib.sha256(
        base.encode(
            "utf-8"
        )
    ).hexdigest()


def safe_request(
    url,
    params=None
):

    try:

        return requests.get(
            url,
            params=params,
            headers=HEADERS,
            timeout=TIMEOUT,
            allow_redirects=True,
        )

    except Exception as error:

        print(
            f"🔴 REQUEST ERROR | "
            f"{type(error).__name__}: "
            f"{error}",
            flush=True
        )

        return None


def safe_request_with_retry(
    url,
    params=None,
    label=""
):

    last_response = None

    for attempt in range(
        1,
        RETRY_ATTEMPTS + 1
    ):

        response = safe_request(
            url,
            params=params
        )

        if response is None:

            if attempt < RETRY_ATTEMPTS:

                wait_seconds = (
                    RETRY_BASE_WAIT
                    * attempt
                )

                print(
                    f"🟠 {label} | "
                    f"REQUEST ERROR | "
                    f"retry in {wait_seconds}s",
                    flush=True
                )

                time.sleep(
                    wait_seconds
                )

            continue

        last_response = response

        status = (
            response.status_code
        )

        if status == 200:

            return response

        if status in (
            429,
            500,
            502,
            503,
            504,
        ):

            if attempt < RETRY_ATTEMPTS:

                wait_seconds = (
                    RETRY_BASE_WAIT
                    * (2 ** (
                        attempt - 1
                    ))
                )

                print(
                    f"🟠 {label} | "
                    f"HTTP {status} | "
                    f"attempt "
                    f"{attempt}/"
                    f"{RETRY_ATTEMPTS} | "
                    f"retry in "
                    f"{wait_seconds}s",
                    flush=True
                )

                time.sleep(
                    wait_seconds
                )

                continue

        return response

    return last_response


def parse_rss_date(value):

    value = clean_text(
        value
    )

    if not value:
        return None

    try:

        parsed = parsedate_to_datetime(
            value
        )

        if parsed.tzinfo is None:

            parsed = parsed.replace(
                tzinfo=timezone.utc
            )

        return parsed.astimezone(
            timezone.utc
        )

    except Exception:

        return None


def within_lookback(
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


def is_non_news_title(
    title
):

    title_lower = normalized_lower(
        title
    )

    return any(
        re.search(
            pattern,
            title_lower,
            flags=re.I
        )

        for pattern
        in NON_NEWS_TITLE_PATTERNS
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

        for keyword
        in keywords
    )


def company_match(
    title,
    company
):

    haystack = normalized_lower(
        title
    )

    if not haystack:
        return False

    for alias in company[
        "aliases"
    ]:

        alias_lower = normalized_lower(
            alias
        )

        if not alias_lower:
            continue

        if len(
            alias_lower
        ) <= 4:

            pattern = (
                r"(?<![\w\u0600-\u06FF])"
                + re.escape(
                    alias_lower
                )
                + r"(?![\w\u0600-\u06FF])"
            )

            if re.search(
                pattern,
                haystack,
                flags=re.I
            ):

                return True

        elif alias_lower in haystack:

            return True

    return False


def normalized_title_key(
    title
):

    title = normalized_lower(
        title
    )

    title = re.sub(
        r"\s+-\s+[^-]{2,80}$",
        "",
        title
    )

    title = re.sub(
        r"[^\w\u0600-\u06FF]+",
        " ",
        title
    )

    title = re.sub(
        r"\s+",
        " ",
        title
    ).strip()

    return title


# ============================================================
# Source Diagnostics
# ============================================================

def test_tadawul():

    response = safe_request(
        TADAWUL_URL
    )

    if response is None:

        return {
            "available":
                False,

            "status":
                "REQUEST_ERROR",
        }

    return {
        "available":
            response.status_code == 200,

        "status":
            f"HTTP_{response.status_code}",
    }


def test_argaam():

    response = safe_request(
        ARGAAM_HOME
    )

    if response is None:

        return {
            "available":
                False,

            "status":
                "REQUEST_ERROR",

            "size":
                0,
        }

    return {
        "available":
            response.status_code == 200,

        "status":
            f"HTTP_{response.status_code}",

        "size":
            len(
                response.content
            ),
    }


# ============================================================
# Google News RSS
# ============================================================

def google_query_general(
    company
):

    return (
        f"\"{company['name_en']}\" "
        f"Saudi Arabia"
    )


def google_query_argaam(
    company
):

    return (
        f"\"{company['name_en']}\" "
        f"site:argaam.com"
    )


def parse_google_rss(
    xml_text,
    company,
    query_type
):

    output = []

    try:

        root = ET.fromstring(
            xml_text
        )

    except Exception as error:

        print(
            f"🔴 RSS XML ERROR | "
            f"{type(error).__name__}: "
            f"{error}",
            flush=True
        )

        return output

    for node in root.findall(
        ".//item"
    ):

        title = clean_text(
            node.findtext(
                "title"
            )
        )

        link = clean_text(
            node.findtext(
                "link"
            )
        )

        published_at = parse_rss_date(
            node.findtext(
                "pubDate"
            )
        )

        source_node = node.find(
            "source"
        )

        publisher = (
            clean_text(
                source_node.text
            )
            if source_node is not None
            else ""
        )

        if not title:
            continue

        if not within_lookback(
            published_at
        ):
            continue

        if not company_match(
            title,
            company
        ):
            continue

        if is_non_news_title(
            title
        ):
            continue

        output.append({
            "source":
                "google_news_rss",

            "query_type":
                query_type,

            "symbol":
                company[
                    "symbol"
                ],

            "company_name":
                company[
                    "name_ar"
                ],

            "title":
                title,

            "url":
                link,

            "publisher":
                publisher,

            "published_at":
                published_at.isoformat(),

            "external_id":
                make_external_id(
                    "google_news_rss",
                    title,
                    link
                ),
        })

        if len(
            output
        ) >= MAX_ITEMS_PER_QUERY:

            break

    return output


def fetch_google_query(
    company,
    query,
    query_type
):

    params = {
        "q":
            query,

        "hl":
            "en-SA",

        "gl":
            "SA",

        "ceid":
            "SA:en",
    }

    label = (
        f"{company['symbol']} | "
        f"{query_type}"
    )

    response = safe_request_with_retry(
        GOOGLE_NEWS_RSS,
        params=params,
        label=label
    )

    if response is None:

        print(
            f"🔴 {label} | "
            "SOURCE_UNAVAILABLE",
            flush=True
        )

        return {
            "status":
                "SOURCE_UNAVAILABLE",

            "items":
                [],
        }

    print(
        f"🌐 {company['symbol']} | "
        f"{query_type} | "
        f"HTTP {response.status_code} | "
        f"{len(response.content):,} bytes",
        flush=True
    )

    if response.status_code != 200:

        return {
            "status":
                (
                    "SOURCE_UNAVAILABLE"
                    if response.status_code
                    in (
                        429,
                        500,
                        502,
                        503,
                        504,
                    )
                    else f"HTTP_{response.status_code}"
                ),

            "items":
                [],
        }

    items = parse_google_rss(
        response.text,
        company,
        query_type
    )

    return {
        "status":
            "OK",

        "items":
            items,
    }


def fetch_company_candidates(
    company
):

    items = []

    source_unavailable = False

    general = fetch_google_query(
        company=company,
        query=google_query_general(
            company
        ),
        query_type="general"
    )

    if general[
        "status"
    ] == "SOURCE_UNAVAILABLE":

        source_unavailable = True

    items.extend(
        general[
            "items"
        ]
    )

    time.sleep(
        REQUEST_DELAY
    )

    argaam_targeted = fetch_google_query(
        company=company,
        query=google_query_argaam(
            company
        ),
        query_type="argaam_targeted"
    )

    if argaam_targeted[
        "status"
    ] == "SOURCE_UNAVAILABLE":

        source_unavailable = True

    items.extend(
        argaam_targeted[
            "items"
        ]
    )

    unique = []

    seen_titles = set()

    for item in sorted(
        items,
        key=lambda x:
            x[
                "published_at"
            ],
        reverse=True
    ):

        title_key = normalized_title_key(
            item[
                "title"
            ]
        )

        if title_key in seen_titles:
            continue

        seen_titles.add(
            title_key
        )

        unique.append(
            item
        )

    return {
        "status":
            (
                "SOURCE_UNAVAILABLE"
                if (
                    source_unavailable
                    and not unique
                )
                else "OK"
            ),

        "items":
            unique,
    }


# ============================================================
# Material Event Filter
# ============================================================

def classify_event(
    title
):

    title_lower = normalized_lower(
        title
    )

    matches = []

    for event_type, rule in EVENT_RULES.items():

        matched_keywords = [
            keyword

            for keyword in rule[
                "keywords"
            ]

            if normalized_lower(
                keyword
            )
            in title_lower
        ]

        if not matched_keywords:
            continue

        matches.append({
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

    if not matches:
        return None

    matches.sort(
        key=lambda item: (
            EVENT_TYPE_PRIORITY.get(
                item["event_type"],
                0
            ),
            item["base_score"],
            len(item["matched_keywords"]),
        ),
        reverse=True
    )

    return matches[0]


def relevance_score(
    company,
    item
):

    if company_match(
        item[
            "title"
        ],
        company
    ):

        return 92.0

    return 0.0


def importance_score(
    title,
    event_match,
    relevance
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
            relevance
            - MIN_RELEVANCE_SCORE
        )
        * 0.12
    )

    keyword_count = len(
        event_match[
            "matched_keywords"
        ]
    )

    if keyword_count >= 2:
        score += 4.0

    if keyword_count >= 3:
        score += 3.0

    return min(
        100.0,
        score
    )


def material_filter(
    company,
    item
):

    relevance = relevance_score(
        company,
        item
    )

    if relevance < MIN_RELEVANCE_SCORE:

        return {
            "accepted":
                False,

            "reason":
                "LOW_RELEVANCE",

            "relevance_score":
                relevance,
        }

    title_lower = normalized_lower(
        item["title"]
    )

    if any(
        re.search(
            pattern,
            title_lower,
            flags=re.IGNORECASE
        )
        for pattern in PRE_EVENT_REJECT_PATTERNS
    ):
        return {
            "accepted":
                False,

            "reason":
                "PREVIEW_OR_COMMENTARY",

            "relevance_score":
                relevance,
        }

    event_match = classify_event(
        item[
            "title"
        ]
    )

    if not event_match:

        return {
            "accepted":
                False,

            "reason":
                "NO_MATERIAL_EVENT",

            "relevance_score":
                relevance,
        }

    importance = importance_score(
        item[
            "title"
        ],
        event_match,
        relevance
    )

    if importance < MIN_IMPORTANCE_SCORE:

        return {
            "accepted":
                False,

            "reason":
                "LOW_IMPORTANCE",

            "relevance_score":
                relevance,

            "importance_score":
                importance,

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

        "event_type":
            event_match[
                "event_type"
            ],

        "relevance_score":
            relevance,

        "importance_score":
            importance,

        "matched_keywords":
            event_match[
                "matched_keywords"
            ],
    }


# ============================================================
# Run
# ============================================================

def run():

    print_header(
        f"📰 SAUDI NEWS ADAPTER "
        f"v{ENGINE_VERSION}"
    )

    print(
        "🔒 READ ONLY / TEST ONLY",
        flush=True
    )

    print(
        f"📅 Lookback: "
        f"{NEWS_LOOKBACK_DAYS} days",
        flush=True
    )

    print(
        f"🔁 Retry Attempts: "
        f"{RETRY_ATTEMPTS}",
        flush=True
    )

    print(
        f"⏱ Request Delay: "
        f"{REQUEST_DELAY}s",
        flush=True
    )

    print(
        "💾 No Supabase writes",
        flush=True
    )

    print(
        f"🕐 Started: "
        f"{datetime.now(timezone.utc).isoformat()}",
        flush=True
    )

    # ========================================================
    # Diagnostics
    # ========================================================

    print_header(
        "🧭 SOURCE DIAGNOSTICS"
    )

    tadawul = test_tadawul()

    print(
        f"🏛 Tadawul | "
        f"Available="
        f"{tadawul['available']} | "
        f"{tadawul['status']}",
        flush=True
    )

    argaam = test_argaam()

    print(
        f"🟢 Argaam | "
        f"Available="
        f"{argaam['available']} | "
        f"{argaam['status']} | "
        f"Size="
        f"{argaam['size']:,}",
        flush=True
    )

    # ========================================================
    # Candidate + Material Review
    # ========================================================

    print_header(
        "🧠 MATERIAL EVENT REVIEW"
    )

    total_candidates = 0
    total_accepted = 0
    source_unavailable_companies = 0

    rejection_counts = defaultdict(
        int
    )

    accepted_by_company = defaultdict(
        int
    )

    for company in TEST_COMPANIES:

        result = fetch_company_candidates(
            company
        )

        if result[
            "status"
        ] == "SOURCE_UNAVAILABLE":

            source_unavailable_companies += 1

            print(
                f"\n🏢 {company['symbol']} | "
                f"{company['name_ar']} | "
                "SOURCE_UNAVAILABLE",
                flush=True
            )

            print(
                "🟠 لم نعتبر الحالة "
                "NO_NEWS لأن المصدر لم يكن متاحًا.",
                flush=True
            )

            continue

        candidates = result[
            "items"
        ]

        total_candidates += len(
            candidates
        )

        accepted = []
        rejected = []

        for item in candidates:

            decision = material_filter(
                company,
                item
            )

            if decision[
                "accepted"
            ]:

                accepted.append({
                    "item":
                        item,

                    "decision":
                        decision,
                })

            else:

                rejection_counts[
                    decision[
                        "reason"
                    ]
                ] += 1

                rejected.append({
                    "item":
                        item,

                    "decision":
                        decision,
                })

        accepted.sort(
            key=lambda entry:
                entry[
                    "decision"
                ][
                    "importance_score"
                ],
            reverse=True
        )

        total_accepted += len(
            accepted
        )

        accepted_by_company[
            company[
                "symbol"
            ]
        ] = len(
            accepted
        )

        print(
            f"\n🏢 {company['symbol']} | "
            f"{company['name_ar']} | "
            f"Candidates="
            f"{len(candidates)} | "
            f"Accepted="
            f"{len(accepted)}",
            flush=True
        )

        if accepted:

            print(
                "\n✅ Accepted Material Events:",
                flush=True
            )

            for index, entry in enumerate(
                accepted[
                    :MAX_PRINT_PER_COMPANY
                ],
                start=1
            ):

                item = entry[
                    "item"
                ]

                decision = entry[
                    "decision"
                ]

                print(
                    f"{index}. "
                    f"[{decision['event_type']}] "
                    f"Importance="
                    f"{decision['importance_score']:.1f} | "
                    f"Relevance="
                    f"{decision['relevance_score']:.1f} | "
                    f"{item['published_at'][:10]} | "
                    f"{item['publisher'] or 'N/A'} | "
                    f"{item['title']}",
                    flush=True
                )

        if rejected:

            print(
                "\n🧹 Rejected:",
                flush=True
            )

            local_counts = defaultdict(
                int
            )

            for entry in rejected:

                local_counts[
                    entry[
                        "decision"
                    ][
                        "reason"
                    ]
                ] += 1

            for reason, count in sorted(
                local_counts.items()
            ):

                print(
                    f"- {reason}: "
                    f"{count}",
                    flush=True
                )

    # ========================================================
    # Final Summary
    # ========================================================

    print_header(
        "🏁 SAUDI NEWS ADAPTER v0.4.1 SUMMARY"
    )

    print(
        f"🏢 Companies Tested: "
        f"{len(TEST_COMPANIES)}",
        flush=True
    )

    print(
        f"🟠 Source-Unavailable Companies: "
        f"{source_unavailable_companies}",
        flush=True
    )

    print(
        f"📰 Recent Unique Candidates: "
        f"{total_candidates}",
        flush=True
    )

    print(
        f"✅ Accepted Material Events: "
        f"{total_accepted}",
        flush=True
    )

    if total_candidates > 0:

        acceptance_rate = (
            total_accepted
            / total_candidates
            * 100.0
        )

    else:

        acceptance_rate = 0.0

    print(
        f"📈 Material Acceptance Rate: "
        f"{acceptance_rate:.2f}%",
        flush=True
    )

    for company in TEST_COMPANIES:

        print(
            f"- {company['symbol']} | "
            f"{company['name_ar']} | "
            f"{accepted_by_company[company['symbol']]} accepted",
            flush=True
        )

    if rejection_counts:

        print(
            "\n📋 Rejection Summary:",
            flush=True
        )

        for reason, count in sorted(
            rejection_counts.items(),
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
        "- 503/429/5xx لا تعني NO_NEWS.",
        flush=True
    )

    print(
        "- عند تعذر المصدر نسجل SOURCE_UNAVAILABLE.",
        flush=True
    )

    print(
        "- لا توجد أي كتابة في Supabase.",
        flush=True
    )

    print(
        "- إذا عاد Google إلى HTTP 200 "
        "سنراجع Accepted Events قبل التوسعة للـ21 شركة.",
        flush=True
    )

    print(
        "=" * 100,
        flush=True
    )


if __name__ == "__main__":

    run()
