import json
import re
from typing import List, Tuple, Set, Optional

from bs4 import BeautifulSoup

from goodreads_recommender.logger import Logger
from goodreads_recommender.services.download_service import DownloadService


class Book:
    def __init__(
        self,
        book_id: str,
        download_service: DownloadService,
        logger: Logger,
    ):
        self._download_service = download_service
        self._logger = logger
        self.book_id = book_id

        self._soup = self._get_book_soup(book_id)
        self._stats = self._get_book_stats()
        self._apollo_state = self._stats["props"]["pageProps"]["apolloState"]

    def _get_book_soup(self, book_id: str) -> BeautifulSoup:
        return self._download_service.get(f"book/show/{book_id}")

    def _get_shelves_soup(self, name: str) -> BeautifulSoup:
        return self._download_service.get(f"work/shelves/{name}")

    def _get_editions_soup(self, id: str) -> BeautifulSoup:
        # congratulations. filtering for audiobook does not include audible.
        return self._download_service.get(f"work/editions/{id}?per_page=100")

    def _get_book_stats(self):
        stats_raw = str(self._soup.select("#__NEXT_DATA__")[0].contents[0])
        stats = json.loads(stats_raw)
        return stats

    def get_user_ids_who_liked_book(self, minimum_score=4) -> List[int]:
        """Get the user_ids of those users that left a positive review."""
        user_ids = []
        for key, value in self._apollo_state.items():
            if not key.startswith("Review:"):
                continue

            if value["rating"] < minimum_score:
                continue

            user_ids.append(int(value["creator"]["__ref"].split(":")[-1]))

        return user_ids

    def get_top_shelves_and_their_count(self) -> List[Tuple[str, int]]:
        # I'll only look at the first page of shelves, as they quickly drop in
        # relevance.
        raw = str(self._soup)
        regex_match = re.search(
            r'https://www\.goodreads\.com/work/shelves/(\d+-.+?)"',
            raw,
        )

        if regex_match is None:
            # page broken, link broken, idk
            return []

        shelves_id = regex_match[1]
        shelves_soup = self._get_shelves_soup(shelves_id)
        shelf_stats = shelves_soup.select(".shelfStat")

        name_and_numbers = []

        for shelf_stat in shelf_stats:
            name = shelf_stat.select("a")[0].contents[0].getText()
            content = shelf_stat.select("div:nth-child(2)")[0].contents[0].getText()
            match = re.search(r"(\d+) people", content)
            if match is not None:
                name_and_numbers.append((name, int(match.groups()[0])))

        return name_and_numbers

    def get_num_ratings(self):
        text = (
            self._soup.select('span[data-testid="ratingsCount"]')[0]
            .contents[0]
            .getText()
        )

        # turn 12,345 to 12345
        return int(text.replace(",", ""))

    def does_audiobook_exist(self) -> bool:
        if "shelf=audiobook" in str(self._soup):
            # This doesn't always work. But it can be used to avoid handling
            # the editions page for performance. And also, turns out the editions
            # aren't always complete, So this check is pretty important
            return True

        genres = self.get_genres()
        if "audible" in genres or "audiobook" in genres:
            return True

        # have to download and parse the editions then

        # get the editions-id
        apollo_state: dict = self._apollo_state
        for state in apollo_state.values():
            if "editions" in state:
                editions_id = state["editions"]["webUrl"].split("/")[-1]
                break
        else:
            # somehow the editions-id is missing...
            self._logger.log("Failed to find editions-id")
            return False

        editions_soup = self._get_editions_soup(editions_id)

        # there are false-positives when just searching for "audible", hardcoded in
        # a html dropdown form or something.
        # Multiple valid strings indicate audiobooks.
        stringified = str(editions_soup)
        return (
            "Audible Studios" in stringified
            # the comma is important! Otherwise false positives
            or "Audio CD," in stringified
            or "Audiobook," in stringified
            or "Audible Audio," in stringified
            or "Unabridged" in stringified
        )

    def get_genres(self) -> List[str]:
        """Get a list of genres like science-fiction-fantasy, possibly containing
        duplicates."""
        # they aren't complete in the html, have to check the json metadata
        apollo_state: dict = self._apollo_state

        key: dict
        genres = []
        for apollo_state_element in apollo_state.values():
            if "bookGenres" in apollo_state_element:
                genres += apollo_state_element["bookGenres"]

        # For example science-fiction-fantasy
        # This is not a set, because genres are sorted by how often they have been
        # shelved or something. A set would lose that information.
        return [
            genre["genre"]["webUrl"].replace("https://www.goodreads.com/genres/", "")
            for genre in genres
        ]

    def get_author(self) -> Optional[str]:
        stats = self._get_book_stats()

        apollo_state: dict = stats["props"]["pageProps"]["apolloState"]

        for apollo_state_element in apollo_state.values():
            if apollo_state_element["__typename"] == "Contributor":
                # for example 17650479.Becky_Chambers
                return apollo_state_element["webUrl"].split("/")[-1]

        return None

    def get_year(self) -> int:
        # <p data-testid="publicationInfo">First published June 1, 2002</p>
        return int(
            self._soup.select('p[data-testid="publicationInfo"]')[0]
            .contents[0]
            .getText()
            .split()[-1]
        )

    def get_rating(self) -> float:
        rating_div = self._soup.select(".RatingStatistics__rating")
        if len(rating_div) == 0:
            # page broken
            # "This item does not meet our catalog guidelines and can no longer be rated or reviewed."
            return 0.0

        return float(
            self._soup.select(".RatingStatistics__rating")[0].contents[0].getText()
        )

    def get_series(self) -> Optional[str]:
        stats = self._get_book_stats()

        apollo_state: dict = stats["props"]["pageProps"]["apolloState"]

        for apollo_state_element in apollo_state.values():
            if apollo_state_element["__typename"] == "Series":
                # for example 170872-wayfarers
                return apollo_state_element["webUrl"].split("/")[-1]

        return None

    def get_series_book_ids(self) -> Set[str]:
        series_id = self.get_series()

        if series_id is None:
            return set()

        soup = self._download_service.get(f"series/{series_id}")

        edition_ids = set()

        rows = soup.select(".listWithDividers__item")
        for row in rows:
            title = str(row.select("h3")[0].contents[0].text)
            if re.match(r"^Book \d(.\d)?$", title):
                # Match "Book 1" "Book 2" "Book 1.5" but not all the other odd stuff.
                # Things like "Book 1-3" or "Book 4 Part 4 of 4" should be excluded
                edition_ids.add(row.select('a[href*="/book/show/"]')[0].attrs["href"])

        return edition_ids

    def get_genres_and_shelves(self) -> List[str]:
        return [
            *[shelf[0] for shelf in self.get_top_shelves_and_their_count()],
            *self.get_genres(),
        ]
