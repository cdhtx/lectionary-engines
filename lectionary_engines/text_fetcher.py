"""
Text Fetcher - Retrieve biblical texts from Bible APIs

Supports multiple translations via Bible Gateway.
"""

import re
import requests
from datetime import date, datetime, timedelta
from typing import Optional, Tuple
from bs4 import BeautifulSoup

MORAVIAN_DAILY_TEXTS_URL = "https://www.moravian.org/daily_texts/"
_BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
}
# "Sunday, October 11 — Isaiah 25:1-9; Psalm 23 ..." - the line that opens each
# daily entry's readings. Group 1 = month name, 2 = day, 3 = the readings.
_MORAVIAN_ENTRY_LINE = re.compile(
    r"^\s*(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),\s+"
    r"([A-Za-z]+)\s+(\d{1,2})\s+—\s+(.+)$"
)


class StaleMoravianEntry(Exception):
    """
    moravian.org has no entry for `today` yet: its newest entry is for
    `entry_date`. Raised by TextFetcher.fetch_moravian() so callers can ask
    the user whether to run on the older entry or wait, instead of silently
    studying yesterday's text as if it were today's.
    """

    def __init__(self, entry_date: date, today: date):
        self.entry_date = entry_date
        self.today = today
        super().__init__(
            f"Moravian Daily Text for {today:%A, %B} {today.day} is not published yet; "
            f"the newest entry is for {entry_date:%A, %B} {entry_date.day}"
        )


# Supported translations with Bible Gateway version codes
SUPPORTED_TRANSLATIONS = {
    "NRSVue": "NRSVUE",  # New Revised Standard Version Updated Edition (default)
    "NIV": "NIV",  # New International Version
    "CEB": "CEB",  # Common English Bible
    "NLT": "NLT",  # New Living Translation
    "MSG": "MSG",  # The Message
}


