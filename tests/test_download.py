import datetime
from legislice.enactments import CrossReference
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
from legislice.name_index import collect_enactments


load_dotenv()

TOKEN = os.getenv("LEGISLICE_API_TOKEN")
API_ROOT = os.getenv("LOCAL_API_ROOT")


class TestDownloadJSON:
    client = Client(api_token=TOKEN, api_root=API_ROOT)

    @pytest.mark.vcr()
    def test_fetch_section(self):
        s102 = self.client.fetch(query="/test/acts/47/1")
        assert s102["start_date"] == "1935-04-01"
        assert s102["end_date"] is None
        assert s102["heading"] == "Short title"

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
    def test_fetch_current_section_with_date(self):
        waiver = self.client.fetch(
            query="/test/acts/47/6D", date=datetime.date(2020, 1, 1)
        )
        assert waiver["url"].endswith("acts/47/6D@2020-01-01")
        assert waiver["children"][0]["start_date"] == "2013-07-18"

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
        fourth_a = self.client.read(query="/us/const/amendment/IV")
        assert fourth_a.selected_text().endswith("persons or things to be seized.")

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
        """Test that the selected_text includes the text of subsections."""
        definition = self.client.read(query="/test/acts/47/4")
        sequence = definition.text_sequence()
        assert str(sequence.strip()).endswith("below the nose.")

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
        assert cited["text_version"]["content"].startswith(
            "Where an exemption is granted"
        )


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


class TestInboundCitations:
    client = Client(api_token=TOKEN, api_root=API_ROOT)

    @pytest.mark.vcr()
    def test_fetch_inbound_citations_to_node(self):
        infringement_statute = self.client.read(query="/us/usc/t17/s501",)
        inbound_refs = self.client.fetch_citations_to(infringement_statute)
        period_ref = inbound_refs["results"][0]["locations"][0]
        assert period_ref.get("text_version", {}).get("content") is None

    @pytest.mark.vcr()
    def test_read_inbound_citations_to_node(self):
        infringement_statute = self.client.read(query="/us/usc/t17/s501",)
        inbound_refs = self.client.citations_to(infringement_statute)
        period_ref = inbound_refs["results"][0]["locations"][0]
        assert period_ref.get("text_version", {}).get("content") is None

