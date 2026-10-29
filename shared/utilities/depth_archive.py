"""Extract only our depth label archive format; never accept arbitrary ZIP paths."""
import json
import zipfile
from pathlib import Path, PurePosixPath


def extract_depth_archive(archive_path: Path, destination: Path):
    with zipfile.ZipFile(archive_path) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)) or "data.json" not in names:
            raise ValueError("Invalid depth archive manifest.")
        for name in names:
            path = PurePosixPath(name)
            if "\\" in name or ":" in name or path.is_absolute() or ".." in path.parts:
                raise ValueError("Unsafe depth archive path.")
            if name != "data.json" and not (len(path.parts) == 2 and path.parts[0] == "depth" and path.suffix == ".npz"):
                raise ValueError("Unexpected file in depth archive.")
        index = json.loads(archive.read("data.json"))
        if index.get("kind") != "monocular_depth" or index.get("schema_version") != 1:
            raise ValueError("Unsupported depth archive schema.")
        referenced = [item["depth_file"] for item in index["images"]]
        if len(referenced) != len(set(referenced)) or set(names) != {"data.json", *referenced}:
            raise ValueError("Depth archive is missing maps or contains unreferenced maps.")
        destination.mkdir(parents=True, exist_ok=True)
        archive.extractall(destination)
    return index
