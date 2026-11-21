import asyncio
import zipfile

import pytest

from printo.convert.office import Office
from printo.errors import UserError
from printo.services.events import Events
from tests.support import running
from tests.test_api import _upload, _wait


def test_missing_office_binary(tmp_path):
    office = Office("printo-soffice-missing", 5)
    with pytest.raises(UserError) as caught:
        office.convert(tmp_path / "source.docx", tmp_path / "document.pdf", tmp_path / "profile")
    assert "Word" in caught.value.message


def test_word_file_becomes_a_pdf(tmp_path):
    docx = tmp_path / "note.docx"
    _write_docx(docx)
    with running(tmp_path, office_timeout_seconds=90) as (client, _ctx, _cups):
        number = _upload(client, "note.docx", docx.read_bytes()).json()["number"]
        job = _wait(client, number, {"ready", "failed"}, seconds=90)
        assert job["status"] == "ready", job["message"]
        assert job["page_count"] >= 1


def test_live_update_is_a_nudge():
    asyncio.run(_read_one_update())


async def _read_one_update() -> None:
    hub = Events(30)
    hub.bind(asyncio.get_running_loop())
    stream = hub.stream()
    hello = await stream.__anext__()
    waiter = asyncio.create_task(stream.__anext__())
    await asyncio.sleep(0)
    hub.publish_removed("abc")
    item = await asyncio.wait_for(waiter, 1)
    await stream.aclose()
    assert "Connected" in hello and "abc" in item


def _write_docx(path) -> None:
    types = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>"""
    rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>"""
    document = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
<w:body><w:p><w:r><w:t>printO</w:t></w:r></w:p>
<w:sectPr><w:pgSz w:w="11906" w:h="16838"/></w:sectPr></w:body></w:document>"""
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("[Content_Types].xml", types)
        archive.writestr("_rels/.rels", rels)
        archive.writestr("word/document.xml", document)
