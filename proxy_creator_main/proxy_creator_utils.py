import re
from pathlib import Path


def lowercase(text: str) -> str:
    """Lowercase only first letter in a string."""
    return text[0].lower() + text[1:] if text else text


def cap(text: str) -> str:
    """Capitalize only first letter in a string."""
    return text[0].upper() + text[1:] if text else text


def strip_first_3d(name: str) -> str:
    """Remove the first 3d_ when the name starts with a digit."""
    if name and name[0].isdigit():
        return name.replace("3d_", "", 1)
    return name


def mesh_version_from_name(mesh_name: str, lod_suffix: str) -> int | None:
    """Return the Megascans mesh index from a name, or None.

    Args:
        mesh_name: Imported mesh transform name, e.g.
            Aset_antique_sculpture_S_ug4kaisva_00_LOD1.
        lod_suffix: LOD token including underscore, e.g. _LOD1.

    """
    short_name = mesh_name.split("|")[-1]
    lod_match = re.search(re.escape(lod_suffix) + r"$", short_name, flags=re.I)
    if not lod_match:
        lod_match = re.search(r"_LOD\d+$", short_name, flags=re.I)
    if not lod_match:
        return None
    token = short_name[: lod_match.start()].split("_")[-1]
    if token.isdigit():
        return int(token)
    return None


def mesh_versions_from_indices(indices: list[int]) -> list[str]:
    """Format mesh versions as v01, shifting up when the file is 0-based."""
    offset = 1 if min(indices) == 0 else 0
    return [f"v{index + offset:02d}" for index in indices]


def prefer_res_filepaths(filepaths: list, tex_res: str) -> list:
    """Return filepaths matching the UI texture resolution, or all if none match.

    Args:
        filepaths: Candidate texture file paths.
        tex_res: Resolution token from the UI, e.g. 2K or 4K.

    """
    token = f"_{tex_res}"
    matched = [fp for fp in filepaths if token in Path(fp).name]
    return matched or list(filepaths)
