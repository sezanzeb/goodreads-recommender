#!/usr/bin/env python3
from goodreads_recommender.bootstrap import bootstrap_list_service
from goodreads_recommender.filters.strict_filter import strict_filter

list_service = bootstrap_list_service(
    book_filter=strict_filter(
        important_genres=["fantasy", "adult"],
        avoid_genres=["robots", "aliens"],
        minimum_rating=3,
        require_audiobook=True,
    ),
    # If you want to have information on why some books were removed,
    # enable verbose logging:
    # verbose=True,
    output_file="./output.txt",
)

# Add a "Fantasy" section to output.txt, using books from various lists and shelves.
# They are going to be filtered in accordance to above configuration.
# Repeat this step multiple times with different configurations to extend output.txt.
list_service.scan_books(
    name="Fantasy",
    list_ids=["176302.Best_Cozy_Fantasy_Books"],
    shelf_ids=["fantasy"],
    book_ids=["13496.A_Game_of_Thrones"],
)

# More `list_service.scan_books` calls to your hearts desire may follow. The result
# will be appended to output.txt.
