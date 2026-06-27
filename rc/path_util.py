# coding=UTF-8
"""
Author: trickerer (https://github.com/trickerer, https://github.com/trickerer01)
"""
#########################################
#
#

import os

from .config import Config
from .defs import DEFAULT_EXT, PREFIX
from .logger import Log
from .rex import re_album_foldername
from .util import normalize_path

__all__ = ('folder_already_exists', 'folder_already_exists_arr', 'scan_dest_folder', 'try_rename')

_found_foldernames_dict: dict[str, list[str]] = {}
_foldername_matches_cache: dict[str, str] = {}


def _report_duplicates() -> None:
    found_vs = dict[str, list[str]]()
    fvks = list[str]()
    for k, filenames in _found_foldernames_dict.items():
        if not filenames:
            continue
        for fname in filenames:
            if not fname.startswith(PREFIX):
                continue
            fm = re_album_foldername.fullmatch(fname)
            if fm:
                fid = fm.group(1)
                if fid not in found_vs:
                    found_vs[fid] = []
                elif fid not in fvks:
                    fvks.append(fid)
                found_vs[fid].append(k + fname)
    if fvks:
        Log.info('Duplicates found:')
        n = '\n  - '
        for kk in fvks:
            Log.info(f' {PREFIX}{kk}.{DEFAULT_EXT}:{n}{n.join(found_vs[kk])}')
    else:
        Log.info('No duplicates found')


def scan_dest_folder() -> None:
    """
    Scans base destination folder plus {Config.folder_scan_depth} levels of subfolders and
    stores found subfolders in dict (key=folder_name)\n
    |folder1:
    |__subfolder1:
    |____subfolder2
    |____subfolder3
    => files{'folder1': ['subfolder1'], 'subfolder1': ['subfolder2','subfolder3']}\n
    This function may only be called once!
    """
    assert len(_found_foldernames_dict.keys()) == 0
    if os.path.isdir(Config.dest_base) or Config.folder_scan_levelup:
        Log.info('Scanning dest folder...')
        dest_base = Config.dest_base
        scan_depth = Config.folder_scan_depth + Config.folder_scan_levelup
        for _ in range(Config.folder_scan_levelup):
            longpath, dirname = os.path.split(os.path.abspath(dest_base))
            dest_base = normalize_path(longpath)
            if not dirname:
                break

        def _scan_folder(base_folder: str, level: int) -> None:
            if os.path.isdir(base_folder):
                with os.scandir(base_folder) as listing:
                    for dentry in listing:
                        fullpath = f'{base_folder}{dentry.name}'
                        if dentry.is_dir():
                            fullpath = normalize_path(fullpath)
                            if level < scan_depth:
                                _found_foldernames_dict[fullpath] = []
                                _scan_folder(fullpath, level + 1)
                            pass
                            _found_foldernames_dict[base_folder].append(dentry.name)

        _found_foldernames_dict[dest_base] = []
        _scan_folder(dest_base, 0)
        if Config.dest_base not in _found_foldernames_dict:
            _found_foldernames_dict[Config.dest_base] = []
            _scan_folder(Config.dest_base, Config.folder_scan_levelup)
        base_folders_count = len(_found_foldernames_dict[dest_base])
        total_files_count = sum(len(li) for li in _found_foldernames_dict.values())
        Log.info(f'Found {base_folders_count:d} folder(s) in base and '
                 f'{total_files_count - base_folders_count:d} folder(s) in {len(_found_foldernames_dict.keys()) - 1:d} subfolder(s) '
                 f'(total folders: {total_files_count:d}, scan depth: {scan_depth:d})')

    if Config.report_duplicates:
        _report_duplicates()


def _get_foldername_match(fname: str) -> str:
    if fname not in _foldername_matches_cache:
        f_match = re_album_foldername.match(fname)
        f_id = f_match.group(1) if f_match else ''
        _foldername_matches_cache[fname] = f_id
    return _foldername_matches_cache[fname]


def _folder_exists_in_folder(base_folder: str, idi: int, check_folder: bool) -> str:
    orig_folder_names = _found_foldernames_dict.get(base_folder)
    if (not check_folder or os.path.isdir(base_folder)) and orig_folder_names is not None:
        for fname in orig_folder_names:
            f_id = _get_foldername_match(fname)
            if f_id and str(idi) == f_id:
                return f'{normalize_path(base_folder)}{fname}'
    return ''


def folder_already_exists(idi: int, check_folder=True) -> str:
    for fullpath in _found_foldernames_dict:
        fullpath = _folder_exists_in_folder(fullpath, idi, check_folder)
        if len(fullpath) > 0:
            return fullpath
    return ''


def _folder_exists_in_folder_arr(base_folder: str, idi: int) -> list[str]:
    orig_folder_names = _found_foldernames_dict.get(base_folder)
    folder_folders: list[str] = []
    if os.path.isdir(base_folder) and orig_folder_names is not None:
        for fname in orig_folder_names:
            f_id = _get_foldername_match(fname)
            if f_id and str(idi) == f_id:
                folder_folders.append(f'{normalize_path(base_folder)}{fname}')
    return folder_folders


def folder_already_exists_arr(idi: int) -> list[str]:
    found_folders: list[str] = []
    for fullpath in _found_foldernames_dict:
        found_folders.extend(_folder_exists_in_folder_arr(fullpath, idi))
    return found_folders


def try_rename(oldpath: str, newpath: str) -> bool:
    try:
        if oldpath == newpath:
            return True
        newpath_folder = os.path.split(newpath.strip('/'))[0]
        if not os.path.isdir(newpath_folder):
            os.makedirs(newpath_folder)
        os.rename(oldpath, newpath)
        return True
    except Exception:
        return False

#
#
#########################################
