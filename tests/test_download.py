import datetime
from typing import Type
from legislice.enactments import CitingProvisionLocation, CrossReference
import os

from anchorpoint import TextQuoteSelector
from dotenv import load_dotenv
import pytest

from legislice.download import (
    Client,
    LegisliceDateError,
    LegislicePathError,
    LegisliceTokenError,
)
from legislice.enactments import InboundReference
from legislice.name_index import collect_enactments


load_dotenv()

TOKEN = os.getenv("LEGISLICE_API_TOKEN")
API_ROOT = os.getenv("API_ROOT")


class TestDownloadJSON:
    client = Client(api_token=TOKEN, api_root=API_ROOT)

    @pytest.mark.vcr()
    def test_fetch_section(self):
        url = self.client.url_from_enactment_uri("/test/acts/47/1")
        response = self.client._fetch_from_url(url=url)

        # Test that there was no redirect from the API
        assert not response.history

        section = response.json()
        assert section["start_date"] == "1935-04-01"
        assert section["end_date"] is None
        assert section["heading"] == "Short title"

    @pytest.mark.vcr()
    def test_fetch_current_section_with_date(self):
        url = self.client.url_from_enactment_uri(
            "/test/acts/47/6D", date=datetime.date(2020, 1, 1)
        )
        response = self.client._fetch_from_url(url=url)

        # Test that there was no redirect from the API
        assert not response.history

        waiver = response.json()
        assert waiver["url"].endswith("acts/47/6D@2020-01-01")
        assert waiver["children"][0]["start_date"] == "2013-07-18"

    @pytest.mark.vcr()
    def test_wrong_api_token(self):
        bad_client = Client(api_token="wr0ngToken")
        with pytest.raises(LegisliceTokenError):
            bad_client.fetch(query="/test/acts/47/1")

    @pytest.mark.vcr()
    def test_no_api_token(self):
        bad_client = Client()
        with pytest.raises(LegisliceTokenError):
            bad_client.fetch(query="/test/acts/47/1")

    @pytest.mark.vcr()
    def test_extraneous_word_token_before_api_token(self):
        extraneous_word_token = "Token " + TOKEN
        client = Client(api_token=extraneous_word_token, api_root=API_ROOT)
        s102 = client.fetch(query="/test/acts/47/1")
        assert s102["start_date"] == "1935-04-01"
        assert s102["end_date"] is None
        assert s102["heading"] == "Short title"

    @pytest.mark.vcr()
    def test_fetch_past_section_with_date(self):
        waiver = self.client.fetch(
            query="/test/acts/47/6D", date=datetime.date(1940, 1, 1)
        )
        assert waiver["url"].endswith("acts/47/6D@1940-01-01")
        assert waiver["children"][0]["start_date"] == "1935-04-01"

    @pytest.mark.vcr()
    def test_omit_terminal_slash(self):
        statute = self.client.fetch(query="us/usc/t17/s102/b/")
        assert not statute["node"].endswith("/")

    @pytest.mark.vcr()
    def test_add_omitted_initial_slash(self):
        statute = self.client.fetch(query="us/usc/t17/s102/b/")
        assert statute["node"].startswith("/")


class TestDownloadAndLoad:
    client = Client(api_token=TOKEN, api_root=API_ROOT)

    @pytest.mark.vcr()
    def test_make_enactment_from_citation(self):
        """
        Test fields for loaded Enactment.

        known_revision_date should indicate whether the start_date is known to be
        the date that the provision was revised in the USC.
        """

        fourth_a = self.client.read(query="/us/const/amendment/IV")
        assert fourth_a.selected_text().endswith("persons or things to be seized.")
        assert fourth_a.known_revision_date is True

    @pytest.mark.vcr()
    def test_make_enactment_from_selector_without_code(self):
        selection = TextQuoteSelector(suffix=", shall be vested")
        art_3 = self.client.read(query="/us/const/article/III/1")
        art_3.select(selection)
        text = art_3.selected_text()

        assert text.startswith("The judicial Power")
        assert text.endswith("the United States…")

    @pytest.mark.vcr()
    def test_bad_uri_for_enactment(self):
        with pytest.raises(LegislicePathError):
            _ = self.client.read(query="/us/const/article-III/1")

    @pytest.mark.vcr()
    def test_download_and_make_enactment_with_text_split(self):
        fourth_a = self.client.read(query="/us/const/amendment/IV",)
        selector = TextQuoteSelector(
            prefix="and", exact="the persons or things", suffix="to be seized."
        )
        fourth_a.select(selector)
        assert fourth_a.selected_text().endswith("or things…")

    @pytest.mark.vcr()
    def test_chapeau_and_subsections_from_uslm_code(self):
        """
        Test that the selected_text includes the text of subsections.

        known_revision_date should be available on the subsection as well as
        the section.
        """
        definition = self.client.read(query="/test/acts/47/4")
        sequence = definition.text_sequence()
        assert str(sequence.strip()).endswith("below the nose.")
        assert definition.known_revision_date is True
        assert definition.children[0].known_revision_date is True

    @pytest.mark.vcr()
    def test_unknown_revision_date(self):
        """
        Test notation that enactment went into effect before start of the available data range.

        This test may begin to fail if earlier statute versions are
        loaded to the API's database.
        """
        enactment = self.client.read(query="/us/usc/t17/s103")
        assert enactment.known_revision_date is False
        assert enactment.children[0].known_revision_date is False

    @pytest.mark.vcr()
    def test_update_linked_enactment(self):
        data = {"node": "/us/const"}
        new = self.client.update_enactment_from_api(data)
        assert new["node"] == "/us/const"
        assert new["start_date"] == "1788-09-13"
        assert isinstance(new["children"][0], str)

    @pytest.mark.vcr()
    def test_download_from_cross_reference(self):
        ref = CrossReference(
            target_uri="/test/acts/47/6C",
            target_url=f"{API_ROOT}/test/acts/47/6C@2020-01-01",
            target_node=1660695,
            reference_text="Section 6C",
        )
        cited = self.client.fetch(ref)
        assert cited["content"].startswith("Where an exemption is granted")


