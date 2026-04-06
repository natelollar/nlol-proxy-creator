import re
from pathlib import Path

from maya import cmds

from proxy_creator_main.proxy_creator_logger import get_logger

logger = get_logger()


def import_proxy(filepaths: list[str]) -> None:
    """Import arnold proxies into Maya.

    Args:
        filepaths: List of file paths to import.

    """
    path_filepaths = [Path(fp) for fp in filepaths]
    arnold_proxy_filepaths = [
        fp for fp in path_filepaths if fp.suffix == ".ass" and fp.is_file()
    ]
    wrong_filepaths = [
        fp for fp in path_filepaths if fp.suffix != ".ass" or not fp.is_file()
    ]
    if wrong_filepaths:
        for filepath in wrong_filepaths:
            logger.info(
                f'Needs ".ass" extension or does not exist. Skipped: {filepath}',
            )

    for filepath in arnold_proxy_filepaths:
        file_name = Path(filepath).stem
        mesh_version = file_name.split('_')[-1]
        if re.match(r"v\d{2}$", mesh_version):  # v01
            mesh_version = f"_{mesh_version}"
        else:
            mesh_version = ""
        file_base_name = file_name.replace(mesh_version, "")
        base_name_stripped = file_base_name.split("_")
        base_name_stripped = [
            re.sub(r"\s+", "", (txt[0].upper() + txt[1:]))
            for txt in base_name_stripped
            if txt
        ]
        base_name_stripped = "".join(base_name_stripped)
        if base_name_stripped[0].isdigit():
            base_name_stripped = base_name_stripped.replace("3d_", "")

        standin_suffix = "_aiStandIn"
        standin_name = f"{base_name_stripped}{mesh_version}{standin_suffix}"
        standin = cmds.createNode(
            "aiStandIn",
            name=f"{standin_name}Shape",
        )
        cmds.select(standin)
        cmds.pickWalk(d="up")
        cmds.rename(f"{standin_name}")  # rename standIn transform
        cmds.setAttr(f"{standin}.dso", filepath, type="string")
        cmds.setAttr(f"{standin}.mode", 3)


def import_proxy_test() -> None:
    """Test."""
    logger.info("----- THIS IS A TEST! -----")
