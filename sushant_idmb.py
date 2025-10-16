import os
import re
import time
import json
import pandas as pd
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

def download_poster(poster_url, title):
    if not poster_url:
        return None
    os.makedirs("posters_show", exist_ok=True)
    safe_title = re.sub(r"[^a-zA-Z0-9]", "_", title or "poster")
    filename = os.path.join("posters_show", f"{safe_title}.jpg")
    try:
        r = requests.get(poster_url, timeout=10)
        if r.status_code == 200:
            with open(filename, "wb") as f:
                f.write(r.content)
            return filename
    except Exception as e:
        print(f"[!] Poster download failed for {title}: {e}")
    return None

def parse_imdb(soup):
    movies = []
    movie_blocks = soup.find_all("div", class_=re.compile(r"cli-parent"))

    for block in movie_blocks:
        movie = {
            "imdb_id": None,
            "title": None,
            "url": None,
            "release_year": None,
            "duration": None,
            "certificate": None,
            "rating": None,
            "genres": [],
            "cast": [],
            "poster": None
        }
        title_link = block.find("a", class_=re.compile("ipc-title-link-wrapper"), href=re.compile(r"/title/tt\d+"))
        if title_link:
            href = title_link.get("href")
            match = re.search(r"/title/(tt\d+)", href)
            if match:
                movie["imdb_id"] = match.group(1)
                movie["url"] = urljoin("https://www.imdb.com", f"/title/{movie['imdb_id']}")
            title_tag = title_link.find("h3", class_=re.compile("ipc-title__text"))
            if title_tag:
                movie["title"] = title_tag.get_text(strip=True)
        print("Fetching details of: ",movie["title"])
        meta_div = block.find("div", class_=re.compile("cli-title-metadata"))
        if meta_div:
            meta_spans = meta_div.find_all("span", class_=re.compile("cli-title-metadata-item"))
            if len(meta_spans) > 0:
                movie["release_year"] = meta_spans[0].get_text(strip=True)
            if len(meta_spans) > 1:
                movie["duration"] = meta_spans[1].get_text(strip=True)
            if len(meta_spans) > 2:
                movie["certificate"] = meta_spans[2].get_text(strip=True)

        rating_div = block.find("div", attrs={"data-testid": "ratingGroup--container"})
        if rating_div:
            rating_value = rating_div.find("span")
            if rating_value:
                movie["rating"] = rating_value.get_text(strip=True)

        poster_div = block.find("div", class_=re.compile("cli-poster-container"))
        if poster_div:
            img = poster_div.find("img")
            if img:
                poster_url = img.get("src") or img.get("data-src")
                try:
                    movie["poster"] = download_poster(poster_url, movie["title"] or movie["imdb_id"])
                except Exception:
                    movie["poster"] = poster_url

        if movie["imdb_id"]:
            try:
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
                    "Accept-Language": "en-US,en;q=0.9",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8"
                }

                details_url = f"https://www.imdb.com/title/{movie['imdb_id']}/"
                details_res = requests.get(details_url, headers=headers, timeout=10)
                details_res.raise_for_status()
                details_soup = BeautifulSoup(details_res.text, "html.parser")

                genre_container = details_soup.find("div", class_=re.compile(r"ipc-chip-list--baseAlt"))
                if not genre_container:
                    genre_container = details_soup.find("div", attrs={"data-testid": "genres"})
                
                if genre_container:
                    genre_links = genre_container.find_all("a", class_=re.compile(r"ipc-chip"))
                    for genre_link in genre_links:
                        genre_span = genre_link.find("span", class_=re.compile(r"ipc-chip__text"))
                        if genre_span:
                            genre_text = genre_span.get_text(strip=True)
                            if genre_text and genre_text not in movie["genres"]:
                                movie["genres"].append(genre_text)

                cast_url = f"https://www.imdb.com/title/{movie['imdb_id']}/fullcredits"
                cast_res = requests.get(cast_url, headers=headers, timeout=10)
                cast_res.raise_for_status()
                cast_soup = BeautifulSoup(cast_res.text, "html.parser")
                cast_table = cast_soup.find("table", class_="cast_list")
                if cast_table:
                    cast_rows = cast_table.find_all("tr", class_=re.compile(r"odd|even"))
                    for row in cast_rows:
                        cells = row.find_all("td")
                        if len(cells) >= 2:
                            actor_cell = cells[1]
                            actor_link = actor_cell.find("a", href=re.compile(r"/name/nm\d+"))
                            if actor_link:
                                actor_name = actor_link.get_text(strip=True)
                                if actor_name and actor_name not in movie["cast"]:
                                    movie["cast"].append(actor_name)
                                    if len(movie["cast"]) >= 10:
                                        break

                if not movie["cast"]:
                    cast_links = cast_soup.find_all("a", href=re.compile(r"/name/nm\d+"))
                    seen_names = set()
                    for link in cast_links:
                        name = link.get_text(strip=True)
                        if name and name not in seen_names and len(name) > 1:
                            seen_names.add(name)
                            movie["cast"].append(name)
                            if len(movie["cast"]) >= 10:
                                break

            except requests.RequestException as e:
                print(f"Network error fetching details for {movie['imdb_id']}: {e}")
            except Exception as e:
                print(f"Failed to fetch details for {movie['imdb_id']}: {e}")
        movies.append(movie)
        time.sleep(1)

    return movies

def main():
    url = input("Enter IMDb trending URL: ").strip()
    #popular movies url: https://www.imdb.com/chart/moviemeter/?ref_=hm_nv_menu
    #popular shows url: https://www.imdb.com/chart/tvmeter/?ref_=chtmvm_nv_menu
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()))
    driver.get(url)
    time.sleep(5)
    soup = BeautifulSoup(driver.page_source, "lxml")
    driver.quit()

    if "imdb.com" in url:
        items = parse_imdb(soup)
    else:
        print("Unsupported site.")
        return

    if not items:
        print("No results found.")
        return

    os.makedirs("output", exist_ok=True)
    csv_path = os.path.join("output", "trending_data_show.csv")
    json_path = os.path.join("output", "trending_data_show.json")

    pd.DataFrame(items).to_csv(csv_path, index=False)
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(items, f, indent=4, ensure_ascii=False)

    print(f"Saved {len(items)} items to:\n→ {csv_path}\n→ {json_path}")
    print("Posters saved in the 'posters/' folder.")

if __name__ == "__main__":
    main()