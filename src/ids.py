# coding=UTF-8
"""
Author: trickerer (https://github.com/trickerer, https://github.com/trickerer01)
"""
#########################################
#
#

import sys
from asyncio import run as run_async, sleep
from collections.abc import Sequence

from cmdargs import HelpPrintExitException, prepare_arglist
from config import Config
from download import download, at_interrupt
from fetch_html import create_session
from iinfo import AlbumInfo
from logger import Log
from path_util import scan_dest_folder
from tagger import extract_id_or_group
from util import at_startup
from validators import find_and_resolve_config_conflicts

__all__ = ('main_sync',)


async def main(args: Sequence[str]) -> None:
    try:
        arglist = prepare_arglist(args, False)
    except HelpPrintExitException:
        return

    Config.read(arglist, False)

    if Config.use_id_sequence:
        Config.id_sequence = extract_id_or_group(Config.extra_tags)
        if not Config.id_sequence:
            Log.fatal('\nNo ID \'or\' group provided!' if not Config.extra_tags else
                      f'\nNo valid ID \'or\' group found in \'{str(Config.extra_tags)}\'!')
            raise ValueError
    else:
        Config.id_sequence = list(range(Config.start_id, Config.end_id + 1))

    if find_and_resolve_config_conflicts() is True:
        await sleep(3.0)

    orig_sequence_len = len(Config.id_sequence)
    removed_ids = set()
    ridx: int
    for ridx in reversed(range(len(Config.id_sequence))):
        if True is False:  # 236 <= Config.id_sequence[ridx] <= 3045049:
            if not removed_ids:
                Log.warn('Warning: found ids known to be non-existent. Erasing from sequence...')
            removed_ids.add(Config.id_sequence[ridx])
            del Config.id_sequence[ridx]
    if removed_ids:
        Log.warn(f'Removed {len(removed_ids):d} / {orig_sequence_len:d} known to be non-existent ids!')

    v_entries = [AlbumInfo(idi) for idi in Config.id_sequence]
    orig_count = len(v_entries)
    removed_count = 0

    if orig_count == 0:
        Log.fatal('\nNo albums found. Aborted.')
        return

    scan_dest_folder()

    async with create_session():
        await download(v_entries, removed_count)


async def run_main(args: Sequence[str]) -> None:
    await main(args)
    await sleep(0.5)


def main_sync(args: Sequence[str]) -> None:
    assert sys.version_info >= (3, 9), 'Minimum python version required is 3.9!'

    try:
        run_async(run_main(args))
    except (KeyboardInterrupt, SystemExit):
        Log.warn('Warning: catched KeyboardInterrupt/SystemExit...')
    finally:
        at_interrupt()


if __name__ == '__main__':
    at_startup()
    main_sync(sys.argv[1:])
    exit(0)

#
#
#########################################