class TextFetcher:
    """Fetches biblical texts from Bible Gateway API"""

    def __init__(self, default_translation: str = "NRSVue"):
        """
        Initialize text fetcher

        Args:
            default_translation: Default translation to use (NRSVue, NIV, CEB, NLT, MSG)
        """
        if default_translation not in SUPPORTED_TRANSLATIONS:
            raise ValueError(
                f"Translation '{default_translation}' not supported. "
                f"Choose from: {', '.join(SUPPORTED_TRANSLATIONS.keys())}"
            )
        self.default_translation = default_translation

    def fetch(self, reference: str, translation: Optional[str] = None) -> str:
        """
        Fetch biblical text from Bible Gateway

        Args:
            reference: Biblical reference (e.g., "John 3:16-21", "Mark 5:1-5")
            translation: Optional translation override (NRSVue, NIV, CEB, NLT, MSG)

        Returns:
            str: Clean biblical text

        Raises:
            Exception: If fetching fails
        """
        # Use provided translation or default
        trans = translation or self.default_translation

        if trans not in SUPPORTED_TRANSLATIONS:
            raise ValueError(
                f"Translation '{trans}' not supported. "
                f"Choose from: {', '.join(SUPPORTED_TRANSLATIONS.keys())}"
            )

        # Get Bible Gateway version code
        version = SUPPORTED_TRANSLATIONS[trans]

        # Build URL
        url = f"https://www.biblegateway.com/passage/?search={reference}&version={version}"

        # Without a browser-like User-Agent, Bible Gateway serves a page
        # with no passage-text div to requests from data-center IPs (e.g.
        # Railway) - see incident 2026-09-05: this made every passage fetch
        # inside fetch_moravian() fail silently (each is wrapped in a bare
        # except: pass), surfacing as "Could not find any Moravian Daily
        # Text readings" even though the moravian.org scrape itself
        # succeeded. Every other request in this file already sends this
        # header; this one was the gap.
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        }

        try:
            # Fetch the page
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()

            # Parse HTML
            soup = BeautifulSoup(response.text, "html.parser")

            # Find the passage content
            passage_div = soup.find("div", class_="passage-text")

            if not passage_div:
                raise Exception(f"Could not find passage text for {reference}")

            # Extract text, removing verse numbers and footnotes
            # Remove verse numbers
            for span in passage_div.find_all("span", class_="chapternum"):
                span.decompose()
            for span in passage_div.find_all("span", class_="versenum"):
                span.decompose()

            # Remove footnotes
            for sup in passage_div.find_all("sup", class_="footnote"):
                sup.decompose()

            # Remove cross-references
            for sup in passage_div.find_all("sup", class_="crossreference"):
                sup.decompose()

            # Get clean text
            text = passage_div.get_text()

            # Clean up whitespace
            text = re.sub(r"\n+", "\n", text)  # Multiple newlines to single
            text = re.sub(r" +", " ", text)  # Multiple spaces to single
            text = text.strip()

            return text

        except requests.exceptions.RequestException as e:
            raise Exception(f"Failed to fetch text from Bible Gateway: {e}")
        except Exception as e:
            raise Exception(f"Error processing biblical text: {e}")

    def validate_reference(self, reference: str) -> bool:
        """
        Basic validation of biblical reference format

        Args:
            reference: Biblical reference to validate

        Returns:
            bool: True if format appears valid
        """
        # Simple regex for biblical references
        # Matches: "Book Chapter:Verse" or "Book Chapter:Verse-Verse" or "Book Chapter"
        pattern = r"^[1-3]?\s?[A-Za-z]+\s+\d+(:\d+(-\d+)?)?$"
        return bool(re.match(pattern, reference))

    def _get_moravian_page(self, today: date) -> BeautifulSoup:
        """
        Today's dated entry page if moravian.org has published it, otherwise
        the /daily_texts/ index (whose newest entry may be an earlier day).
        """
        dated_url = f"{MORAVIAN_DAILY_TEXTS_URL}{today:%A}-{today:%B}-{today.day}-{today.year}/".lower()
        try:
            response = requests.get(dated_url, headers=_BROWSER_HEADERS, timeout=30)
            if response.status_code == 200:
                return BeautifulSoup(response.text, "html.parser")
        except requests.exceptions.RequestException:
            pass  # fall back to the index below

        response = requests.get(MORAVIAN_DAILY_TEXTS_URL, headers=_BROWSER_HEADERS, timeout=30)
        response.raise_for_status()
        return BeautifulSoup(response.text, "html.parser")

    @staticmethod
    def _parse_moravian_entry(soup: BeautifulSoup, today: date) -> Tuple[date, list]:
        """
        The (date, [readings]) of the first "Weekday, Month D — readings"
        line on the page - the entry the page is actually about. Later
        matches (e.g. a sidebar block for next Sunday) are ignored.
        """
        for p in soup.find_all("p"):
            # Readings are split by ";" and/or <br> ("Psalm 23<br>Philippians
            # 4:1-9"), so treat a <br> as ";" - on a copy, leaving the page intact.
            line = BeautifulSoup(str(p), "html.parser")
            for br in line.find_all("br"):
                br.replace_with("; ")
            match = _MORAVIAN_ENTRY_LINE.match(line.get_text(" ", strip=True))
            if not match:
                continue
            month, day, refs = match.groups()
            try:
                entry_date = datetime.strptime(f"{month} {day} {today.year}", "%B %d %Y").date()
            except ValueError:
                continue
            # A Dec entry viewed in early Jan (or vice versa) belongs to the other year.
            if entry_date > today + timedelta(days=7):
                entry_date = entry_date.replace(year=today.year - 1)
            readings = [r.strip() for r in refs.split(";") if re.search(r"\d", r)]
            return entry_date, readings
        raise Exception("Could not find the readings line on moravian.org/daily_texts")

    def moravian_status(self, today: Optional[date] = None) -> dict:
        """
        Whether moravian.org has published today's entry yet. Cheap enough to
        poll: one or two page fetches, no Bible Gateway calls.
        """
        today = today or date.today()
        entry_date, _ = self._parse_moravian_entry(self._get_moravian_page(today), today)
        return {
            "entry_date": entry_date.isoformat(),
            "today": today.isoformat(),
            "is_current": entry_date == today,
        }

    def fetch_moravian(self, allow_stale: bool = False, today: Optional[date] = None) -> Tuple[str, str]:
        """
        Fetch today's complete Moravian Daily Text

        The Moravian Daily Text includes multiple biblical passages:
        - Daily Psalm
        - Daily OT Reading
        - Daily NT Reading
        - Watchword (OT verse)
        - Daily Text (NT verse)

        All passages are fetched and combined for comprehensive study.

        Returns:
            tuple: (reference, text)
                  reference: Summary of all passages
                  text: Combined text with all passages clearly labeled

        Raises:
            Exception: If fetching fails
        """
        today = today or date.today()

        try:
            soup = self._get_moravian_page(today)
            entry_date, daily_readings = self._parse_moravian_entry(soup, today)

            # moravian.org lags: its newest entry may be an earlier day. Let
            # the caller decide whether to run on it rather than quietly
            # studying yesterday's text as today's.
            is_stale = entry_date != today
            if is_stale and not allow_stale:
                raise StaleMoravianEntry(entry_date, today)

            paragraphs = soup.find_all("p")

            watchword_ref = None
            watchword_text_content = None
            daily_text_ref = None
            daily_text_content = None

            # Parse the page structure
            for i, p in enumerate(paragraphs):
                text = p.get_text()

                # Look for Watchword link
                if "Watchword" not in text:
                    watchword_links = p.find_all("a", href=re.compile(r"biblegateway\.com/passage"))
                    if watchword_links and not watchword_ref:
                        link = watchword_links[0]
                        href = link.get("href")
                        match = re.search(r"search=([^&]+)", href)
                        if match:
                            watchword_ref = match.group(1).replace("%20", " ").replace("+", " ").replace("%3A", ":")
                            # Get the verse text from the paragraph
                            watchword_text_content = p.get_text().split("Psalm")[0].strip() if "Psalm" in p.get_text() else None

            # Find Bible Gateway links for Watchword and Daily Text
            links = soup.find_all("a", href=re.compile(r"biblegateway\.com/passage"))

            if len(links) >= 2:
                # First link is watchword, second is daily text
                if not watchword_ref:
                    watchword_href = links[0].get("href")
                    match = re.search(r"search=([^&]+)", watchword_href)
                    if match:
                        watchword_ref = match.group(1).replace("%20", " ").replace("+", " ").replace("%3A", ":")

                daily_href = links[1].get("href")
                match = re.search(r"search=([^&]+)", daily_href)
                if match:
                    daily_text_ref = match.group(1).replace("%20", " ").replace("+", " ").replace("%3A", ":")

            # Fetch all biblical texts
            passages = []

            # Add daily readings (Psalm, OT, NT)
            for ref in daily_readings:
                try:
                    text = self.fetch(ref)
                    passages.append(f"DAILY READING — {ref}:\n{text}")
                except:
                    # If fetch fails, skip this passage
                    pass

            # Add Watchword
            if watchword_ref:
                try:
                    text = self.fetch(watchword_ref)
                    passages.append(f"WATCHWORD — {watchword_ref}:\n{text}")
                except:
                    pass

            # Add Daily Text
            if daily_text_ref:
                try:
                    text = self.fetch(daily_text_ref)
                    passages.append(f"DAILY TEXT — {daily_text_ref}:\n{text}")
                except:
                    pass

            if not passages:
                raise Exception("Could not find any Moravian Daily Text readings")

            # Combine all passages
            entry_label = f"{entry_date:%A, %B} {entry_date.day}, {entry_date.year}"
            combined_text = f"MORAVIAN DAILY TEXT FOR {entry_label}\n\n" + "="*80 + "\n\n".join(passages)

            # Create reference summary
            all_refs = daily_readings + ([f"Watchword: {watchword_ref}"] if watchword_ref else []) + ([f"Daily Text: {daily_text_ref}"] if daily_text_ref else [])
            combined_reference = " | ".join(all_refs)
            if is_stale:
                combined_reference += f" | (Moravian text from {entry_label})"

            return (combined_reference, combined_text)

        except StaleMoravianEntry:
            raise
        except Exception as e:
            raise Exception(f"Failed to fetch Moravian Daily Text: {e}")

    def fetch_rcl(self, reading_type: str = "gospel") -> Tuple[str, str]:
        """
        Fetch today's Revised Common Lectionary reading

        Args:
            reading_type: "ot" (Old Testament), "psalm", "epistle", or "gospel" (default)

        Returns:
            tuple: (reference, text)

        Raises:
            Exception: If fetching fails
        """
        from datetime import datetime

        today = datetime.now()

        # URL for Vanderbilt daily readings page
        url = "https://lectionary.library.vanderbilt.edu/daily-readings/"
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        }

        try:
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, "html.parser")

            # The page uses date-based IDs in format: MMDDYYYY (e.g., "01052026")
            date_id = today.strftime("%m%d%Y")

            # Find today's reading section by ID
            reading_section = soup.find(id=date_id)

            if not reading_section:
                raise Exception(
                    f"No readings found for {today.strftime('%B %d, %Y')}. "
                    "RCL daily readings may not be available for all dates."
                )

            # Find all scripture links in this section
            scripture_links = reading_section.find_all("a", href=re.compile(r"biblegateway\.com"))

            if not scripture_links:
                raise Exception(f"Could not find scripture readings for today")

            # Map reading types to typical labels
            reading_labels = {
                "ot": ["old testament", "first reading"],
                "psalm": ["psalm"],
                "epistle": ["epistle", "second reading", "new testament"],
                "gospel": ["gospel"]
            }

            # Try to find the specific reading type requested
            target_labels = reading_labels.get(reading_type.lower(), ["gospel"])
            reference_link = None

            # Search for the reading by looking at surrounding text
            for link in scripture_links:
                # Check text before the link for reading type label
                prev_text = ""
                prev_elem = link.find_previous(text=True)
                if prev_elem:
                    prev_text = prev_elem.strip().lower()

                # Check if this matches our target reading type
                for label in target_labels:
                    if label in prev_text:
                        reference_link = link
                        break

                if reference_link:
                    break

            # If no specific match, use positional fallback
            if not reference_link:
                reading_map = {"ot": 0, "psalm": 1, "epistle": 2, "gospel": 3}
                reading_index = reading_map.get(reading_type.lower(), 3)

                if reading_index < len(scripture_links):
                    reference_link = scripture_links[reading_index]
                else:
                    reference_link = scripture_links[-1]  # Use last as fallback

            # Extract reference from link
            reference = reference_link.get_text().strip()

            # Fetch the actual text
            text = self.fetch(reference)

            return (reference, text)

        except Exception as e:
            raise Exception(f"Failed to fetch RCL reading: {e}")

    def fetch_sunday_lectionary_readings(self) -> dict:
        """
        Fetch this week's Sunday RCL service readings (Gospel, Epistle,
        Hebrew Scripture, Psalm - primary/semicontinuous track) as clean
        biblical references (e.g. "Luke 14:1-14"), not full text.

        Unlike fetch_rcl() (which serves the *daily office* reading for
        today, used by the /generate RCL source option), this targets
        Vanderbilt's separate Sunday-specific lectionary texts page, which
        has a clean per-reading-type structure the daily-readings page
        lacks: weekdays wrap 3 readings in one link with no Gospel at all,
        and Sundays have zero scripture links in that page's daily section.

        Returns:
            dict: {"gospel": str, "epistle": str, "ot": str, "psalm": str}
            Keys are present only for readings successfully parsed - a
            malformed/missing single pericope on the page is skipped
            rather than failing the whole fetch.

        Raises:
            Exception: if the daily-readings page or the linked Sunday
            texts page can't be fetched, or this Sunday's entry can't be
            found at all (the page's fundamental structure changed).
        """
        from datetime import datetime, timedelta

        today = datetime.now().date()
        days_until_sunday = (6 - today.weekday()) % 7  # Monday=0 ... Sunday=6
        sunday = today + timedelta(days=days_until_sunday)
        date_id = sunday.strftime("%m%d%Y")

        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        }

        daily_url = "https://lectionary.library.vanderbilt.edu/daily-readings/"
        response = requests.get(daily_url, headers=headers, timeout=30)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")

        sunday_entry = soup.find(id=date_id)
        if not sunday_entry:
            raise Exception(f"No lectionary entry found for Sunday {sunday.strftime('%B %d, %Y')}")

        texts_link = sunday_entry.find("a", href=True)
        if not texts_link:
            raise Exception(f"No texts page link found for Sunday {sunday.strftime('%B %d, %Y')}")

        texts_url = texts_link["href"]
        if texts_url.startswith("/"):
            texts_url = "https://lectionary.library.vanderbilt.edu" + texts_url

        texts_response = requests.get(texts_url, headers=headers, timeout=30)
        texts_response.raise_for_status()
        texts_soup = BeautifulSoup(texts_response.text, "html.parser")

        pericope_ids = {
            "gospel": "pericope_gospel_reading",
            "epistle": "pericope_epistle_reading",
            "ot": "pericope_hebrew_reading",
            "psalm": "pericope_psalm_reading",
        }

        readings = {}
        for reading_type, div_id in pericope_ids.items():
            div = texts_soup.find(id=div_id)
            if not div:
                continue
            h2 = div.find("h2")
            if not h2:
                continue
            span = h2.find("span")
            reference = span.get_text(strip=True) if span else h2.get_text(strip=True)
            if reference:
                readings[reading_type] = reference

        if not readings:
            raise Exception(
                f"Found Sunday {sunday.strftime('%B %d, %Y')}'s texts page but could not parse any readings from it"
            )

        return readings

    @staticmethod
    def list_translations() -> dict:
        """
        List all supported translations

        Returns:
            dict: Translation names and codes
        """
        return SUPPORTED_TRANSLATIONS.copy()
