import json
import os
import re
import sys
from pathlib import Path

parent = str(Path(os.getcwd()).parents[0])
if parent not in sys.path:
    sys.path.append(parent)

from maya import cmds

from proxy_creator_main.proxy_creator_logger import get_logger

logger = get_logger()


CURRENT_FOLDER = Path.cwd().as_posix()
DATA_FILE = f"{CURRENT_FOLDER}/data/data.json"


class CreateArnoldProxy:
    def __init__(self) -> None:
        self.filepaths: list[str] = []
        self.proxy_folder: str = ""

    # ------------------------- LAUNCH -------------------------#
    def create_proxy_launch(self) -> None:
        """Load data and run proxy creation for all valid FBX filepaths."""
        self.load_data()

        path_filepaths = [Path(fp) for fp in self.filepaths]
        valid_filepaths = [
            fp
            for fp in path_filepaths
            if fp.suffix in (".fbx", ".obj") and fp.is_file()
        ]
        invalid_filepaths = [
            fp
            for fp in path_filepaths
            if fp.suffix not in (".fbx", ".obj") or not fp.is_file()
        ]
        for filepath in invalid_filepaths:
            logger.info(
                f'Needs "fbx/obj" ext or doesnt exist. Skipped: {filepath}',
            )

        for filepath in valid_filepaths:
            try:
                logger.info(f"Processing: {filepath}")
                self.create_proxy(filepath)
            except Exception as e:
                logger.warning(f"Processing failed: {filepath}, {e}")

    # ------------------------- DATA FILE -------------------------#
    def load_data(self) -> None:
        """Load filepaths and proxy folder path from the combined data file into instance variables."""
        with open(DATA_FILE) as f:
            data = json.load(f)

        self.filepaths = data.get("filepaths", [])
        self.proxy_folder = data.get("proxy_folder_path", "")

    # ------------------------- CREATE PROXY -------------------------#
    def create_proxy(self, fbxobj_filepath: str) -> None:
        """Run the full proxy creation pipeline for a single FBX file.

        Args:
            fbxobj_filepath: Full file path to the source FBX file.

        """
        self.fbxobj_stem = Path(fbxobj_filepath).stem
        self.lod_suffix = f"_{self.fbxobj_stem.split('_')[-1]}"
        self.prnt_folder_name = re.sub(r"\s+", "", Path(fbxobj_filepath).parent.name)
        if self.prnt_folder_name[0].isdigit():
            self.prnt_folder_name = self.prnt_folder_name.replace("3d_", "")
        self.prnt_folder_name_lod = f"{self.prnt_folder_name}{self.lod_suffix}"
        self.prnt_name_stripped = self.prnt_folder_name.split("_")
        self.prnt_name_stripped = [
            self.cap(txt) for txt in self.prnt_name_stripped if txt
        ]
        self.prnt_name_stripped = "".join(self.prnt_name_stripped)
        self.prnt_name_stripped_lod = f"{self.prnt_name_stripped}{self.lod_suffix}"

        cmds.file(new=True, force=True)
        self.import_fbxobj(fbxobj_filepath)
        self.rename_objects()

        self.create_texture_nodes()
        self.create_material()
        self.assign_material()
        self.reset_soften_normals()
        self.export_proxy()
        self.save_maya_file()

    def import_fbxobj(self, fbxobj_filepath: str) -> None:
        """Import an FBX or OBJ file into the current Maya scene.

        Args:
            fbxobj_filepath: Full file path to the FBX/OBJ file to import.

        """
        if not cmds.pluginInfo("fbxmaya", q=True, loaded=True):
            cmds.loadPlugin("fbxmaya")

        self.imported_nodes = cmds.file(
            fbxobj_filepath,
            i=True,
            ignoreVersion=True,
            mergeNamespacesOnClash=True,
            returnNewNodes=True,
        )
        logger.info(f"Imported FBX/OBJ file: {fbxobj_filepath}")
        logger.info(f"Imported nodes: {self.imported_nodes}")

    def rename_objects(self) -> None:
        """Rename import mesh objects."""
        imported_meshes = [
            nd for nd in self.imported_nodes if cmds.objectType(nd) == "mesh"
        ]
        imported_meshes = [
            cmds.listRelatives(nd, parent=True)[0] for nd in imported_meshes
        ]
        imported_meshes = list(set(imported_meshes))

        self.scene_meshes = []
        if len(imported_meshes) == 1:
            mesh = cmds.rename(imported_meshes[0], f"{self.prnt_name_stripped_lod}_geo")
            self.scene_meshes.append(mesh)
        else:
            for i, mesh in enumerate(imported_meshes, 1):
                mesh = cmds.rename(
                    mesh,
                    f"{self.prnt_name_stripped}{self.lod_suffix}v{i:02d}_geo",
                )
                self.scene_meshes.append(mesh)

    def create_texture_nodes(self):
        """Find texture files in the proxy folder and create Maya file texture nodes."""
        tex_folder = Path(self.proxy_folder) / self.prnt_folder_name

        color_filepath = None
        roughness_filepath = None
        color_name = ""
        roughness_name = ""
        normal_candidates = []

        for filepath in tex_folder.iterdir():
            if not filepath.is_file() or ".tx" in filepath.name:
                continue
            stem = filepath.stem
            if "_Albedo" in stem:
                color_filepath = filepath
                color_name = f"{self.prnt_name_stripped}Albedo"
            elif "_Roughness" in stem:
                roughness_filepath = filepath
                roughness_name = f"{self.prnt_name_stripped}Roughness"
            elif "_Normal" in stem:
                normal_candidates.append(filepath)

        # prefer lod-specific normal, then generic, then first available
        normal_filepath = (
            next((fp for fp in normal_candidates if self.lod_suffix in fp.name), None)
            or next(
                (fp for fp in normal_candidates if self.lod_suffix not in fp.name),
                None,
            )
            or normal_candidates[0]
        )
        normal_name = f"{self.prnt_name_stripped}Normal"

        self.create_2dplace_node()
        color_node = self.create_texture_node(color_name, color_filepath)
        roughness_node = self.create_texture_node(roughness_name, roughness_filepath)
        normal_node = self.create_texture_node(normal_name, normal_filepath)

        self.color_node = color_node
        self.roughness_node = roughness_node
        self.normal_node = normal_node

    def create_texture_node(self, base_name: str, filepath: str) -> str:
        """Create a Maya file texture node with a connected place2dTexture node.

        Args:
            base_name: Name used for the file and place2dTexture nodes.
            filepath: Full path to the texture file to load.

        Returns:
            Name of the created file texture node.

        """
        file_node = cmds.shadingNode(
            "file",
            asTexture=True,
            isColorManaged=True,
            name=f"{base_name}{self.lod_suffix}_file",
        )
        cmds.setAttr(f"{file_node}.fileTextureName", filepath, type="string")

        connections = [
            ("coverage", "coverage"),
            ("translateFrame", "translateFrame"),
            ("rotateFrame", "rotateFrame"),
            ("mirrorU", "mirrorU"),
            ("mirrorV", "mirrorV"),
            ("stagger", "stagger"),
            ("wrapU", "wrapU"),
            ("wrapV", "wrapV"),
            ("repeatUV", "repeatUV"),
            ("offset", "offset"),
            ("rotateUV", "rotateUV"),
            ("noiseUV", "noiseUV"),
            ("vertexUvOne", "vertexUvOne"),
            ("vertexUvTwo", "vertexUvTwo"),
            ("vertexUvThree", "vertexUvThree"),
            ("vertexCameraOne", "vertexCameraOne"),
            ("outUV", "uvCoord"),
            ("outUvFilterSize", "uvFilterSize"),
        ]
        for place2d_attr, file_attr in connections:
            cmds.connectAttr(
                f"{self.place2d_node}.{place2d_attr}",
                f"{file_node}.{file_attr}",
                force=True,
            )

        return file_node

    def create_2dplace_node(self) -> str:
        """Create place2dTexture node to be shared between image file nodes.

        Returns:
           Name of place2dTexture node.

        """
        self.place2d_node = cmds.shadingNode(
            "place2dTexture",
            asUtility=True,
            name=f"{self.prnt_name_stripped}{self.lod_suffix}_place2dTexture",
        )

    def create_material(self) -> str:
        """Create an openPBR material and connect color, roughness, and normal textures.

        Returns:
            Name of the created PBR material node.

        """
        openpbr_mat = cmds.shadingNode(
            "openPBRSurface",
            asShader=True,
            name=f"{self.prnt_name_stripped}{self.lod_suffix}_mat",
        )
        openpbr_matsg = cmds.sets(
            renderable=True,
            noSurfaceShader=True,
            empty=True,
            name=f"{self.prnt_name_stripped}{self.lod_suffix}_matSG",
        )
        cmds.connectAttr(
            f"{openpbr_mat}.outColor",
            f"{openpbr_matsg}.surfaceShader",
            force=True,
        )

        # connect color texture
        cmds.connectAttr(
            f"{self.color_node}.outColor",
            f"{openpbr_mat}.baseColor",
            force=True,
        )

        # connect roughness texture
        cmds.connectAttr(
            f"{self.roughness_node}.outAlpha",
            f"{openpbr_mat}.specularRoughness",
            force=True,
        )
        cmds.setAttr(f"{self.roughness_node}.ignoreColorSpaceFileRules", True)
        cmds.setAttr(f"{self.roughness_node}.colorSpace", "Raw", type="string")
        cmds.setAttr(f"{self.roughness_node}.alphaIsLuminance", 1)

        # connect normal texture
        normal_map_node = cmds.shadingNode(
            "aiNormalMap",
            asShader=True,
            name=f"{self.normal_node.replace('_file', '')}_aiNormalMap",
        )
        cmds.connectAttr(
            f"{self.normal_node}.outColor",
            f"{normal_map_node}.input",
            force=True,
        )
        cmds.connectAttr(
            f"{normal_map_node}.outValue",
            f"{openpbr_mat}.normalCamera",
            force=True,
        )
        cmds.setAttr(f"{self.normal_node}.ignoreColorSpaceFileRules", True)
        cmds.setAttr(f"{self.normal_node}.colorSpace", "Raw", type="string")

        self.openpbr_mat = openpbr_mat

    def assign_material(self) -> None:
        """Assign a material to mesh objects in the scene."""
        for mesh in self.scene_meshes:
            cmds.hyperShade(geometries=mesh, assign=self.openpbr_mat)
            logger.info(f"Assigend material: {self.openpbr_mat} ->  {mesh}")

    def reset_soften_normals(self) -> None:
        """Reset normals to face normals and apply 180-degree softening on all meshes in the scene."""
        for mesh in self.scene_meshes:
            vertex_count = cmds.polyEvaluate(mesh, vertex=True)
            cmds.select(f"{mesh}.vtx[0:{vertex_count - 1}]")
            cmds.polySetToFaceNormal()
            cmds.polySoftEdge(mesh, a=180, ch=0)
            logger.info(f"Normals set to face and softened: {mesh}")

    def export_proxy(self) -> None:
        """Export each mesh in the scene as an Arnold .ass proxy file to self.proxy_folder."""
        if len(self.scene_meshes) == 1:
            export_filepath = (
                Path(self.proxy_folder) / f"{self.prnt_folder_name}.ass"
            )
            cmds.arnoldExportAss(self.scene_meshes, filename=export_filepath)
        else:
            for i, mesh in enumerate(self.scene_meshes, 1):
                export_filepath = (
                    Path(self.proxy_folder)
                    / f"{self.prnt_folder_name}_v{i:02d}.ass"
                )
                cmds.select(clear=True)
                cmds.select(mesh)
                cmds.arnoldExportAss(filename=export_filepath, selected=True)
        logger.info(f"Exported proxy: {self.scene_meshes}")

    def save_maya_file(self) -> None:
        """Save the current Maya scene as a .ma file in the proxy subfolder."""
        save_path = (
            Path(self.proxy_folder)
            / self.prnt_folder_name
            / f"{self.prnt_folder_name_lod}.ma"
        )
        cmds.file(rename=save_path)
        cmds.file(save=True, type="mayaAscii")

    def cap(self, text: str) -> str:
        """Capitalize only first letter in a string."""
        return text[0].upper() + text[1:] if text else text


if __name__ == "__main__":
    CreateArnoldProxy().create_proxy_launch()
