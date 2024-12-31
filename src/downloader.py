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
from collections.abc import Callable, Coroutine
from contextlib import suppress
from os import path, remove, makedirs
from typing import Any

from config import Config
from defs import (
    DownloadResult, Mem, MAX_IMAGES_QUEUE_SIZE, DOWNLOAD_QUEUE_STALL_CHECK_TIMER, DOWNLOAD_CONTINUE_FILE_CHECK_TIMER, PREFIX,
    START_TIME, UTF8, CONNECT_REQUEST_DELAY,
)
from iinfo import AlbumInfo, ImageInfo, get_min_max_ids
from logger import Log
from path_util import folder_already_exists_arr
from util import format_time, get_elapsed_time_i, get_elapsed_time_s, calc_sleep_time

__all__ = ('AlbumDownloadWorker', 'ImageDownloadWorker')


class AlbumDownloadWorker:
    """
    Async queue wrapper which binds list of lists of arguments to a download function call and processes them
    asynchronously with a limit of simulteneous downloads defined by MAX_IMAGES_QUEUE_SIZE
    """
    _instance: AlbumDownloadWorker | None = None

    @staticmethod
    def get() -> AlbumDownloadWorker | None:
        return AlbumDownloadWorker._instance

    def __enter__(self) -> AlbumDownloadWorker:
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        AlbumDownloadWorker._instance = None

    def __init__(self, sequence: list[AlbumInfo], func: Callable[[AlbumInfo], Coroutine[Any, Any, DownloadResult]]) -> None:
        assert AlbumDownloadWorker._instance is None
        AlbumDownloadWorker._instance = self

        self._original_sequence = sequence
        self._func = func
        self._seq = [ai for ai in sequence]  # form our own container to erase from
        self._queue: AsyncQueue[tuple[AlbumInfo, Coroutine[Any, Any, DownloadResult]]] = AsyncQueue(1)
        self._orig_count = len(self._seq)
        self._scan_count = 0
        self._scanned_count = 0
        self._downloaded_count = 0
        self._already_exist_count = 0
        self._skipped_count = 0
        self._404_count = 0
        self._minmax_id = get_min_max_ids(self._seq)

        self._404_counter = 0
        self._extra_ids: list[int] = list()

        self._downloads_active: dict[int, AlbumInfo] = dict()
        self._scans_active: list[AlbumInfo] = list()
        self._failed_items: list[int] = list()

        self._total_queue_size_last = 0
        self._scan_queue_size_last = 0

    def _extend_with_extra(self) -> None:
        extra_cur = Config.lookahead - self._404_counter
        if extra_cur > 0:
            last_id = Config.end_id + len(self._extra_ids)
            extra_idseq = [(last_id + i + 1) for i in range(extra_cur)]
            extra_vis = [AlbumInfo(idi) for idi in extra_idseq]
            minid, maxid = get_min_max_ids(extra_vis)
            Log.warn(f'[lookahead] extending queue after {last_id:d} with {extra_cur:d} extra ids: {minid:d}-{maxid:d}')
            self._seq.extend(extra_vis)
            self._original_sequence.extend(extra_vis)
            self._extra_ids.extend(extra_idseq)

    async def _at_task_start(self, ai: AlbumInfo) -> None:
        self._scans_active.append(ai)
        Log.trace(f'[queue] {ai.sname} added to active')

    async def _at_task_finish(self, ai: AlbumInfo, result: DownloadResult) -> None:
        self._scan_count += 1
        if result in (DownloadResult.FAIL_NOT_FOUND, DownloadResult.FAIL_RETRIES,
                      DownloadResult.FAIL_DELETED, DownloadResult.FAIL_FILTERED_OUTER, DownloadResult.FAIL_SKIPPED):
            founditems = list(filter(None, [folder_already_exists_arr(ai.id)]))
            if any(ffs for ffs in founditems):
                newline = '\n'
                Log.info(f'{ai.sname} scan returned {str(result)} but it was already downloaded:'
                         f'\n - {f"{newline} - ".join(f"{newline} - ".join(ffs) for ffs in founditems)}')
        if result == DownloadResult.FAIL_NOT_FOUND:
            ai.set_flag(AlbumInfo.Flags.RETURNED_404)
        self._404_counter = self._404_counter + 1 if result == DownloadResult.FAIL_NOT_FOUND else 0
        if len(self._seq) + self._queue.qsize() == 0 and not not Config.lookahead:
            self._extend_with_extra()
        self._scans_active.remove(ai)
        Log.trace(f'[queue] {ai.sname} removed from active')
        if result == DownloadResult.FAIL_ALREADY_EXISTS:
            self._already_exist_count += 1
        elif result in (DownloadResult.FAIL_SKIPPED, DownloadResult.FAIL_FILTERED_OUTER):
            self._skipped_count += 1
        elif result in (DownloadResult.FAIL_NOT_FOUND, DownloadResult.FAIL_DELETED):
            self._404_count += 1
        elif result == DownloadResult.FAIL_RETRIES:
            self._failed_items.append(ai.id)
        elif result == DownloadResult.SUCCESS:
            self._scanned_count += 1
            self._downloads_active[ai.id] = ai

    async def _prod(self) -> None:
        while self.get_workload_size() > 0:
            if self._queue.full() is False and self._seq:
                self._seq[0].set_state(AlbumInfo.State.QUEUED)
                await self._queue.put((self._seq[0], self._func(self._seq[0])))
                del self._seq[0]
            else:
                await sleep(0.1)

    async def _cons(self) -> None:
        while len(self._seq) + self._queue.qsize() > 0:
            if self._queue.empty() is False and len(self._scans_active) < 1:
                ai, task = await self._queue.get()
                await self._at_task_start(ai)
                result = await task
                await self._at_task_finish(ai, result)
                self._queue.task_done()
            else:
                await sleep(0.07)

    async def _state_reporter(self) -> None:
        base_sleep_time = calc_sleep_time(3.0)
        force_check_seconds = DOWNLOAD_QUEUE_STALL_CHECK_TIMER
        last_check_seconds = 0
        while self.get_workload_size() > 0:
            await sleep(base_sleep_time if len(self._seq) + self._queue.qsize() > 0 else 1.0)
            queue_size = len(self._seq) + self._queue.qsize()
            scan_count = self._scan_count
            extra_count = max(0, scan_count - self._orig_count)
            active_count = len(self._scans_active)
            queue_last = self._total_queue_size_last
            scanning_last = self._scan_queue_size_last
            elapsed_seconds = get_elapsed_time_i()
            force_check = elapsed_seconds >= force_check_seconds and elapsed_seconds - last_check_seconds >= force_check_seconds
            if queue_last != queue_size or scanning_last != active_count or force_check:
                scan_msg = f'scanned: {f"{min(scan_count, self._orig_count)}+{extra_count:d}" if Config.lookahead else str(scan_count)}'
                Log.info(f'[{get_elapsed_time_s()}] {scan_msg}, queue: {queue_size:d}, active: {active_count:d}')
                last_check_seconds = elapsed_seconds
                self._total_queue_size_last = queue_size
                self._scan_queue_size_last = active_count

    async def _continue_file_checker(self) -> None:
        if not Config.store_continue_cmdfile:
            return
        minmax_id = self._minmax_id
        continue_file_name = f'{PREFIX}{START_TIME.strftime("%Y-%m-%d_%H_%M_%S")}_{minmax_id[0]:d}-{minmax_id[1]:d}.continue.conf'
        continue_file_fullpath = f'{Config.dest_base}{continue_file_name}'
        arglist_base = Config.make_continue_arguments()
        base_sleep_time = calc_sleep_time(3.0)
        write_delay = DOWNLOAD_CONTINUE_FILE_CHECK_TIMER
        last_check_seconds = 0
        while self.get_workload_size() + len(self._downloads_active) > 0:
            if self.get_workload_size() == 0:
                elapsed_seconds = get_elapsed_time_i()
                if elapsed_seconds >= write_delay and elapsed_seconds - last_check_seconds >= write_delay:
                    last_check_seconds = elapsed_seconds
                    a_ids = sorted(self._downloads_active)
                    arglist = ['-seq', f'({"~".join(f"id={idi:d}" for idi in a_ids)})'] if len(a_ids) > 1 else ['-start', str(a_ids[0])]
                    arglist.extend(arglist_base)
                    try:
                        Log.trace(f'Storing continue file to \'{continue_file_name}\'...')
                        if not path.isdir(Config.dest_base):
                            makedirs(Config.dest_base)
                        with open(continue_file_fullpath, 'wt', encoding=UTF8, buffering=1) as cfile:
                            cfile.write('\n'.join(str(e) for e in arglist))
                    except (OSError, IOError):
                        Log.error(f'Unable to save continue file to \'{continue_file_name}\'!')
            await sleep(base_sleep_time)
        if not Config.aborted and path.isfile(continue_file_fullpath):
            Log.trace(f'All files downloaded. Removing continue file \'{continue_file_name}\'...')
            remove(continue_file_fullpath)

    async def _after_download(self) -> None:
        newline = '\n'
        Log.info(f'\n[Albums] Scan finished, {self._scanned_count:d} / {self._orig_count:d}'
                 f'{f"+{self.get_extra_count():d}" if Config.lookahead else ""} album(s) enqueued for download, '
                 f'{self._already_exist_count:d} already existed, '
                 f'{self._skipped_count:d} skipped, {self._404_count:d} not found')
        if len(self._seq) > 0:
            Log.fatal(f'total queue is still at {len(self._seq):d} != 0!')
        if len(self._failed_items) > 0:
            Log.fatal(f'failed items:\n{newline.join(str(fi) for fi in sorted(self._failed_items))}')
            self._failed_items.clear()

    def after_download_all(self) -> None:
        newline = '\n'
        Log.info(f'[Albums] Done. {self._downloaded_count:d} / {self._scanned_count:d} album(s) downloaded')
        if len(self._downloads_active) > 0:
            Log.fatal(f'active album downloads queue is still at {len(self._downloads_active):d} != 0!')
        if len(self._failed_items) > 0:
            Log.fatal(f'failed items:\n{newline.join(str(fi) for fi in sorted(self._failed_items))}')

    def at_album_completed(self, ai: AlbumInfo) -> None:
        Log.info(f'Album {ai.sname}: all images processed')
        if all(ii.state == ImageInfo.State.DONE for ii in ai.images):
            self._downloaded_count += 1
        else:
            self._failed_items.append(ai.id)
        ai.images.clear()
        ai.set_state(AlbumInfo.State.PROCESSED)
        if ai.id in self._downloads_active:
            del self._downloads_active[ai.id]

    async def run(self) -> None:
        for cv in as_completed([self._prod(), self._state_reporter(), *(self._cons() for _ in range(MAX_IMAGES_QUEUE_SIZE))]):
            await cv
        await self._after_download()

    @property
    def albums_left(self) -> int:
        return len(self._downloads_active)

    def get_workload_size(self) -> int:
        return len(self._seq) + self._queue.qsize() + len(self._scans_active)

    def get_extra_count(self) -> int:
        return len(self._extra_ids)

    def get_extra_ids(self) -> list[int]:
        return self._extra_ids

    def find_ainfo(self, id_: int) -> AlbumInfo | None:
        with suppress(StopIteration):
            return next(filter(lambda ai: ai.id == id_, self._original_sequence))


