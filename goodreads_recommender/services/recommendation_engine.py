import os
import pickle
import traceback
from typing import Dict, List, Optional, Tuple, NamedTuple, Self

from bs4 import Tag

from goodreads_recommender.entities.book import Book
from goodreads_recommender.logger import Logger
from goodreads_recommender.services.download_service import DownloadService
from goodreads_recommender.services.list_service import BookFilter
from goodreads_recommender.services.report_service import ReportService


class BookScore(NamedTuple):
    total_score: float
    number_of_reviews: int

    def merge(self, book_score: Self) -> Self:
        assert book_score is not None
        return BookScore(
            total_score=book_score.total_score + self.total_score,
            number_of_reviews=book_score.number_of_reviews + self.number_of_reviews,
        )


class BookScores(dict):
    # { book_id: (total_score, number_of_reviews) }

    def merge_book_scores(
        self,
        book_scores: Dict[str, BookScore],
    ) -> None:
        for book_id in book_scores:
            self[book_id] = book_scores[book_id].merge(
                self.get(book_id) or BookScore(0, 0)
            )

    def get_recommendations(self, minimum_rating: int = 4) -> Self:
        # Return only popular books, and only if they have a positive average rating
        # (rating as in "average rating of all the people that were reading the same
        # books as me", not as in "average rating on goodreads across all users")
        def key(item: Tuple[str, BookScore]):
            return -item[1].number_of_reviews

        sorted_book_scores = sorted(
            self.items(),
            key=key,
        )

        # dicts remember their order
        return BookScores(
            {
                book_id: book_score
                for book_id, book_score in sorted_book_scores
                if (book_score.total_score / book_score.number_of_reviews)
                >= minimum_rating
            }
        )


rating_map = {
    "did not like it": 1,
    "it was ok": 2,
    "liked it": 3,
    "really liked it": 4,
    "it was amazing": 5,
}


