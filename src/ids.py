# coding=UTF-8
"""
Author: trickerer (https://github.com/trickerer, https://github.com/trickerer01)
"""
#########################################
#
#

import sys
from asyncio import run as run_async, sleep
from typing import Sequence

from cmdargs import prepare_arglist, HelpPrintExitException
from config import Config
from defs import SITE_AJAX_REQUEST_ALBUM
from download import download, at_interrupt
from fetch_html import make_session
from iinfo import AlbumInfo
from logger import Log
from tagger import try_parse_id_or_group
from util import at_startup
from validators import find_and_resolve_config_conflicts

__all__ = ('main_sync',)


async def main(args: Sequence[str]) -> None:
    try:
        arglist = prepare_arglist(args, False)
    except HelpPrintExitException:
        return

    Config.read(arglist, False)

    id_sequence = try_parse_id_or_group(Config.extra_tags) if Config.use_id_sequence else [int()] * 0
    if Config.use_id_sequence is True and len(id_sequence) == 0:
        Log.fatal(f'\nInvalid ID \'or\' group \'{Config.extra_tags[0] if len(Config.extra_tags) > 0 else ""}\'!')
        raise ValueError

    if find_and_resolve_config_conflicts() is True:
        await sleep(3.0)

    async with await make_session() as s:
        if len(id_sequence) == 0:
            id_sequence = list(range(Config.start_id, Config.end_id + 1))
        else:
            Config.extra_tags.clear()

        v_entries = [AlbumInfo(idi, SITE_AJAX_REQUEST_ALBUM % (idi, 'z')) for idi in id_sequence]

        if len(v_entries) == 0:
            Log.fatal('\nNo albums found. Aborted.')
            return

        minid, maxid = min(v_entries, key=lambda x: x.my_id).my_id, max(v_entries, key=lambda x: x.my_id).my_id
        Log.info(f'\nOk! {len(v_entries):d} ids, bound {minid:d} to {maxid:d}. Working...\n')

        await download(v_entries, s)


async def run_main(args: Sequence[str]) -> None:
    await main(args)
    await sleep(0.5)


def main_sync(args: Sequence[str]) -> None:
    assert sys.version_info >= (3, 7), 'Minimum python version required is 3.7!'

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
