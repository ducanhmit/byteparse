import json
from pathlib import Path

from byteparse.__main__ import main

FIXTURES = Path(__file__).parent / "fixtures"


def test_dump_tree(capsys):
    assert main(["dump", str(FIXTURES / "tiny.png"), "--format", "png"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("PNGFile\n")
    assert "    [0]: PNGChunk\n" in out
    assert "      chunk_type: b'IHDR'\n" in out


def test_dump_json(capsys):
    assert main(["dump", str(FIXTURES / "example_a.dns"), "--format", "dns", "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["answers"][0]["rtype"] == "A"
    assert data["answers"][0]["rdata"] == "5db8d70e"


def test_dump_failure_prints_error_and_partial(tmp_path, capsys):
    bad = tmp_path / "bad.png"
    bad.write_bytes((FIXTURES / "tiny.png").read_bytes()[:40])
    assert main(["dump", str(bad), "--format", "png"]) == 1
    captured = capsys.readouterr()
    assert "error: PNGFile.chunks[1]" in captured.err
    assert "partial result:" in captured.err
    assert captured.out.startswith("PNGFile (partial)\n")


def test_dump_missing_file(tmp_path, capsys):
    assert main(["dump", str(tmp_path / "nope"), "--format", "png"]) == 2
    assert "error:" in capsys.readouterr().err
