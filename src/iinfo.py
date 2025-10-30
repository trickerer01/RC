# coding=UTF-8
"""
Author: trickerer (https://github.com/trickerer, https://github.com/trickerer01)
"""
#########################################
#
#

from __future__ import annotations

import os
import re
from collections.abc import Iterable
from enum import IntEnum

from config import Config
from defs import DEFAULT_EXT, PREFIX, UTF8
from logger import Log
from rex import re_infolist_filename
from util import normalize_filename, normalize_path

__all__ = ('AlbumInfo', 'ImageInfo', 'export_album_info', 'get_min_max_ids')


class AlbumInfo:
    class State(IntEnum):
        NEW = 0
        QUEUED = 1
        ACTIVE = 2
        SCANNED = 3
        PROCESSED = 4

    class Flags(IntEnum):
        NONE = 0x0
        RETURNED_404 = 0x8

    def __init__(self, m_id: int, m_title='', *, preview_link='') -> None:
        self._id = m_id or 0

        self.title: str = m_title or ''
        self.subfolder: str = ''
        self.name: str = ''
        self.rating: str = ''
        self.preview_link: str = preview_link or ''
        self.tags: str = ''
        self.description: str = ''
        self.comments: str = ''
        self.uploader: str = ''
        self.private: bool = False
        self.images: list[ImageInfo] = []
        self.dstart_time: int = 0

        self._state = AlbumInfo.State.NEW
        self._flags = AlbumInfo.Flags.NONE

    def set_state(self, state: AlbumInfo.State) -> None:
        self._state = state

    def set_flag(self, flag: ImageInfo.Flags) -> None:
        self._flags |= flag

    def has_flag(self, flag: int | ImageInfo.Flags) -> bool:
        return bool(self._flags & flag)

    def all_done(self) -> bool:
        return all(ii.state in (ImageInfo.State.DONE, ImageInfo.State.FAILED) for ii in self.images) if self.images else False

    def total_size(self) -> int:
        return sum(ii.bytes_written for ii in self.images)

    def __eq__(self, other: AlbumInfo | int) -> bool:
        return self.id == other.id if isinstance(other, type(self)) else self.id == other if isinstance(other, int) else False

    def __str__(self) -> str:
        return (
            f'[{self.state_str}] \'{PREFIX}{self.id:d}_{self.title}.album\''
            f'\nDest: \'{self.my_folder}\''
        )

    @property
    def id(self) -> int:
        return self._id

    @property
    def state(self) -> AlbumInfo.State:
        return self._state

    @property
    def images_count(self) -> int:
        return len(self.images)

    @property
    def sname(self) -> str:
        return f'{PREFIX}{self.id:d}.album'

    @property
    def sfsname(self) -> str:
        return normalize_filename(self.sname, self.subfolder)

    @property
    def my_sfolder(self) -> str:
        return normalize_path(self.subfolder)

    @property
    def my_sfolder_full(self) -> str:
        return normalize_path(f'{self.my_sfolder}{self.name}')

    @property
    def my_folder_base(self) -> str:
        return normalize_path(f'{Config.dest_base}{self.subfolder}')

    @property
    def my_folder(self) -> str:
        return normalize_path(f'{self.my_folder_base}{self.name}')

    @property
    def state_str(self) -> str:
        return self._state.name

    __repr__ = __str__


class ImageInfo:
    class State(IntEnum):
        NEW = 0
        QUEUED = 1
        ACTIVE = 2
        DOWNLOADING = 3
        WRITING = 4
        DONE = 5
        FAILED = 6

    class Flags(IntEnum):
        NONE = 0x0
        ALREADY_EXISTED_EXACT = 0x1
        ALREADY_EXISTED_SIMILAR = 0x2
        FILE_WAS_CREATED = 0x4

    def __init__(self, album_info: AlbumInfo, m_id: int, m_link: str, m_filename: str, *, num=1) -> None:
        self._album = album_info
        self._id = m_id or 0
        self._num = num or 1

        self.link: str = m_link or ''
        self.filename: str = m_filename or ''
        self.ext: str = self.filename[self.filename.rfind('.'):]
        self.expected_size: int = 0
        self.bytes_written: int = 0

        self._state = ImageInfo.State.NEW
        self._flags = ImageInfo.Flags.NONE

    def set_state(self, state: ImageInfo.State) -> None:
        self._state = state

    def set_flag(self, flag: ImageInfo.Flags) -> None:
        self._flags |= flag

    def has_flag(self, flag: int | ImageInfo.Flags) -> bool:
        return bool(self._flags & flag)

    def __eq__(self, other: ImageInfo | int) -> bool:
        return self.id == other.id if isinstance(other, type(self)) else self.id == other if isinstance(other, int) else False

    def __str__(self) -> str:
        return (f'[{self.state_str}] {self.my_num_fmt} \'{self.album.sname}/{self.sname}\''
                f'\nDest: \'{self.my_fullpath}\'\nLink: \'{self.link}\'')

    @property
    def id(self) -> int:
        return self._id

    @property
    def num(self) -> int:
        return self._num

    @property
    def album(self) -> AlbumInfo:
        return self._album

    @property
    def is_preview(self) -> bool:
        return self.id == self.album.id and self.link.endswith(f'preview.{DEFAULT_EXT}')

    @property
    def my_num_fmt(self) -> str:
        return f'({self.num:d} / {self.album.images_count:d})'

    @property
    def sname(self) -> str:
        return f'{PREFIX}{self.id:d}.{DEFAULT_EXT}'

    @property
    def my_shortname(self) -> str:
        return f'{self.my_sfolder}{self.album.sname}/{PREFIX}{self.id:d}{self.ext}'

    @property
    def my_sfolder(self) -> str:
        return self.album.my_sfolder

    @property
    def my_folder(self) -> str:
        return self.album.my_folder

    @property
    def my_fullpath(self) -> str:
        return normalize_filename(self.filename, self.my_folder)

    @property
    def state(self) -> ImageInfo.State:
        return self._state

    @property
    def state_str(self) -> str:
        return self._state.name

    __repr__ = __str__


