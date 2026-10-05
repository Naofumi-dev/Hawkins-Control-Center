"""Turn the supplied workbook into a disabled, reviewable source directory.

This importer reads XLSX files as ZIP/XML with the Python standard library. It
does not open URLs, run spreadsheet formulas, or treat listed sites as leads.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import posixpath
import re
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit


WORKBOOK = Path(
    "/Users/armageddonvivas/Downloads/Ronin Ren/Copy of PALDOGIE - Job Platforms.xlsx"
)
OUTPUT = Path(__file__).resolve().parents[1] / "data" / "source_registry.json"
MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
NS = {"m": MAIN_NS}


def normalize_url(raw: str) -> str:
    """Normalize only URL components whose equivalence is reliable here.

    A slash after a host is equivalent to the empty root path. Slashes on
    non-root paths, query strings, fragments, and path case are preserved.
    """

    if any(ord(char) < 32 for char in raw):
        raise ValueError("URL contains a control character")
    value = raw.strip()
    if not value or any(char.isspace() for char in value):
        raise ValueError("URL is empty or contains whitespace")

    parts = urlsplit(value)
    scheme = parts.scheme.lower()
    if scheme not in {"http", "https"} or not parts.hostname:
        raise ValueError("URL must be an absolute HTTP(S) URL")
    if parts.username is not None or parts.password is not None:
        raise ValueError("URL must not contain credentials")

    host = parts.hostname.lower()
    if ":" in host:  # IPv6 literal
        host = f"[{host}]"
    port = parts.port  # Also rejects malformed ports.
    default_port = 80 if scheme == "http" else 443
    netloc = host if port in (None, default_port) else f"{host}:{port}"
    path = "" if parts.path == "/" else parts.path
    return urlunsplit((scheme, netloc, path, parts.query, parts.fragment))


def _shared_strings(archive: zipfile.ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in archive.namelist():
        return []
    root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
    return [
        "".join(text.text or "" for text in item.iter(f"{{{MAIN_NS}}}t"))
        for item in root.findall(f"{{{MAIN_NS}}}si")
    ]


def _cell_text(cell: ET.Element, strings: list[str]) -> str:
    if cell.find(f"{{{MAIN_NS}}}f") is not None:
        raise ValueError(f"Formula in source cell {cell.get('r')}")
    kind = cell.get("t")
    if kind == "inlineStr":
        inline = cell.find(f"{{{MAIN_NS}}}is")
        return "".join(node.text or "" for node in inline.iter(f"{{{MAIN_NS}}}t")) if inline is not None else ""
    value = cell.find(f"{{{MAIN_NS}}}v")
    if value is None or value.text is None:
        return ""
    return strings[int(value.text)] if kind == "s" else value.text


def _sheet_path(archive: zipfile.ZipFile) -> tuple[str, str]:
    workbook = ET.fromstring(archive.read("xl/workbook.xml"))
    sheets = workbook.findall("m:sheets/m:sheet", NS)
    if len(sheets) != 1:
        raise ValueError("Expected one worksheet in the source workbook")
    sheet = sheets[0]
    rel_id = sheet.get(f"{{{REL_NS}}}id")
    relationships = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    target = next((rel.get("Target") for rel in relationships if rel.get("Id") == rel_id), None)
    if not target:
        raise ValueError("Worksheet relationship is missing")
    path = target.lstrip("/") if target.startswith("/") else posixpath.normpath(posixpath.join("xl", target))
    if path not in archive.namelist():
        raise ValueError("Worksheet XML is missing")
    return sheet.get("name", "Sheet1"), path


def _hyperlink_targets(archive: zipfile.ZipFile, sheet_path: str, root: ET.Element) -> dict[str, str]:
    rels_path = posixpath.join(
        posixpath.dirname(sheet_path), "_rels", posixpath.basename(sheet_path) + ".rels"
    )
    if rels_path not in archive.namelist():
        return {}
    relationships = ET.fromstring(archive.read(rels_path))
    targets = {rel.get("Id"): rel.get("Target") for rel in relationships}
    return {
        link.get("ref", ""): targets[link.get(f"{{{REL_NS}}}id")]
        for link in root.findall("m:hyperlinks/m:hyperlink", NS)
        if link.get(f"{{{REL_NS}}}id") in targets
    }


def read_source_rows(path: Path) -> list[dict[str, object]]:
    """Read original A:C data without following links or evaluating formulas."""

    with zipfile.ZipFile(path) as archive:
        strings = _shared_strings(archive)
        sheet_name, sheet_path = _sheet_path(archive)
        root = ET.fromstring(archive.read(sheet_path))
        hyperlink_targets = _hyperlink_targets(archive, sheet_path, root)
        rows = root.findall("m:sheetData/m:row", NS)
        if not rows:
            raise ValueError("Source workbook is empty")

        result: list[dict[str, object]] = []
        for row in rows:
            row_number = int(row.get("r", "0"))
            cells: dict[str, str] = {}
            for cell in row.findall("m:c", NS):
                reference = cell.get("r", "")
                match = re.match(r"[A-Z]+", reference)
                if match and match.group() in {"A", "B", "C"}:
                    cells[match.group()] = _cell_text(cell, strings)
            if row_number == 1:
                if [cells.get(column, "").strip() for column in ("A", "B", "C")] != [
                    "Name", "URL", "Category"
                ]:
                    raise ValueError("Unexpected source headers")
                continue
            if not any(cells.get(column, "") for column in ("A", "B", "C")):
                continue

            name = cells.get("A", "")
            original_url = cells.get("B", "")
            if not name.strip() or not original_url.strip():
                raise ValueError(f"Missing name or URL in workbook row {row_number}")
            target = hyperlink_targets.get(f"B{row_number}")
            if target and target != original_url:
                raise ValueError(f"Displayed URL differs from hyperlink in workbook row {row_number}")
            result.append(
                {
                    "sheet": sheet_name,
                    "row": row_number,
                    "name": name,
                    "original_url": original_url,
                    "original_category": cells.get("C", ""),
                }
            )
    return result


def build_registry(path: Path) -> dict[str, object]:
    rows = read_source_rows(path)
    sources_by_url: dict[str, dict[str, object]] = {}
    for row in rows:
        url = normalize_url(str(row["original_url"]))
        category = str(row["original_category"]).strip().lower() or "unclassified"
        if url not in sources_by_url:
            sources_by_url[url] = {
                "url": url,
                "name": row["name"],
                "category": category,
                "access_method": "manual_review",
                "enabled": False,
                "source_rows": [],
            }
        source = sources_by_url[url]
        if source["category"] != category:
            source["category"] = "mixed"
        source["source_rows"].append(row)

    return {
        "schema_version": 1,
        "source_workbook": path.name,
        "source_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "row_count": len(rows),
        "source_count": len(sources_by_url),
        "sources": list(sources_by_url.values()),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=WORKBOOK)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    arguments = parser.parse_args()

    registry = build_registry(arguments.input)
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(json.dumps(registry, ensure_ascii=False, indent=2) + "\n")
    print(f"Saved {registry['row_count']} workbook rows as {registry['source_count']} disabled sources")


if __name__ == "__main__":
    main()
