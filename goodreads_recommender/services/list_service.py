import os
import traceback
from typing import Optional, Set, Callable, Iterable

from bs4 import BeautifulSoup
from requests import HTTPError

from goodreads_recommender.entities.book import Book
from goodreads_recommender.logger import Logger
from goodreads_recommender.services.config_service import ConfigService
from goodreads_recommender.services.download_service import DownloadService
from goodreads_recommender.services.report_service import ReportService, Report

BookFilter = Callable[[Book, Logger], bool]


class ListService:
    """A service to filter many books at once."""

    def __init__(
        self,
        config_service: ConfigService,
        download_service: DownloadService,
        report_service: ReportService,
        logger: Logger,
        book_filter: BookFilter,
    ):
        self.config_service = config_service
        self.download_service = download_service
        self.report_service = report_service
        self.logger = logger
        self.book_filter = book_filter

    def scan_books(
        self,
        name: str,
        list_ids: Optional[Iterable[str]] = None,
        shelf_ids: Optional[Iterable[str]] = None,
        book_ids: Optional[Iterable[str]] = None,
    ):
        """Check a few books of those lists, and write the result to the output file."""
        reports = []

        self.logger.verbose(f"# {name}")

        book_ids_from_all_sources: Set[str] = set()

        if book_ids is not None:
            book_ids_from_all_sources.update(book_ids)

        for list_id in list_ids or []:
            book_ids_from_all_sources = book_ids_from_all_sources.union(
                self._get_book_ids_in_list(list_id)
            )

        for shelf_id in shelf_ids or []:
            book_ids_from_all_sources = book_ids_from_all_sources.union(
                self._get_book_ids_in_shelf(shelf_id)
            )

        for book_id in book_ids_from_all_sources:
            try:
                report = self._analyze_book(book_id)
                if report is not None:
                    reports.append(report)
            except HTTPError:
                self.logger.log("Failed to download data for", book_id)
            except Exception as e:
                self.logger.log(book_id, "Failed due to a bug")
                traceback.print_exc()

        self.report_service.append_reports_to_file(name, reports)

        return reports

    def _get_list_soup(self, name: str, page: int) -> BeautifulSoup:
        return self.download_service.get(f"list/show/{name}?page={str(page)}")

    def _get_shelf_soup(self, name: str) -> BeautifulSoup:
        return self.download_service.get(f"shelf/show/{name}")

    def _get_book_ids_in_list(self, name: str) -> set[str]:
        # try to download the first n pages each. eventually, pages will be empty,
        # but this script doesn't check for the highest page yet.
        result = set()
        for page in range(1, 5):
            list_page = self._get_list_soup(name, page)
            hrefs = [a.get("href") for a in list_page.select('a[href*="/book/show/"]')]
            result.update(
                set([os.path.basename(href) for href in hrefs if isinstance(href, str)])
            )

        return result

    def _get_book_ids_in_shelf(self, name: str) -> set[str]:
        shelf_page = self._get_shelf_soup(name)
        hrefs = [a.get("href") for a in shelf_page.select('a[href*="/book/show/"]')]
        return set([os.path.basename(href) for href in hrefs if isinstance(href, str)])

    def _analyze_book(self, book_id) -> Optional[Report]:
        """Check if the book is interesting. If not, return None."""
        self.logger.verbose(f'Analyzing "{book_id}"')

        book = Book(
            book_id,
            self.download_service,
            self.logger,
        )

        if not self.book_filter(book, self.logger):
            return None

        return self.report_service.create_report(book)
