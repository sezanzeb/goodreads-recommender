import os
from typing import Optional

import requests
from bs4 import BeautifulSoup

from goodreads_recommender.logger import Logger


class DownloadService:
    def __init__(self, logger: Logger, cookie: Optional[str] = None):
        self.logger = logger
        self.cookie = cookie

    def delete_from_cache(self, path: str) -> None:
        os.remove(os.path.join("goodreads_cache", path))
        self.logger.verbose(f'Cleared cache "{path}"')

    def get(self, path: str) -> BeautifulSoup:
        """Make a get request to goodreads and cache the result."""
        download_path = os.path.join("goodreads_cache", path)

        try:
            with open(download_path, "r") as f:
                content = f.read()
                # self.logger.log('read cached list:', name, page)
                return BeautifulSoup(content, features="lxml")
        except FileNotFoundError:
            pass

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
        }

        if self.cookie is not None:
            headers["Cookie"] = self.cookie

        self.logger.verbose(f'Downloading "{path}" to "{download_path}"')

        attempts = 0
        while True:
            attempts += 1
            try:
                response = requests.get(
                    os.path.join("https://www.goodreads.com/", path),
                    headers=headers,
                    timeout=10 * attempts,
                )
                response.raise_for_status()
                break
            except Exception as exception:
                # retry downloading once if it fails
                if attempts >= 3:
                    raise exception

        content = response.text

        os.makedirs(os.path.dirname(download_path), exist_ok=True)
        with open(download_path, "x") as f:
            f.write(content)

        return BeautifulSoup(content, features="lxml")
