"""Download German spelling-alphabet audio from German Wiktionary.

The script looks for <a rel="mw:MediaLink"> elements in each page's HTML,
then downloads German audio files (whose original filenames start with De-).
It uses only Python's standard library.
"""

from __future__ import annotations

import argparse
import time
from html.parser import HTMLParser
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, unquote, urlparse
from urllib.request import Request, urlopen


WORDS = [ "Quelle",
    "Richard", "Siegfried", "Schule", "Eszett", "Theodor", "Ulrich",
    "Übermut", "Viktor", "Wilhelm", "Xanthippe", "Ypsilon", "Zeppelin",
]


USER_AGENT = "GermanLearningAudioDownloader/1.0 (personal learning project)"


class MediaLinkParser(HTMLParser):
    """Collect Wikimedia media links exposed by Wiktionary."""

    def __init__(self) -> None:
        super().__init__()
        self.urls: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        attributes = dict(attrs)
        if attributes.get("rel") != "mw:MediaLink":
            return
        href = attributes.get("href")
        #print(f"href {href}")
        if href:
            self.urls.append(href)


def request(url: str, retries: int, timeout: int):
    """Open a URL, retrying rate limits and temporary server errors."""
    for attempt in range(retries + 1):
        try:
            return urlopen(Request(url, headers={"User-Agent": USER_AGENT}), timeout=timeout)
        except HTTPError as error:
            if error.code not in {429, 500, 502, 503, 504} or attempt == retries:
                raise
            retry_after = error.headers.get("Retry-After")
            wait_seconds = int(retry_after) if retry_after and retry_after.isdigit() else 30 * (attempt + 1)
            print(f"  HTTP {error.code}; retrying in {wait_seconds}s...")
            time.sleep(wait_seconds)
        except URLError:
            if attempt == retries:
                raise
            wait_seconds = 15 * (attempt + 1)
            print(f"  Network error; retrying in {wait_seconds}s...")
            time.sleep(wait_seconds)
    raise RuntimeError("Unreachable")


def media_url_for_word(word: str, retries: int, timeout: int) -> str | None:
    page_url = f"https://de.wiktionary.org/wiki/{quote(word)}"
    #print(f"page_url {page_url}")
    with request(page_url, retries, timeout) as response:
        page_html = response.read().decode("utf-8", errors="replace")
        #print(f"page_html {page_html}")

    parser = MediaLinkParser()
    #print(f"parser {parser}")
    parser.feed(page_html)
    if not parser.urls:
        return None
    download_url = "https:" + parser.urls[0]
    #print(f"download_url {download_url}")
    return download_url


def filename_from_url(url: str) -> str:
    filename = unquote(Path(urlparse(url).path).name)
    # if not filename.startswith("De-") or not filename.lower().endswith((".ogg", ".oga")):
    #     raise ValueError(f"Unexpected media filename: {filename}")
    # return filename

    if not filename.lower().endswith((".ogg", ".oga")):
        raise ValueError(f"Unexpected media filename: {filename}")
    return filename


def download(url: str, destination: Path, retries: int, timeout: int) -> None:
    #print(f"in download url - {url}")
    #print(f"destination.suffix {destination.suffix}")
    temporary = destination.with_suffix(destination.suffix + ".part")
    #print(f"temporary {temporary}")
    try:
        with request(url, retries, timeout) as response, temporary.open("wb") as output:
            while chunk := response.read(1024 * 128):
                output.write(chunk)
        temporary.replace(destination)
    finally:
        if temporary.exists():
            temporary.unlink()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("alphabet_sounds"), help="Download folder")
    parser.add_argument("--delay", type=float, default=5.0, help="Seconds between words (default: 5)")
    parser.add_argument("--retries", type=int, default=4, help="Retries for temporary failures (default: 4)")
    parser.add_argument("--timeout", type=int, default=30, help="Request timeout in seconds (default: 30)")
    args = parser.parse_args()

    args.output.mkdir(parents=True, exist_ok=True)
    downloaded = skipped = unavailable = 0

    for index, word in enumerate(WORDS, start=1):
        print(f"[{index}/{len(WORDS)}] {word}")
        try:
            url = media_url_for_word(word, args.retries, args.timeout)
            #print(f"url {url}")
            if not url:
                print("  No German audio link on this page.")
                unavailable += 1
            else:
                destination = args.output / filename_from_url(url)
                if destination.exists():
                    print(f"  Already present: {destination.name}")
                    skipped += 1
                else:
                    download(url, destination, args.retries, args.timeout)
                    print(f"  Downloaded: {destination.name}")
                    downloaded += 1
        except (HTTPError, URLError, ValueError) as error:
            print(f"  Failed: {error}")
            unavailable += 1

        if index < len(WORDS):
            time.sleep(args.delay)

    print(f"\nFinished: {downloaded} downloaded, {skipped} already present, {unavailable} unavailable.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
