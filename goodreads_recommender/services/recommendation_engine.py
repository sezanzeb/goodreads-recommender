import json
import os
import traceback
from typing import Dict, List, Optional, Tuple

from bs4 import Tag

from goodreads_recommender.entities.book import Book
from goodreads_recommender.logger import Logger
from goodreads_recommender.services.download_service import DownloadService
from goodreads_recommender.services.list_service import BookFilter
from goodreads_recommender.services.report_service import ReportService

# { book_id: (total_score, number_of_reviews) }
# Actually, I think I'm not even using the total_score. Right now I'm just sorting by
# number_of_reviews, which works fine.
BookScores = Dict[str, Tuple[float, int]]


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
    # 3. add the score of all books up, print a ranking
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

    def recommend(
        self,
        user_id: int,
        book_filter: Optional[BookFilter] = None,
    ) -> None:
        cached_book_scores_path = f"cached_book_scores_{user_id}.json"
        try:
            with open(cached_book_scores_path, "r") as file:
                self.logger.log(
                    f'Loading review scores from "{cached_book_scores_path}"'
                )
                book_scores = json.load(file)
        except FileNotFoundError:
            book_scores = self._get_book_scores_of_people_who_read_the_same_books(
                user_id
            )
            # For faster debugging, the result of this is cached. Also allows to
            # quickly play around with different filters.
            self.logger.log(f'Caching review scores to "{cached_book_scores_path}"')
            with open(cached_book_scores_path, "w") as file:
                file.write(json.dumps(book_scores))

        sorted_book_scores = self._sort_book_scores(book_scores)
        self.report_service.append_books_to_file(
            name="Raw",
            book_ids=list(sorted_book_scores.keys())[: self.number_of_recommendations],
            sort=False,
        )

        if book_filter is not None:
            self.logger.verbose("Generating filtered recommendations...")
            filtered_book_scores = self._filter_book_scores(
                max_books=self.number_of_recommendations,
                book_scores=sorted_book_scores,
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

    def _get_book_ratings_from_reviews_page(
        self,
        user_id: int,
        page_nr: int,
    ) -> Dict[str, float]:
        path = f"review/list/{user_id}?sort=rating&view=reviews&page={page_nr}"
        reviews_soup = self.download_service.get(path)

        if reviews_soup.select("#privateProfile"):
            # Turns out the private profile error-page seems to also have the "Sign in"
            # text on it. Beware, check for private profiles first.
            return {}

        if "Sign in" in str(reviews_soup.select("meta[name=description]")):
            self.download_service.delete_from_cache(path)
            raise Exception("Not logged in")

        ratings: Dict[str, float] = {}
        for review in reviews_soup.select(".bookalike.review"):
            rating = self._get_rating(review)

            if rating is None:
                continue

            href = [a.get("href") for a in review.select('a[href*="/book/show/"]')][0]
            book_id = os.path.basename(str(href))
            ratings[book_id] = rating

        return ratings

    def _get_users_book_ids_and_rating(self, user_id: int) -> Dict[str, float]:
        pages = 2
        ratings = {}
        for page_nr in range(1, pages + 1):
            ratings.update(self._get_book_ratings_from_reviews_page(user_id, page_nr))

        return ratings

    def _get_user_ids_who_liked_book(self, book_id: str) -> List[int]:
        return Book(
            book_id,
            self.download_service,
            self.logger,
        ).get_user_ids_who_liked_book()

    def _collect_review_scores_of_users(
        self,
        user_ids: List[int],
        book_scores: BookScores,
    ) -> None:
        for user_id in user_ids:
            try:
                their_reviews = self._get_users_book_ids_and_rating(user_id)
                self.logger.verbose(
                    f"  - {len(their_reviews)} reviews of user {user_id}"
                )
                for their_book_id, score in their_reviews.items():
                    old_book_score = book_scores.get(their_book_id, (0, 0))
                    book_scores[their_book_id] = (
                        old_book_score[0] + score,
                        int(old_book_score[1] + 1),
                    )
            except Exception:
                traceback.print_exc()
                self.logger.verbose(f"Failed to collect reviews of user {user_id}")

    def _filter_book_scores(
        self,
        max_books: int,
        book_scores: BookScores,
        book_filter: BookFilter,
    ) -> BookScores:
        filtered_book_scores = {}

        i = 0
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

            i += 1
            if i >= max_books:
                break

        return filtered_book_scores

    def _sort_book_scores(self, book_scores: BookScores) -> BookScores:
        # max_review_count = max([count for _, count in book_scores.values()])

        def key(item: Tuple[str, Tuple[float, int]]):
            # Sorting by average:
            # avg = item[1][0] / item[1][1]
            # popular books get a slight boost, to avoid having a book with 1 5-star
            # rating overshadow everything else
            # popularity_benefit = item[1][1] / max_review_count
            # Starting with the best one, hence `-`
            # return -(avg + popularity_benefit)

            # Turns out just sorting by review-count is very similar. There is probably
            # (duh) a strong correlation between a high review_count and a high average
            # review.
            return -item[1][1]

        sorted_book_scores = sorted(
            book_scores.items(),
            key=key,
        )

        # dicts remember their order afaik
        return {book_id: score for book_id, score in sorted_book_scores}

    def _get_book_scores_of_people_who_read_the_same_books(
        self,
        own_user_id: int,
    ) -> BookScores:
        own_book_reviews = self._get_users_book_ids_and_rating(own_user_id)

        book_scores: BookScores = {}

        self.logger.verbose(f"{len(own_book_reviews)} books")

        for i, our_book_id in enumerate(own_book_reviews):
            if own_book_reviews[our_book_id] < 3:
                self.logger.verbose(f"Skipping {our_book_id}, didn't like")
                continue

            reviewers_user_ids = self._get_user_ids_who_liked_book(our_book_id)

            self.logger.verbose(
                f"- {len(reviewers_user_ids)} users for book {our_book_id} "
                f"{i}/{len(own_book_reviews)}"
            )

            self._collect_review_scores_of_users(reviewers_user_ids, book_scores)

        books_scores_without_owned_books = {
            book_id: score
            for book_id, score in book_scores.items()
            if book_id not in own_book_reviews
        }

        return books_scores_without_owned_books
