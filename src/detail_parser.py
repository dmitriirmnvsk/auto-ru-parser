import time
from bs4 import BeautifulSoup

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


TEST_URL = "https://auto.ru/cars/used/sale/xiaomi/su7/1131262957-65c74a09/"


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
        time.sleep(1)
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
        time.sleep(1)
    except Exception as exc:
        print(f"Блок характеристик не появился: {exc}")
        return data

    groups = driver.find_elements(By.CSS_SELECTOR, "div.ModificationInfo__group-RYeJn")
    print(f"Найдено групп характеристик: {len(groups)}")

    for group in groups:
        try:
            group_name = group.find_element(
                By.CSS_SELECTOR, "h3.ModificationInfo__groupName-Egj4Q"
            ).text.strip()

            options = group.find_elements(
                By.CSS_SELECTOR, "li.ModificationInfo__option-hNkzE"
            )

            print(f"Группа '{group_name}', строк: {len(options)}")

            for option in options:
                spans = option.find_elements(By.TAG_NAME, "span")
                if len(spans) < 2:
                    continue

                key = spans[0].text.replace("\xa0", " ").strip()
                value = spans[1].text.replace("\xa0", " ").strip()

                if key and value:
                    full_key = f"{group_name}__{key}"
                    data[full_key] = value

        except Exception as exc:
            print(f"Ошибка при разборе группы: {exc}")
            continue

    return data


def main() -> None:
    driver = get_driver()

    try:
        print("Open:", TEST_URL)
        driver.get(TEST_URL)

        WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
        time.sleep(5)

        opened = open_characteristics(driver)
        print("Modal opened:", opened)

        data = extract_modal_characteristics(driver)

        print("\nВсе характеристики из модалки:\n")
        for k, v in data.items():
            print(f"{k}: {v}")

        print(f"\nВсего полей: {len(data)}")

    finally:
        driver.quit()


if __name__ == "__main__":
    main()