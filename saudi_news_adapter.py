import re
import time
import hashlib
from datetime import datetime, timezone
from html import unescape
from html.parser import HTMLParser
from urllib.parse import quote_plus, urljoin
from xml.etree import ElementTree as ET

import requests


# ============================================================
# SAUDI NEWS ADAPTER v0.1
#
# READ ONLY / TEST ONLY
#
# الهدف:
# اختبار عدة مصادر أخبار سعودية من ملف واحد:
#
# 1) Tadawul
# 2) Argaam
# 3) Google News RSS
#
# مهم:
# - لا يكتب إلى Supabase
# - لا يحاول تجاوز أي حماية
# - إذا فشل مصدر ينتقل للمصدر التالي
# - هذه النسخة للتشخيص فقط
# ============================================================


ENGINE_VERSION = "0.1"

TIMEOUT = 25

REQUEST_DELAY = 0.5

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


TEST_COMPANIES = [
    {
        "symbol": "7203.SR",
        "code": "7203",
        "name_en": "Elm Company",
        "name_ar": "علم",
    },
    {
        "symbol": "4190.SR",
        "code": "4190",
        "name_en": "Jarir Marketing",
        "name_ar": "جرير",
    },
    {
        "symbol": "1810.SR",
        "code": "1810",
        "name_en": "Seera Group",
        "name_ar": "سيرا",
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
        f"🔗 Final URL: "
        f"{response.url}",
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

    parser = PublicHTMLParser()

    parser.feed(
        response.text
    )

    items = []

    for link in parser.links:

        text = clean_text(
            link.get(
                "text"
            )
        )

        href = clean_text(
            link.get(
                "href"
            )
        )

        if not href:
            continue

        full_url = urljoin(
            BASE_TADAWUL,
            href
        )

        haystack = (
            f"{text} "
            f"{full_url}"
        ).lower()

        if any(
            token in haystack
            for token in (
                "issuer-announcements-details",
                "announcement",
            )
        ):

            items.append({
                "source":
                    "tadawul",

                "title":
                    text,

                "url":
                    full_url,

                "external_id":
                    make_external_id(
                        "tadawul",
                        text,
                        full_url
                    ),
            })

    print(
        f"📰 Announcement-like items: "
        f"{len(items)}",
        flush=True
    )

    return {
        "source":
            "tadawul",

        "available":
            True,

        "status":
            "HTTP_200",

        "items":
            items,
    }


# ============================================================
# 2) Argaam
# ============================================================

def extract_argaam_candidate_links(
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

        if not title or not href:
            continue

        full_url = urljoin(
            base_url,
            href
        )

        url_lower = (
            full_url.lower()
        )

        if any(
            token in url_lower
            for token in (
                "/article/",
                "/news/",
                "/company/",
            )
        ):

            candidates.append({
                "source":
                    "argaam",

                "title":
                    title,

                "url":
                    full_url,

                "external_id":
                    make_external_id(
                        "argaam",
                        title,
                        full_url
                    ),
            })

    unique = []

    seen = set()

    for item in candidates:

        key = (
            item[
                "title"
            ],
            item[
                "url"
            ]
        )

        if key in seen:
            continue

        seen.add(
            key
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

        items = (
            extract_argaam_candidate_links(
                response.text,
                response.url
            )
        )

        all_items.extend(
            items
        )

        time.sleep(
            REQUEST_DELAY
        )

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

    print(
        f"📰 Candidate links found: "
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

    # نستخدم الاسم الإنجليزي + Saudi Arabia
    # لتقليل نتائج الشركات الأجنبية ذات الأسماء المشابهة.
    return (
        f"\"{company['name_en']}\" "
        f"Saudi Arabia"
    )


def parse_google_news_rss(
    xml_text
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

    for item in root.findall(
        ".//item"
    ):

        title = clean_text(
            item.findtext(
                "title"
            )
        )

        link = clean_text(
            item.findtext(
                "link"
            )
        )

        pub_date = clean_text(
            item.findtext(
                "pubDate"
            )
        )

        if not title:
            continue

        items.append({
            "source":
                "google_news_rss",

            "title":
                title,

            "url":
                link,

            "published_raw":
                pub_date,

            "external_id":
                make_external_id(
                    "google_news_rss",
                    title,
                    link
                ),
        })

    return items


def test_google_news():

    print_header(
        "🔵 SOURCE 3: GOOGLE NEWS RSS"
    )

    all_items = []

    success_count = 0

    for company in TEST_COMPANIES:

        query = (
            google_news_query(
                company
            )
        )

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
            response.text
        )

        for item in items:

            item[
                "symbol"
            ] = company[
                "symbol"
            ]

            item[
                "company_name"
            ] = company[
                "name_en"
            ]

        all_items.extend(
            items
        )

        print(
            f"📰 {company['symbol']} | "
            f"RSS items: "
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
# Result
# ============================================================

def print_source_summary(
    result
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

    results = []

    # ========================================================
    # Source 1: Tadawul
    # ========================================================

    tadawul = test_tadawul()

    results.append(
        tadawul
    )

    # ========================================================
    # Source 2: Argaam
    # ========================================================

    argaam = test_argaam()

    results.append(
        argaam
    )

    # ========================================================
    # Source 3: Google News RSS
    # ========================================================

    google_news = test_google_news()

    results.append(
        google_news
    )

    # ========================================================
    # Final Summary
    # ========================================================

    print_header(
        "🏁 SAUDI NEWS SOURCE SUMMARY"
    )

    for result in results:

        print_source_summary(
            result
        )

    usable_sources = [
        result
        for result in results
        if result[
            "available"
        ]
    ]

    print(
        f"\n✅ Usable Sources: "
        f"{len(usable_sources)}/"
        f"{len(results)}",
        flush=True
    )

    print(
        "\n📌 Source Priority Recommendation:",
        flush=True
    )

    if argaam[
        "available"
    ]:

        print(
            "1. Argaam = Primary Saudi news candidate",
            flush=True
        )

    if google_news[
        "available"
    ]:

        print(
            "2. Google News RSS = Secondary coverage source",
            flush=True
        )

    if tadawul[
        "available"
    ]:

        print(
            "3. Tadawul = Official source when automation is accessible",
            flush=True
        )

    else:

        print(
            "3. Tadawul = Official arbiter only "
            "(direct automation currently unavailable)",
            flush=True
        )

    print(
        "\n📌 IMPORTANT:",
        flush=True
    )

    print(
        "- هذه النسخة تشخيصية فقط.",
        flush=True
    )

    print(
        "- لا يتم حفظ أي خبر.",
        flush=True
    )

    print(
        "- بعد اختيار المصدر سنربطه مع "
        "news_data.py للفلترة قبل الحفظ.",
        flush=True
    )

    print(
        "- إذا فشل مصدر لا يؤثر على بقية المصادر.",
        flush=True
    )

    print(
        "=" * 100,
        flush=True
    )


if __name__ == "__main__":

    run()
