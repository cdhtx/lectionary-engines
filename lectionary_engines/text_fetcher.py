"""
Text Fetcher - Retrieve biblical texts from Bible APIs

Supports multiple translations via Bible Gateway.
"""

import re
import requests
from typing import Optional, Tuple
from bs4 import BeautifulSoup


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

        try:
            # Fetch the page
            response = requests.get(url, timeout=10)
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

    def fetch_moravian(self) -> Tuple[str, str]:
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
        from datetime import datetime

        url = "https://www.moravian.org/daily_texts/"
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        }

        try:
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, "html.parser")

            # Find today's date section
            today = datetime.now()
            day_name = today.strftime("%A")  # e.g., "Tuesday"

            # Find all paragraphs that might contain today's readings
            paragraphs = soup.find_all("p")

            daily_readings = []
            watchword_ref = None
            watchword_text_content = None
            daily_text_ref = None
            daily_text_content = None

            # Parse the page structure
            for i, p in enumerate(paragraphs):
                text = p.get_text()

                # Look for today's daily readings (Psalm, Genesis/OT, Matthew/NT pattern)
                if day_name in text and "—" in text:
                    # Extract the references after the em dash
                    parts = text.split("—")
                    if len(parts) > 1:
                        refs = parts[1].strip()
                        # Parse individual references (e.g., "Psalm 5; Genesis 6:1-7:10; Matthew 3")
                        for ref in refs.split(";"):
                            ref = ref.strip()
                            if ref and re.search(r'\d', ref):  # Has a number (chapter/verse)
                                daily_readings.append(ref)

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
            combined_text = "\n\n" + "="*80 + "\n\n".join(passages)

            # Create reference summary
            all_refs = daily_readings + ([f"Watchword: {watchword_ref}"] if watchword_ref else []) + ([f"Daily Text: {daily_text_ref}"] if daily_text_ref else [])
            combined_reference = " | ".join(all_refs)

            return (combined_reference, combined_text)

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
            response = requests.get(url, headers=headers, timeout=10)
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

    @staticmethod
    def list_translations() -> dict:
        """
        List all supported translations

        Returns:
            dict: Translation names and codes
        """
        return SUPPORTED_TRANSLATIONS.copy()
