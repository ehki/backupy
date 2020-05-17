# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.

# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

# https://github.com/elesiuta/backupy

import os
import shutil

from .config import ConfigObject
from .dirinfo import DirInfo
from .logman import LogManager
from .statusbar import StatusBar
from .utils import getString


class FileManager:
    # expose the copy function as a class attribute for easy monkey-patching
    copy_function = shutil.copy2

    def __init__(self, config: ConfigObject, source: DirInfo, dest: DirInfo, log: LogManager, backup_time: int, gui: bool):
        """Provides file operation methods (used by BackupManager)"""
        # init variables
        self.log = log
        self.backup_time = backup_time
        self.gui = gui
        self.config = config
        self.source = source
        self.dest = dest

    ##########################################################################
    # Basic file operation methods (only these methods touch files directly) #
    ##########################################################################

    def _removeFile(self, root_path: str, file_relative_path: str) -> None:
        try:
            self.log.append(["Remove:", root_path, file_relative_path])
            self.source.updateDictOnRemove(root_path, file_relative_path, self.dest)
            if not self.config.dry_run:
                path = os.path.join(root_path, file_relative_path)
                if os.path.isdir(path):
                    os.rmdir(path)
                else:
                    os.remove(path)
                if self.config.cleanup_empty_dirs:
                    head = os.path.dirname(path)
                    if len(os.listdir(head)) == 0:
                        os.removedirs(head)
        except Exception as e:
            self.log.append(["REMOVE ERROR", root_path, file_relative_path, str(e)])
            print(e)

    def _copyFile(self, source_root: str, dest_root: str, source_file: str, dest_file: str) -> None:
        try:
            self.log.append(["Copy:", source_root, source_file, dest_root, dest_file])
            self.source.updateDictOnCopy(source_root, dest_root, source_file, dest_file, self.dest)
            if not self.config.dry_run:
                source = os.path.join(source_root, source_file)
                dest = os.path.join(dest_root, dest_file)
                if os.path.isdir(source):
                    os.makedirs(dest)
                else:
                    if not os.path.isdir(os.path.dirname(dest)):
                        os.makedirs(os.path.dirname(dest))
                    FileManager.copy_function(source, dest)
                    if self.config.verify_copy:
                        self.source.verifyCrcOnCopy(source_root, dest_root, source_file, dest_file, self.dest)
        except Exception as e:
            self.log.append(["COPY ERROR", source_root, source_file, dest_root, dest_file, str(e)])
            print(e)

    def _moveFile(self, source_root: str, dest_root: str, source_file: str, dest_file: str) -> None:
        try:
            self.log.append(["Move:", source_root, source_file, dest_root, dest_file])
            self.source.updateDictOnMove(source_root, dest_root, source_file, dest_file, self.dest)
            if not self.config.dry_run:
                source = os.path.join(source_root, source_file)
                dest = os.path.join(dest_root, dest_file)
                if not os.path.isdir(os.path.dirname(dest)):
                    os.makedirs(os.path.dirname(dest))
                shutil.move(source, dest)
                if self.config.cleanup_empty_dirs:
                    head = os.path.dirname(source)
                    if len(os.listdir(head)) == 0:
                        os.removedirs(head)
        except Exception as e:
            self.log.append(["MOVE ERROR", source_root, source_file, dest_root, dest_file, str(e)])
            print(e)

    ##########################################################################
    # Batch file operation methods (do not perform file operations directly) #
    ##########################################################################

    def _removeFiles(self, root_path: str, file_relative_paths: list) -> None:
        if file_relative_paths:
            self.log.colourPrint(getString("Removing %s unique files from:\n%s") % (len(file_relative_paths), root_path), "OKBLUE")
            for f in file_relative_paths:
                self._removeFile(root_path, f)
            self.log.colourPrint(getString("Removal completed!"), "NONE")

    def copyFiles(self, source_root: str, dest_root: str, source_files: str, dest_files: str) -> None:
        if source_files:
            self.log.colourPrint(getString("Copying %s unique files from:\n%s\nto:\n%s") % (len(source_files), source_root, dest_root), "OKBLUE")
            copy_status = StatusBar("Copying", len(source_files), self.config.stdout_status_bar, gui=self.gui)
            for i in range(len(source_files)):
                copy_status.update(source_files[i])
                self._copyFile(source_root, dest_root, source_files[i], dest_files[i])
            copy_status.endProgress()

    def _moveFiles(self, source_root: str, dest_root: str, source_files: str, dest_files: str) -> None:
        if source_files:
            self.log.colourPrint(getString("Archiving %s unique files from:\n%s") % (len(source_files), source_root), "OKBLUE")
            for i in range(len(source_files)):
                self._moveFile(source_root, dest_root, source_files[i], dest_files[i])
            self.log.colourPrint(getString("Archiving completed!"), "NONE")

    def handleDeletedFiles(self, root_path: str, file_relative_paths: list) -> None:
        if file_relative_paths:
            if self.config.noarchive:
                self._removeFiles(root_path, file_relative_paths)
            else:
                recycle_bin = os.path.join(root_path, self.config.trash_dir, self.backup_time)
                self._moveFiles(root_path, recycle_bin, file_relative_paths, file_relative_paths)

    def handleMovedFiles(self, moved_pairs: list, reverse: bool = False) -> None:
        if moved_pairs and not self.config.nomoves:
            # conflicts shouldn't happen since moved is a subset of files from source_only and dest_only
            # depends on source_info.dirCompare(dest_info) otherwise source and dest keys will be reversed
            self.log.colourPrint(getString("Moving %s files on destination to match source") % (len(moved_pairs)), "OKBLUE")
            for f in moved_pairs:
                if reverse:
                    dest = self.config.source
                    oldLoc = f["source"]
                    newLoc = f["dest"]
                else:
                    dest = self.config.dest
                    oldLoc = f["dest"]
                    newLoc = f["source"]
                self._moveFile(dest, dest, oldLoc, newLoc)
            self.log.colourPrint(getString("Moving completed!"), "NONE")

    def _archiveFile(self, root_path: str, file_relative_path: str) -> None:
        if not self.config.noarchive:
            archive_path = os.path.join(root_path, self.config.archive_dir, self.backup_time)
            self._moveFile(root_path, archive_path, file_relative_path, file_relative_path)

    def handleChangedFiles(self, source_root: str, dest_root: str, source_dict: dict, dest_dict: dict, changed: list) -> None:
        if changed:
            self.log.colourPrint(getString("Handling %s file changes per selection mode") % (len(changed)), "OKBLUE")
            copy_status = StatusBar("Copying", len(changed), self.config.stdout_status_bar, gui=self.gui)
            for frp in changed:
                copy_status.update(frp)
                if self.config.select_mode == "source":
                    self._archiveFile(dest_root, frp)
                    self._copyFile(source_root, dest_root, frp, frp)
                elif self.config.select_mode == "dest":
                    self._archiveFile(source_root, frp)
                    self._copyFile(dest_root, source_root, frp, frp)
                elif self.config.select_mode == "new":
                    if source_dict[frp]["mtime"] > dest_dict[frp]["mtime"]:
                        self._archiveFile(dest_root, frp)
                        self._copyFile(source_root, dest_root, frp, frp)
                    else:
                        self._archiveFile(source_root, frp)
                        self._copyFile(dest_root, source_root, frp, frp)
                else:
                    break
            copy_status.endProgress()
