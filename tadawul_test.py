import requests
import pandas as pd
from io import StringIO


URL = (
    "https://www.saudiexchange.sa/wps/portal/saudiexchange/"
    "newsandreports/issuer-news/issuer-announcements/"
    "issuer-announcements-details/"
    "?anCat=1&anId=97053&cs=2283&locale=en"
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


def test_tadawul():

    print("=" * 70)
    print("TEST: Saudi Exchange - First Mills 2283")
    print("=" * 70)

    response = requests.get(
        URL,
        headers=HEADERS,
        timeout=30
    )

    print(f"HTTP Status: {response.status_code}")

    response.raise_for_status()

    print(
        f"Downloaded HTML: {len(response.text):,} characters"
    )

    tables = pd.read_html(
        StringIO(response.text)
    )

    print(
        f"Tables found: {len(tables)}"
    )

    found_financial_table = False

    for index, table in enumerate(tables):

        columns_text = " ".join(
            str(column)
            for column in table.columns
        ).lower()

        table_text = table.to_string().lower()

        if (
            "current quarter" in columns_text
            or "sales/revenue" in table_text
            or "gross profit" in table_text
        ):

            found_financial_table = True

            print("\n" + "=" * 70)
            print(
                f"FINANCIAL TABLE FOUND #{index}"
            )
            print("=" * 70)

            print(
                table.to_string(index=False)
            )

    if found_financial_table:

        print("\n✅ SUCCESS")
        print(
            "Quarterly financial data was read directly "
            "from Saudi Exchange."
        )

    else:

        print("\n⚠️ NO FINANCIAL TABLE FOUND")


if __name__ == "__main__":
    test_tadawul()
