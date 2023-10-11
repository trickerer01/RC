# coding=UTF-8
"""
Author: trickerer (https://github.com/trickerer, https://github.com/trickerer01)
"""
#########################################
#
#

from __future__ import annotations

from asyncio.queues import Queue as AsyncQueue
from asyncio.tasks import sleep, as_completed
from os import path, remove
from typing import List, Tuple, Coroutine, Any, Callable, Optional, Iterable

from aiohttp import ClientSession

from defs import (
    MAX_IMAGES_QUEUE_SIZE, DOWNLOAD_QUEUE_STALL_CHECK_TIMER, Log, Config, DownloadResult, prefixp, calc_sleep_time, format_time,
    get_elapsed_time_i, get_elapsed_time_s,
)
from iinfo import AlbumInfo, ImageInfo

__all__ = ('AlbumDownloadWorker', 'ImageDownloadWorker')


class AlbumDownloadWorker:
    """
    Async queue wrapper which binds list of lists of arguments to a download function call and processes them
    asynchronously with a limit of simulteneous downloads defined by MAX_IMAGES_QUEUE_SIZE
    """
    _instance = None  # type: Optional[AlbumDownloadWorker]

    @staticmethod
    def get() -> Optional[AlbumDownloadWorker]:
        return AlbumDownloadWorker._instance

    def __enter__(self) -> AlbumDownloadWorker:
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        AlbumDownloadWorker._instance = None

    def __init__(self, sequence: Iterable[AlbumInfo], func: Callable[[AlbumInfo], Coroutine[Any, Any, DownloadResult]],
                 session: ClientSession) -> None:
        assert AlbumDownloadWorker._instance is None
        AlbumDownloadWorker._instance = self

        self._func = func
        self.session = session
        self._seq = [ai for ai in sequence]  # form our own container to erase from
        self._queue = AsyncQueue(MAX_IMAGES_QUEUE_SIZE)  # type: AsyncQueue[Tuple[AlbumInfo, Coroutine[Any, Any, DownloadResult]]]
        self.orig_count = len(self._seq)
        self.scanned_count = 0
        self.filtered_count_after = 0
        self.skipped_count = 0

        self._scans_active = list()  # type: List[AlbumInfo]
        self.failed_items = list()  # type: List[int]

        self._total_queue_size_last = 0
        self._scan_queue_size_last = 0

    async def _at_task_start(self, ai: AlbumInfo) -> None:
        self._scans_active.append(ai)
        Log.trace(f'[queue] album {prefixp()}{ai.my_id:d} added to queue')

    async def _at_task_finish(self, ai: AlbumInfo, result: DownloadResult) -> None:
        self._scans_active.remove(ai)
        Log.trace(f'[queue] album {prefixp()}{ai.my_id:d} removed from queue')
        if result == DownloadResult.DOWNLOAD_FAIL_ALREADY_EXISTS:
            self.filtered_count_after += 1
        elif result == DownloadResult.DOWNLOAD_FAIL_SKIPPED:
            self.skipped_count += 1
        elif result == DownloadResult.DOWNLOAD_FAIL_RETRIES:
            self.failed_items.append(ai.my_id)
        elif result == DownloadResult.DOWNLOAD_SUCCESS:
            self.scanned_count += 1

    async def _prod(self) -> None:
        while len(self._seq) > 0:
            if self._queue.full() is False:
                self._seq[0].set_state(AlbumInfo.AlbumState.QUEUED)
                await self._queue.put((self._seq[0], self._func(self._seq[0])))
                del self._seq[0]
            else:
                await sleep(0.1)

    async def _cons(self) -> None:
        while len(self._seq) + self._queue.qsize() > 0:
            if self._queue.empty() is False and len(self._scans_active) < MAX_IMAGES_QUEUE_SIZE:
                ai, task = await self._queue.get()
                await self._at_task_start(ai)
                result = await task
                await self._at_task_finish(ai, result)
                self._queue.task_done()
            else:
                await sleep(0.07)

    async def _state_reporter(self) -> None:
        base_sleep_time = calc_sleep_time(5.0)
        force_check_seconds = DOWNLOAD_QUEUE_STALL_CHECK_TIMER
        last_check_seconds = 0
        while len(self._seq) + self._queue.qsize() + len(self._scans_active) > 0:
            await sleep(base_sleep_time if len(self._seq) + self._queue.qsize() > 0 else 1.0)
            queue_size = len(self._seq) + self._queue.qsize()
            scan_count = len(self._scans_active)
            queue_last = self._total_queue_size_last
            scanning_last = self._scan_queue_size_last
            elapsed_seconds = get_elapsed_time_i()
            force_check = elapsed_seconds >= force_check_seconds and elapsed_seconds - last_check_seconds >= force_check_seconds
            if queue_last != queue_size or scanning_last != scan_count or force_check:
                Log.info(f'[albums] [{get_elapsed_time_s()}] queue: {queue_size:d}, active: {scan_count:d}')
                last_check_seconds = elapsed_seconds
                self._total_queue_size_last = queue_size
                self._scan_queue_size_last = scan_count

    async def _after_download(self) -> None:
        self._done = True
        newline = '\n'
        Log.info(f'\n[albums] {self.scanned_count:d} / {self.orig_count:d} albums enqueued for download, '
                 f'{self.filtered_count_after:d} already existed, '
                 f'{self.skipped_count:d} skipped')
        if len(self._seq) > 0:
            Log.fatal(f'total queue is still at {len(self._seq):d} != 0!')
        if len(self.failed_items) > 0:
            Log.fatal(f'failed items:\n{newline.join(str(fi) for fi in sorted(self.failed_items))}')

    async def run(self) -> None:
        for cv in as_completed([self._prod(), self._state_reporter()] + [self._cons() for _ in range(MAX_IMAGES_QUEUE_SIZE)]):
            await cv
        await self._after_download()


