import csv
import json
import re
import time
from pathlib import Path

from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


OUTPUT_FILE = Path("data/electro_cars_details.csv")
PROGRESS_FILE = Path("data/electro_cars_details_progress.json")
SAVE_EVERY = 10


def get_driver() -> webdriver.Chrome:
    service = Service()
    options = Options()

    options.add_argument(r"--user-data-dir=C:\temp\auto_ru_selenium_profile")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)

    prefs = {
        "profile.managed_default_content_settings.images": 2,
        "profile.default_content_setting_values.notifications": 2,
    }
    options.add_experimental_option("prefs", prefs)

    driver = webdriver.Chrome(service=service, options=options)
    driver.set_window_size(1920, 1080)
    driver.execute_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    )
    return driver


def normalize_text(text: str) -> str:
    return text.replace("\xa0", " ").strip() if text else ""


def safe_find_text(driver: webdriver.Chrome, by: By, value: str) -> str:
    try:
        return normalize_text(driver.find_element(by, value).text)
    except Exception:
        return ""


def extract_year_from_title(title: str) -> str:
    match = re.search(r"\b(20\d{2}|19\d{2})\b", title)
    return match.group(1) if match else ""


def extract_price_bs(soup: BeautifulSoup) -> str:
    node = soup.select_one("span.OfferPriceCaption__price")
    if not node:
        return ""
    return normalize_text(node.get_text()).replace("₽", "").strip()


def extract_brand_bs(soup: BeautifulSoup) -> str:
    items = soup.select("a.CardBreadcrumbs__itemText")
    for item in items:
        href = item.get("href", "") or ""
        text = normalize_text(item.get_text())
        if "/cars/" in href and "/used/" in href and text not in {
            "Продажа автомобилей",
            "С пробегом",
        }:
            return text
    return ""


def extract_region_bs(soup: BeautifulSoup) -> str:
    node = soup.select_one("span.MetroListPlace__regionName")
    if node:
        return normalize_text(node.get_text())
    return ""


def extract_title_bs(soup: BeautifulSoup) -> str:
    node = soup.select_one("h1.CardHead__title")
    return normalize_text(node.get_text()) if node else ""


def extract_ownership_info_bs(soup: BeautifulSoup) -> dict[str, str]:
    data = {}
    rows = soup.select("li.CardInfoSummarySimpleRow-CY5TE")

    for row in rows:
        label_node = row.select_one(".CardInfoSummarySimpleRow__label-uJbU8")
        value_node = row.select_one(".CardInfoSummarySimpleRow__content-IIKcj")

        label = normalize_text(label_node.get_text()) if label_node else ""
        value = normalize_text(value_node.get_text()) if value_node else ""

        if label and value:
            data[f"Владение__{label}"] = value

    return data


def extract_modal_characteristics_from_soup(soup: BeautifulSoup) -> dict[str, str]:
    data = {}
    groups = soup.select("div.ModificationInfo__group-RYeJn")

    for group in groups:
        group_name_node = group.select_one("h3.ModificationInfo__groupName-Egj4Q")
        group_name = normalize_text(group_name_node.get_text()) if group_name_node else ""
        if not group_name:
            continue

        options = group.select("li.ModificationInfo__option-hNkzE")
        for option in options:
            spans = option.find_all("span")
            if len(spans) < 2:
                continue

            key = normalize_text(spans[0].get_text())
            value = normalize_text(spans[1].get_text())

            if key and value:
                data[f"{group_name}__{key}"] = value

    return data


def open_characteristics(driver: webdriver.Chrome) -> bool:
    wait = WebDriverWait(driver, 4)

    try:
        button = wait.until(
            EC.element_to_be_clickable(
                (By.CSS_SELECTOR, "button.CardOfferBody__catalogLink-Je2aE")
            )
        )
        driver.execute_script("arguments[0].click();", button)

        wait.until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, "div.ModificationInfo__group-RYeJn")
            )
        )
        time.sleep(0.1)
        return True

    except Exception as exc:
        print(f"Не удалось открыть модалку характеристик: {exc}")
        return False


