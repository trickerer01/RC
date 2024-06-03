# coding=UTF-8
"""
Author: trickerer (https://github.com/trickerer, https://github.com/trickerer01)
"""
#########################################
#
#

from asyncio import CancelledError, Task, sleep, get_running_loop
from collections import deque
from os import path, stat
from typing import Optional, Deque, Union

from aiohttp import ClientResponse

from config import Config
from defs import Mem, DOWNLOAD_STATUS_CHECK_TIMER
from downloader import ImageDownloadWorker
from iinfo import ImageInfo
from logger import Log


class ThrottleChecker:
    def __init__(self, vi: ImageInfo) -> None:
        self._ii = vi
        self._init_size = 0
        self._slow_download_amount_threshold = ThrottleChecker._orig_threshold()
        self._interrupted_speeds = deque(maxlen=3)  # type: Deque[float]
        self._speeds = deque(maxlen=5)  # type: Deque[str]
        self._response = None  # type: Optional[ClientResponse]
        self._cheker = None  # type: Optional[Task]

    def prepare(self, response: ClientResponse, init_size: int) -> None:
        self._init_size = init_size
        self._response = response

    def run(self) -> None:
        assert self._cheker is None
        self._cheker = get_running_loop().create_task(self._check_album_download_status())

    def reset(self) -> None:
        if self._cheker is not None:
            self._cheker.cancel()
            self._cheker = None
        self._response = None
        self._speeds.clear()

    @staticmethod
    def _orig_threshold() -> int:
        return ThrottleChecker._calc_threshold(Config.throttle)

    @staticmethod
    def _calc_threshold(speed: Union[int, float]) -> int:
        return max(1, int(DOWNLOAD_STATUS_CHECK_TIMER * speed * Mem.KB))

    @staticmethod
    def _calc_speed(threshold: int) -> float:
        return threshold / Mem.KB / DOWNLOAD_STATUS_CHECK_TIMER

    def _recalculate_slow_download_amount_threshold(self) -> None:
        # Hyperbolic averaging with additional 2% off to prevent cycling interruptions in case of perfect connection stability
        all_speeds = [*self._interrupted_speeds, self._calc_speed(self._slow_download_amount_threshold)]
        avg_speed = 0.98 * sum(all_speeds) / len(all_speeds)
        Log.trace(f'[throttler] recalculation, speeds + threshold: {str(all_speeds)}. New speed threshold: {avg_speed:.6f} KB/s')
        self._slow_download_amount_threshold = self._calc_threshold(avg_speed)

    async def _check_album_download_status(self) -> None:
        dwn = ImageDownloadWorker.get()
        dest = self._ii.my_fullpath
        last_size = self._init_size
        try:
            while True:
                await sleep(float(DOWNLOAD_STATUS_CHECK_TIMER))
                if not dwn.is_writing(dest):  # finished already
                    Log.error(f'[throttler] {self._ii.my_shortname} checker is still running for finished download!')
                    break
                if self._response is None:
                    Log.debug(f'[throttler] {self._ii.my_shortname} self._response is None...')
                    continue
                file_size = stat(dest).st_size if path.isfile(dest) else 0
                last_speed = (file_size - last_size) / Mem.KB / DOWNLOAD_STATUS_CHECK_TIMER
                self._speeds.append(f'{last_speed:.2f} KB/s')
                if file_size < last_size + self._slow_download_amount_threshold:
                    Log.warn(f'[throttler] {self._ii.my_shortname} check failed at {file_size:d} ({last_speed:.2f} KB/s)! '
                             f'Interrupting current try...')
                    self._response.connection.transport.abort()  # abort download task (forcefully - close connection)
                    # calculate normalized threshold if needed
                    if Config.throttle_auto is True and self._orig_threshold() > 10 * Mem.KB:
                        self._interrupted_speeds.append(last_speed)
                        if len(self._interrupted_speeds) >= self._interrupted_speeds.maxlen:
                            self._recalculate_slow_download_amount_threshold()
                            self._interrupted_speeds.clear()
                    break
                else:
                    self._interrupted_speeds.clear()
                last_size = file_size
        except CancelledError:
            pass

    def __str__(self) -> str:
        return f'{self._ii.my_shortname} (orig size {self._init_size / Mem.MB:.2f} MB): {", ".join(self._speeds)}'

    __repr__ = __str__

#
#
#########################################
