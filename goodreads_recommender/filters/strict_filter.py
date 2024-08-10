from typing import List, Optional

from goodreads_recommender.entities.book import Book
from goodreads_recommender.logger import Logger


def strict_filter(
    important_genres: List[str],
    avoid_genres: List[str],
    minimum_rating: Optional[float] = None,
    require_audiobook: bool = False,
):
    """
    important_genres:
        Only show books containing all of those genres
    avoid_genres:
        Remove all books, even those with matching important_genres, if one or more
        of those genres are present.
    """

    def wrapped(book: Book, logger: Logger):
        genres = book.get_genres()
        for important_genre in important_genres:
            if important_genre not in genres:
                logger.verbose(f'Removed: {book.book_id}: "{important_genre}" missing')
                return False

        for avoid_genre in avoid_genres:
            if avoid_genre in genres:
                logger.verbose(f'Removed: {book.book_id}: has "{avoid_genre}"')
                return False

        if minimum_rating is not None and book.get_rating() < minimum_rating:
            logger.verbose(f"Removed: {book.book_id}: Rating too low")
            return False

        if require_audiobook and not book.does_audiobook_exist():
            logger.verbose(f"Removed: {book.book_id}: Has no audiobook")
            return False

        return True

    return wrapped
