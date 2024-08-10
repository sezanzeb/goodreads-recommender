from typing import Dict

from goodreads_recommender.entities.book import Book


def weighted_filter(
    shelves: Dict[str, float],
    minimum_rating: float,
    require_audiobook: bool,
):
    """If a lot of people added a specific shelf, it gets more weight. And even more
    weight, if the `shelves` parameter maps to a high positive number.

    The number has to be between [-1 and 1].

    Popular shelves and negative numbers cause books to get a low weight.

    Shelves that were added by only few people aren't significant either way.

    Since this filter not only needs to download books, but also each books
    shelves, it is slow.
    """

    def wrapped(book: Book, _):
        if book.get_rating() < minimum_rating:
            return False

        books_shelves = book.get_top_shelves_and_their_count()

        # Or, idk, cosine distance. But I guess this is good enough.
        score = 0.0
        total = 0
        for shelf, count in books_shelves:
            if shelf in shelves:
                assert -1 <= shelves[shelf] <= 1
                weight = shelves[shelf] * count
                score += weight
                total += count

        # 1 would mean only shelves that are weighted with a factor of 1 are present.
        # -1 is the worst possible score.
        fractional_score = (score / total) if total > 0 else 0

        assert -1 <= fractional_score <= 1

        if fractional_score < 0.5:
            return False

        if require_audiobook and not book.does_audiobook_exist():
            return False

        return True

    return wrapped