class RecommendationEngine:
    # 1. iterate over all your books with a high rating
    # 2. iterate over the most popular reviews of each book, download each users reviews
    # 3. add the score of all books up, and get the highest ranking ones
    # this works for recommendations, because
    # - if this would download a user multiple times because they appear as reviewer of
    #   multiple of my books, then their books get a higher total score, which is good
    # - if readers of my favourite books all enjoyed another particular book (that I
    #   ideally haven't read yet), this book gets a high total score

    def __init__(
        self,
        download_service: DownloadService,
        report_service: ReportService,
        logger: Logger,
        number_of_recommendations: int,
    ):
        self.download_service = download_service
        self.report_service = report_service
        self.logger = logger
        self.number_of_recommendations = number_of_recommendations

    def _load_book_scores_pickle(self, user_id: int) -> BookScores:
        cached_book_scores_path = f"cached_book_scores_{user_id}.pickle"
        try:
            with open(cached_book_scores_path, "rb") as file:
                self.logger.log(
                    f'Loading review scores from "{cached_book_scores_path}"'
                )
                book_scores = pickle.load(file)
        except FileNotFoundError:
            book_scores = self._get_book_scores_of_users_who_read_the_same_books(
                user_id
            )
            # For faster debugging, the result of this is cached. Also allows to
            # quickly play around with different filters.
            self.logger.log(f'Caching review scores to "{cached_book_scores_path}"')
            with open(cached_book_scores_path, "wb") as file:
                pickle.dump(book_scores, file)

        return book_scores

    def recommend(
        self,
        user_id: int,
        book_filter: Optional[BookFilter] = None,
        pickle_book_scores: bool = False,
    ) -> None:
        if pickle_book_scores:
            book_scores = self._load_book_scores_pickle(user_id)
        else:
            book_scores = self._get_book_scores_of_users_who_read_the_same_books(
                user_id
            )

        recommendations = book_scores.get_recommendations()
        self.report_service.append_books_to_file(
            name="Raw",
            book_ids=list(recommendations.keys())[: self.number_of_recommendations],
            sort=False,
        )

        if book_filter is not None:
            self.logger.verbose("Generating filtered recommendations...")
            filtered_book_scores = self._filter_book_scores(
                max_books=self.number_of_recommendations,
                book_scores=recommendations,
                book_filter=book_filter,
            )
            self.report_service.append_books_to_file(
                name="Filtered",
                book_ids=filtered_book_scores.keys(),
                # Don't resort them, as they are already sorted by how much this script
                # recommends them to the user.
                sort=False,
            )

    def _get_rating(self, review_soup: Tag) -> Optional[int]:
        """review_soup: element with .bookalike.review classes."""
        rating_value_soups = review_soup.select(".rating > .value > span")
        if len(rating_value_soups) == 0:
            # has not been rated
            return None

        # "title" refers to the human-readable rating
        title = rating_value_soups[0].get("title")

        if title is None:
            return None

        return rating_map[str(title)]

    def get_review_page_path(self, user_id, page_nr):
        return f"review/list/{user_id}?sort=rating&view=reviews&page={page_nr}"

    def _get_users_book_scores(
        self,
        user_id: int,
        minimum_review_score: int = 1,
        num_review_pages_to_scrape: int = 2,
    ) -> BookScores:
        """Go into the users reviews page, and collect the various books that they rated."""
        book_scores = BookScores()
        for page_nr in range(1, num_review_pages_to_scrape + 1):
            path = self.get_review_page_path(user_id, page_nr)
            reviews_soup = self.download_service.get(path)

            if reviews_soup.select("#privateProfile"):
                # Turns out the private profile error-page seems to also have the
                # "Sign in" text on it. Beware, check for private profiles first.
                # Return empty.
                self.logger.verbose(
                    f"Profile {user_id} is private, or your cookie is invalid"
                )
                return BookScores()

            if "Sign in" in str(reviews_soup.select("meta[name=description]")):
                self.download_service.delete_from_cache(path)
                raise Exception("Not logged in")

            for review in reviews_soup.select(".bookalike.review"):
                rating = self._get_rating(review)

                if rating is None or rating < minimum_review_score:
                    continue

                hrefs = [a.get("href") for a in review.select('a[href*="/book/show/"]')]
                book_id = os.path.basename(str(hrefs[0]))

                book_scores[book_id] = BookScore(
                    total_score=rating,
                    number_of_reviews=1,
                )

        return book_scores

    def _get_user_ids_who_liked_book(self, book_id: str) -> List[int]:
        return Book(
            book_id,
            self.download_service,
            self.logger,
        ).get_user_ids_who_liked_book()

    def _filter_book_scores(
        self,
        max_books: int,
        book_scores: BookScores,
        book_filter: BookFilter,
    ) -> BookScores:
        filtered_book_scores = BookScores({})

        for book_id, score in book_scores.items():
            try:
                keep = book_filter(
                    Book(
                        book_id,
                        self.download_service,
                        self.logger,
                    ),
                    self.logger,
                )
            except Exception as e:
                traceback.print_exc()
                print(f"Failed to filter {book_id}")
                continue

            if not keep:
                continue

            self.logger.verbose(f"Added {book_id}")
            filtered_book_scores[book_id] = score

            if len(filtered_book_scores) >= max_books:
                break

        return filtered_book_scores

    def _get_book_scores_of_users(self, user_ids: List[int]) -> BookScores:
        accumulated_book_scores = BookScores()
        for user_id in user_ids:
            try:
                their_book_scores = self._get_users_book_scores(user_id)
                self.logger.verbose(
                    f"  - {len(their_book_scores)} reviews of user {user_id}"
                )

                accumulated_book_scores.merge_book_scores(their_book_scores)

            except Exception:
                traceback.print_exc()
                self.logger.verbose(f"Failed to collect reviews of user {user_id}")

        return accumulated_book_scores

    def _get_book_scores_of_users_who_read_the_same_books(
        self,
        own_user_id: int,
    ) -> BookScores:
        num_review_pages_to_scrape = 2

        # Clear any existing reviews of the user, for which recommendations are
        # generated, to get updated recommendations once more books are read.
        # TODO I might actually want to have an option to redownload all cached reviews,
        #  including those of other users.
        #  - clear_own_cached_reviews
        #  - clear_others_cached_reviews

        for page_nr in range(1, num_review_pages_to_scrape + 1):
            try:
                self.download_service.delete_from_cache(
                    self.get_review_page_path(own_user_id, page_nr)
                )
            except FileNotFoundError:
                break

        own_book_scores = self._get_users_book_scores(
            own_user_id,
            num_review_pages_to_scrape,
        )

        accumulated_book_scores = BookScores()

        self.logger.verbose(f"{len(own_book_scores)} books")

        for i, our_book_id in enumerate(own_book_scores):
            if own_book_scores[our_book_id].total_score < 3:
                self.logger.verbose(f"Skipping {our_book_id}, didn't like")
                continue

            other_readers_user_ids = self._get_user_ids_who_liked_book(our_book_id)

            self.logger.verbose(
                f"- {len(other_readers_user_ids)} users for book {our_book_id} "
                f"{i}/{len(own_book_scores)}"
            )

            accumulated_book_scores.merge_book_scores(
                self._get_book_scores_of_users(other_readers_user_ids)
            )

        # Remove books that the user already read
        for book_id in own_book_scores:
            if book_id in accumulated_book_scores:
                del accumulated_book_scores[book_id]

        return accumulated_book_scores
