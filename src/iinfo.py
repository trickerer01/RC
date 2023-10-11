# coding=UTF-8
"""
Author: trickerer (https://github.com/trickerer, https://github.com/trickerer01)
"""
#########################################
#
#

from __future__ import annotations
from enum import IntEnum
from typing import Dict, Optional, Callable, Iterable, Union, List

from defs import Config, normalize_path, normalize_filename, prefixp, UTF8

__all__ = ('AlbumInfo', 'ImageInfo', 'export_album_info')


class AlbumInfo:
    class AlbumState(IntEnum):
        NEW = 0
        QUEUED = 1
        ACTIVE = 2
        SCANNED = 3
        PROCESSED = 4

    def __init__(self, m_id: int, m_link: str, m_title='') -> None:
        self.my_id = m_id or 0
        self.my_link = m_link or ''
        self.my_title = m_title or ''

        self.my_subfolder = ''
        self.my_name = ''

        self.my_tags = ''
        self.my_comments = ''
        self.my_images = list()  # type: List[ImageInfo]
        self._state = AlbumInfo.AlbumState.NEW

    def set_state(self, state: AlbumInfo.AlbumState) -> None:
        self._state = state

    @property
    def state(self) -> AlbumInfo.AlbumState:
        return self._state

    def all_done(self) -> bool:
        return all(ii.state == ImageInfo.ImageState.DONE for ii in self.my_images) if self.my_images else False

    def __eq__(self, other: Union[AlbumInfo, int]) -> bool:
        return self.my_id == other.my_id if isinstance(other, type(self)) else self.my_id == other if isinstance(other, int) else False

    def __repr__(self) -> str:
        return f'[{self.state_str}] \'{prefixp()}{self.my_id:d}.album\'\nDest: \'{self.my_folder}\'\nLink: \'{self.my_link}\''

    @property
    def my_shortname(self) -> str:
        return normalize_path(f'{prefixp()}{self.my_id:d}')

    @property
    def my_sfolder(self) -> str:
        return normalize_path(self.my_subfolder)

    @property
    def my_sfolder_full(self) -> str:
        return normalize_path(f'{self.my_sfolder}{self.my_name}')

    @property
    def my_folder(self) -> str:
        return normalize_path(f'{Config.dest_base}{self.my_subfolder}')

    @property
    def my_folder_full(self) -> str:
        return normalize_path(f'{self.my_folder}{self.my_name}')

    @property
    def state_str(self) -> str:
        return self._state.name


class ImageInfo:
    class ImageState(IntEnum):
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
        self._state = ImageInfo.ImageState.NEW

    def set_state(self, state: ImageInfo.ImageState) -> None:
        self._state = state

    @property
    def state(self) -> ImageInfo.ImageState:
        return self._state

    def __eq__(self, other: Union[ImageInfo, int]) -> bool:
        return self.my_id == other.my_id if isinstance(other, type(self)) else self.my_id == other if isinstance(other, int) else False

    def __repr__(self) -> str:
        return (
            f'[{self.state_str}] \'{prefixp()}{self.my_id:d}.jpg\''
            f'\nDest: \'{self.my_fullpath}\'\nLink: \'{self.my_link}\''
        )

    @property
    def my_shortname(self) -> str:
        return f'{self.my_sfolder}{self.my_album.my_shortname}{prefixp()}{self.my_id:d}{self.my_ext}'

    @property
    def my_sfolder(self) -> str:
        return self.my_album.my_sfolder

    @property
    def my_folder_full(self) -> str:
        return self.my_album.my_folder_full

    @property
    def my_fullpath(self) -> str:
        return normalize_filename(self.my_filename, self.my_album.my_folder_full)

    @property
    def state_str(self) -> str:
        return self._state.name


async def export_album_info(info_list: Iterable[AlbumInfo]) -> None:
    """Saves tags and comments for each subfolder in scenario and base dest folder based on album info"""
    tags_dict, comm_dict = dict(), dict()  # type: Dict[str, Dict[int, str]]
    for ai in info_list:
        if ai.state == AlbumInfo.AlbumState.PROCESSED:
            for d, s in zip((tags_dict, comm_dict), (ai.my_tags, ai.my_comments)):
                if ai.my_sfolder_full not in d:
                    d[ai.my_sfolder_full] = dict()
                d[ai.my_sfolder_full][ai.my_id] = s
    for conf, dct, name, proc_cb in (
        (Config.save_tags, tags_dict, 'tags', lambda tags: f' {tags.strip()}\n'),
        (Config.save_comments, comm_dict, 'comments', lambda comment: f'{comment}\n')
    ):  # type: Optional[bool], Dict[str, Dict[int, str]], str, Callable[[str], str]
        if conf is True:
            for subfolder, sdct in dct.items():
                if len(sdct) > 0:
                    min_id, max_id = min(sdct.keys()), max(sdct.keys())
                    fullpath = f'{Config.dest_base}{subfolder}{prefixp()}!{name}_{min_id:d}-{max_id:d}.txt'
                    with open(fullpath, 'wt', encoding=UTF8) as sfile:
                        sfile.writelines(f'{prefixp()}{idi:d}:{proc_cb(elem)}' for idi, elem in sorted(sdct.items(), key=lambda t: t[0]))

#
#
#########################################
