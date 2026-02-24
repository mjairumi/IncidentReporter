import httpx
import xml.etree.ElementTree as ET
from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import Optional
from bs4 import BeautifulSoup

from CustomHttpClientPool import CustomHttpClientPool
from PollingInterface import PollingInterface, PollResult
from IncidentReportDto import IncidentReportDto
from Logger import logger


class OpenAIPoller(PollingInterface):

    RSS_URL = "https://status.openai.com/feed.rss"

    def __init__(self):
        self.frequency = 15
        self.incident_frequency = 15
        self.is_incident_active = False
        self._seen_guids: set[str] = set()
        self._first_poll = True
        self._last_build_date: Optional[datetime] = None  # Track lastBuildDate

    def getPollingFrequency(self) -> int:
        return self.incident_frequency if self.is_incident_active else self.frequency

    async def poll(self) -> PollResult:
        try:
            client = CustomHttpClientPool.get_client()
            response = await client.get(self.RSS_URL)
            response.raise_for_status()

            root = ET.fromstring(response.text)
            channel = root.find("channel")

            # Check lastBuildDate before doing anything else
            last_build_date = self._parse_last_build_date(channel)

            if self._first_poll:
                self._last_build_date = last_build_date
                incidents = self._parse_items(channel)
                self._seen_guids = {inc["guid"] for inc in incidents}
                self._first_poll = False
                logger.info(
                    f"[OpenAIPoller] Initialized. "
                    f"Last build: {self._last_build_date}. "
                    f"Tracking {len(self._seen_guids)} existing incidents."
                )
                return PollResult()

            # Feed hasn't been updated since last poll — skip entirely
            if last_build_date == self._last_build_date:
                logger.debug("[OpenAIPoller] No feed update detected, skipping.")
                return PollResult()

            # Feed has changed — update and parse items
            logger.info(
                f"[OpenAIPoller] Feed updated: "
                f"{self._last_build_date} -> {last_build_date}"
            )
            self._last_build_date = last_build_date
            incidents = self._parse_items(channel)

            new_incidents = [inc for inc in incidents if inc["guid"] not in self._seen_guids]

            if not new_incidents:
                if self.is_incident_active and self._all_resolved(incidents):
                    self.is_incident_active = False
                    logger.info("[OpenAIPoller] All incidents resolved — switching to normal polling.")
                    return PollResult(new_frequency=self.frequency)
                return PollResult()

            latest = new_incidents[0]
            for inc in new_incidents:
                self._seen_guids.add(inc["guid"])

            status = self._extract_status(latest["description"])
            is_resolved = status.lower() == "resolved"

            if not is_resolved and not self.is_incident_active:
                self.is_incident_active = True
                logger.info("[OpenAIPoller] Active incident detected — switching to fast polling.")
            elif is_resolved and self.is_incident_active and self._all_resolved(incidents):
                self.is_incident_active = False
                logger.info("[OpenAIPoller] Incident resolved — switching to normal polling.")

            return PollResult(
                incident=IncidentReportDto(
                    status=status,
                    message=latest["title"],
                    source="OpenAI",
                    createdAt=latest["pub_date"]
                ),
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

    def _parse_last_build_date(self, channel) -> Optional[datetime]:
        """Parse lastBuildDate from channel — this is updated every 30s by OpenAI."""
        raw = channel.findtext("lastBuildDate", default="")
        try:
            return parsedate_to_datetime(raw)
        except Exception:
            logger.warning("[OpenAIPoller] Could not parse lastBuildDate.")
            return None

    def _parse_items(self, channel) -> list[dict]:
        """Parse all incident items from channel."""
        items = []
        for item in channel.findall("item"):
            pub_date_str = item.findtext("pubDate", default="")
            try:
                pub_date = parsedate_to_datetime(pub_date_str)
            except Exception:
                pub_date = datetime.now()

            items.append({
                "guid": item.findtext("guid", default=""),
                "title": item.findtext("title", default=""),
                "description": item.findtext("description", default=""),
                "pub_date": pub_date,
            })
        return items

    def _extract_status(self, description_html: str) -> str:
        try:
            soup = BeautifulSoup(description_html, "html.parser")
            bold = soup.find("b")
            if bold and "Status:" in bold.text:
                return bold.text.replace("Status:", "").strip()
        except Exception:
            pass
        return "Unknown"

    def _all_resolved(self, incidents: list[dict]) -> bool:
        return all(
            "resolved" in self._extract_status(inc["description"]).lower()
            for inc in incidents[:5]
        )
