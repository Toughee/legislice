from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import List, Optional, Tuple, Union

from anchorpoint import TextQuoteSelector, TextPositionSelector
from anchorpoint.textselectors import TextPositionSet

# Path parts known to indicate the level of law they refer to.
KNOWN_CONSTITUTIONS = ["const"]
KNOWN_STATUTE_CODES = ["acts", "usc"]


@dataclass(frozen=True)
class TextPassage:
    """
    A contiguous passage of legislative text.

    :param passage:
    """

    text: str

    def means(self, other: Optional[TextPassage]) -> bool:
        if not isinstance(other, self.__class__):
            return False

        return self.text.strip(",:;. ") == other.text.strip(",:;. ")

    def __ge__(self, other: Optional[TextPassage]) -> bool:
        if not other:
            return True

        other_text = other.text.strip(",:;. ")
        return other_text in self.text


@dataclass(frozen=True)
class Enactment:
    """
    One or more passages of legislative text, selected from within a cited location.

    :param node:
        identifier for the site where the provision is codified

    :param heading:
        full heading of the provision

    :param content:
        full text content at this node, even if not all of it is cited

    :param children:
        other nodes nested within this one

    :param start_date:
        date when the text was enacted at the cited location

    :param end_date:
        date when the text was removed from the cited location

    :param selector:
        identifier for the part of the provision being cited
    """

    node: str
    heading: str
    content: str
    start_date: date
    end_date: Optional[date] = None
    children: List[Enactment] = field(default_factory=list)
    selection: Union[bool, Tuple[TextPositionSelector, ...]] = True

    @property
    def sovereign(self):
        identifier_parts = self.node.split("/")
        return identifier_parts[1]

    @property
    def code(self):
        identifier_parts = self.node.split("/")
        if len(identifier_parts) < 3:
            return None
        return identifier_parts[2]

    @property
    def level(self):
        if self.code in KNOWN_STATUTE_CODES:
            return "statute"
        if self.code in KNOWN_CONSTITUTIONS:
            return "constitution"
        raise NotImplementedError

    @property
    def text(self):
        """Get all text including subnodes, regardless of which text is "selected"."""
        text_parts = [self.content]
        for child in self.children:
            text_parts.append(child.text)
        return " ".join(text_parts)

    def __str__(self):
        return f'"{self.selected_text}" ({self.node} {self.start_date})'

    def use_selector(self, selector: TextQuoteSelector) -> Enactment:
        new_attrs = self.__dict__.copy()
        position_in_own_content = selector.as_position(self.content)
        if position_in_own_content:
            new_attrs["selection"] = TextPositionSet(position_in_own_content)
            return self.__class__(**new_attrs)
        raise NotImplementedError

    def selected_as_list(
        self, include_nones: bool = True
    ) -> List[Union[None, TextPassage]]:
        """
        List the phrases in the Enactment selected by TextPositionSelectors.

        :param include_nones:
            Whether the list of phrases should include `None` to indicate a block of
            unselected text
        """
        selected: List[Union[None, TextPassage]] = []
        if self.selection is True:
            selected.append(TextPassage(self.content))
        elif self.selection:
            for passage in self.selection:
                end_value = None if passage.end > 999999 else passage.end
                selected.append(TextPassage(self.content[passage.start : end_value]))
                if include_nones and passage.end and (passage.end < len(self.content)):
                    selected.append(None)
        elif include_nones and (not selected or selected[-1] is not None):
            selected.append(None)
        for child in self.children:
            selected += child.selected_as_list(include_nones=include_nones)
        return selected

    @property
    def selected_text(self) -> str:
        result = ""
        for phrase in self.selected_as_list():
            if phrase is None:
                if not result.endswith("..."):
                    result += "..."
            else:
                if result and not result.endswith(("...", " ")):
                    result += " "
                result += phrase.text
        return result

    def means(self, other: Enactment) -> bool:
        r"""
        Find whether meaning of ``self`` is equivalent to that of ``other``.

        ``Self`` must be neither broader nor narrower than ``other`` to return True.

        :returns:
            whether ``self`` and ``other`` represent the same text
            issued by the same sovereign in the same level of
            :class:`Enactment`\.
        """
        if not isinstance(other, self.__class__):
            return False
        self_selected_passages = self.selected_as_list()
        other_selected_passages = other.selected_as_list()
        zipped = zip(self_selected_passages, other_selected_passages)
        if not all((pair[0] is None) == (pair[1] is None) for pair in zipped):
            return False
        return all(pair[0] is None or pair[0].means(pair[1]) for pair in zipped)

    def __ge__(self, other):
        """
        Tells whether ``self`` implies ``other``.

        :returns:
            Whether ``self`` contains at least all the same text as ``other``.
        """
        if not isinstance(other, self.__class__):
            return False
        self_selected_passages = self.selected_as_list(include_nones=False)
        other_selected_passages = other.selected_as_list(include_nones=False)
        for other_passage in other_selected_passages:
            if not any(
                self_passage >= other_passage for self_passage in self_selected_passages
            ):
                return False
        return True

    def __gt__(self, other) -> bool:
        """Test whether ``self`` implies ``other`` without having same meaning."""
        if self == other:
            return False
        return self >= other
