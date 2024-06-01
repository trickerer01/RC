# coding=UTF-8
"""
Author: trickerer (https://github.com/trickerer, https://github.com/trickerer01)
"""
#########################################
#
#

from os import path, listdir, rename
from typing import List, Optional, Dict

from config import Config
from defs import MAX_DEST_SCAN_SUB_DEPTH
from logger import Log
from rex import re_album_foldername
from scenario import DownloadScenario
from util import normalize_path

__all__ = ('folder_already_exists', 'scan_dest_folder', 'try_rename')

found_foldernames_dict = dict()  # type: Dict[str, List[str]]


def scan_dest_folder() -> None:
    """
    Scans base destination folder plus {MAX_DEST_SCAN_SUB_DEPTH} levels of subfolders and
    stores found subfolders in dict (key=folder_name)\n\n
    |folder1:\n\n
    |__subfolder1:\n\n
    |____subfolder2\n\n
    |____subfolder3\n\n
    => files{'folder1': ['subfolder1'], 'subfolder1': ['subfolder2','subfolder3']}\n\n
    This function may only be called once!
    """
    assert len(found_foldernames_dict.keys()) == 0
    if path.isdir(Config.dest_base):
        Log.info('Scanning dest folder...')
        dest_base = path.abspath(Config.dest_base)
        scan_depth = MAX_DEST_SCAN_SUB_DEPTH + Config.folder_scan_levelup
        for _ in range(Config.folder_scan_levelup):
            longpath, dirname = path.split(path.abspath(dest_base))
            dest_base = normalize_path(longpath)
            if dirname == '':
                break

        def scan_folder(base_folder: str, level: int) -> None:
            for cname in listdir(base_folder):
                fullpath = f'{base_folder}{cname}'
                if path.isdir(fullpath):
                    fullpath = normalize_path(fullpath)
                    if level < scan_depth:
                        found_foldernames_dict[fullpath] = list()
                        scan_folder(fullpath, level + 1)
                    pass
                    found_foldernames_dict[base_folder].append(cname)

        found_foldernames_dict[dest_base] = list()
        scan_folder(dest_base, 0)
        if Config.dest_base not in found_foldernames_dict:
            found_foldernames_dict[Config.dest_base] = list()
            scan_folder(Config.dest_base, 0)
        base_folders_count = len(found_foldernames_dict[dest_base])
        total_files_count = sum(len(li) for li in found_foldernames_dict.values())
        Log.info(f'Found {base_folders_count:d} folder(s) in base and '
                 f'{total_files_count - base_folders_count:d} folder(s) in {len(found_foldernames_dict.keys()) - 1:d} subfolder(s) '
                 f'(total folders: {total_files_count:d}, scan depth: {scan_depth:d})')


def folder_exists_in_folder(base_folder: str, idi: int) -> str:
    orig_folder_names = found_foldernames_dict.get(normalize_path(base_folder))
    if path.isdir(base_folder) and orig_folder_names is not None:
        for fname in orig_folder_names:
            try:
                f_match = re_album_foldername.match(fname)
                f_id = f_match.group(1)
                if str(idi) == f_id:
                    return f'{normalize_path(base_folder)}{fname}'
            except Exception:
                continue
    return ''


def folder_already_exists(idi: int) -> str:
    scenario = Config.scenario  # type: Optional[DownloadScenario]
    if scenario:
        for q in scenario.queries:
            fullpath = folder_exists_in_folder(f'{Config.dest_base}{q.subfolder}', idi)
            if len(fullpath) > 0:
                return fullpath
    else:
        for fullpath in found_foldernames_dict:
            fullpath = folder_exists_in_folder(fullpath, idi)
            if len(fullpath) > 0:
                return fullpath
    return ''


def try_rename(oldpath: str, newpath: str) -> bool:
    try:
        rename(oldpath, newpath)
        return True
    except Exception:
        return False

#
#
#########################################
