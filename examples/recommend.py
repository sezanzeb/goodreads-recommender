#!/usr/bin/env python
from goodreads_recommender.bootstrap import recommend
from goodreads_recommender.filters.strict_filter import strict_filter


def main():
    print("Cookie extracted from the browser (Firefox)")
    print("- Open goodreads.com and log in")
    print("- Go to the developer menu (F12)")
    print('- Go to the "Network" tab')
    print("- Open any page on goodreads")
    print('- Find the "html" request to any https://www.goodreads.com/... site')
    print('- Go to the "Request Headers"')
    print("- check the switch to view the raw headers, otherwise they are truncated")
    print('- Copy the value of the "Cookie" header.')
    cookie = input("Paste your goodreads cookie: ")
    print()

    print("Extract a user-id to recommend for from a profile url")
    print("For example 1324 in https://www.goodreads.com/user/show/1234-foo-bar")
    user_id = int(input("Paste the user-id here: "))
    print()

    recommend(
        user_id=user_id,
        cookie=cookie,
        verbose=True,
        number_of_recommendations=20,
    )


if __name__ == "__main__":
    main()
