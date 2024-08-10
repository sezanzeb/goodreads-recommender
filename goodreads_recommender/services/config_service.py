import argparse
import os
import sys
from typing import Optional


class ConfigService:
    def __init__(
        self,
        output_file: Optional[str] = None,
        verbose: bool = False,
        parse_args: bool = False,
    ):
        self.output_file = output_file
        self.verbose = verbose

        if parse_args:
            self.parse_args()

    def parse_args(self):
        parser = argparse.ArgumentParser()
        parser.add_argument(
            "-o",
            "--output-file",
            type=str,
            help='where to save the sorted output. Example: "output.txt"',
            default=None,
        )
        parser.add_argument(
            "-v",
            "--verbose",
            action="store_true",
        )

        args = parser.parse_args()

        self.output_file = args.output_file
        self.verbose = args.verbose

        if self.output_file is None:
            print("No path for clean and sorted output specified.")
        else:
            if os.path.isfile(self.output_file):
                print(f'"{self.output_file}" already exists!')
                sys.exit(1)
