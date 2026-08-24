from adapters.chunking.metadata_extractor import ExtractedSection, MetadataExtractor


def test_single_page_with_no_heading_produces_one_untitled_section() -> None:
    sections = MetadataExtractor().extract_sections("Your annual deductible is $500.")

    assert sections == [
        ExtractedSection(
            section_title=None, page_number=None, text="Your annual deductible is $500."
        )
    ]


def test_all_caps_line_starts_a_new_section() -> None:
    text = "ELIGIBILITY\nYou must work 30+ hours per week to enroll."

    sections = MetadataExtractor().extract_sections(text)

    assert sections == [
        ExtractedSection(
            section_title="ELIGIBILITY",
            page_number=None,
            text="You must work 30+ hours per week to enroll.",
        )
    ]


def test_numbered_heading_starts_a_new_section() -> None:
    text = "1.2 Eligibility Requirements\nEmployees become eligible after 90 days."

    sections = MetadataExtractor().extract_sections(text)

    assert sections[0].section_title == "1.2 Eligibility Requirements"
    assert sections[0].text == "Employees become eligible after 90 days."


def test_title_case_line_starts_a_new_section() -> None:
    text = "Coverage Details\nThe plan covers dependents up to age 26."

    sections = MetadataExtractor().extract_sections(text)

    assert sections[0].section_title == "Coverage Details"


def test_sheet_marker_line_starts_a_new_section() -> None:
    text = "# Dental Plan\nEmployee | Premium\nJane Doe | 24.50"

    sections = MetadataExtractor().extract_sections(text)

    assert sections[0].section_title == "Dental Plan"
    assert sections[0].text == "Employee | Premium\nJane Doe | 24.50"


def test_line_ending_in_punctuation_is_never_treated_as_a_heading() -> None:
    text = "Coverage Details.\nMore body text follows."

    sections = MetadataExtractor().extract_sections(text)

    assert sections[0].section_title is None
    assert sections[0].text == "Coverage Details.\nMore body text follows."


def test_single_all_caps_word_is_a_heading() -> None:
    text = "OVERVIEW\nThis plan is administered by Acme Health."

    sections = MetadataExtractor().extract_sections(text)

    assert sections[0].section_title == "OVERVIEW"


def test_short_lowercase_word_is_not_a_heading() -> None:
    text = "Yes\nEnrollment is open through November."

    sections = MetadataExtractor().extract_sections(text)

    assert sections[0].section_title is None
    assert "Yes" in sections[0].text


def test_multiple_headings_on_one_page_each_start_a_new_section() -> None:
    text = (
        "Preamble text before any heading.\nELIGIBILITY\nWho can enroll."
        "\nCOVERAGE\nWhat is covered."
    )

    sections = MetadataExtractor().extract_sections(text)

    assert [s.section_title for s in sections] == [None, "ELIGIBILITY", "COVERAGE"]
    assert sections[0].text == "Preamble text before any heading."
    assert sections[1].text == "Who can enroll."
    assert sections[2].text == "What is covered."


def test_heading_immediately_followed_by_another_heading_produces_no_empty_section() -> None:
    text = "ELIGIBILITY\nCOVERAGE\nWhat is covered."

    sections = MetadataExtractor().extract_sections(text)

    assert [s.section_title for s in sections] == ["COVERAGE"]


def test_form_feed_separated_text_is_split_into_numbered_pages() -> None:
    text = "Page one body.\fPage two body."

    sections = MetadataExtractor().extract_sections(text)

    assert [(s.page_number, s.text) for s in sections] == [
        (1, "Page one body."),
        (2, "Page two body."),
    ]


def test_text_without_a_form_feed_has_no_page_number() -> None:
    sections = MetadataExtractor().extract_sections("Body text with no page markers.")

    assert sections[0].page_number is None


def test_blank_text_produces_no_sections() -> None:
    assert MetadataExtractor().extract_sections("   \n\n  ") == []


def test_extracted_section_is_frozen() -> None:
    section = ExtractedSection(section_title=None, page_number=1, text="body")

    try:
        section.text = "changed"  # type: ignore[misc]
    except AttributeError:
        pass
    else:
        raise AssertionError("ExtractedSection should be immutable")
