import httpx
import xml.etree.ElementTree as ET
from datetime import datetime
from email.utils import parsedate_to_datetime
from bs4 import BeautifulSoup

import IncidentReportDto
from PollingInterface import PollingInterface, PollResult
from Logger import logger

class OpenAIPoller(PollingInterface):

    RSS_URL = "https://status.openai.com/feed.rss"

    def __init__(self):
        self.frequency = 60                             # Check every 60s normally
        self.incident_frequency = 15                    # Check every 15s during active incident
        self.is_incident_active = False
        self._seen_guids: set[str] = set()              # Track already reported incidents by guid
        self._first_poll = True                         # Ignore all existing incidents on startup

    def getPollingFrequency(self) -> int:
        return self.incident_frequency if self.is_incident_active else self.frequency

    async def poll(self) -> PollResult:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(self.RSS_URL)
                response.raise_for_status()

            incidents = self._parse_feed(response.text)

            # On first poll, just snapshot all existing guids — don't report them
            if self._first_poll:
                self._seen_guids = {inc["guid"] for inc in incidents}
                self._first_poll = False
                logger.info(f"[OpenAIPoller] Initialized with {len(self._seen_guids)} existing incidents.")
                return PollResult()

            # Find any guids we haven't seen before
            new_incidents = [inc for inc in incidents if inc["guid"] not in self._seen_guids]

            if not new_incidents:
                # Check if all known incidents are resolved — if so, return to normal frequency
                if self.is_incident_active and self._all_resolved(incidents):
                    self.is_incident_active = False
                    logger.info("[OpenAIPoller] All incidents resolved — switching to normal polling.")
                    return PollResult(new_frequency=self.frequency)
                return PollResult()

            # Take the most recent new incident
            latest = new_incidents[0]

            # Mark all new ones as seen
            for inc in new_incidents:
                self._seen_guids.add(inc["guid"])

            # Parse status from description
            status = self._extract_status(latest["description"])
            is_resolved = status.lower() == "resolved"

            # Update incident mode
            if not is_resolved and not self.is_incident_active:
                self.is_incident_active = True
                logger.info("[OpenAIPoller] Active incident detected — switching to fast polling.")
            elif is_resolved and self.is_incident_active and self._all_resolved(incidents):
                self.is_incident_active = False
                logger.info("[OpenAIPoller] Incident resolved — switching to normal polling.")

            incident = IncidentReportDto(
                status=status,
                message=latest["title"],
                source="OpenAI",
                createdAt=latest["pub_date"]
            )

            return PollResult(
                incident=incident,
                new_frequency=self.getPollingFrequency()
            )

        except httpx.TimeoutException:
            logger.error("[OpenAIPoller] Request timed out.")
            return PollResult()
        except httpx.HTTPStatusError as e:
            logger.error(f"[OpenAIPoller] HTTP error: {e.response.status_code}")
            return PollResult()
        except Exception as e:
            logger.error(f"[OpenAIPoller] Unexpected error: {e}")
            return PollResult()

    # ------------------------------------------------------------------ #
    #  Parsing
    # ------------------------------------------------------------------ #

    def _parse_feed(self, xml_text: str) -> list[dict]:
        """Parse RSS XML and return list of incident dicts ordered newest first."""
        root = ET.fromstring(xml_text)
        channel = root.find("channel")
        items = []

        for item in channel.findall("item"):
            guid = item.findtext("guid", default="")
            title = item.findtext("title", default="")
            description = item.findtext("description", default="")
            pub_date_str = item.findtext("pubDate", default="")

            try:
                pub_date = parsedate_to_datetime(pub_date_str)
            except Exception:
                pub_date = datetime.now()

            items.append({
                "guid": guid,
                "title": title,
                "description": description,
                "pub_date": pub_date,
            })

        return items  # RSS feed already orders newest first

    def _extract_status(self, description_html: str) -> str:
        """Extract status string from HTML description e.g. 'Resolved', 'Investigating'."""
        try:
            soup = BeautifulSoup(description_html, "html.parser")
            bold = soup.find("b")
            if bold and "Status:" in bold.text:
                return bold.text.replace("Status:", "").strip()
        except Exception:
            pass
        return "Unknown"

    def _all_resolved(self, incidents: list[dict]) -> bool:
        """Check if all recent incidents in the feed are resolved."""
        return all(
            "resolved" in self._extract_status(inc["description"]).lower()
            for inc in incidents[:5]  # Only check the 5 most recent
        )