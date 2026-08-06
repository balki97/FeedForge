import zlib
from collections.abc import Callable
from hashlib import md5
from io import BytesIO

from construct import (
    Adapter,
    Bytes,
    BytesInteger,
    Const,
    Construct,
    GreedyRange,
    Int16ub,
    Int32ub,
    Struct,
    this,
)

from .crypto import decrypt_bom, encrypt_bom, decrypt_psarc, encrypt_psarc

ENTRY = Struct(
    "md5" / Bytes(16),
    "zindex" / Int32ub,
    "length" / BytesInteger(5),
    "offset" / BytesInteger(5),
)


class BOMAdapter(Adapter):
    def _encode(self, obj, context, path):
        data = Struct(
            "entries" / ENTRY[context.n_entries], "zlength" / GreedyRange(Int16ub)
        ).build(obj)
        return encrypt_bom(data)

    def _decode(self, obj, context, path):
        data = decrypt_bom(obj)
        return Struct(
            "entries" / ENTRY[context.n_entries], "zlength" / GreedyRange(Int16ub)
        ).parse(data)


VERSION = 65540
ENTRY_SIZE = ENTRY.sizeof()
BLOCK_SIZE = 2 ** 16
ARCHIVE_FLAGS = 4

HEADER = Struct(
    "MAGIC" / Const(b"PSAR"),
    "VERSION" / Const(Int32ub.build(VERSION)),
    "COMPRESSION" / Const(b"zlib"),
    "header_size" / Int32ub,
    "ENTRY_SIZE" / Const(Int32ub.build(ENTRY_SIZE)),
    "n_entries" / Int32ub,
    "BLOCK_SIZE" / Const(Int32ub.build(BLOCK_SIZE)),
    "ARCHIVE_FLAGS" / Const(Int32ub.build(ARCHIVE_FLAGS)),
    "bom" / BOMAdapter(Bytes(this.header_size - 32)),
)


def read_entry(stream, n, bom, end_offset=None):
    entry = bom.entries[n]
    stream.seek(entry.offset)
    zlength = bom.zlength[entry.zindex :]

    data = BytesIO()
    length = 0
    for z in zlength:
        if length == entry.length:
            break

        read_size = BLOCK_SIZE if z == 0 else z
        if end_offset is not None:
            read_size = min(read_size, max(0, end_offset - stream.tell()))
        chunk = stream.read(read_size)
        try:
            chunk = zlib.decompress(chunk)
        except zlib.error:
            pass

        data.write(chunk)
        length += len(chunk)

    data = data.getvalue()
    assert len(data) == entry.length
    return data


def read_index(stream):
    """Read the PSARC table and file listing without expanding archive payloads."""
    header = HEADER.parse_stream(stream)
    stream.seek(0, 2)
    file_size = stream.tell()
    offsets = [entry.offset for entry in header.bom.entries]
    end_offsets = offsets[1:] + [file_size]
    listing_data = read_entry(stream, 0, header.bom, end_offsets[0])
    listing = listing_data.decode("utf-8", errors="replace").splitlines()
    expected = max(0, header.n_entries - 1)
    if len(listing) != expected:
        raise ValueError(f"PSARC listing contains {len(listing)} paths but the archive table contains {expected} entries.")
    return header, listing, end_offsets


def create_entry(name, data):
    zlength = []
    output = BytesIO()

    for i in range(0, len(data), BLOCK_SIZE):
        raw = data[i : i + BLOCK_SIZE]
        compressed = zlib.compress(raw, zlib.Z_BEST_COMPRESSION)
        if len(compressed) < len(raw):
            output.write(compressed)
            zlength.append(len(compressed))
        else:
            output.write(raw)
            zlength.append(len(raw) % BLOCK_SIZE)

    return {
        "md5": md5(name.encode()).digest() if name != "" else bytes(16),
        "zlength": zlength,
        "length": len(data),
        "data": output.getvalue(),
    }


def create_bom(entries):
    offset, zindex, zlength = 0, 0, []
    for entry in entries:
        entry["offset"] = offset
        entry["zindex"] = zindex
        offset += len(entry["data"])
        zindex += len(entry["zlength"])
        zlength += entry["zlength"]

    header_size = 32 + ENTRY_SIZE * len(entries) + 2 * len(zlength)
    for entry in entries:
        entry["offset"] += header_size

    return {"entries": entries, "zlength": zlength, "header_size": header_size}


class PSARC(Construct):
    def __init__(self, crypto=True):
        self.crypto = crypto
        super().__init__()

    def _parse(self, stream, context, path):
        header, listing, end_offsets = read_index(stream)
        content = {
            name: read_entry(stream, index, header.bom, end_offsets[index])
            for index, name in enumerate(listing, start=1)
        }
        if self.crypto:
            content = decrypt_psarc(content)
        return content

    def parse_selected_stream(
        self,
        stream,
        include: Callable[[str], bool],
        *,
        placeholder: Callable[[str], bool] | None = None,
    ):
        """Read only selected archive entries while retaining chosen path placeholders."""
        header, listing, end_offsets = read_index(stream)
        content = {}
        for index, name in enumerate(listing, start=1):
            if include(name):
                content[name] = read_entry(stream, index, header.bom, end_offsets[index])
            elif placeholder is not None and placeholder(name):
                content[name] = b""
        if self.crypto:
            content = decrypt_psarc(content)
        return content

    def parse_metadata_stream(self, stream):
        """Read naming metadata and SNG paths without expanding chart/audio payloads."""
        metadata_suffixes = (".json", ".hsan")
        return self.parse_selected_stream(
            stream,
            lambda name: name.replace("\\", "/").lower().endswith(metadata_suffixes),
            placeholder=lambda name: name.replace("\\", "/").lower().endswith(".sng"),
        )

    def parse_preview_stream(self, stream):
        """Read preview metadata, charts, and artwork while skipping audio payloads."""
        preview_suffixes = (
            ".json",
            ".hsan",
            ".version",
            ".txt",
            ".ini",
            ".xml",
            ".sng",
            ".png",
            ".jpg",
            ".jpeg",
            ".dds",
        )
        return self.parse_selected_stream(
            stream,
            lambda name: name.replace("\\", "/").lower().endswith(preview_suffixes),
        )

    def _build(self, content, stream, context, path):
        if self.crypto:
            content = encrypt_psarc(content)

        names = list(sorted(content.keys(), reverse=True))
        data = ["\n".join(names).encode("utf-8")] + [content[k] for k in names]

        entries = [create_entry(n, e) for n, e in zip([""] + names, data)]
        bom = create_bom(entries)

        header = HEADER.build(
            {"header_size": bom["header_size"], "n_entries": len(entries), "bom": bom}
        )

        stream.write(header)
        for e in entries:
            stream.write(e["data"])