def get_min_max_ids(seq: Iterable[AlbumInfo]) -> tuple[int, int]:
    min_id, max_id = 10**18, 0
    for ii in seq:
        id_ = ii.id
        if id_ < min_id:
            min_id = id_
        if id_ > max_id:
            max_id = id_
    return min_id, max_id


def try_merge_info_files(info_dict: dict[int, str], subfolder: str, list_type: str) -> list[str]:
    parsed_files: list[str] = []
    if not Config.merge_lists:
        return parsed_files
    dir_fullpath = normalize_path(f'{Config.dest_base}{subfolder}')
    if not os.path.isdir(dir_fullpath):
        return parsed_files
    # Log.debug(f'\nMerging {Config.dest_base}{subfolder} \'{list_type}\' info lists...')
    info_lists: list[re.Match[str]] = sorted((m for m in (re_infolist_filename.fullmatch(f.name) for f in os.scandir(dir_fullpath)
                                             if f.is_file() and f.name.startswith(f'{PREFIX}!{list_type}_')) if bool(m)),
                                             key=lambda m: m.string)
    if not info_lists:
        return parsed_files
    parsed_dict: dict[int, str] = {}
    for fmatch in info_lists:
        fmname = fmatch.string
        # Log.debug(f'Parsing {fmname}...')
        list_fullpath = f'{dir_fullpath}{fmname}'
        try:
            with open(list_fullpath, 'rt', encoding=UTF8) as listfile:
                last_id = 0
                for line in listfile.readlines():
                    line = line.strip('\ufeff')
                    if line in ('', '\n'):
                        continue
                    if line.startswith(PREFIX):
                        delim_idx = line.find(':')
                        idi = line[len(PREFIX):delim_idx]
                        last_id = int(idi)
                        # Log.debug(f'new id: {last_id:d}{f" (override!)" if last_id in parsed_dict else ""}...')
                        parsed_dict[last_id] = ''
                        if len(line) > delim_idx + 2:
                            parsed_dict[last_id] += line[delim_idx + 2:].strip()
                            # Log.debug(f'at {last_id:d}: (in place) now \'{parsed_dict[last_id]}\'')
                            last_id = 0
                    else:
                        assert last_id
                        if not parsed_dict[last_id]:
                            line = f'\n{line}'
                        parsed_dict[last_id] += line
                        # Log.debug(f'at {last_id:d}: adding \'{line}\'')
                parsed_files.append(list_fullpath)
        except Exception:
            Log.error(f'Error reading from {fmname}. Skipped')
            continue
    for k, v in parsed_dict.items():
        if k not in info_dict:
            info_dict[k] = v
    return parsed_files


def export_album_info(info_list: Iterable[AlbumInfo]) -> None:
    """Saves tags, descriptions and comments for each subfolder in scenario and base dest folder based on album info"""
    tags_dict: dict[str, dict[int, str]] = {}
    desc_dict: dict[str, dict[int, str]] = {}
    comm_dict: dict[str, dict[int, str]] = {}
    for ai in info_list:
        if ai.state == AlbumInfo.State.PROCESSED:
            for d, s in zip((tags_dict, desc_dict, comm_dict), (ai.tags, ai.description, ai.comments), strict=True):
                if ai.my_sfolder not in d:
                    d[ai.my_sfolder] = {}
                d[ai.my_sfolder][ai.id] = s
    for conf, dct, name, proc_cb in zip(
        (Config.save_tags, Config.save_descriptions, Config.save_comments),
        (tags_dict, desc_dict, comm_dict),
        ('tags', 'descriptions', 'comments'),
        (lambda tags: f' {tags.strip()}\n', lambda description: f'{description}\n', lambda comments: f'{comments}\n'),
        strict=True,
    ):
        if not conf:
            continue
        for subfolder, sdct in dct.items():
            merged_files = try_merge_info_files(sdct, subfolder, name)
            if not sdct:
                continue
            if Config.skip_empty_lists and not any(sdct[idi] for idi in sdct):
                continue
            keys = sorted(sdct.keys())
            min_id, max_id = keys[0], keys[-1]
            info_folder = f'{Config.dest_base}{subfolder}'
            fullpath = f'{normalize_path(info_folder)}{PREFIX}!{name}_{min_id:d}-{max_id:d}.txt'
            if not os.path.isdir(info_folder):
                os.makedirs(info_folder)
            with open(fullpath, 'wt', encoding=UTF8) as sfile:
                sfile.writelines(f'{PREFIX}{idi:d}:{proc_cb(sdct[idi])}' for idi in keys)
            [os.remove(merged_file) for merged_file in merged_files if merged_file != fullpath]

#
#
#########################################
