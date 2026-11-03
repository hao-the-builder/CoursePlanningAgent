"""Download official requirement PDFs into raw/requirements/ (Phase 1).

Builds the list of majors and minors for the cohort from the official Program &
Course Catalog index, then downloads one PDF per program.

Rules: skip files that already exist, sleep between requests, respect
robots.txt, never hand-edit anything under raw/. Record every URL and download
date in raw/SOURCES.md.
"""


def main() -> None:
    raise NotImplementedError("Phase 1")


if __name__ == "__main__":
    main()
