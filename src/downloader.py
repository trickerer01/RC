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
from os import path, remove, makedirs
from typing import List, Tuple, Coroutine, Any, Callable, Optional, Iterable, Union, Dict

from aiohttp import ClientSession

from config import Config
from defs import (
    DownloadResult, Mem, MAX_IMAGES_QUEUE_SIZE, DOWNLOAD_QUEUE_STALL_CHECK_TIMER, DOWNLOAD_CONTINUE_FILE_CHECK_TIMER, PREFIX,
    START_TIME, UTF8, LOGGING_FLAGS, CONNECT_TIMEOUT_BASE, DOWNLOAD_POLICY_DEFAULT, NAMING_FLAGS_DEFAULT,
    DOWNLOAD_MODE_DEFAULT,
)
from iinfo import AlbumInfo, ImageInfo, get_min_max_ids
from logger import Log
from util import format_time, get_elapsed_time_i, get_elapsed_time_s, calc_sleep_time

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
        self._session = session
        self._seq = [ai for ai in sequence]  # form our own container to erase from
        self._queue = AsyncQueue(MAX_IMAGES_QUEUE_SIZE)  # type: AsyncQueue[Tuple[AlbumInfo, Coroutine[Any, Any, DownloadResult]]]
        self._orig_count = len(self._seq)
        self._scanned_count = 0
        self._filtered_count_after = 0
        self._skipped_count = 0
        self._minmax_id = get_min_max_ids(self._seq)

        self._downloads_active = dict()  # type: Dict[int, AlbumInfo]
        self._scans_active = list()  # type: List[AlbumInfo]
        self._failed_items = list()  # type: List[int]

        self._total_queue_size_last = 0
        self._scan_queue_size_last = 0

    async def _at_task_start(self, ai: AlbumInfo) -> None:
        self._scans_active.append(ai)
        Log.trace(f'[queue] album {PREFIX}{ai.my_id:d} added to queue')

    async def _at_task_finish(self, ai: AlbumInfo, result: DownloadResult) -> None:
        self._scans_active.remove(ai)
        Log.trace(f'[queue] album {PREFIX}{ai.my_id:d} removed from queue')
        if result == DownloadResult.FAIL_ALREADY_EXISTS:
            self._filtered_count_after += 1
        elif result == DownloadResult.FAIL_SKIPPED:
            self._skipped_count += 1
        elif result == DownloadResult.FAIL_RETRIES:
            self._failed_items.append(ai.my_id)
        elif result == DownloadResult.SUCCESS:
            self._scanned_count += 1
            self._downloads_active[ai.my_id] = ai

    async def _prod(self) -> None:
        while len(self._seq) > 0:
            if self._queue.full() is False:
                self._seq[0].set_state(AlbumInfo.State.QUEUED)
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
                Log.info(f'[{get_elapsed_time_s()}] queue: {queue_size:d}, active: {scan_count:d}')
                last_check_seconds = elapsed_seconds
                self._total_queue_size_last = queue_size
                self._scan_queue_size_last = scan_count

    async def _continue_file_checker(self) -> None:
        if not Config.store_continue_cmdfile:
            return
        minmax_id = self._minmax_id
        continue_file_path = (
            f'{Config.dest_base}{PREFIX}{START_TIME.strftime("%Y-%m-%d_%H_%M_%S")}_{minmax_id[0]:d}-{minmax_id[1]:d}.continue.conf'
        )
        arglist_base = [
            '-path', Config.dest_base, '-continue', '--store-continue-cmdfile',
            '-log', next(filter(lambda x: int(LOGGING_FLAGS[x], 16) == Config.logging_flags, LOGGING_FLAGS.keys())),
            *(('-utp', Config.utp) if Config.utp != DOWNLOAD_POLICY_DEFAULT and not Config.scenario else ()),
            *(('-minrating', Config.min_rating) if Config.min_rating else ()),
            *(('-minscore', Config.min_score) if Config.min_score else ()),
            *(('-naming', Config.naming_flags) if Config.naming_flags != NAMING_FLAGS_DEFAULT else ()),
            *(('-dmode', Config.download_mode) if Config.download_mode != DOWNLOAD_MODE_DEFAULT else ()),
            *(('-proxy', Config.proxy) if Config.proxy else ()),
            *(('-throttle', Config.throttle) if Config.throttle else ()),
            *(('-timeout', int(Config.timeout.connect)) if int(Config.timeout.connect) != CONNECT_TIMEOUT_BASE else ()),
            *(('-unfinish',) if Config.keep_unfinished else ()),
            *(('-tdump',) if Config.save_tags else ()),
            # *(('-ddump',) if Config.save_descriptions else ()),
            *(('-cdump',) if Config.save_comments else ()),
            # *(('-sdump',) if Config.save_screenshots else ()),
            *(('-session_id', Config.session_id,) if Config.session_id else ()),
            *Config.extra_tags,
            *(('-script', Config.scenario.fmt_str) if Config.scenario else ())
        ]
        base_sleep_time = calc_sleep_time(3.0)
        write_delay = DOWNLOAD_CONTINUE_FILE_CHECK_TIMER
        last_check_seconds = 0
        while len(self._seq) + self._queue.qsize() + len(self._scans_active) + len(self._downloads_active) > 0:
            if len(self._seq) + self._queue.qsize() + len(self._scans_active) == 0:
                elapsed_seconds = get_elapsed_time_i()
                if elapsed_seconds >= write_delay and elapsed_seconds - last_check_seconds >= write_delay:
                    last_check_seconds = elapsed_seconds
                    a_ids = sorted(self._downloads_active)
                    arglist = ['-seq', f'({"~".join(f"id={idi:d}" for idi in a_ids)})'] if len(a_ids) > 1 else ['-start', str(a_ids[0])]
                    arglist.extend(arglist_base)
                    try:
                        Log.trace(f'Storing continue file to \'{continue_file_path}\'...')
                        if not path.isdir(Config.dest_base):
                            makedirs(Config.dest_base)
                        with open(continue_file_path, 'wt', encoding=UTF8, buffering=1) as cfile:
                            cfile.write('\n'.join(str(e) for e in arglist))
                    except (OSError, IOError):
                        Log.error(f'Unable to save continue file to {continue_file_path}!')
            await sleep(base_sleep_time)
        if path.isfile(continue_file_path):
            Log.trace(f'All files downloaded. Removing continue file \'{continue_file_path}\'...')
            remove(continue_file_path)

    async def _after_download(self) -> None:
        self._done = True
        newline = '\n'
        Log.info(f'\n[Albums] scan finished, {self._scanned_count:d} / {self._orig_count:d} album(s) enqueued for download, '
                 f'{self._filtered_count_after:d} already existed, '
                 f'{self._skipped_count:d} skipped')
        if len(self._seq) > 0:
            Log.fatal(f'total queue is still at {len(self._seq):d} != 0!')
        if len(self._failed_items) > 0:
            Log.fatal(f'failed items:\n{newline.join(str(fi) for fi in sorted(self._failed_items))}')

    def at_album_completed(self, ai: AlbumInfo) -> None:
        Log.info(f'Album {PREFIX}{ai.my_id:d}: all images processed')
        ai.my_images.clear()
        ai.set_state(AlbumInfo.State.PROCESSED)
        if ai.my_id in self._downloads_active:
            del self._downloads_active[ai.my_id]

    async def run(self) -> None:
        for cv in as_completed([self._prod(), self._state_reporter(), *(self._cons() for _ in range(MAX_IMAGES_QUEUE_SIZE))]):
            await cv
        await self._after_download()

    @property
    def albums_left(self) -> int:
        return len(self._downloads_active)

    @property
    def session(self) -> ClientSession:
        return self._session


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
        self._session = session
        self._seq = list()  # type: List[ImageInfo]
        self._queue = AsyncQueue(MAX_IMAGES_QUEUE_SIZE)  # type: AsyncQueue[Tuple[ImageInfo, Coroutine[Any, Any, DownloadResult]]]
        self._orig_count = 0
        self._downloaded_count = 0
        self._downloaded_amount = 0
        self._filtered_count_after = 0
        self._skipped_count = 0

        self._downloads_active = list()  # type: List[ImageInfo]
        self._writes_active = list()  # type: List[str]
        self._failed_items = list()  # type: List[str]

        self._my_start_time = 0
        self._total_queue_size_last = 0
        self._download_queue_size_last = 0
        self._write_queue_size_last = 0

    async def _at_task_start(self, ii: ImageInfo) -> None:
        self._downloads_active.append(ii)
        Log.trace(f'[queue] image {PREFIX}{ii.my_id:d} added to queue')

    async def _at_task_finish(self, ii: ImageInfo, result: DownloadResult) -> None:
        self._downloads_active.remove(ii)
        Log.trace(f'[queue] image {PREFIX}{ii.my_id:d} removed from queue')
        if ii.my_album.all_done():
            AlbumDownloadWorker.get().at_album_completed(ii.my_album)
        if result == DownloadResult.FAIL_ALREADY_EXISTS:
            self._filtered_count_after += 1
        elif result == DownloadResult.FAIL_SKIPPED:
            self._skipped_count += 1
        elif result == DownloadResult.FAIL_RETRIES:
            self._failed_items.append(ii.my_shortname)
        elif result == DownloadResult.SUCCESS:
            self._downloaded_count += 1
            self._downloaded_amount += ii.my_expected_size

    async def _prod(self) -> None:
        while len(self._seq) > 0:
            if self._queue.full() is False:
                self._seq[0].set_state(ImageInfo.State.QUEUED)
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
        adwn = AlbumDownloadWorker.get()
        base_sleep_time = calc_sleep_time(5.0)
        force_check_seconds = DOWNLOAD_QUEUE_STALL_CHECK_TIMER
        last_check_seconds = 0
        while len(self._seq) + self._queue.qsize() + len(self._downloads_active) > 0:
            await sleep(base_sleep_time if len(self._seq) + self._queue.qsize() > 0 else 1.0)
            queue_size = len(self._seq) + self._queue.qsize()
            download_count = len(self._downloads_active)
            write_count = len(self._writes_active)
            queue_last = self._total_queue_size_last
            downloading_last = self._download_queue_size_last
            write_last = self._write_queue_size_last
            elapsed_seconds = get_elapsed_time_i() - self._my_start_time
            force_check = elapsed_seconds >= force_check_seconds and elapsed_seconds - last_check_seconds >= force_check_seconds
            if queue_last >= queue_size + 10 or downloading_last != download_count or write_last != write_count or force_check:
                last_check_seconds = elapsed_seconds
                self._total_queue_size_last = queue_size
                self._download_queue_size_last = download_count
                self._write_queue_size_last = write_count
                dps = self.processed_count / max(1, elapsed_seconds) or 1.0
                bps = self._downloaded_amount / max(1, elapsed_seconds) or 1.0
                allow_prediction = self._downloaded_count >= min(200, 25 + self._orig_count // 50)
                not_done = queue_size + download_count != 0
                bps_str = f'{bps / Mem.KB:.2f}' if allow_prediction else '??'
                eamount = self._downloaded_amount / max(1, self._downloaded_count) * self._orig_count
                eamount_str = f'{"~" * not_done}{eamount / Mem.MB:.{"0" if not_done else "2"}f}' if allow_prediction else '??'
                damount_str = f'{self._downloaded_amount / Mem.MB:.2f} Mb / {eamount_str} Mb, {bps_str} Kb/s'
                eta_str = format_time(int((queue_size + download_count) / dps)) if allow_prediction else '??:??:??'
                elapsed_str = format_time(elapsed_seconds)
                Log.info(f'[{get_elapsed_time_s()}] albums left: {adwn.albums_left:d}, queue: {queue_size:d}, '
                         f'active: {download_count:d} (writing: {write_count:d}), ETA: {eta_str}, '
                         f'{damount_str} ({self.processed_count:d} in {elapsed_str}, avg {dps * 60:.1f} / min)')

    @staticmethod
    async def _continue_file_checker() -> None:
        adwn = AlbumDownloadWorker.get()
        return await getattr(adwn, '_continue_file_checker')()

    async def _after_download(self) -> None:
        newline = '\n'
        Log.info(f'\nDone. {self._downloaded_count:d} / {self._orig_count:d} file(s) downloaded, '
                 f'{self._filtered_count_after:d} already existed, '
                 f'{self._skipped_count:d} skipped')
        if len(self._seq) > 0:
            Log.fatal(f'total queue is still at {len(self._seq):d} != 0!')
        if len(self._writes_active) > 0:
            Log.fatal(f'active writes count is still at {len(self._writes_active):d} != 0!')
        if len(self._failed_items) > 0:
            Log.fatal(f'failed items:\n{newline.join(sorted(self._failed_items))}')

    async def run(self) -> None:
        adwn = AlbumDownloadWorker.get()
        self._my_start_time = get_elapsed_time_i()
        if not self._seq:
            return
        self._seq.sort(key=lambda ii: ii.my_album.my_id)
        minid, maxid = min(self._seq, key=lambda x: x.my_id).my_id, max(self._seq, key=lambda x: x.my_id).my_id
        Log.info(f'\n[Images] {len(self._seq):d} ids across {adwn.albums_left:d} albums in queue, '
                 f'bound {minid:d} to {maxid:d}. Working...\n')
        for cv in as_completed([self._prod(), self._state_reporter(),  self._continue_file_checker(),
                               *(self._cons() for _ in range(MAX_IMAGES_QUEUE_SIZE))]):
            await cv
        await self._after_download()

    def at_interrupt(self) -> None:
        if len(self._writes_active) > 0:
            if Config.keep_unfinished:
                unfinished_str = '\n '.join(f'{i + 1:d}) {s}' for i, s in enumerate(sorted(self._writes_active)))
                Log.debug(f'at_interrupt: keeping {len(self._writes_active):d} unfinished file(s):\n {unfinished_str}')
                return
            Log.debug(f'at_interrupt: cleaning {len(self._writes_active):d} unfinished file(s)...')
            for unfinished in sorted(self._writes_active):
                Log.debug(f'at_interrupt: trying to remove \'{unfinished}\'...')
                if path.isfile(unfinished):
                    remove(unfinished)
                else:
                    Log.debug(f'at_interrupt: file \'{unfinished}\' not found!')

    def store_image_info(self, ii: ImageInfo) -> None:
        self._orig_count += 1
        self._seq.append(ii)

    @property
    def processed_count(self) -> int:
        return self._downloaded_count + self._filtered_count_after + self._skipped_count + len(self._failed_items)

    @property
    def session(self) -> ClientSession:
        return self._session

    def is_writing(self, videst: Union[ImageInfo, str]) -> bool:
        return (videst.my_fullpath if isinstance(videst, ImageInfo) else videst) in self._writes_active

    def add_to_writes(self, vi: ImageInfo) -> None:
        self._writes_active.append(vi.my_fullpath)

    def remove_from_writes(self, vi: ImageInfo) -> None:
        self._writes_active.remove(vi.my_fullpath)

#
#
#########################################
