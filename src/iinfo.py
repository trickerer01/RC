# coding=UTF-8
"""
Author: trickerer (https://github.com/trickerer, https://github.com/trickerer01)
"""
#########################################
#
#

from __future__ import annotations
from enum import IntEnum
from typing import Dict, Iterable, Union, List, Tuple

from config import Config
from defs import PREFIX, UTF8
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
        self.my_id = m_id or 0
        self.my_title = m_title or ''

        self.my_subfolder = ''
        self.my_name = ''
        self.my_rating = ''
        self.my_preview_link = preview_link

        self.my_tags = ''
        self.my_description = ''
        self.my_comments = ''
        self.my_images = list()  # type: List[ImageInfo]
        self._state = AlbumInfo.State.NEW

    def set_state(self, state: AlbumInfo.State) -> None:
        self._state = state

    @property
    def state(self) -> AlbumInfo.State:
        return self._state

    def all_done(self) -> bool:
        return all(ii.state in (ImageInfo.State.DONE, ImageInfo.State.FAILED) for ii in self.my_images) if self.my_images else False

    def __eq__(self, other: Union[AlbumInfo, int]) -> bool:
        return self.my_id == other.my_id if isinstance(other, type(self)) else self.my_id == other if isinstance(other, int) else False

    def __repr__(self) -> str:
        return (
            f'[{self.state_str}] \'{PREFIX}{self.my_id:d}_{self.my_title}.album\''
            f'\nDest: \'{self.my_folder}\''
        )

    @property
    def my_shortname(self) -> str:
        return normalize_path(f'{PREFIX}{self.my_id:d}')

    @property
    def my_sfolder(self) -> str:
        return normalize_path(self.my_subfolder)

    @property
    def my_sfolder_full(self) -> str:
        return normalize_path(f'{self.my_sfolder}{self.my_name}')

    @property
    def my_folder_base(self) -> str:
        return normalize_path(f'{Config.dest_base}{self.my_subfolder}')

    @property
    def my_folder(self) -> str:
        return normalize_path(f'{self.my_folder_base}{self.my_name}')

    @property
    def state_str(self) -> str:
        return self._state.name


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
        self.my_album = album_info
        self.my_id = m_id or 0
        self.my_link = m_link or ''
        self.my_filename = m_filename or ''
        self.my_ext = self.my_filename[self.my_filename.rfind('.'):]

        self.my_expected_size = 0
        self._state = ImageInfo.State.NEW

    def set_state(self, state: ImageInfo.State) -> None:
        self._state = state

    @property
    def state(self) -> ImageInfo.State:
        return self._state

    @property
    def is_preview(self) -> bool:
        return self.my_id == self.my_album.my_id and self.my_link.endswith('preview.jpg')

    def __eq__(self, other: Union[ImageInfo, int]) -> bool:
        return self.my_id == other.my_id if isinstance(other, type(self)) else self.my_id == other if isinstance(other, int) else False

    def __repr__(self) -> str:
        return f'[{self.state_str}] \'{PREFIX}{self.my_id:d}.jpg\'\nDest: \'{self.my_fullpath}\'\nLink: \'{self.my_link}\''

    @property
    def my_shortname(self) -> str:
        return f'{self.my_sfolder}{self.my_album.my_shortname}{PREFIX}{self.my_id:d}{self.my_ext}'

    @property
    def my_sfolder(self) -> str:
        return self.my_album.my_sfolder

    @property
    def my_folder(self) -> str:
        return self.my_album.my_folder

    @property
    def my_fullpath(self) -> str:
        return normalize_filename(self.my_filename, self.my_folder)

    @property
    def state_str(self) -> str:
        return self._state.name


def get_min_max_ids(seq: List[AlbumInfo]) -> Tuple[int, int]:
    return min(seq, key=lambda x: x.my_id).my_id, max(seq, key=lambda x: x.my_id).my_id


def export_album_info(info_list: Iterable[AlbumInfo]) -> None:
    """Saves tags, descriptions and comments for each subfolder in scenario and base dest folder based on album info"""
    tags_dict, desc_dict, comm_dict = dict(), dict(), dict()  # type: Dict[str, Dict[int, str]]
    for ai in info_list:
        if ai.state == AlbumInfo.State.PROCESSED:
            for d, s in zip((tags_dict, desc_dict, comm_dict), (ai.my_tags, ai.my_description, ai.my_comments)):
                if ai.my_sfolder not in d:
                    d[ai.my_sfolder] = dict()
                d[ai.my_sfolder][ai.my_id] = s
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
            keys = sorted(sdct.keys())
            min_id, max_id = keys[0], keys[-1]
            fullpath = f'{normalize_path(f"{Config.dest_base}{subfolder}")}{PREFIX}!{name}_{min_id:d}-{max_id:d}.txt'
            with open(fullpath, 'wt', encoding=UTF8) as sfile:
                sfile.writelines(f'{PREFIX}{idi:d}:{proc_cb(sdct[idi])}' for idi in keys)

#
#
#########################################
