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

    if not cmds.pluginInfo("mtoa", q=True, loaded=True):
        cmds.loadPlugin("mtoa")

    for i, filepath in enumerate(arnold_proxy_filepaths):
        object_name = filepath.stem
        if "aistandin" in object_name.lower():
            standin_name = object_name
        else:
            standin_name = f"{object_name}AiStandIn"
        if cmds.objExists(standin_name):
            logger.info(f'Already exists: "{standin_name}". Reloading filepath...')
            standin_shape = cmds.listRelatives(standin_name, shapes=True)[0]
            cmds.setAttr(f"{standin_shape}.dso", str(filepath), type="string")
            cmds.dgdirty(standin_shape)
            if i == len(arnold_proxy_filepaths) - 1:
                logger.info("Refreshing scene...")
                cmds.refresh(force=True)
        else:
            standin_shape = cmds.createNode(
                "aiStandIn",
                name=f"{standin_name}Shape",
            )
            standin_transform = cmds.listRelatives(standin_shape, parent=True)[0]
            cmds.rename(standin_transform, standin_name)
            cmds.setAttr(f"{standin_shape}.dso", str(filepath), type="string")
            cmds.setAttr(f"{standin_shape}.mode", 3)
