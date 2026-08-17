import re
import time
import hashlib
from collections import defaultdict
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html import unescape
from html.parser import HTMLParser
from urllib.parse import urljoin
from xml.etree import ElementTree as ET

import requests


# ============================================================
# SAUDI NEWS ADAPTER v0.2
#
# READ ONLY / TEST ONLY
#
# المصادر:
# 1) Tadawul            -> Official arbiter only if blocked
# 2) Argaam             -> Primary Saudi-news candidate
# 3) Google News RSS    -> Secondary coverage
#
# أهداف v0.2:
# - استخراج أخبار مرشحة فعلية بدل مجرد عدّ الروابط
# - ربط الخبر بالشركة Company Hint قبل أي حفظ
# - إزالة الروابط العامة/صفحات الشركات من أرقام
# - إزالة التكرار
# - طباعة عينات قابلة للمراجعة
# - لا يكتب أي شيء في Supabase
#
# بعد نجاح v0.2:
# يتم تمرير المخرجات إلى news_data.py
# لكي يعمل Material Event Filter قبل الحفظ.
# ============================================================


ENGINE_VERSION = "0.2"

TIMEOUT = 25
REQUEST_DELAY = 0.45

MAX_ARGAAM_ITEMS = 120
MAX_GOOGLE_ITEMS_PER_COMPANY = 30
MAX_PRINT_PER_COMPANY = 8

BASE_TADAWUL = "https://www.saudiexchange.sa"

TADAWUL_URL = (
    "https://www.saudiexchange.sa/wps/portal/saudiexchange/"
    "newsandreports/issuer-news/issuer-announcements?locale=en"
)

ARGAAM_URLS = [
    "https://www.argaam.com/",
    "https://www.argaam.com/ar/",
]

GOOGLE_NEWS_RSS = (
    "https://news.google.com/rss/search"
)


# ============================================================
# شركات الاختبار
#
# سنبدأ بثلاث شركات فقط حتى نراجع الجودة يدويًا.
# بعد النجاح نربطه تلقائيًا بجدول stocks.
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

        response = requests.get(
            url,
            params=params,
            headers=HEADERS,
            timeout=TIMEOUT,
            allow_redirects=True,
        )

        return response

    except Exception as error:

        print(
            f"🔴 REQUEST ERROR | "
            f"{type(error).__name__}: "
            f"{error}",
            flush=True
        )

        return None


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

        # Aliases القصيرة جدًا مثل "علم" و"سيرا" تحتاج
        # حدود كلمة حتى لا تطابق أجزاء من كلمات أخرى.
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


def identify_company(
    title
):

    matches = []

    for company in TEST_COMPANIES:

        if company_match(
            title,
            company
        ):

            matches.append(
                company
            )

    if len(
        matches
    ) == 1:

        return matches[0]

    return None


# ============================================================
# Minimal HTML Parser
# ============================================================

class PublicHTMLParser(
    HTMLParser
):

    def __init__(self):

        super().__init__()

        self.links = []

        self.current_href = None
        self.current_text = []

    def handle_starttag(
        self,
        tag,
        attrs
    ):

        if tag.lower() != "a":
            return

        attrs = dict(
            attrs
        )

        self.current_href = (
            attrs.get(
                "href"
            )
        )

        self.current_text = []

    def handle_data(
        self,
        data
    ):

        if self.current_href is not None:

            self.current_text.append(
                data
            )

    def handle_endtag(
        self,
        tag
    ):

        if (
            tag.lower() == "a"
            and self.current_href is not None
        ):

            text = clean_text(
                " ".join(
                    self.current_text
                )
            )

            self.links.append({
                "text":
                    text,

                "href":
                    self.current_href,
            })

            self.current_href = None
            self.current_text = []


# ============================================================
# 1) Tadawul
# ============================================================

def test_tadawul():

    print_header(
        "🏛 SOURCE 1: TADAWUL"
    )

    response = safe_request(
        TADAWUL_URL
    )

    if response is None:

        return {
            "source":
                "tadawul",

            "available":
                False,

            "status":
                "REQUEST_ERROR",

            "items":
                [],
        }

    print(
        f"🌐 HTTP Status: "
        f"{response.status_code}",
        flush=True
    )

    print(
        f"📦 Response Size: "
        f"{len(response.content):,} bytes",
        flush=True
    )

    if response.status_code != 200:

        print(
            "🔴 Tadawul unavailable for direct automation.",
            flush=True
        )

        return {
            "source":
                "tadawul",

            "available":
                False,

            "status":
                f"HTTP_{response.status_code}",

            "items":
                [],
        }

    return {
        "source":
            "tadawul",

        "available":
            True,

        "status":
            "HTTP_200",

        "items":
            [],
    }


# ============================================================
# 2) Argaam
# ============================================================