class ImageDownloadWorker:
    """
    Async queue wrapper which binds list of lists of arguments to a download function call and processes them
    asynchronously with a limit of simulteneous downloads defined by MAX_IMAGES_QUEUE_SIZE
    """
    _instance = None  # type: Optional[ImageDownloadWorker]

    def __enter__(self) -> ImageDownloadWorker:
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        ImageDownloadWorker._instance = None

    @staticmethod
    def get() -> Optional[ImageDownloadWorker]:
        return ImageDownloadWorker._instance

    def __init__(self, func: Callable[[ImageInfo], Coroutine[Any, Any, DownloadResult]], session: ClientSession) -> None:
        assert ImageDownloadWorker._instance is None
        ImageDownloadWorker._instance = self

        self._func = func
        self.session = session
        self._seq = list()  # type: List[ImageInfo]
        self._queue = AsyncQueue(MAX_IMAGES_QUEUE_SIZE)  # type: AsyncQueue[Tuple[ImageInfo, Coroutine[Any, Any, DownloadResult]]]
        self.orig_count = 0
        self.downloaded_count = 0
        self.filtered_count_after = 0
        self.skipped_count = 0

        self._downloads_active = list()  # type: List[ImageInfo]
        self.writes_active = list()  # type: List[str]
        self.failed_items = list()  # type: List[str]

        self._my_start_time = 0
        self._total_queue_size_last = 0
        self._download_queue_size_last = 0
        self._write_queue_size_last = 0

    def store_image_info(self, ii: ImageInfo) -> None:
        self.orig_count += 1
        self._seq.append(ii)

    @property
    def processed_count(self) -> int:
        return self.downloaded_count + self.filtered_count_after + self.skipped_count + len(self.failed_items)

    async def _at_task_start(self, ii: ImageInfo) -> None:
        self._downloads_active.append(ii)
        Log.trace(f'[queue] image {prefixp()}{ii.my_id:d} added to queue')

    async def _at_task_finish(self, ii: ImageInfo, result: DownloadResult) -> None:
        self._downloads_active.remove(ii)
        Log.trace(f'[queue] image {prefixp()}{ii.my_id:d} removed from queue')
        if ii.my_album.all_done():
            Log.info(f'Album {prefixp()}{ii.my_album.my_id:d}: all images processed')
            ii.my_album.my_images.clear()
            ii.my_album.set_state(AlbumInfo.AlbumState.PROCESSED)
        if result == DownloadResult.DOWNLOAD_FAIL_ALREADY_EXISTS:
            self.filtered_count_after += 1
        elif result == DownloadResult.DOWNLOAD_FAIL_SKIPPED:
            self.skipped_count += 1
        elif result == DownloadResult.DOWNLOAD_FAIL_RETRIES:
            self.failed_items.append(ii.my_shortname)
        elif result == DownloadResult.DOWNLOAD_SUCCESS:
            self.downloaded_count += 1

    async def _prod(self) -> None:
        while len(self._seq) > 0:
            if self._queue.full() is False:
                self._seq[0].set_state(ImageInfo.ImageState.QUEUED)
                await self._queue.put((self._seq[0], self._func(self._seq[0])))
                del self._seq[0]
            else:
                await sleep(0.1)

    async def _cons(self) -> None:
        while len(self._seq) + self._queue.qsize() > 0:
            if self._queue.empty() is False and len(self._downloads_active) < MAX_IMAGES_QUEUE_SIZE:
                ii, task = await self._queue.get()
                await self._at_task_start(ii)
                result = await task
                await self._at_task_finish(ii, result)
                self._queue.task_done()
            else:
                await sleep(0.07)

    async def _state_reporter(self) -> None:
        base_sleep_time = calc_sleep_time(5.0)
        force_check_seconds = DOWNLOAD_QUEUE_STALL_CHECK_TIMER
        last_check_seconds = 0
        while len(self._seq) + self._queue.qsize() + len(self._downloads_active) > 0:
            await sleep(base_sleep_time if len(self._seq) + self._queue.qsize() > 0 else 1.0)
            queue_size = len(self._seq) + self._queue.qsize()
            download_count = len(self._downloads_active)
            write_count = len(self.writes_active)
            queue_last = self._total_queue_size_last
            downloading_last = self._download_queue_size_last
            write_last = self._write_queue_size_last
            elapsed_seconds = get_elapsed_time_i() - self._my_start_time
            dps = self.processed_count / max(1, elapsed_seconds)
            force_check = elapsed_seconds >= force_check_seconds and elapsed_seconds - last_check_seconds >= force_check_seconds
            if queue_last != queue_size or downloading_last != download_count or write_last != write_count or force_check:
                last_check_seconds = elapsed_seconds
                self._total_queue_size_last = queue_size
                self._download_queue_size_last = download_count
                self._write_queue_size_last = write_count
                eta_str = format_time(int((queue_size + download_count) / dps))
                elapsed_str = format_time(elapsed_seconds)
                Log.info(f'[images] [{get_elapsed_time_s()}] queue: {queue_size:d}, active: {download_count:d} (writing: {write_count:d}), '
                         f'ETA: {eta_str} ({self.processed_count:d} in {elapsed_str}, avg. {dps * 60:.1f} / min)')

    async def _after_download(self) -> None:
        newline = '\n'
        Log.info(f'\nDone. {self.downloaded_count:d} / {self.orig_count:d} files downloaded, '
                 f'{self.filtered_count_after:d} already existed, '
                 f'{self.skipped_count:d} skipped')
        if len(self._seq) > 0:
            Log.fatal(f'total queue is still at {len(self._seq):d} != 0!')
        if len(self.writes_active) > 0:
            Log.fatal(f'active writes count is still at {len(self.writes_active):d} != 0!')
        if len(self.failed_items) > 0:
            Log.fatal(f'failed items:\n{newline.join(sorted(self.failed_items))}')

    async def run(self) -> None:
        self._my_start_time = get_elapsed_time_i()
        minid, maxid = min(self._seq, key=lambda x: x.my_id).my_id, max(self._seq, key=lambda x: x.my_id).my_id
        Log.info(f'\n[images] {len(self._seq):d} ids in queue, bound {minid:d} to {maxid:d}. Working...\n')
        for cv in as_completed([self._prod(), self._state_reporter()] + [self._cons() for _ in range(MAX_IMAGES_QUEUE_SIZE)]):
            await cv
        await self._after_download()

    def at_interrupt(self) -> None:
        if len(self.writes_active) > 0:
            if Config.keep_unfinished:
                unfinished_str = '\n '.join(f'{i + 1:d}) {s}' for i, s in enumerate(sorted(self.writes_active)))
                Log.debug(f'at_interrupt: keeping {len(self.writes_active):d} unfinished files:\n {unfinished_str}')
                return
            Log.debug(f'at_interrupt: cleaning {len(self.writes_active):d} unfinished files...')
            for unfinished in sorted(self.writes_active):
                Log.debug(f'at_interrupt: trying to remove \'{unfinished}\'...')
                if path.isfile(unfinished):
                    remove(unfinished)
                else:
                    Log.debug(f'at_interrupt: file \'{unfinished}\' not found!')

#
#
#########################################