def parse_one_offer(driver: webdriver.Chrome, url: str) -> dict[str, str]:
    print(f"\nОткрываем: {url}")
    driver.get(url)

    WebDriverWait(driver, 8).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "h1.CardHead__title"))
    )
    time.sleep(0.15)

    html = driver.page_source
    soup = BeautifulSoup(html, "html.parser")

    title = extract_title_bs(soup)
    price = extract_price_bs(soup)
    brand = extract_brand_bs(soup)
    region = extract_region_bs(soup)

    row = {
        "url": url,
        "brand": brand,
        "region": region,
        "title": title,
        "price": price,
    }

    ownership_info = extract_ownership_info_bs(soup)
    row.update(ownership_info)

    if "Владение__Год выпуска" not in row or not row["Владение__Год выпуска"]:
        row["Владение__Год выпуска"] = extract_year_from_title(title)

    specs = extract_modal_characteristics_from_soup(soup)

    if specs:
        print(f"Характеристики найдены без открытия модалки: {len(specs)}")
        row.update(specs)
        return row

    opened = open_characteristics(driver)
    print(f"Модалка открыта: {opened}")

    if opened:
        html = driver.page_source
        soup = BeautifulSoup(html, "html.parser")
        specs = extract_modal_characteristics_from_soup(soup)
        row.update(specs)
        print(f"Собрано характеристик: {len(specs)}")
    else:
        print("Характеристики не собраны")

    return row


def save_progress(processed_urls: set[str], path: Path = PROGRESS_FILE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"processed_urls": sorted(processed_urls)}, f, ensure_ascii=False, indent=2)


def load_progress(path: Path = PROGRESS_FILE) -> set[str]:
    if not path.exists():
        return set()

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return set(data.get("processed_urls", []))
    except Exception:
        return set()


def save_to_csv(rows: list[dict[str, str]], path: Path = OUTPUT_FILE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    all_fields = set()
    for row in rows:
        all_fields.update(row.keys())

    preferred = ["url", "brand", "region", "title", "price"]
    other_fields = sorted([f for f in all_fields if f not in preferred])
    fieldnames = preferred + other_fields

    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def load_existing_rows(path: Path = OUTPUT_FILE) -> list[dict[str, str]]:
    if not path.exists():
        return []

    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def parse_links_to_details(links: list[str]) -> list[dict[str, str]]:
    processed_urls = load_progress()
    existing_rows = load_existing_rows()
    rows = existing_rows.copy()

    remaining_links = [url for url in links if url not in processed_urls]
    print(f"Уже обработано: {len(processed_urls)}")
    print(f"Осталось обработать: {len(remaining_links)}")

    driver = get_driver()

    try:
        for i, url in enumerate(remaining_links, start=1):
            print(f"\n===== {i}/{len(remaining_links)} =====")
            try:
                row = parse_one_offer(driver, url)
                rows.append(row)
                processed_urls.add(url)
            except Exception as exc:
                print(f"Ошибка на объявлении {url}: {exc}")

            if i % SAVE_EVERY == 0:
                save_to_csv(rows)
                save_progress(processed_urls)
                print(f"Промежуточно сохранено после {i} новых объявлений")

            time.sleep(0.1)

    finally:
        driver.quit()

    save_to_csv(rows)
    save_progress(processed_urls)
    return rows


if __name__ == "__main__":
    links_file = Path("data/links.txt")

    if not links_file.exists():
        print(f"Файл со ссылками не найден: {links_file}")
    else:
        with open(links_file, "r", encoding="utf-8") as f:
            links = [line.strip() for line in f if line.strip()]

        print(f"Ссылок к обработке: {len(links)}")
        rows = parse_links_to_details(links)
        save_to_csv(rows)
        print("Готово. Детали сохранены в CSV.")