class ImageDownloadWorker:
    """
    Async queue wrapper which binds list of lists of arguments to a download function call and processes them
    asynchronously with a limit of simulteneous downloads defined by MAX_IMAGES_QUEUE_SIZE
    """
    _instance: ImageDownloadWorker | None = None

    def __enter__(self) -> ImageDownloadWorker:
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        ImageDownloadWorker._instance = None

    @staticmethod
    def get() -> ImageDownloadWorker | None:
        return ImageDownloadWorker._instance

    def __init__(self, func: Callable[[ImageInfo], Coroutine[Any, Any, DownloadResult]]) -> None:
        assert ImageDownloadWorker._instance is None
        ImageDownloadWorker._instance = self

        self._func = func
        self._seq: list[ImageInfo] = list()
        self._queue: AsyncQueue[tuple[ImageInfo, Coroutine[Any, Any, DownloadResult]]] = AsyncQueue(MAX_IMAGES_QUEUE_SIZE)
        self._orig_count = 0
        self._downloaded_count = 0
        self._downloaded_amount = 0
        self._filtered_count_after = 0
        self._skipped_count = 0

        self._downloads_active: list[ImageInfo] = list()
        self._writes_active: list[str] = list()
        self._failed_items: list[str] = list()

        self._my_start_time = 0
        self._total_queue_size_last = 0
        self._download_queue_size_last = 0
        self._write_queue_size_last = 0

    async def _at_task_start(self, ii: ImageInfo) -> None:
        self._downloads_active.append(ii)
        # Log.trace(f'[queue] {ii.sname} added to active')

    async def _at_task_finish(self, ii: ImageInfo, result: DownloadResult) -> None:
        self._downloads_active.remove(ii)
        # Log.trace(f'[queue] {ii.sname} removed from active')
        if ii.album.all_done():
            AlbumDownloadWorker.get().at_album_completed(ii.album)
        if result == DownloadResult.FAIL_ALREADY_EXISTS:
            self._filtered_count_after += 1
        elif result == DownloadResult.FAIL_SKIPPED:
            self._skipped_count += 1
        elif result == DownloadResult.FAIL_RETRIES:
            self._failed_items.append(ii.my_shortname)
        elif result == DownloadResult.SUCCESS:
            self._downloaded_count += 1
            self._downloaded_amount += ii.expected_size

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
        base_sleep_time = calc_sleep_time(3.0)
        force_check_seconds = DOWNLOAD_QUEUE_STALL_CHECK_TIMER
        last_check_seconds = 0
        while self.get_workload_size() > 0:
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
                eamount = self._downloaded_amount / max(1, self._downloaded_count) * (self._orig_count - self._filtered_count_after)
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
        adwn = AlbumDownloadWorker.get()
        newline = '\n'
        Log.info(f'\n[Images] Done. {self._downloaded_count:d} / {self._orig_count:d} file(s) downloaded, '
                 f'{self._filtered_count_after:d} already existed, '
                 f'{self._skipped_count:d} skipped')
        if len(self._seq) > 0:
            Log.fatal(f'total queue is still at {len(self._seq):d} != 0!')
        if len(self._writes_active) > 0:
            Log.fatal(f'active writes count is still at {len(self._writes_active):d} != 0!')
        if len(self._failed_items) > 0:
            Log.fatal(f'failed items:\n{newline.join(sorted(self._failed_items))}')
        adwn.after_download_all()

    async def run(self) -> None:
        adwn = AlbumDownloadWorker.get()
        self._my_start_time = get_elapsed_time_i()
        if not self._seq:
            return
        self._seq.sort(key=lambda ii: ii.album.id)
        eta_min = int(2.0 + (CONNECT_REQUEST_DELAY * 1.5 + 0.02) * len(self._seq))
        minid, maxid = min(self._seq, key=lambda x: x.id).id, max(self._seq, key=lambda x: x.id).id
        Log.info(f'\n[Images] {len(self._seq):d} ids across {adwn.albums_left:d} album(s), bound {minid:d} to {maxid:d}. Working...\n'
                 f'\nThis will take at least {eta_min:d} seconds{f" ({format_time(eta_min)})" if eta_min >= 60 else ""}!\n')
        for cv in as_completed([self._prod(), self._state_reporter(), self._continue_file_checker(),
                               *(self._cons() for _ in range(MAX_IMAGES_QUEUE_SIZE))]):
            await cv
        await self._after_download()

    def at_interrupt(self) -> None:
        if len(self._downloads_active) > 0:
            active_items = sorted([ii for ii in self._downloads_active if path.isfile(ii.my_fullpath)
                                   and ii.has_flag(ImageInfo.Flags.FILE_WAS_CREATED)], key=lambda ii: ii.id)
            if Config.keep_unfinished:
                unfinished_str = '\n '.join(f'{i + 1:d}) {ii.my_fullpath}' for i, ii in enumerate(active_items))
                Log.debug(f'at_interrupt: keeping {len(active_items):d} unfinished file(s):\n {unfinished_str}')
                return
            for ii in active_items:
                Log.debug(f'at_interrupt: trying to remove \'{ii.my_fullpath}\'...')
                remove(ii.my_fullpath)

    def store_image_info(self, ii: ImageInfo) -> None:
        self._orig_count += 1
        self._seq.append(ii)

    @property
    def processed_count(self) -> int:
        return self._downloaded_count + self._filtered_count_after + self._skipped_count + len(self._failed_items)

    def is_writing(self, iidest: ImageInfo | str) -> bool:
        return (iidest.my_fullpath if isinstance(iidest, ImageInfo) else iidest) in self._writes_active

    def add_to_writes(self, vi: ImageInfo) -> None:
        self._writes_active.append(vi.my_fullpath)

    def remove_from_writes(self, vi: ImageInfo) -> None:
        self._writes_active.remove(vi.my_fullpath)

    def get_workload_size(self) -> int:
        return len(self._seq) + self._queue.qsize() + len(self._downloads_active)

#
#
#########################################
