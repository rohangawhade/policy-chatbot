"""Tests for scripts/download_gov_docs.py (Step 11.1). No real network
calls -- every HTTP interaction goes through `httpx.MockTransport`.
`_OUTPUT_ROOT`/`_MANIFEST_PATH` are monkeypatched per test to an isolated
`tmp_path` so nothing touches the real `data/gov_pdfs/`.
"""

import asyncio
import hashlib
import io
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from unittest import mock

import download_gov_docs as script
import httpx
import openpyxl
import pytest


@contextmanager
def _mock_asyncclient_transport(
    handler: Callable[[httpx.Request], httpx.Response],
) -> Iterator[None]:
    """`_download_all`/`_fetch` construct their own `httpx.AsyncClient()`
    internally rather than taking one as a parameter -- patching the
    class itself is the only way to swap in a `MockTransport` without
    touching the script's own signature."""
    real_client_cls = httpx.AsyncClient
    with mock.patch.object(
        httpx,
        "AsyncClient",
        lambda **kwargs: real_client_cls(transport=httpx.MockTransport(handler), **kwargs),
    ):
        yield


@pytest.fixture(autouse=True)
def _no_real_retry_delay(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _instant_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr(asyncio, "sleep", _instant_sleep)


def _fake_plan_key_xlsx(rows: list[tuple[str, ...]]) -> bytes:
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.append(("Carrier Name", "Plan Option Name", "Plan Code", "Brochure Number"))
    for row in rows:
        sheet.append(row)
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


@pytest.fixture(autouse=True)
def _isolated_output(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    output_root = tmp_path / "gov_pdfs"
    monkeypatch.setattr(script, "_OUTPUT_ROOT", output_root)
    monkeypatch.setattr(script, "_MANIFEST_PATH", output_root / "manifest.json")


# --- brochure code extraction -----------------------------------------


def test_brochure_code_regex_extracts_a_well_formed_code() -> None:
    match = script._BROCHURE_CODE_RE.search("RI 73-860")
    assert match is not None
    assert match.group(1) == "73-860"


def test_brochure_code_regex_handles_a_four_digit_suffix() -> None:
    match = script._BROCHURE_CODE_RE.search("RI 71-0041")
    assert match is not None
    assert match.group(1) == "71-0041"


def test_brochure_code_regex_rejects_the_known_malformed_value() -> None:
    # The real, malformed row found in OPM's own 2026 spreadsheet during
    # this step's research: "RI-73 899" instead of "RI 73-899" -- no
    # `\d{2}-\d{3,4}` substring exists in it, so this must return None
    # rather than silently matching something wrong.
    assert script._BROCHURE_CODE_RE.search("RI-73 899") is None


# --- Manifest -----------------------------------------------------------


def test_manifest_load_returns_empty_when_no_file_exists() -> None:
    manifest = script.Manifest.load()
    assert manifest.entries == {}
    assert manifest.has("opm/brochures/73-860.pdf") is False


def test_manifest_record_save_and_reload_round_trips() -> None:
    manifest = script.Manifest.load()
    manifest.record("opm/brochures/73-860.pdf", url="https://example.gov/x.pdf", content=b"hello")
    manifest.save()

    reloaded = script.Manifest.load()
    assert reloaded.has("opm/brochures/73-860.pdf") is True
    entry = reloaded.entries["opm/brochures/73-860.pdf"]
    assert entry["url"] == "https://example.gov/x.pdf"
    assert entry["size_bytes"] == 5
    assert entry["sha256"] == hashlib.sha256(b"hello").hexdigest()


# --- _discover_opm_brochures --------------------------------------------


async def test_discover_opm_brochures_dedupes_and_skips_malformed_rows() -> None:
    xlsx_bytes = _fake_plan_key_xlsx(
        [
            ("Acme Health", "High Option", "AH", "RI 73-860"),
            ("Acme Health", "Standard Option", "AH", "RI 73-860"),  # duplicate brochure
            ("Beta Dental", "Basic Option", "BD", "RI 71-0041"),
            ("Broken Row", "N/A", "BR", "RI-73 899"),  # malformed, must be skipped
        ]
    )

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == script._OPM_PLAN_KEY_URL
        return httpx.Response(200, content=xlsx_bytes)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        targets = await script._discover_opm_brochures(client)

    codes = {t.filename for t in targets}
    assert codes == {"73-860.pdf", "71-0041.pdf"}
    assert all(t.source == "opm" and t.subfolder == "brochures" for t in targets)
    assert all(
        t.url == script._OPM_BROCHURE_URL_TEMPLATE.format(code=t.filename[:-4]) for t in targets
    )


async def test_discover_opm_brochures_returns_empty_list_when_the_plan_key_url_is_stale() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        targets = await script._discover_opm_brochures(client)

    # A stale plan-key URL (the filename embeds a date that changes every
    # plan year) must degrade to "no OPM documents this run," not crash
    # the whole script -- CMS/DOL's curated lists are independent of it.
    assert targets == []


# --- _download_all --------------------------------------------------------


def _target(name: str, url: str) -> script.DownloadTarget:
    return script.DownloadTarget(source="cms", subfolder="sbc_templates", filename=name, url=url)


async def test_download_all_writes_files_and_records_the_manifest(tmp_path: Path) -> None:
    target = _target("a.pdf", "https://example.gov/a.pdf")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"%PDF-fake-content")

    with _mock_asyncclient_transport(handler):
        downloaded, skipped, failed = await script._download_all(
            [target], dry_run=False, force=False, request_delay_seconds=0
        )

    assert (downloaded, skipped, failed) == (1, 0, 0)
    written = script._OUTPUT_ROOT / "cms" / "sbc_templates" / "a.pdf"
    assert written.read_bytes() == b"%PDF-fake-content"
    assert script.Manifest.load().has("cms/sbc_templates/a.pdf")


async def test_download_all_dry_run_does_not_write_anything() -> None:
    target = _target("a.pdf", "https://example.gov/a.pdf")

    downloaded, skipped, failed = await script._download_all(
        [target], dry_run=True, force=False, request_delay_seconds=0
    )

    assert (downloaded, skipped, failed) == (1, 0, 0)
    assert not (script._OUTPUT_ROOT / "cms" / "sbc_templates" / "a.pdf").exists()
    assert not script._MANIFEST_PATH.exists()


async def test_download_all_skips_a_file_already_in_the_manifest() -> None:
    target = _target("a.pdf", "https://example.gov/a.pdf")
    destination = script._OUTPUT_ROOT / "cms" / "sbc_templates" / "a.pdf"
    destination.parent.mkdir(parents=True)
    destination.write_bytes(b"already here")
    manifest = script.Manifest.load()
    manifest.record("cms/sbc_templates/a.pdf", url=target.url, content=b"already here")
    manifest.save()

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("should not fetch a file already in the manifest")

    with _mock_asyncclient_transport(handler):
        downloaded, skipped, failed = await script._download_all(
            [target], dry_run=False, force=False, request_delay_seconds=0
        )

    assert (downloaded, skipped, failed) == (0, 1, 0)


async def test_download_all_records_a_failed_download_without_raising() -> None:
    target = _target("a.pdf", "https://example.gov/a.pdf")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    with _mock_asyncclient_transport(handler):
        downloaded, skipped, failed = await script._download_all(
            [target], dry_run=False, force=False, request_delay_seconds=0
        )

    assert (downloaded, skipped, failed) == (0, 0, 1)
    assert not (script._OUTPUT_ROOT / "cms" / "sbc_templates" / "a.pdf").exists()
