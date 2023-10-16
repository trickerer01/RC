# coding=UTF-8
"""
Author: trickerer (https://github.com/trickerer, https://github.com/trickerer01)
"""
#########################################
#
#

import sys
from asyncio import run as run_async, sleep
from re import compile as re_compile
from typing import Sequence

from cmdargs import prepare_arglist_pages, read_cmdfile, is_parsed_cmdfile
from defs import Log, Config, LoggingFlags, HelpPrintExitException, prefixp, at_startup, SITE_AJAX_REQUEST_PAGE, SEARCH_RULE_ALL
from download import download, at_interrupt
from fetch_html import make_session, fetch_html
from iinfo import AlbumInfo
from validators import find_and_resolve_config_conflicts

__all__ = ('main_sync',)


async def main(args: Sequence[str]) -> None:
    try:
        arglist = prepare_arglist_pages(args)
        while is_parsed_cmdfile(arglist):
            arglist = prepare_arglist_pages(read_cmdfile(arglist.path))
    except HelpPrintExitException:
        return
    except Exception:
        Log.fatal(f'\nUnable to parse cmdline. Exiting.\n{sys.exc_info()[0]}: {sys.exc_info()[1]}')
        return

    try:
        Config.read(arglist, True)
        search_str = arglist.search  # type: str
        search_tags = arglist.search_tag  # type: str
        search_arts = arglist.search_art  # type: str
        search_cats = arglist.search_cat  # type: str
        search_rule_tag = arglist.search_rule_tag  # type: str
        search_rule_art = arglist.search_rule_art  # type: str
        search_rule_cat = arglist.search_rule_cat  # type: str
        allow_duplicates = arglist.no_deduplicate_names  # type: bool

        re_page_entry = re_compile(r'albums/(\d+)/')
        re_paginator = re_compile(r'from(?:_albums)?:(\d+)')
        album_ref_class = 'th'

        if Config.get_maxid:
            Config.logging_flags = LoggingFlags.LOGGING_FATAL
            Config.start = Config.end = Config.start_id = Config.end_id = 1

        if Config.start_id > Config.end_id:
            Log.fatal(f'\nError: invalid album id bounds: start ({Config.start_id:d}) > end ({Config.end_id:d})')
            raise ValueError

        if search_tags.find(',') != -1 and search_rule_tag == SEARCH_RULE_ALL:
            search_tags = f'{SEARCH_RULE_ALL},{search_tags}'
        if search_arts.find(',') != -1 and search_rule_art == SEARCH_RULE_ALL:
            search_arts = f'{SEARCH_RULE_ALL},{search_arts}'
        if search_cats.find(',') != -1 and search_rule_cat == SEARCH_RULE_ALL:
            search_cats = f'{SEARCH_RULE_ALL},{search_cats}'

        if find_and_resolve_config_conflicts() is True:
            await sleep(3.0)
    except Exception:
        Log.fatal(f'\nError reading parsed arglist!\n{sys.exc_info()[0]}: {sys.exc_info()[1]}')
        return

    def check_id_bounds(album_id: int) -> bool:
        if album_id > Config.end_id:
            Log.trace(f'skipping {album_id:d} > {Config.end_id:d}')
            return False
        if album_id < Config.start_id:
            Log.trace(f'skipping {album_id:d} < {Config.start_id:d}')
            return False
        return True

    v_entries = list()
    maxpage = Config.end if Config.start == Config.end else 0

    pi = Config.start
    async with await make_session() as s:
        while pi <= Config.end:
            if pi > maxpage > 0:
                Log.info('reached parsed max page, page scan completed')
                break

            page_addr = SITE_AJAX_REQUEST_PAGE % (search_tags, search_arts, search_cats, search_str, pi)
            a_html = await fetch_html(page_addr, session=s)
            if not a_html:
                Log.error(f'Error: cannot get html for page {pi:d}')
                continue

            pi += 1

            if maxpage == 0:
                for page_ajax in a_html.find_all('a', attrs={'data-action': 'ajax'}):
                    try:
                        maxpage = max(maxpage, int(re_paginator.search(str(page_ajax.get('data-parameters'))).group(1)))
                    except Exception:
                        pass
                if maxpage == 0:
                    Log.info('Could not extract max page, assuming single page search')
                    maxpage = 1
                else:
                    Log.debug(f'Extracted max page: {maxpage:d}')

            if Config.get_maxid:
                miref = a_html.find('a', class_=album_ref_class)
                max_id = re_page_entry.search(str(miref.get('href'))).group(1)
                Log.fatal(f'{prefixp()[:2].upper()}: {max_id}')
                return

            Log.info(f'page {pi - 1:d}...{" (this is the last page!)" if (0 < maxpage == pi - 1) else ""}')

            arefs = a_html.find_all('a', class_=album_ref_class)
            for aref in arefs:
                href = str(aref.get('href'))
                cur_id = int(re_page_entry.search(href).group(1))
                if check_id_bounds(cur_id) is False:
                    continue
                elif cur_id in v_entries:
                    Log.warn(f'Warning: id {cur_id:d} already queued, skipping')
                    continue
                my_title = str(aref.get('title'))
                v_entries.append(AlbumInfo(cur_id, href, my_title))

        if len(v_entries) == 0:
            Log.fatal('\nNo albums found. Aborted.')
            return

        v_entries.reverse()

        if allow_duplicates is False:
            orig_count = len(v_entries)
            known_names = dict()
            for i in reversed(range(len(v_entries))):  # type: int
                title = v_entries[i].my_title.lower()
                if title not in known_names:
                    known_names[title] = v_entries[i]
                else:
                    Log.debug(f'Removing duplicate of {prefixp()}{known_names[title].my_id:d}: '
                              f'{prefixp()}{v_entries[i].my_id:d} \'{v_entries[i].my_title}\'')
                    del v_entries[i]
            removed_count = orig_count - len(v_entries)
            if removed_count > 0:
                Log.info(f'[Deduplicate] {removed_count:d} / {orig_count:d} albums were removed as duplicates!')

        minid, maxid = min(v_entries, key=lambda x: x.my_id).my_id, max(v_entries, key=lambda x: x.my_id).my_id
        Log.info(f'\nOk! {len(v_entries):d} ids, bound {minid:d} to {maxid:d}. Working...\n')

        await download(v_entries, s)


async def run_main(args: Sequence[str]) -> None:
    await main(args)
    await sleep(0.5)


def main_sync(args: Sequence[str]) -> None:
    assert sys.version_info >= (3, 7), 'Minimum python version required is 3.7!'

    interrupted = False
    try:
        run_async(run_main(args))
    except (KeyboardInterrupt, SystemExit):
        Log.warn('Warning: catched KeyboardInterrupt/SystemExit...')
        interrupted = True
    except Exception:
        interrupted = True
    finally:
        if interrupted:
            at_interrupt()


if __name__ == '__main__':
    at_startup()
    main_sync(sys.argv[1:])
    exit(0)

#
#
#########################################
