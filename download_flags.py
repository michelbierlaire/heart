from pathlib import Path
import urllib.request
import yaml

COUNTRIES_FILE = Path("data/countries.yml")
OUTPUT_DIR = Path("assets/flags/svg")

FLAG_ICONS_BASE_URL = (
    "https://raw.githubusercontent.com/lipis/flag-icons/main/flags/4x3"
)

CUSTOM_CODES = {"EU", "INTL"}


def download_flag(iso2: str) -> None:
    iso2 = iso2.upper()
    output_file = OUTPUT_DIR / f"{iso2}.svg"

    if output_file.exists():
        print(f"Already exists: {output_file}")
        return

    if iso2 in CUSTOM_CODES:
        print(f"Custom flag needed, skipped: {iso2}")
        return

    url = f"{FLAG_ICONS_BASE_URL}/{iso2.lower()}.svg"

    try:
        urllib.request.urlretrieve(url, output_file)
        print(f"Downloaded: {iso2}")
    except Exception as error:
        print(f"Could not download {iso2}: {error}")


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    with COUNTRIES_FILE.open("r", encoding="utf-8") as file:
        countries = yaml.safe_load(file)

    for country in countries:
        iso2 = country["iso2"]
        download_flag(iso2)


if __name__ == "__main__":
    main()