def is_argaam_article_url(
    url
):

    url_lower = normalized_lower(
        url
    )

    # نستهدف صفحات الأخبار/المقالات فقط.
    # نستبعد صفحات الشركات والتصنيفات والتنقل العام.
    positive = any(
        token in url_lower

        for token in (
            "/article/articledetail/",
            "/article/",
            "/news/",
        )
    )

    negative = any(
        token in url_lower

        for token in (
            "/company/",
            "/companies/",
            "/market/",
            "/markets/",
            "/indices/",
            "/stock/",
            "/stocks/",
            "/sector/",
            "/sectors/",
        )
    )

    return (
        positive
        and not negative
    )


def extract_argaam_articles(
    html_text,
    base_url
):

    parser = PublicHTMLParser()

    parser.feed(
        html_text
    )

    candidates = []

    for link in parser.links:

        title = clean_text(
            link.get(
                "text"
            )
        )

        href = clean_text(
            link.get(
                "href"
            )
        )

        if (
            not title
            or not href
        ):
            continue

        # عنوان قصير جدًا غالبًا ليس خبرًا.
        if len(
            title
        ) < 18:
            continue

        full_url = urljoin(
            base_url,
            href
        )

        if not is_argaam_article_url(
            full_url
        ):
            continue

        company = identify_company(
            title
        )

        if company is None:
            continue

        candidates.append({
            "source":
                "argaam",

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
                full_url,

            "published_at":
                None,

            "external_id":
                make_external_id(
                    "argaam",
                    title,
                    full_url
                ),
        })

    # Deduplicate
    unique = []
    seen = set()

    for item in candidates:

        external_id = (
            item[
                "external_id"
            ]
        )

        if external_id in seen:
            continue

        seen.add(
            external_id
        )

        unique.append(
            item
        )

    return unique


def test_argaam():

    print_header(
        "🟢 SOURCE 2: ARGAAM"
    )

    all_items = []

    successful_endpoint = False

    for url in ARGAAM_URLS:

        response = safe_request(
            url
        )

        if response is None:

            print(
                f"🔴 {url} | REQUEST ERROR",
                flush=True
            )

            continue

        print(
            f"🌐 {url} | "
            f"HTTP {response.status_code} | "
            f"{len(response.content):,} bytes",
            flush=True
        )

        if response.status_code != 200:
            continue

        successful_endpoint = True

        items = extract_argaam_articles(
            response.text,
            response.url
        )

        all_items.extend(
            items
        )

        time.sleep(
            REQUEST_DELAY
        )

    # Deduplicate across endpoints
    unique = []
    seen = set()

    for item in all_items:

        external_id = (
            item[
                "external_id"
            ]
        )

        if external_id in seen:
            continue

        seen.add(
            external_id
        )

        unique.append(
            item
        )

    unique = unique[
        :MAX_ARGAAM_ITEMS
    ]

    print(
        f"📰 Company-matched article candidates: "
        f"{len(unique)}",
        flush=True
    )

    return {
        "source":
            "argaam",

        "available":
            successful_endpoint,

        "status":
            (
                "HTTP_200"
                if successful_endpoint
                else "UNAVAILABLE"
            ),

        "items":
            unique,
    }


# ============================================================
# 3) Google News RSS
# ============================================================

def google_news_query(
    company
):

    # استخدام الاسم الإنجليزي + السعودية
    # يقلل النتائج من الشركات الأجنبية المشابهة.
    return (
        f"\"{company['name_en']}\" "
        f"Saudi Arabia"
    )


