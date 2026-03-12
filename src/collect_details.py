import csv
import re
import time
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


OUTPUT_FILE = Path("data/electro_cars_details.csv")


def get_driver() -> webdriver.Chrome:
    service = Service()
    options = Options()

    options.add_argument(r"--user-data-dir=C:\temp\auto_ru_selenium_profile")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)

    driver = webdriver.Chrome(service=service, options=options)
    driver.set_window_size(1920, 1080)
    driver.execute_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    )
    return driver


def safe_find_text(driver: webdriver.Chrome, by: By, value: str) -> str:
    try:
        return driver.find_element(by, value).text.replace("\xa0", " ").strip()
    except Exception:
        return ""


def safe_find_text_from_element(element, by: By, value: str) -> str:
    try:
        return element.find_element(by, value).text.replace("\xa0", " ").strip()
    except Exception:
        return ""


def extract_year_from_title(title: str) -> str:
    match = re.search(r"\b(20\d{2}|19\d{2})\b", title)
    return match.group(1) if match else ""


def extract_price(driver: webdriver.Chrome) -> str:
    try:
        return driver.find_element(
            By.CSS_SELECTOR,
            "span.OfferPriceCaption__price"
        ).text.replace("\xa0", " ").replace("₽", "").strip()
    except Exception:
        return ""


def extract_brand(driver: webdriver.Chrome) -> str:
    try:
        breadcrumbs = driver.find_elements(By.CSS_SELECTOR, "a.CardBreadcrumbs__itemText")
        for item in breadcrumbs:
            href = item.get_attribute("href") or ""
            text = item.text.replace("\xa0", " ").strip()
            if "/cars/" in href and "/used/" in href and text and text not in {
                "Продажа автомобилей",
                "С пробегом",
            }:
                return text
    except Exception:
        pass
    return ""


def extract_region(driver: webdriver.Chrome) -> str:
    try:
        return driver.find_element(
            By.CSS_SELECTOR,
            "span.MetroListPlace__regionName"
        ).text.replace("\xa0", " ").strip()
    except Exception:
        return ""


def extract_ownership_info(driver: webdriver.Chrome) -> dict[str, str]:
    data = {}

    try:
        rows = driver.find_elements(
            By.CSS_SELECTOR,
            "li.CardInfoSummarySimpleRow-CY5TE"
        )

        for row in rows:
            try:
                label = row.find_element(
                    By.CSS_SELECTOR,
                    ".CardInfoSummarySimpleRow__label-uJbU8"
                ).text.replace("\xa0", " ").strip()

                value = row.find_element(
                    By.CSS_SELECTOR,
                    ".CardInfoSummarySimpleRow__content-IIKcj"
                ).text.replace("\xa0", " ").strip()

                if label and value:
                    data[f"Владение__{label}"] = value
            except Exception:
                continue

    except Exception:
        pass

    return data


def open_characteristics(driver: webdriver.Chrome) -> bool:
    wait = WebDriverWait(driver, 10)

    try:
        button = wait.until(
            EC.element_to_be_clickable(
                (By.CSS_SELECTOR, "button.CardOfferBody__catalogLink-Je2aE")
            )
        )

        driver.execute_script(
            "arguments[0].scrollIntoView({block: 'center'});", button
        )
        time.sleep(0.5)
        driver.execute_script("arguments[0].click();", button)

        wait.until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, "div.ModificationInfo-iyGE4")
            )
        )
        time.sleep(0.8)
        return True

    except Exception as exc:
        print(f"Не удалось открыть модалку характеристик: {exc}")
        return False


def extract_modal_characteristics(driver: webdriver.Chrome) -> dict[str, str]:
    wait = WebDriverWait(driver, 10)
    data = {}

    try:
        wait.until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, "div.ModificationInfo-iyGE4")
            )
        )
        time.sleep(0.5)
    except Exception as exc:
        print(f"Блок характеристик не появился: {exc}")
        return data

    groups = driver.find_elements(By.CSS_SELECTOR, "div.ModificationInfo__group-RYeJn")

    for group in groups:
        try:
            group_name = group.find_element(
                By.CSS_SELECTOR, "h3.ModificationInfo__groupName-Egj4Q"
            ).text.replace("\xa0", " ").strip()

            options = group.find_elements(
                By.CSS_SELECTOR, "li.ModificationInfo__option-hNkzE"
            )

            for option in options:
                spans = option.find_elements(By.TAG_NAME, "span")
                if len(spans) < 2:
                    continue

                key = spans[0].text.replace("\xa0", " ").strip()
                value = spans[1].text.replace("\xa0", " ").strip()

                if key and value:
                    data[f"{group_name}__{key}"] = value

        except Exception:
            continue

    return data


def parse_one_offer(driver: webdriver.Chrome, url: str) -> dict[str, str]:
    print(f"\nОткрываем: {url}")
    driver.get(url)

    WebDriverWait(driver, 20).until(
        EC.presence_of_element_located((By.TAG_NAME, "body"))
    )
    time.sleep(2)

    title = safe_find_text(driver, By.CSS_SELECTOR, "h1.CardHead__title")
    price = extract_price(driver)
    brand = extract_brand(driver)
    region = extract_region(driver)

    row = {
        "url": url,
        "brand": brand,
        "region": region,
        "title": title,
        "price": price,
    }

    ownership_info = extract_ownership_info(driver)
    row.update(ownership_info)

    if "Владение__Год выпуска" not in row or not row["Владение__Год выпуска"]:
        row["Владение__Год выпуска"] = extract_year_from_title(title)

    opened = open_characteristics(driver)
    print(f"Модалка открыта: {opened}")

    if opened:
        specs = extract_modal_characteristics(driver)
        row.update(specs)
        print(f"Собрано характеристик: {len(specs)}")
    else:
        print("Характеристики не собраны")

    return row


def parse_links_to_details(links: list[str]) -> list[dict[str, str]]:
    driver = get_driver()
    rows = []

    try:
        for i, url in enumerate(links, start=1):
            print(f"\n===== {i}/{len(links)} =====")
            try:
                row = parse_one_offer(driver, url)
                rows.append(row)
            except Exception as exc:
                print(f"Ошибка на объявлении {url}: {exc}")

            time.sleep(2)

    finally:
        driver.quit()

    return rows


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