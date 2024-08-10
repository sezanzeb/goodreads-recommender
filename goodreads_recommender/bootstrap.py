from typing import Optional, Set

from goodreads_recommender.logger import Logger
from goodreads_recommender.services.config_service import ConfigService
from goodreads_recommender.services.download_service import DownloadService
from goodreads_recommender.services.list_service import ListService, BookFilter
from goodreads_recommender.services.recommendation_engine import RecommendationEngine
from goodreads_recommender.services.report_service import ReportService


def bootstrap_list_service(
    book_filter: BookFilter,
    output_file: Optional[str] = None,
    verbose: bool = False,
    parse_args: bool = False,
    report_shelves: Optional[Set[str]] = None,
) -> ListService:
    """
    book_filter: for example the `strict_filter`

    parse_args: Instead of using the passed output_file and verbosity setting, parse
    them from the command-line. Use `--help` when calling your script to get help.

    report_shelves: A set of shelves that you want to see in the generated output for
    each book. Helps to understand what kind of book that is. By default uses the
    genres of each book. For example { "slice-of-life", "friendship" }
    """
    config_service = ConfigService(
        output_file=output_file,
        verbose=verbose,
        parse_args=parse_args,
    )
    logger = Logger(config_service)
    download_service = DownloadService(logger)
    report_service = ReportService(
        config_service,
        download_service,
        logger,
        report_shelves,
    )
    list_service = ListService(
        config_service,
        download_service,
        report_service,
        logger,
        book_filter,
    )
    return list_service


def recommend(
    user_id: int,
    cookie: str,
    book_filter: BookFilter,
    output_file: Optional[str] = None,
    verbose: bool = False,
    parse_args: bool = False,
    report_shelves: Optional[Set[str]] = None,
):
    """
    book_filter: for example the `strict_filter`

    user_id: Taken from the url when navigating to your profile. In this example,
    your user_id is 1234: https://www.goodreads.com/user/show/1234-foo-bar

    cookie: Copied from the request headers in the browser.

    parse_args: Instead of using the passed output_file and verbosity setting, parse
    them from the command-line. Use `--help` when calling your script to get help.

    report_shelves: A set of shelves that you want to see in the generated output for
    each book. Helps to understand what kind of book that is. By default uses the
    genres of each book. For example { "slice-of-life", "friendship" }
    """
    config_service = ConfigService(
        output_file=output_file,
        verbose=verbose,
        parse_args=parse_args,
    )
    logger = Logger(config_service)
    download_service = DownloadService(logger, cookie)
    report_service = ReportService(
        config_service,
        download_service,
        logger,
        report_shelves,
    )
    recommendation_engine = RecommendationEngine(
        download_service,
        report_service,
        logger,
    )
    recommendation_engine.recommend(
        user_id=user_id,
        book_filter=book_filter,
    )