class TestReadJSON:
    client = Client(api_token=TOKEN, api_root=API_ROOT)

    @pytest.mark.vcr()
    def test_read_from_json(self):
        enactment = self.client.read_from_json(data={"node": "/us/const/amendment/IV"})
        assert enactment.start_date.isoformat() == "1791-12-15"

    @pytest.mark.vcr()
    def test_read_from_cross_reference(self):
        """Test reading old version of statute by passing date param."""
        ref = CrossReference(
            target_uri="/test/acts/47/6D",
            target_url=f"{API_ROOT}/test/acts/47/6D",
            reference_text="Section 6D",
        )
        cited = self.client.read(ref, date="1950-01-01")
        assert "bona fide religious or cultural reasons." in str(cited)

    @pytest.mark.vcr()
    def test_read_enactment_without_version_url(self):
        data = {
            "start_date": "1935-04-01",
            "selection": [
                {"start": 0, "include_end": False, "end": 250, "include_start": True}
            ],
            "text_version": {
                "content": (
                    "Where the Department provides an exemption from the prohibition "
                    "in section 5, except as defined in section 6D, the person to whom "
                    "such exemption is granted shall be liable to pay to the Department "
                    "of Beards such fee as may be levied under section 6B."
                ),
                "id": None,
                "url": None,
            },
            "heading": "Levy of beard tax",
            "anchors": [],
            "children": [],
            "node": "/test/acts/47/6A",
            "end_date": None,
        }
        result = self.client.read_from_json(data)
        assert result.content.startswith("Where")


class TestInboundCitations:
    client = Client(api_token=TOKEN, api_root=API_ROOT)

    @pytest.mark.vcr()
    def test_fetch_inbound_citations_to_node(self):
        infringement_statute = self.client.read(query="/us/usc/t17/s501",)
        inbound_refs = self.client.fetch_citations_to(infringement_statute)
        period_ref = inbound_refs[0]["locations"][0]
        assert period_ref.get("text_version", {}).get("content") is None

    @pytest.mark.vcr()
    def test_fetch_inbound_citations_in_multiple_locations(self):
        """
        Test InboundReference with multiple "locations".

        The string should be something like:
        InboundReference to /us/usc/t2/s1301, from (/us/usc/t2/s60c-5/a/2/A 2013-07-18) and 2 other locations

        But it's not clear which of the three locations will be chosen.
        """

        definitions = "/us/usc/t2/s1301"
        inbound_refs = self.client.citations_to(definitions)
        period_ref = inbound_refs[0]
        assert str(period_ref).endswith("and 2 other locations")

    @pytest.mark.vcr()
    def test_read_inbound_citations_to_node(self):
        infringement_statute = self.client.read(query="/us/usc/t17/s501",)
        inbound_refs = self.client.citations_to(infringement_statute)
        assert inbound_refs[0].content.startswith(
            "Any person who distributes a phonorecord"
        )
        assert inbound_refs[1].content.startswith(
            "The relevant provisions of paragraphs (2)"
        )
        period_ref = inbound_refs[0].locations[0]
        assert isinstance(period_ref, CitingProvisionLocation)
        assert period_ref.node == "/us/usc/t17/s109/b/4"
        assert period_ref.start_date.isoformat() == "2013-07-18"

    @pytest.mark.vcr()
    def test_download_inbound_citations_from_uri(self):
        inbound_refs = self.client.citations_to("/us/usc/t17/s501")
        assert inbound_refs[0].content.startswith(
            "Any person who distributes a phonorecord"
        )

    @pytest.mark.vcr()
    def test_download_enactment_from_inbound_citation(self):
        reference = InboundReference(
            content="Any person who distributes...",
            reference_text="section 501 of this title",
            target_uri="/us/usc/t17/s501",
            locations=[
                CitingProvisionLocation(
                    heading="",
                    node="/us/usc/t17/s109/b/4",
                    start_date=datetime.date(2013, 7, 18),
                )
            ],
        )
        cited = self.client.read(reference)
        assert cited.node == "/us/usc/t17/s109/b/4"
        assert cited.start_date == datetime.date(2013, 7, 18)

    @pytest.mark.vcr()
    def test_download_enactment_from_citing_location(self):

        location = CitingProvisionLocation(
            heading="",
            node="/us/usc/t17/s109/b/4",
            start_date=datetime.date(2013, 7, 18),
        )
        enactment = self.client.read(location)
        assert enactment.content.startswith("Any person who distributes")
