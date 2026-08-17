import re
import time
import hashlib
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from html import unescape
from urllib.parse import urlparse
from xml.etree import ElementTree as ET

import requests


# ============================================================
# SAUDI NEWS ADAPTER v0.3
#
# READ ONLY / TEST ONLY
#
# القرار بعد v0.2:
# - Tadawul: Official Arbiter فقط بسبب HTTP 403
# - Argaam: الموقع متاح، لكن Homepage parsing غير موثوق
# - Google News RSS: مصدر التجميع العملي الحالي
#
# v0.3:
# 1) Google News RSS - General company search
# 2) Google News RSS - Argaam-targeted search
# 3) Lookback filter = 21 days
# 4) إزالة الأخبار القديمة قبل عرضها
# 5) إزالة صفحات البيانات/الملفات العامة غير الخبرية
# 6) Company identity confirmation
# 7) Cross-query deduplication
# 8) لا كتابة في Supabase
#
# بعد نجاح v0.3:
# نربط Candidate News مع news_data.py Material Event Filter.
# ============================================================


ENGINE_VERSION = "0.3"

TIMEOUT = 25
REQUEST_DELAY = 0.45

NEWS_LOOKBACK_DAYS = 21

MAX_ITEMS_PER_QUERY = 40
MAX_PRINT_PER_COMPANY = 10

TADAWUL_URL = (
    "https://www.saudiexchange.sa/wps/portal/saudiexchange/"
    "newsandreports/issuer-news/issuer-announcements?locale=en"
)

ARGAAM_HOME = "https://www.argaam.com/"

GOOGLE_NEWS_RSS = (
    "https://news.google.com/rss/search"
)


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
# Noise / non-news title rules
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


def parse_rss_date(
    value
):

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
# Source diagnostics
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

    response = safe_request(
        GOOGLE_NEWS_RSS,
        params=params
    )

    if response is None:

        return []

    print(
        f"🌐 {company['symbol']} | "
        f"{query_type} | "
        f"HTTP {response.status_code} | "
        f"{len(response.content):,} bytes",
        flush=True
    )

    if response.status_code != 200:

        return []

    return parse_google_rss(
        response.text,
        company,
        query_type
    )


def fetch_company_candidates(
    company
):

    items = []

    general_items = fetch_google_query(
        company=company,
        query=google_query_general(
            company
        ),
        query_type="general"
    )

    items.extend(
        general_items
    )

    time.sleep(
        REQUEST_DELAY
    )

    argaam_items = fetch_google_query(
        company=company,
        query=google_query_argaam(
            company
        ),
        query_type="argaam_targeted"
    )

    items.extend(
        argaam_items
    )

    # Deduplicate by normalized title within the company.
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

    return unique


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
    # Candidate collection
    # ========================================================

    print_header(
        "🔎 COMPANY CANDIDATE REVIEW"
    )

    all_items = []

    for company in TEST_COMPANIES:

        items = fetch_company_candidates(
            company
        )

        all_items.extend(
            items
        )

        print(
            f"\n🏢 {company['symbol']} | "
            f"{company['name_ar']} | "
            f"Recent Candidates="
            f"{len(items)}",
            flush=True
        )

        if not items:

            print(
                "- No recent confirmed candidates.",
                flush=True
            )

            continue

        for index, item in enumerate(
            items[
                :MAX_PRINT_PER_COMPANY
            ],
            start=1
        ):

            print(
                f"{index}. "
                f"[{item['query_type']}] "
                f"{item['published_at'][:10]} | "
                f"{item['publisher'] or 'N/A'} | "
                f"{item['title']}",
                flush=True
            )

    # ========================================================
    # Final Summary
    # ========================================================

    print_header(
        "🏁 SAUDI NEWS ADAPTER v0.3 SUMMARY"
    )

    grouped = defaultdict(
        int
    )

    query_types = defaultdict(
        int
    )

    for item in all_items:

        grouped[
            item[
                "symbol"
            ]
        ] += 1

        query_types[
            item[
                "query_type"
            ]
        ] += 1

    print(
        f"🏢 Companies Tested: "
        f"{len(TEST_COMPANIES)}",
        flush=True
    )

    print(
        f"📰 Recent Unique Candidates: "
        f"{len(all_items)}",
        flush=True
    )

    print(
        f"🌐 General RSS Candidates: "
        f"{query_types['general']}",
        flush=True
    )

    print(
        f"🟢 Argaam-targeted RSS Candidates: "
        f"{query_types['argaam_targeted']}",
        flush=True
    )

    for company in TEST_COMPANIES:

        print(
            f"- {company['symbol']} | "
            f"{company['name_ar']} | "
            f"{grouped[company['symbol']]} candidates",
            flush=True
        )

    print(
        "\n📌 IMPORTANT:",
        flush=True
    )

    print(
        "- الأخبار الأقدم من 21 يومًا تم حذفها قبل العرض.",
        flush=True
    )

    print(
        "- صفحات البيانات العامة مثل Revenue Breakdown "
        "وFinancial Statements تم استبعادها.",
        flush=True
    )

    print(
        "- هذه ليست مرحلة Material Event النهائية بعد.",
        flush=True
    )

    print(
        "- الخطوة التالية بعد مراجعة العناوين: "
        "تمريرها إلى news_data.py للتصنيف والفلترة قبل الحفظ.",
        flush=True
    )

    print(
        "- Tadawul يبقى Official Arbiter بسبب الحماية.",
        flush=True
    )

    print(
        "=" * 100,
        flush=True
    )


if __name__ == "__main__":

    run()