def parse_google_news_rss(
    xml_text,
    company
):

    items = []

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

        return items

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

        pub_date_raw = clean_text(
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

        # Google RSS query قد يعيد نتائج جانبية،
        # لذلك نعيد تأكيد اسم الشركة في العنوان.
        if not company_match(
            title,
            company
        ):
            continue

        published_at = None

        if pub_date_raw:

            try:

                parsed = parsedate_to_datetime(
                    pub_date_raw
                )

                if parsed.tzinfo is None:

                    parsed = parsed.replace(
                        tzinfo=timezone.utc
                    )

                published_at = (
                    parsed.astimezone(
                        timezone.utc
                    )
                    .isoformat()
                )

            except Exception:

                published_at = None

        items.append({
            "source":
                "google_news_rss",

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
                published_at,

            "external_id":
                make_external_id(
                    "google_news_rss",
                    title,
                    link
                ),
        })

        if len(
            items
        ) >= MAX_GOOGLE_ITEMS_PER_COMPANY:

            break

    return items


def test_google_news():

    print_header(
        "🔵 SOURCE 3: GOOGLE NEWS RSS"
    )

    all_items = []

    success_count = 0

    for company in TEST_COMPANIES:

        params = {
            "q":
                google_news_query(
                    company
                ),

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

            print(
                f"🔴 {company['symbol']} | "
                "REQUEST ERROR",
                flush=True
            )

            continue

        print(
            f"🌐 {company['symbol']} | "
            f"HTTP {response.status_code} | "
            f"{len(response.content):,} bytes",
            flush=True
        )

        if response.status_code != 200:
            continue

        success_count += 1

        items = parse_google_news_rss(
            response.text,
            company
        )

        all_items.extend(
            items
        )

        print(
            f"📰 {company['symbol']} | "
            f"Company-confirmed RSS items: "
            f"{len(items)}",
            flush=True
        )

        time.sleep(
            REQUEST_DELAY
        )

    return {
        "source":
            "google_news_rss",

        "available":
            success_count > 0,

        "status":
            (
                "HTTP_200"
                if success_count > 0
                else "UNAVAILABLE"
            ),

        "items":
            all_items,
    }


# ============================================================
# Cross-source dedupe
# ============================================================

def normalized_title_key(
    title
):

    title = normalized_lower(
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


def merge_candidate_items(
    source_results
):

    merged = []

    seen_exact = set()
    seen_title = set()

    for result in source_results:

        for item in result[
            "items"
        ]:

            exact_key = (
                item[
                    "external_id"
                ]
            )

            title_key = (
                item[
                    "symbol"
                ],
                normalized_title_key(
                    item[
                        "title"
                    ]
                )
            )

            if exact_key in seen_exact:
                continue

            if title_key in seen_title:
                continue

            seen_exact.add(
                exact_key
            )

            seen_title.add(
                title_key
            )

            merged.append(
                item
            )

    return merged


# ============================================================
# Print candidates
# ============================================================

def print_company_candidates(
    merged
):

    grouped = defaultdict(
        list
    )

    for item in merged:

        grouped[
            item[
                "symbol"
            ]
        ].append(
            item
        )

    print_header(
        "🔎 COMPANY CANDIDATE REVIEW"
    )

    for company in TEST_COMPANIES:

        symbol = company[
            "symbol"
        ]

        items = grouped.get(
            symbol,
            []
        )

        print(
            f"\n🏢 {symbol} | "
            f"{company['name_ar']} | "
            f"Candidates={len(items)}",
            flush=True
        )

        if not items:

            print(
                "- No confirmed candidate news.",
                flush=True
            )

            continue

        for index, item in enumerate(
            items[
                :MAX_PRINT_PER_COMPANY
            ],
            start=1
        ):

            date_text = (
                item.get(
                    "published_at"
                )
                or "N/A"
            )

            publisher = (
                item.get(
                    "publisher"
                )
                or item[
                    "source"
                ]
            )

            print(
                f"{index}. "
                f"[{item['source']}] "
                f"{date_text} | "
                f"{publisher} | "
                f"{item['title']}",
                flush=True
            )


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
        "🚫 No protection bypass",
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
    # Source 1
    # ========================================================

    tadawul = test_tadawul()

    # ========================================================
    # Source 2
    # ========================================================

    argaam = test_argaam()

    # ========================================================
    # Source 3
    # ========================================================

    google_news = test_google_news()

    source_results = [
        argaam,
        google_news,
    ]

    merged = merge_candidate_items(
        source_results
    )

    print_company_candidates(
        merged
    )

    # ========================================================
    # Final Summary
    # ========================================================

    print_header(
        "🏁 SAUDI NEWS SOURCE SUMMARY"
    )

    for result in (
        tadawul,
        argaam,
        google_news,
    ):

        print(
            f"{result['source']} | "
            f"Available="
            f"{result['available']} | "
            f"Status="
            f"{result['status']} | "
            f"Items="
            f"{len(result['items'])}",
            flush=True
        )

    print(
        f"\n🧩 Cross-source unique "
        f"company candidates: "
        f"{len(merged)}",
        flush=True
    )

    if (
        argaam[
            "available"
        ]
        and len(
            argaam[
                "items"
            ]
        ) > 0
    ):

        print(
            "🟢 Argaam extraction is usable.",
            flush=True
        )

    elif argaam[
        "available"
    ]:

        print(
            "🟡 Argaam is reachable but "
            "company-title extraction needs refinement.",
            flush=True
        )

    if (
        google_news[
            "available"
        ]
        and len(
            google_news[
                "items"
            ]
        ) > 0
    ):

        print(
            "🟢 Google News RSS company matching is usable.",
            flush=True
        )

    print(
        "\n📌 NEXT GATE:",
        flush=True
    )

    print(
        "- نراجع العناوين المطبوعة أولًا.",
        flush=True
    )

    print(
        "- إذا كانت تخص الشركات فعلًا، "
        "نربطها مع Material Event Filter في news_data.py.",
        flush=True
    )

    print(
        "- لا يتم الحفظ قبل اجتياز الفلترة.",
        flush=True
    )

    print(
        "- تداول يبقى Official Arbiter بسبب HTTP 403.",
        flush=True
    )

    print(
        "=" * 100,
        flush=True
    )


if __name__ == "__main__":

    run()
