import traceback
from typing import List, Tuple, Set, NamedTuple, Optional, Iterable

from goodreads_recommender.entities.book import Book
from goodreads_recommender.logger import Logger
from goodreads_recommender.services.config_service import ConfigService
from goodreads_recommender.services.download_service import DownloadService


class Report(NamedTuple):
    author: str
    series: str
    book_id: str
    rating: float
    year: int
    formatted_report_shelves: str
    series_length: int


class ReportService:
    """Write the report for recommendations to a file."""

    column_size = 50

    def __init__(
        self,
        config_service: ConfigService,
        download_service: DownloadService,
        logger: Logger,
        report_shelves: Optional[Set[str]] = None,
    ):
        """
        report_shelves:
            Which shelves to show in the output of this tool, to get a sense about what
            kind of book is listed.
        """
        self.config_service = config_service
        self.download_service = download_service
        self.report_shelves = report_shelves
        self.logger = logger

    def create_report(self, book: Book) -> Report:
        series_book_ids = book.get_series_book_ids()

        author = book.get_author() or "unknown"

        # not having this None is important for sorting later on. Because you can't
        # compare non with str. whatever. this code is relatively bad, but good enough
        series = book.get_series() or ""

        year = book.get_year()

        rating = book.get_rating()

        if self.report_shelves is not None:
            report_shelves_with_count = self._get_report_shelves_with_count(book)
            formatted_report_shelves = ", ".join(
                [f"{topic} {count}" for topic, count in report_shelves_with_count]
            )
        else:
            formatted_report_shelves = ", ".join(book.get_genres())

        report = Report(
            author=author,
            series=series,
            book_id=book.book_id,
            rating=rating,
            year=year,
            formatted_report_shelves=formatted_report_shelves,
            series_length=len(series_book_ids),
        )

        # This will be sorted and written to the report file later on
        self.logger.log(self.format_report(report))

        return report

    def _get_report_shelves_with_count(self, book: Book) -> List[Tuple[str, int]]:
        """topics = genres and shelves.
        Check if any of those of the book are in my report_shelves list."""
        if self.report_shelves is None:
            return []

        # shelves are all over the place. but there can be some that are interesting
        # to know. I'll use them to get some categorization in the log output.

        important_topics_of_book = book.get_top_shelves_and_their_count()

        intersection = [
            topic
            for topic in important_topics_of_book
            if topic[0] in self.report_shelves
        ]

        return intersection

    def append_books_to_file(
        self,
        name: str,
        book_ids: Iterable[str],
        sort=True,
    ):
        reports = []
        for book_id in book_ids:
            book = Book(
                book_id,
                self.download_service,
                self.logger,
            )
            try:
                report = self.create_report(book)
                reports.append(report)
            except Exception as e:
                traceback.print_exc()
                self.logger.log(f"Failed to generate report for {book_id}")

        self.append_reports_to_file(
            name,
            reports,
            sort,
        )

    def append_reports_to_file(
        self,
        section_header,
        reports: List[Report],
        sort=True,
    ):
        # Finally, create another dump, this time sorted
        if self.config_service.output_file is None:
            return

        with open(self.config_service.output_file, "a") as file:
            file.write(f"# {section_header}\n")
            # I think this should sort by the first element (author) first,
            # then the second element (series)
            sorted_reports = sorted(reports) if sort else reports

            for report in sorted_reports:
                file.write(self.format_report(report))
                file.write("\n")

            file.write("\n")

    def format_report(self, report: Report):
        """Format the book-info from handle_book into a neat human-readable string."""
        series_formatted = (
            f"{report.series} ({report.series_length})" if report.series != "" else ""
        )

        return (
            (
                (report.author.ljust(self.column_size) + series_formatted).ljust(
                    self.column_size * 2
                )
                + report.book_id[: self.column_size - 1]
            ).ljust(self.column_size * 3)
            + str(report.year).ljust(8)
            + str(report.rating).ljust(8)
            + report.formatted_report_shelves
        )
