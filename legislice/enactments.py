from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date
from typing import Sequence, List, Optional, Tuple, Union

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


class TextSequence(Sequence[Union[None, TextPassage]]):
    """
    Sequential passages of legislative text that need not be consecutive.

    Unlike an Enactment, a TextSequence does not preserve the citation structure
    of the enacted statute.

    :param passages:
        the text passages included in the TextSequence, which should be chosen
        to express a coherent idea. "None"s in the sequence represent spans of
        text that exist in the source statute, but that haven't been chosen
        to be part of the TextSequence.
    """

    def __init__(self, passages=Sequence[TextPassage]):
        self.passages = passages

    def __len__(self):
        return len(self.passages)

    def __getitem__(self, key):
        return self.passages[key]

    def __str__(self):
        result = ""
        for phrase in self.passages:
            if phrase is None:
                if not result.endswith("..."):
                    result += "..."
            else:
                if result and not result.endswith(("...", " ")):
                    result += " "
                result += phrase.text
        return result

    def __ge__(self, other: TextSequence):
        for other_passage in other.passages:
            if not any(self_passage >= other_passage for self_passage in self.passages):
                return False
        return True

    def __gt__(self, other: TextSequence):
        if self.means(other):
            return False
        return self >= other

    def strip(self) -> TextSequence:
        result = self.passages.copy()
        if result and result[0] is None:
            result = result[1:]
        if result and result[-1] is None:
            result = result[:-1]
        return TextSequence(result)

    def means(self, other: TextSequence) -> bool:
        self_passages = self.strip().passages
        other_passages = other.strip().passages
        if len(self_passages) != len(other_passages):
            return False

        zipped = zip(self_passages, other_passages)
        return all(
            (pair[0] is None and pair[1] is None) or pair[0].means(pair[1])
            for pair in zipped
        )


@dataclass
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

    def __init__(
        self,
        node: str,
        heading: str,
        content: str,
        start_date: date,
        end_date: Optional[date] = None,
        children: List[Enactment] = None,
        selection: Union[bool, List[TextPositionSelector]] = True,
    ):
        self.node = node
        self._content = content
        self._heading = heading
        self._start_date = start_date
        self._end_date = end_date

        if selection is True:
            self._selection = TextPositionSet(
                TextPositionSelector(0, len(self.content))
            )
        elif selection is False:
            self._selection = TextPositionSet()
        else:
            self._selection = selection

        if not children:
            self._children = []
        else:
            self._children = children

    @property
    def heading(self):
        return self._heading

    @property
    def content(self):
        return self._content

    @property
    def start_date(self):
        return self._start_date

    @property
    def end_date(self):
        return self._end_date

    @property
    def children(self):
        return self._children

    @property
    def selection(self):
        return self._selection

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
    def padded_length(self):
        """Get length of self's content plus one character for space before next section."""
        if self.content:
            return len(self.content) + 1
        return 0

    @property
    def text(self):
        """Get all text including subnodes, regardless of which text is "selected"."""
        text_parts = [self.content]
        for child in self.children:
            text_parts.append(child.text)
        joined = " ".join(text_parts)
        return joined.strip()

    def __str__(self):
        text_sequence = self.text_sequence()
        return f'"{text_sequence}" ({self.node} {self.start_date})'

    def select_from_text_positions(self, selection: TextPositionSet):

        self._selection: List[TextPositionSelector] = []
        selections = selection.ranges()
        while selections and selections[0].start < len(self.content):
            if selections[0].end <= len(self.content):
                self.selection.append(
                    TextPositionSelector(
                        start=selections[0].start, end=selections[0].end
                    )
                )
                selections = selections[1:]
            else:
                self.selection.append(
                    TextPositionSelector(
                        start=selections[0].start, end=len(self.content)
                    )
                )
                selections[0] = TextPositionSelector(
                    start=self.padded_length, end=selections[0].end
                )
        if selections:
            selections = [selection - self.padded_length for selection in selections]
            for child in self.children:
                selections = child.select(TextPositionSet(selections))
        return selections

    def select(self, selection: TextQuoteSelector) -> TextPositionSet:
        """Select text using one TextQuoteSelector, returning a new Enactment."""

        if isinstance(selection, TextQuoteSelector):
            selection = [selection]
        elif isinstance(selection, TextPositionSelector):
            selection = TextPositionSet(selection)
        if isinstance(selection, Sequence) and isinstance(
            selection[0], TextQuoteSelector
        ):
            selection = self.get_positions_for_quotes(selection)
        unused_selectors = self.select_from_text_positions(selection)
        return unused_selectors

    def selected_text(self) -> str:
        return str(self.text_sequence())

    def get_positions_for_quotes(
        self, quotes: List[TextQuoteSelector]
    ) -> TextPositionSet:
        position_selectors = [quote.as_position(self.text) for quote in quotes]
        return TextPositionSet(position_selectors)

    def text_sequence(self, include_nones: bool = True) -> TextSequence:
        """
        List the phrases in the Enactment selected by TextPositionSelectors.

        :param include_nones:
            Whether the list of phrases should include `None` to indicate a block of
            unselected text
        """
        selected: List[Union[None, TextPassage]] = []

        # To delete?
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
            child_passages = child.text_sequence(include_nones=include_nones)
            if (
                selected
                and selected[-1] is None
                and child_passages
                and child_passages[0] is None
            ):
                selected += child_passages[1:]
            else:
                selected += child_passages
        return TextSequence(selected)

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
        self_selected_passages = self.text_sequence()
        other_selected_passages = other.text_sequence()
        return self_selected_passages.means(other_selected_passages)

    def __ge__(self, other: Enactment):
        """
        Tells whether ``self`` implies ``other``.

        :returns:
            Whether ``self`` contains at least all the same text as ``other``.
        """
        if not isinstance(other, self.__class__):
            return False
        self_selected_passages = self.text_sequence(include_nones=False)
        other_selected_passages = other.text_sequence(include_nones=False)
        return self_selected_passages >= other_selected_passages

    def __gt__(self, other) -> bool:
        """Test whether ``self`` implies ``other`` without having same meaning."""
        if self.means(other):
            return False
        return self >= other
