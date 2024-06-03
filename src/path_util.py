# coding=UTF-8
"""
Author: trickerer (https://github.com/trickerer, https://github.com/trickerer01)
"""
#########################################
#
#

from os import path, listdir, rename, makedirs
from typing import List, Dict

from config import Config
from defs import PREFIX, DEFAULT_EXT
from logger import Log
from rex import re_album_foldername
from util import normalize_path

__all__ = ('folder_already_exists', 'folder_already_exists_arr', 'scan_dest_folder', 'try_rename')

found_foldernames_dict: Dict[str, List[str]] = dict()


def report_duplicates() -> None:
    found_vs = dict()
    k: str
    for k in found_foldernames_dict:
        if not found_foldernames_dict[k]:
            continue
        for fname in found_foldernames_dict[k]:
            if not fname.startswith(PREFIX):
                continue
            fm = re_album_foldername.fullmatch(fname)
            if fm:
                fid = fm.group(1)
                if fid not in found_vs:
                    found_vs[fid] = [''] * 0
                found_vs[fid].append(k + fname)
    if found_vs:
        Log.info('Duplicates found:')
        n = '\n  - '
        for kk in found_vs:
            vv = found_vs[kk]
            if len(vv) > 1:
                Log.info(f' {PREFIX}{kk}.{DEFAULT_EXT}:{n}{n.join(vv)}')
    else:
        Log.info('No duplicates found')


def scan_dest_folder() -> None:
    """
    Scans base destination folder plus {Config.folder_scan_depth} levels of subfolders and
    stores found subfolders in dict (key=folder_name)\n\n
    |folder1:\n\n
    |__subfolder1:\n\n
    |____subfolder2\n\n
    |____subfolder3\n\n
    => files{'folder1': ['subfolder1'], 'subfolder1': ['subfolder2','subfolder3']}\n\n
    This function may only be called once!
    """
    assert len(found_foldernames_dict.keys()) == 0
    if path.isdir(Config.dest_base) or Config.folder_scan_levelup:
        Log.info('Scanning dest folder...')
        dest_base = Config.dest_base
        scan_depth = Config.folder_scan_depth + Config.folder_scan_levelup
        for _ in range(Config.folder_scan_levelup):
            longpath, dirname = path.split(path.abspath(dest_base))
            dest_base = normalize_path(longpath)
            if dirname == '':
                break

        def scan_folder(base_folder: str, level: int) -> None:
            if path.isdir(base_folder):
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
            scan_folder(Config.dest_base, Config.folder_scan_levelup)
        base_folders_count = len(found_foldernames_dict[dest_base])
        total_files_count = sum(len(li) for li in found_foldernames_dict.values())
        Log.info(f'Found {base_folders_count:d} folder(s) in base and '
                 f'{total_files_count - base_folders_count:d} folder(s) in {len(found_foldernames_dict.keys()) - 1:d} subfolder(s) '
                 f'(total folders: {total_files_count:d}, scan depth: {scan_depth:d})')

    if Config.report_duplicates:
        report_duplicates()


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
    for fullpath in found_foldernames_dict:
        fullpath = folder_exists_in_folder(fullpath, idi)
        if len(fullpath) > 0:
            return fullpath
    return ''


def folder_exists_in_folder_arr(base_folder: str, idi: int) -> List[str]:
    orig_folder_names = found_foldernames_dict.get(normalize_path(base_folder))
    folder_folders = list()
    if path.isdir(base_folder) and orig_folder_names is not None:
        for fname in orig_folder_names:
            try:
                f_match = re_album_foldername.match(fname)
                f_id = f_match.group(1)
                if str(idi) == f_id:
                    folder_folders.append(f'{normalize_path(base_folder)}{fname}')
            except Exception:
                continue
    return folder_folders


def folder_already_exists_arr(idi: int) -> List[str]:
    found_folders = list()
    for fullpath in found_foldernames_dict:
        found_folders.extend(folder_exists_in_folder_arr(fullpath, idi))
    return found_folders


def try_rename(oldpath: str, newpath: str) -> bool:
    try:
        if oldpath == newpath:
            return True
        newpath_folder = path.split(newpath.strip('/'))[0]
        if not path.isdir(newpath_folder):
            makedirs(newpath_folder)
        rename(oldpath, newpath)
        return True
    except Exception:
        return False

#
#
#########################################
