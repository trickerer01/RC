# coding=UTF-8
"""
Author: trickerer (https://github.com/trickerer, https://github.com/trickerer01)
"""
#########################################
#
#

from __future__ import annotations
from enum import IntEnum
from typing import Dict, Iterable, Union, Tuple, List

from config import Config
from defs import PREFIX, UTF8, DEFAULT_EXT
from util import normalize_path, normalize_filename

__all__ = ('AlbumInfo', 'ImageInfo', 'get_min_max_ids', 'export_album_info')


class AlbumInfo:
    class State(IntEnum):
        NEW = 0
        QUEUED = 1
        ACTIVE = 2
        SCANNED = 3
        PROCESSED = 4

    def __init__(self, m_id: int, m_title='', *, preview_link='') -> None:
        self._id = m_id or 0

        self.title = m_title or ''
        self.subfolder = ''
        self.name = ''
        self.rating = ''
        self.preview_link = preview_link
        self.tags = ''
        self.description = ''
        self.comments = ''
        self.images = list()  # type: List[ImageInfo]

        self._state = AlbumInfo.State.NEW

    def set_state(self, state: AlbumInfo.State) -> None:
        self._state = state

    def all_done(self) -> bool:
        return all(ii.state in (ImageInfo.State.DONE, ImageInfo.State.FAILED) for ii in self.images) if self.images else False

    def __eq__(self, other: Union[AlbumInfo, int]) -> bool:
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

    def __init__(self, album_info: AlbumInfo, m_id: int, m_link: str, m_filename: str) -> None:
        self._album = album_info
        self._id = m_id or 0

        self.link = m_link or ''
        self.filename = m_filename or ''
        self.ext = self.filename[self.filename.rfind('.'):]
        self.expected_size = 0

        self._state = ImageInfo.State.NEW

    def set_state(self, state: ImageInfo.State) -> None:
        self._state = state

    def __eq__(self, other: Union[ImageInfo, int]) -> bool:
        return self.id == other.id if isinstance(other, type(self)) else self.id == other if isinstance(other, int) else False

    def __str__(self) -> str:
        return (
            f'[{self.state_str}] \'{self.album.sname}/{self.sname}\''
            f'\nDest: \'{self.my_fullpath}\'\nLink: \'{self.link}\''
        )

    @property
    def id(self) -> int:
        return self._id

    @property
    def album(self) -> AlbumInfo:
        return self._album

    @property
    def state(self) -> ImageInfo.State:
        return self._state

    @property
    def is_preview(self) -> bool:
        return self.id == self.album.id and self.link.endswith(f'preview.{DEFAULT_EXT}')

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
    def state_str(self) -> str:
        return self._state.name

    __repr__ = __str__


def get_min_max_ids(seq: Iterable[AlbumInfo]) -> Tuple[int, int]:
    return min(seq, key=lambda x: x.id).id, max(seq, key=lambda x: x.id).id


def export_album_info(info_list: Iterable[AlbumInfo]) -> None:
    """Saves tags, descriptions and comments for each subfolder in scenario and base dest folder based on album info"""
    tags_dict, desc_dict, comm_dict = dict(), dict(), dict()  # type: Dict[str, Dict[int, str]]
    for ai in info_list:
        if ai.state == AlbumInfo.State.PROCESSED:
            for d, s in zip((tags_dict, desc_dict, comm_dict), (ai.tags, ai.description, ai.comments)):
                if ai.my_sfolder not in d:
                    d[ai.my_sfolder] = dict()
                d[ai.my_sfolder][ai.id] = s
    for conf, dct, name, proc_cb in zip(
        (Config.save_tags, Config.save_descriptions, Config.save_comments),
        (tags_dict, desc_dict, comm_dict),
        ('tags', 'descriptions', 'comments'),
        (lambda tags: f' {tags.strip()}\n', lambda description: f'{description}\n', lambda comment: f'{comment}\n')
    ):
        if not conf:
            continue
        for subfolder, sdct in dct.items():
            if not sdct:
                continue
            if Config.skip_empty_lists and not any(sdct[idi] for idi in sdct.keys()):
                continue
            keys = sorted(sdct.keys())
            min_id, max_id = keys[0], keys[-1]
            fullpath = f'{normalize_path(f"{Config.dest_base}{subfolder}")}{PREFIX}!{name}_{min_id:d}-{max_id:d}.txt'
            with open(fullpath, 'wt', encoding=UTF8) as sfile:
                sfile.writelines(f'{PREFIX}{idi:d}:{proc_cb(sdct[idi])}' for idi in keys)

#
#
#########################################
