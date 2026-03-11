"""Parse and process data from the server."""

import random
import time
import re

from bs4 import BeautifulSoup
from requests import Response, get
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from settings import app_settings
from src import strings
from src.schemas import Car

TIME_TO_ENTER_CAPCHA = 3


def get_pages_amount(content: bytes) -> int:
    """Calculate number of pages from pagination links."""
    html_text = content.decode("utf-8", errors="ignore")
    soup = BeautifulSoup(html_text, "html.parser")

    page_links = soup.find_all("a", href=True)
    max_page = 1

    for link in page_links:
        href = link.get("href", "")
        if "/cars/all/engine-electro/" not in href:
            continue

        match = re.search(r"[?&]page=(\d+)", href)
        if match:
            page_num = int(match.group(1))
            if page_num > max_page:
                max_page = page_num

    print(f"Определено страниц в пагинации: {max_page}")
    return max_page


def parse_content(*, content: bytes) -> list[Car]:
    """Parsing page content."""
    cars: list[Car] = []

    html_text = content.decode("utf-8", errors="ignore")
    soup = BeautifulSoup(html_text, "html.parser")

    links = soup.find_all("a", href=True)

    seen = set()

    for link in links:
        href = link.get("href", "").strip()
        if "/cars/used/sale/" not in href:
            continue
        if href in seen:
            continue
        seen.add(href)

        cars.append(
            Car(
                description="",
                url=href,
                price=0,
                year=0,
            )
        )

    print(f"Уникальных ссылок на объявления на странице: {len(cars)}")
    return cars


def get_html(url: str, headers: dict, params: dict | None = None) -> Response:
    """Get the response from the server."""
    try:
        return get(url, headers=headers, params=params)
    except Exception as error:
        raise ConnectionError(f"При выполнении запроса произошла ошибка: {error}")


def get_html_with_selenium(url: str) -> tuple[str | None, str | None]:
    """Get HTML content using Selenium for better anti-bot protection bypass."""
    service = Service()
    options = Options()

    options.add_argument(r"--user-data-dir=C:\temp\auto_ru_selenium_profile")

    if app_settings.USE_SELENIUM_IN_BACKGROUND:
        options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument(f"user-agent={app_settings.HEADERS['user-agent']}")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)

    driver = webdriver.Chrome(service=service, options=options)
    driver.set_window_size(1920, 1080)
    driver.execute_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    )

    try:
        full_url = url
        driver.get(full_url)

        if app_settings.COOKIE:
            for cookie_str in app_settings.COOKIE.split(";"):
                if "=" in cookie_str:
                    name, value = cookie_str.strip().split("=", 1)
                    try:
                        driver.add_cookie(
                            {"name": name, "value": value, "domain": ".auto.ru"}
                        )
                    except Exception:
                        pass

            driver.get(full_url)

        print("Requested URL:", full_url)
        print("Actual URL:", driver.current_url)

        time.sleep(TIME_TO_ENTER_CAPCHA)

        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )

        time.sleep(5)

        driver.execute_script("window.scrollTo(0, document.body.scrollHeight * 0.3);")
        time.sleep(2)

        driver.execute_script("window.scrollTo(0, document.body.scrollHeight * 0.6);")
        time.sleep(2)

        driver.execute_script("window.scrollTo(0, document.body.scrollHeight * 0.9);")
        time.sleep(2)

        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(4)

        print("Final URL:", driver.current_url)
        print("Page title:", driver.title)
        print("Page height:", driver.execute_script("return document.body.scrollHeight"))

        return driver.page_source, driver.current_url

    except Exception as exc:
        print(f"Ошибка при использовании Selenium: {exc}")
        return None, None

    finally:
        try:
            driver.quit()
        except Exception:
            pass


def parse_response(url: str) -> list[Car] | None:
    """Parse the request."""
    url = url or app_settings.URL

    if app_settings.USE_SELENIUM:
        cars = parse_response_with_selenium(url)
    else:
        cars = simple_parse_response(url)

    if not cars:
        return None

    print(f"Получены данные по {len(cars)} авто.")

    return sorted(cars, key=lambda car: int(car.price), reverse=True)


def simple_parse_response(url: str) -> list[Car] | None:
    html = get_html(url, app_settings.HEADERS)
    if html.status_code != 200:
        print(f"Сайт вернул статус-код {html.status_code}")
        return None

    if "captcha" in html.text.lower():
        print(
            "Обнаружена капча! 🤬 \n"
            "Попробуйте обойти капчу и получить данные при помощи Selenium, "
            "для этого нужно запустить парсер с переменной 'USE_SELENIUM=True'. "
        )
        return None

    cars: list[Car] = []
    pages_amount = get_pages_amount(html.content)
    for page in range(1, pages_amount + 1):
        print(f"Парсим {page} страницу из {pages_amount}...")

        html = get_html(url, app_settings.HEADERS, params={"page": page})
        cars.extend(parse_content(content=html.content))

    return cars


def parse_response_with_selenium(url: str) -> list[Car] | None:
    cars: list[Car] = []
    seen_urls = set()

    print(f"\nПарсим страницу 1: {url}")
    first_page_html, first_final_url = get_html_with_selenium(url)

    if not first_page_html:
        print("Не удалось получить первую страницу")
        return None

    if "captcha" in first_page_html.lower():
        print("Обнаружена капча на первой странице!")
        return None

    first_page_bytes = first_page_html.encode("utf-8")
    pages_amount = get_pages_amount(first_page_bytes)

    first_page_cars = parse_content(content=first_page_bytes)
    new_count = 0
    for car in first_page_cars:
        if car.url not in seen_urls:
            seen_urls.add(car.url)
            cars.append(car)
            new_count += 1

    print(f"Новых объявлений на странице 1: {new_count}")
    print(f"Всего уникальных объявлений собрано: {len(cars)}")

    if not first_final_url:
        print("Не удалось определить финальный URL первой страницы")
        return cars if cars else None

    base_url = first_final_url.split("?")[0]
    print(f"Базовый URL для пагинации: {base_url}")

    for page in range(2, pages_amount + 1):
        page_url = f"{base_url}?page={page}"
        print(f"\nПарсим страницу {page}: {page_url}")

        page_html, final_url = get_html_with_selenium(page_url)

        if not page_html:
            print(f"Не удалось получить страницу {page}")
            continue

        if "captcha" in page_html.lower():
            print(f"Обнаружена капча на странице {page}! Пропускаем...")
            continue

        page_html_bytes = page_html.encode("utf-8")
        page_cars = parse_content(content=page_html_bytes)

        new_count = 0
        for car in page_cars:
            if car.url not in seen_urls:
                seen_urls.add(car.url)
                cars.append(car)
                new_count += 1

        print(f"Новых объявлений на странице {page}: {new_count}")
        print(f"Всего уникальных объявлений собрано: {len(cars)}")

        if final_url:
            print(f"Финальный URL страницы {page}: {final_url}")

        sleep_time = random.uniform(3, 7)
        print(f"Ожидание {sleep_time:.2f} секунд перед следующим запросом...")
        time.sleep(sleep_time)

    return cars if cars else None