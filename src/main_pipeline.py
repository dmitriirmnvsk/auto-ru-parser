from settings import app_settings
from src.parser import parse_response
from src.collect_details import parse_links_to_details, save_to_csv


def main() -> None:
    url = input("Please enter a URL to parse: ").strip() or app_settings.URL

    cars = parse_response(url)
    if not cars:
        print("Не удалось собрать ссылки.")
        return

    links = [car.url for car in cars if car.url]
    print(f"Собрано ссылок: {len(links)}")

    rows = parse_links_to_details(links)
    if not rows:
        print("Не удалось собрать детали объявлений.")
        return

    save_to_csv(rows)
    print("Готово. Итоговый CSV сохранён.")


if __name__ == "__main__":
    main()