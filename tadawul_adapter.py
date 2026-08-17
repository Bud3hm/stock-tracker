import re
from datetime import datetime, timezone
from html import unescape
from html.parser import HTMLParser
from urllib.parse import urljoin

import requests

# ============================================================
# TADAWUL ANNOUNCEMENTS ADAPTER v0.1
# READ ONLY / TEST ONLY
#
# الهدف:
# - اختبار وصول GitHub Actions إلى صفحة إعلانات تداول.
# - لا يحاول تجاوز أي حماية.
# - لا يكتب إلى Supabase.
# - لا يستخدم API غير موثق.
# - يفحص HTML العام فقط ويحاول اكتشاف روابط/نصوص الإعلانات.
# ============================================================

ENGINE_VERSION = "0.1"
TEST_MODE = True
TIMEOUT = 25

BASE_URL = "https://www.saudiexchange.sa"
ANNOUNCEMENTS_URL = (
    "https://www.saudiexchange.sa/wps/portal/saudiexchange/"
    "newsandreports/issuer-news/issuer-announcements?locale=en"
)

TEST_COMPANIES = [
    {"symbol": "7203.SR", "code": "7203", "name": "Elm", "arabic": "علم"},
    {"symbol": "4190.SR", "code": "4190", "name": "Jarir", "arabic": "جرير"},
    {"symbol": "1810.SR", "code": "1810", "name": "Seera", "arabic": "سيرا"},
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.9,ar;q=0.8",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
}


def clean_text(value):
    value = unescape(str(value or ""))
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def print_header(title):
    print("\n" + "=" * 100, flush=True)
    print(title, flush=True)
    print("=" * 100, flush=True)


class PublicHTMLParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.text_chunks = []
        self.current_href = None
        self.current_text = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag.lower() == "a":
            self.current_href = attrs.get("href")
            self.current_text = []

    def handle_data(self, data):
        text = clean_text(data)
        if text:
            self.text_chunks.append(text)
            if self.current_href is not None:
                self.current_text.append(text)

    def handle_endtag(self, tag):
        if tag.lower() == "a" and self.current_href is not None:
            text = clean_text(" ".join(self.current_text))
            self.links.append({
                "text": text,
                "href": self.current_href,
            })
            self.current_href = None
            self.current_text = []


def fetch_public_page():
    session = requests.Session()
    response = session.get(
        ANNOUNCEMENTS_URL,
        headers=HEADERS,
        timeout=TIMEOUT,
        allow_redirects=True,
    )

    print(f"🌐 HTTP Status: {response.status_code}", flush=True)
    print(f"🔗 Final URL: {response.url}", flush=True)
    print(
        f"📦 Response Size: {len(response.content):,} bytes",
        flush=True,
    )
    print(
        f"🧾 Content-Type: {response.headers.get('content-type', 'N/A')}",
        flush=True,
    )

    response.raise_for_status()
    return response


def detect_protection(response):
    text = response.text.lower()

    flags = []

    protection_terms = {
        "captcha": "CAPTCHA",
        "access denied": "ACCESS_DENIED",
        "forbidden": "FORBIDDEN",
        "cloudflare": "CLOUDFLARE",
        "incapsula": "INCAPSULA",
        "imperva": "IMPERVA",
        "akamai": "AKAMAI",
        "verify you are human": "HUMAN_VERIFICATION",
    }

    for needle, label in protection_terms.items():
        if needle in text:
            flags.append(label)

    return sorted(set(flags))


def parse_public_html(html_text):
    parser = PublicHTMLParser()
    parser.feed(html_text)

    links = []
    for item in parser.links:
        href = clean_text(item.get("href"))
        text = clean_text(item.get("text"))

        if not href:
            continue

        links.append({
            "text": text,
            "url": urljoin(BASE_URL, href),
        })

    return {
        "links": links,
        "text": clean_text(" ".join(parser.text_chunks)),
    }


def find_announcement_like_links(parsed):
    output = []

    for item in parsed["links"]:
        text = item["text"]
        url = item["url"]
        haystack = f"{text} {url}".lower()

        if any(token in haystack for token in (
            "announcement",
            "issuer-announcements-details",
            "issuer announcement",
        )):
            output.append(item)

    # Deduplicate
    unique = []
    seen = set()

    for item in output:
        key = (item["text"], item["url"])
        if key not in seen:
            seen.add(key)
            unique.append(item)

    return unique


