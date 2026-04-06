import json
import os
import re
import shutil
import socket
import sys
from pathlib import Path

import win32com.client
from proxy_creator_logger import get_logger
from PySide6.QtCore import QProcess
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QLineEdit,
    QListWidget,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

CURRENT_FOLDER = Path(__file__).parent.as_posix()
GRANDPARENT_FOLDER = Path(__file__).parents[1].as_posix()
DATA_FILE = f"{CURRENT_FOLDER}/data/data.json"

logger = get_logger()


# -----------------------------------------------------------------------------------#
# ------------------------- Windows Explorer Item Selection -------------------------#
def get_selected_items() -> list[str]:
    """Retrieve selected items from Windows Explorer.

    Returns:
        List of file paths currently selected in File Explorer.

    """
    shell = win32com.client.Dispatch("Shell.Application")
    selected_items = []

    for window in shell.Windows():
        if window.Name == "File Explorer":
            try:
                selection = window.Document.SelectedItems()
                selected_items.extend([item.Path for item in selection])
            except AttributeError:
                continue

    return selected_items


# -------------------------------------------------------------------#
# ------------------------ PySide GUI CLASS -------------------------#
# -------------------------------------------------------------------#
class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.started = False
        self.maya_socket = None
        self.cmd_process = QProcess(self)

        # instance variables shared across methods
        self.filepaths: list[str] = []
        self.proxy_folder: str = ""

        self.setWindowTitle("Megascans to Arnold Proxy")
        self.resize(800, 600)
        self.setWindowIcon(QIcon(f"{CURRENT_FOLDER}/icons/lion_head1_icon.jpg"))

        main_layout = QVBoxLayout(self)
        folder_layout = QHBoxLayout()
        addremove_layout = QHBoxLayout()

        self.tex_res_combo = QComboBox()
        self.tex_res_combo.addItems(["2K", "4K"])
        folder_layout.addWidget(self.tex_res_combo)

        self.tex_ext_combo = QComboBox()
        self.tex_ext_combo.addItems([".jpg", ".png"])
        folder_layout.addWidget(self.tex_ext_combo)

        self.browse_btn = QPushButton("Select Folder")
        self.browse_btn.clicked.connect(self.select_save_folder)
        folder_layout.addWidget(self.browse_btn)

        self.folder_line_edit = QLineEdit()
        self.folder_line_edit.setReadOnly(True)
        folder_layout.addWidget(self.folder_line_edit)

        self.save_proxies_btn = QPushButton("Export Objects ->")
        self.save_proxies_btn.clicked.connect(self.save_proxies_launch)
        folder_layout.addWidget(self.save_proxies_btn)

        main_layout.addLayout(folder_layout)

        self.add_btn = QPushButton("Add File Paths")
        self.add_btn.clicked.connect(self.add_selected_items_main)
        addremove_layout.addWidget(self.add_btn)

        self.remove_btn = QPushButton("Remove File Paths")
        self.remove_btn.clicked.connect(self.remove_selected_items_main)
        addremove_layout.addWidget(self.remove_btn)

        main_layout.addLayout(addremove_layout)

        self.list_widget_main = QListWidget()
        self.list_widget_main.setSelectionMode(QListWidget.MultiSelection)
        main_layout.addWidget(self.list_widget_main)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        main_layout.addWidget(self.progress_bar)

        self.import_proxies_btn = QPushButton("Import Proxies to Maya (Port 7001)")
        self.import_proxies_btn.clicked.connect(self.proxy_import_launch)
        main_layout.addWidget(self.import_proxies_btn)

        self.add_selected_items_main()
        self.load_data()
        self.folder_line_edit.setText(self.proxy_folder)

    # ------------------------- DATA FILE (filepaths + metadata) -------------------------#
    def load_data(self) -> None:
        """Load filepaths and proxy folder path from the combined data file into instance variables."""
        try:
            with open(DATA_FILE) as f:
                data = json.load(f)
        except FileNotFoundError:
            data = {"filepaths": [], "proxy_folder_path": ""}
            with open(DATA_FILE, "w") as f:
                json.dump(data, f, indent=4)

        self.filepaths = data.get("filepaths", [])
        self.proxy_folder = data.get("proxy_folder_path", "")

    def save_data(self) -> None:
        """Save self.filepaths and self.proxy_folder to the combined data file."""
        with open(DATA_FILE, "w") as f:
            json.dump(
                {"filepaths": self.filepaths, "proxy_folder_path": self.proxy_folder},
                f,
                indent=4,
            )

    def refresh_list_widget(self) -> None:
        """Sync the list widget display with self.filepaths."""
        self.list_widget_main.clear()
        self.list_widget_main.addItems(self.filepaths)

    # ------------------------- MAIN LIST ITEMS -------------------------#
    def add_selected_items_main(self) -> None:
        """Add Explorer-selected filepaths to the list and save."""
        if self.started:
            new_filepaths = get_selected_items()
        else:
            new_filepaths = []
            self.started = True

        self.load_data()
        self.filepaths = sorted(set(self.filepaths + new_filepaths))
        logger.info(f"{self.filepaths = }")
        self.save_data()
        self.refresh_list_widget()

    # ------------------------- REMOVE MAIN LIST ITEMS -------------------------#
    def remove_selected_items_main(self) -> None:
        """Remove selected items from the list and save."""
        selected = {item.text() for item in self.list_widget_main.selectedItems()}
        self.filepaths = sorted(fp for fp in self.filepaths if fp not in selected)
        self.save_data()
        self.refresh_list_widget()

    # ------------------------- Save To Folder Path -------------------------#
    def select_save_folder(self) -> None:
        """Open a dialog to select the proxy save folder and persist the choice."""
        folder_path = QFileDialog.getExistingDirectory(
            self,
            "Select Folder to Save Proxies",
            os.getcwd(),
        )
        if folder_path:
            self.proxy_folder = folder_path
            self.folder_line_edit.setText(self.proxy_folder)
            self.save_data()

    # ------------------------- Copy Images to Proxy Folder -------------------------#
    def copy_images_over(self) -> None:
        """Copy texture images to custom proxy folder."""
        tex_res = f"_{self.tex_res_combo.currentText()}"
        tex_ext = f"{self.tex_ext_combo.currentText()}"

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
            logger.info(f'Needs "fbx/obj" ext or doesnt exist. Skipped: {filepath}')

        for fbxobj_path in valid_filepaths:
            fbxobj_stem = fbxobj_path.stem
            lod_suffix = f"_{fbxobj_stem.split('_')[-1]}"
            base_name = fbxobj_stem.replace(lod_suffix, "")
            parent_folder_name = re.sub(r"\s+", "", fbxobj_path.parent.name)
            if parent_folder_name[0].isdigit():
                parent_folder_name = parent_folder_name.replace("3d_", "")

            item_proxy_folder = Path(self.proxy_folder) / parent_folder_name
            item_proxy_folder.mkdir(parents=True, exist_ok=True)

            # --- copy fbx/obj source file ---
            self.copy_file(
                fbxobj_path,
                item_proxy_folder / fbxobj_path.name,
                "FBX MODEL",
            )

            # --- color and roughness maps ---
            for label, tex_suffix in [
                ("COLOR MAP", "_Albedo"),
                ("ROUGHNESS MAP", "_Roughness"),
            ]:
                tex_name = f"{base_name}{tex_res}{tex_suffix}"
                source = fbxobj_path.parent / f"{tex_name}{tex_ext}"
                destination = item_proxy_folder / f"{tex_name}{tex_ext}"
                self.copy_file(source, destination, label)

            # --- normal map: try lod suffix, then no suffix, then LOD0-5 ---
            normal_candidates = [
                f"{base_name}{tex_res}_Normal{lod_suffix}",
                f"{base_name}{tex_res}_Normal",
                *[f"{base_name}{tex_res}_Normal_LOD{i}" for i in range(6)],
            ]

            source_normal = next(
                (
                    fbxobj_path.parent / f"{candidate}{tex_ext}"
                    for candidate in normal_candidates
                    if (fbxobj_path.parent / f"{candidate}{tex_ext}").is_file()
                ),
                None,
            )

            if source_normal:
                self.copy_file(
                    source_normal,
                    item_proxy_folder / source_normal.name,
                    "NORMAL MAP",
                )
            else:
                logger.warning(f"No NORMAL MAP: {fbxobj_path}")

    def copy_file(
        self,
        source: Path,
        destination: Path,
        label: str,
    ) -> None:
        """Copy a texture file if the source exists and the destination does not.

        Args:
            source: Source texture file path to copy from.
            destination: Destination file path to copy to.
            label: Texture type label used in print messages (e.g. "COLOR", "NORMAL").

        """
        if source.is_file():
            if destination.is_file():
                logger.info(f"Skipping. Already exists: {destination}")
            else:
                shutil.copy2(source, destination)
        else:
            logger.warning(f"No {label}: {source}")

    # ------------------------- Create Proxies CMD Methods -------------------------#
    def run_with_progress(self, func, progress_value: int) -> None:
        """Run a function and update the progress bar afterward.

        Args:
            func: The function to call.
            progress_value: Progress bar value to set after the function completes (0-100).

        """
        func()
        self.progress_bar.setValue(progress_value)

    def save_proxies_launch(self) -> None:
        """Copy images over and export proxies to the save folder."""
        self.progress_bar.setValue(0)
        self.save_proxies_btn.setEnabled(False)
        self.run_with_progress(self.copy_images_over, 50)
        self.run_with_progress(self.create_proxy_cmd, 100)
        self.save_proxies_btn.setEnabled(True)

    def create_proxy_cmd(self) -> None:
        """Launch the proxy creation batch script via QProcess."""
        cmd_path = Path(CURRENT_FOLDER) / "create_proxy_batch.cmd"
        if not cmd_path.is_file():
            logger.error(f"No CMD File Path: {cmd_path}")
            return

        if self.cmd_process.state() == QProcess.Running:
            self.cmd_process.close()

        logger.info(f"Starting process: {cmd_path}")
        self.cmd_process.start("cmd.exe", ["/k", str(cmd_path)])

    # ------------------------- Import Proxies To Maya -------------------------#
    def proxy_import_launch(self) -> None:
        """Build and send the Maya import command using self.filepaths."""
        command = (
            "import sys\n"
            f"if '{GRANDPARENT_FOLDER}' not in sys.path:\n"
            f"  sys.path.append('{GRANDPARENT_FOLDER}')\n"
            "from proxy_creator_main import proxy_import\n"
            "import importlib\n"
            "importlib.reload(proxy_import)\n"
            f"proxy_import.import_proxy({self.filepaths})\n"
        )
        self.send_to_maya(command)

    def send_to_maya(self, command: str) -> None:
        """Send a Python command string to Maya via socket on port 7001.

        Run this in Maya first:
            cmds.commandPort(name=":7001", sourceType="python", echoOutput=True)

        Args:
            command: The Python command string to execute in Maya.

        """
        maya_port = 7001
        try:
            logger.info(f"Connecting to Maya on port {maya_port}...")
            self.maya_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.maya_socket.connect(("127.0.0.1", maya_port))
            logger.info(f"Sending command: {command}")
            self.maya_socket.sendall(command.encode("utf-8"))
            logger.info("Command sent successfully.")
        except Exception as e:
            logger.warning(f"Error connecting to Maya: {e}")

    def closeEvent(self, event) -> None:
        """Handle cleanup when the window closes. Native PySide method.

        Args:
            event: The close event passed by PySide.

        """
        if self.maya_socket:
            logger.info("Closing Maya socket...")
            self.maya_socket.close()
            self.maya_socket = None
            logger.info("Socket closed.")
        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
