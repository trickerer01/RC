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
from defs import (
    NamingFlags, SITE_AJAX_REQUEST_SEARCH_PAGE, SITE_AJAX_REQUEST_UPLOADER_PAGE,
    SITE_AJAX_REQUEST_FAVOURITES_PAGE, SITE_AJAX_REQUEST_MODEL_PAGE,
)
from download import download, at_interrupt
from fetch_html import create_session, fetch_html
from iinfo import AlbumInfo
from logger import Log
from path_util import scan_dest_folder
from rex import re_page_entry, re_paginator
from util import at_startup, has_naming_flag
from validators import find_and_resolve_config_conflicts
from version import APP_NAME

__all__ = ('main_sync',)


async def main(args: Sequence[str]) -> None:
    try:
        arglist = prepare_arglist(args, True)
    except HelpPrintExitException:
        return

    Config.read(arglist, True)

    allow_duplicates: bool = arglist.allow_duplicate_names
    album_ref_class = 'th'

    if find_and_resolve_config_conflicts() is True:
        await sleep(3.0)

    def check_id_bounds(album_id: int) -> int:
        if album_id > Config.end_id:
            Log.trace(f'skipping {album_id:d} > {Config.end_id:d}')
            return 1
        if album_id < Config.start_id:
            Log.trace(f'skipping {album_id:d} < {Config.start_id:d}')
            return -1
        return 0

    v_entries = list()
    maxpage = Config.end if Config.start == Config.end else 0

    pi = Config.start
    async with create_session():
        while pi <= Config.end:
            if pi > maxpage > 0:
                Log.info('reached parsed max page, page scan completed')
                break

            page_addr = (
                # (SITE_AJAX_REQUEST_PLAYLIST_PAGE % (Config.playlist_id, Config.playlist_name, pi)) if Config.playlist_name else
                (SITE_AJAX_REQUEST_FAVOURITES_PAGE % (Config.favourites, pi)) if Config.favourites else
                (SITE_AJAX_REQUEST_UPLOADER_PAGE % (Config.uploader, pi)) if Config.uploader else
                (SITE_AJAX_REQUEST_MODEL_PAGE % (Config.model, pi)) if Config.model else
                (SITE_AJAX_REQUEST_SEARCH_PAGE % (Config.search_tags, Config.search_arts, Config.search_cats, Config.search, pi))
            )
            a_html = await fetch_html(page_addr)
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
                mirefs = a_html.find_all('a', class_=album_ref_class)
                max_id = max(int(re_page_entry.search(str(_.get('href'))).group(1)) for _ in mirefs)
                Log.fatal(f'{APP_NAME}: {max_id:d}')
                return

            Log.info(f'page {pi - 1:d}...{" (this is the last page!)" if (0 < maxpage == pi - 1) else ""}')

            arefs = a_html.find_all('a', class_=album_ref_class)
            lower_count = 0
            orig_count = len(arefs)
            for aref in arefs:
                href = str(aref.get('href'))
                cur_id = int(re_page_entry.search(href).group(1))
                bound_res = check_id_bounds(cur_id)
                if bound_res != 0:
                    if bound_res < 0:
                        lower_count += 1
                    continue
                elif cur_id in v_entries:
                    Log.warn(f'Warning: id {cur_id:d} already queued, skipping')
                    continue
                my_title = aref.parent.find('div', class_='thumb_title').text
                my_utitle = aref['href'][:-1][aref['href'][:-1].rfind('/') + 1:]
                my_preview_link = aref.parent.find('img').get('data-original')
                use_utitle = has_naming_flag(NamingFlags.USE_URL_TITLE)
                v_entries.append(AlbumInfo(cur_id, my_utitle if use_utitle else my_title, preview_link=my_preview_link))

            if pi - 1 > Config.start and lower_count == orig_count > 0 and not Config.scan_all_pages:
                if maxpage == 0 or pi - 1 < maxpage:
                    Log.info(f'Page {pi - 1:d} has all post ids below lower bound. Pages scan stopped!')
                break

        v_entries.reverse()
        orig_count = len(v_entries)

        if allow_duplicates is False:
            known_names = dict()
            i: int
            for i in reversed(range(len(v_entries))):
                title = v_entries[i].title.lower()
                if title not in known_names:
                    known_names[title] = v_entries[i]
                else:
                    Log.debug(f'Removing duplicate of {known_names[title].sname}: {v_entries[i].sname} \'{v_entries[i].title}\'')
                    del v_entries[i]

        removed_count = orig_count - len(v_entries)

        if orig_count == removed_count:
            if orig_count > 0:
                Log.fatal(f'\nAll {orig_count:d} albums already exist. Aborted.')
            else:
                Log.fatal('\nNo albums found. Aborted.')
            return
        elif removed_count > 0:
            Log.info(f'[Deduplicate] {removed_count:d} / {orig_count:d} albums were removed as duplicates!')

        scan_dest_folder()

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