def company_presence(parsed, company):
    haystack = parsed["text"].lower()

    terms = [
        company["symbol"].lower(),
        company["code"].lower(),
        company["name"].lower(),
        company["arabic"].lower(),
    ]

    matched = [
        term
        for term in terms
        if term and term in haystack
    ]

    return matched


def run():
    print_header(
        f"🏛 TADAWUL ANNOUNCEMENTS ADAPTER v{ENGINE_VERSION}"
    )

    print("🔒 READ ONLY / TEST ONLY", flush=True)
    print("🚫 No protection bypass", flush=True)
    print("💾 No Supabase writes", flush=True)
    print(
        f"🕐 Started: {datetime.now(timezone.utc).isoformat()}",
        flush=True,
    )

    try:
        response = fetch_public_page()
    except Exception as exc:
        print_header("❌ FETCH FAILED")
        print(
            f"{type(exc).__name__}: {exc}",
            flush=True,
        )
        print(
            "\n📌 إذا ظهر 403/429 أو فشل اتصال من GitHub Actions، "
            "نوقف مسار تداول ولا نحاول تجاوز الحماية.",
            flush=True,
        )
        raise

    protection = detect_protection(response)

    print_header("🛡 ACCESS DIAGNOSTIC")

    if protection:
        print(
            "⚠️ Protection indicators: "
            + ", ".join(protection),
            flush=True,
        )
    else:
        print(
            "✅ No obvious blocking page detected.",
            flush=True,
        )

    parsed = parse_public_html(response.text)

    print(
        f"🔗 Parsed Links: {len(parsed['links'])}",
        flush=True,
    )

    announcement_links = find_announcement_like_links(
        parsed
    )

    print(
        f"📰 Announcement-like Links: {len(announcement_links)}",
        flush=True,
    )

    if announcement_links:
        print("\n🔎 Sample Links:", flush=True)

        for idx, item in enumerate(
            announcement_links[:10],
            start=1,
        ):
            print(
                f"{idx}. {item['text'][:180] or '[NO TEXT]'}",
                flush=True,
            )
            print(
                f"   {item['url']}",
                flush=True,
            )

    print_header("🏢 COMPANY PRESENCE TEST")

    total_matches = 0

    for company in TEST_COMPANIES:
        matches = company_presence(
            parsed,
            company,
        )

        if matches:
            total_matches += 1
            print(
                f"🟢 {company['symbol']} | "
                f"Matched: {', '.join(matches)}",
                flush=True,
            )
        else:
            print(
                f"⚪ {company['symbol']} | "
                "No company text found in initial HTML",
                flush=True,
            )

    print_header("🏁 RESULT")

    if response.status_code == 200 and announcement_links:
        print(
            "🟢 RESULT: PUBLIC_HTML_USABLE",
            flush=True,
        )
        print(
            "يمكننا تجربة استخراج الإعلانات مباشرة من HTML.",
            flush=True,
        )

    elif response.status_code == 200:
        print(
            "🟡 RESULT: PAGE_ACCESSIBLE_BUT_DATA_DYNAMIC",
            flush=True,
        )
        print(
            "الصفحة متاحة، لكن بيانات الإعلانات نفسها لا تظهر "
            "كروابط واضحة في HTML الأولي.",
            flush=True,
        )
        print(
            "الخطوة التالية ستكون تشخيص طريقة تحميل البيانات "
            "بدون تجاوز أي حماية.",
            flush=True,
        )

    else:
        print(
            "🔴 RESULT: PAGE_NOT_USABLE",
            flush=True,
        )

    print(
        f"\n🏢 Initial HTML company matches: "
        f"{total_matches}/{len(TEST_COMPANIES)}",
        flush=True,
    )

    print("\n📌 IMPORTANT:", flush=True)
    print(
        "- هذا اختبار وصول فقط ولا يحفظ أي بيانات.",
        flush=True,
    )
    print(
        "- لا توجد محاولة لتجاوز CAPTCHA/WAF أو أي حماية.",
        flush=True,
    )
    print(
        "- إذا كانت البيانات Dynamic سنشخص مصدر التحميل "
        "ثم نقرر الاستمرار أو الانتقال لمصدر آخر.",
        flush=True,
    )
    print("=" * 100, flush=True)


if __name__ == "__main__":
    run()
