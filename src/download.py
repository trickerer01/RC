# coding=UTF-8
"""
Author: trickerer (https://github.com/trickerer, https://github.com/trickerer01)
"""
#########################################
#
#

from asyncio import sleep, get_running_loop, Task, CancelledError
from os import path, stat, remove, makedirs
from random import uniform as frand
from typing import Optional, Iterable, Dict

from aiofile import async_open
from aiohttp import ClientSession, ClientResponse, ClientPayloadError

from config import Config
from defs import (
    CONNECT_RETRIES_BASE, DOWNLOAD_POLICY_ALWAYS, DOWNLOAD_MODE_TOUCH, DOWNLOAD_MODE_SKIP, DOWNLOAD_STATUS_CHECK_TIMER, TAGS_CONCAT_CHAR,
    DownloadResult, NamingFlags, Mem, PREFIX,
)
from downloader import AlbumDownloadWorker, ImageDownloadWorker
from fetch_html import fetch_html, wrap_request
from iinfo import AlbumInfo, ImageInfo, export_album_info
from logger import Log
from rex import re_replace_symbols, prepare_regex_search
from scenario import DownloadScenario
from tagger import filtered_tags, is_filtered_out_by_extra_tags
from util import has_naming_flag

__all__ = ('download', 'at_interrupt')


async def download(sequence: Iterable[AlbumInfo], session: ClientSession) -> None:
    async with session:
        with AlbumDownloadWorker(sequence, process_album, session) as adwn:
            with ImageDownloadWorker(download_image, session) as idwn:
                await adwn.run()
                await idwn.run()
    await export_album_info(sequence)


async def process_album(ai: AlbumInfo) -> DownloadResult:
    adwn = AlbumDownloadWorker.get()
    idwn = ImageDownloadWorker.get()
    scenario = Config.scenario  # type: Optional[DownloadScenario]
    sname = f'{PREFIX}{ai.my_id:d}.album'

    ai.set_state(AlbumInfo.AlbumState.ACTIVE)
    a_html = await fetch_html(ai.my_link, session=adwn.session)
    if a_html is None:
        Log.error(f'Error: unable to retreive html for {sname}! Aborted!')
        return DownloadResult.FAIL_RETRIES

    if a_html.find('title', string='404 Not Found'):
        Log.error(f'Got error 404 for {sname}, skipping...')
        return DownloadResult.FAIL_SKIPPED

    if not ai.my_title:
        titleh1 = a_html.find('h1', class_='title_video')  # not a mistake
        ai.my_title = titleh1.text if titleh1 else ''
    try:
        my_authors = [str(a.string).lower() for a in a_html.find('div', string='Artists:').parent.find_all('span')]
    except Exception:
        Log.warn(f'Warning: cannot extract authors for {sname}.')
        my_authors = list()
    try:
        my_categories = [str(c.string).lower() for c in a_html.find('div', string='Categories:').parent.find_all('span')]
    except Exception:
        Log.warn(f'Warning: cannot extract categories for {sname}.')
        my_categories = list()
    tdiv = a_html.find('div', string='Tags:')
    if tdiv is None:
        Log.info(f'Warning: album {sname} has no tags!')
    tags = [str(elem.string) for elem in tdiv.parent.find_all('a', class_='tag_item')] if tdiv else ['']
    tags_raw = [tag.replace(' ', '_').lower() for tag in tags if len(tag) > 0]
    for add_tag in [ca.replace(' ', '_') for ca in my_categories + my_authors if len(ca) > 0]:
        if add_tag not in tags_raw:
            tags_raw.append(add_tag)
    if is_filtered_out_by_extra_tags(ai.my_id, tags_raw, Config.extra_tags, False, ai.my_subfolder):
        Log.info(f'Info: album {sname} is filtered out by{" outer" if scenario is not None else ""} extra tags, skipping...')
        return DownloadResult.FAIL_SKIPPED
    if scenario is not None:
        matching_sq = scenario.get_matching_subquery(ai.my_id, tags_raw)
        utpalways_sq = scenario.get_utp_always_subquery() if tdiv is None else None
        if matching_sq:
            ai.my_subfolder = matching_sq.subfolder
        elif utpalways_sq:
            ai.my_subfolder = utpalways_sq.subfolder
        else:
            Log.info(f'Info: unable to find matching or utp scenario subquery for {sname}, skipping...')
            return DownloadResult.FAIL_SKIPPED
    elif tdiv is None and len(Config.extra_tags) > 0 and Config.utp != DOWNLOAD_POLICY_ALWAYS:
        Log.warn(f'Warning: could not extract tags from {sname}, skipping due to untagged albums download policy...')
        return DownloadResult.FAIL_SKIPPED
    if Config.save_tags:
        ai.my_tags = ' '.join(sorted(tags_raw))
    if Config.save_comments:
        cidivs = a_html.find_all('div', class_='comment-info')
        cudivs = [cidiv.find('a') for cidiv in cidivs]
        cbdivs = [cidiv.find('div', class_='coment-text') for cidiv in cidivs]
        if cudivs and cbdivs:
            assert len(cbdivs) == len(cudivs)
        if Config.save_comments:
            comments_list = [f'{cudivs[i].text}:\n' + cbdivs[i].get_text('\n').strip() for i in range(len(cbdivs))]
            ai.my_comments = ('\n' + '\n\n'.join(comments_list) + '\n') if comments_list else ''
    tags_str = filtered_tags(list(sorted(tags_raw)))
    my_tags = tags_str

    try:
        file_divs = a_html.find('div', 'thumbs-gallery')
        file_arefs = file_divs.find_all('a')
        file_links = [str(aref.get('href')) for aref in file_arefs]
    except Exception:
        Log.error(f'Cannot find download section for {sname}, failed!')
        return DownloadResult.FAIL_RETRIES

    re_flink = prepare_regex_search(rf'/{ai.my_id:d}/(\d+)(\.[^/]{{3,5}})/')
    rc_ = PREFIX if has_naming_flag(NamingFlags.PREFIX) else ''
    extra_len = 3 + 1  # 3 underscores + 1 extra slash
    fname = f'{rc_}{ai.my_id:d}{f"_{ai.my_title}" if ai.my_title and has_naming_flag(NamingFlags.TITLE) else ""}'
    if has_naming_flag(NamingFlags.TAGS):
        while len(my_tags) > max(0, 200 - (len(ai.my_folder_full) + len(fname) + extra_len)):
            my_tags = my_tags[:max(0, my_tags.rfind(TAGS_CONCAT_CHAR))]
        fname = f'{fname}{f"_({my_tags})" if len(my_tags) > 0 else ""}'
    if len(my_tags) == 0 and len(fname) > max(0, 200 - (len(ai.my_folder_full) + extra_len)):
        fname = fname[:max(0, 200 - (len(ai.my_folder_full) + extra_len))]
    ai.my_name = re_replace_symbols.sub('_', fname)
    for ilink in file_links:
        matches = re_flink.search(ilink).groups()
        ii = ImageInfo(ai, int(matches[0]), ilink, f'{rc_}{matches[0]}{matches[1]}')
        ai.my_images.append(ii)
    if path.isdir(ai.my_folder_full) and all(path.isfile(imi.my_fullpath) for imi in ai.my_images):
        Log.info(f'Album {sname} \'{ai.my_name}\' and all its {len(ai.my_images):d} images already exist. Skipped.')
        ai.my_images.clear()
        return DownloadResult.FAIL_ALREADY_EXISTS

    Log.info(f'{sname}: {len(ai.my_images):d} images')
    [idwn.store_image_info(ii) for ii in ai.my_images]

    ai.set_state(AlbumInfo.AlbumState.SCANNED)
    return DownloadResult.SUCCESS


async def check_image_download_status(idi: int, dest: str, resp: ClientResponse) -> None:
    idwn = ImageDownloadWorker.get()
    sname = f'{PREFIX}{idi:d}.jpg'
    check_timer = float(DOWNLOAD_STATUS_CHECK_TIMER)
    try:
        # Log.trace(f'{sname} status check started...')
        last_size = -1
        while True:
            await sleep(check_timer)
            if not idwn.is_writing(dest):  # finished already
                Log.error(f'{sname} status checker is still running for finished download!')
                break
            file_size = stat(dest).st_size if path.isfile(dest) else 0
            if file_size in (0, last_size):
                Log.error(f'{sname} status check failed (download stalled at {file_size:d})! Interrupting current try...')
                resp.connection.transport.abort()  # abort download task (forcefully - close connection)
                break
            # Log.trace(f'{sname} status check passed at {file_size:d}...')
            last_size = file_size
    except CancelledError:
        # Log.trace(f'{sname} status check cancelled...')
        pass


async def download_image(ii: ImageInfo) -> DownloadResult:
    idwn = ImageDownloadWorker.get()
    sname = f'{PREFIX}{ii.my_id:d}.jpg'
    sfilename = f'{ii.my_sfolder}{ii.my_album.my_sfolder_full}{ii.my_filename}'
    retries = 0
    ret = DownloadResult.SUCCESS
    skip = Config.dm == DOWNLOAD_MODE_SKIP
    status_checker = None  # type: Optional[Task]

    if skip is True:
        ii.set_state(ImageInfo.ImageState.DONE)
    else:
        ii.set_state(ImageInfo.ImageState.DOWNLOADING)
        if not path.isdir(ii.my_folder_full):
            try:
                makedirs(ii.my_folder_full)
            except Exception:
                raise IOError(f'ERROR: Unable to create subfolder \'{ii.my_folder_full}\'!')
        else:
            rv_curfile = path.isfile(ii.my_fullpath)
            if rv_curfile and Config.continue_mode is False:
                Log.info(f'{ii.my_filename} already exists. Skipped.')
                return DownloadResult.FAIL_ALREADY_EXISTS

    while (not skip) and retries < CONNECT_RETRIES_BASE:
        try:
            if Config.dm == DOWNLOAD_MODE_TOUCH:
                Log.info(f'Saving<touch> {sname} {0.0:.2f} Mb to {sfilename}')
                with open(ii.my_fullpath, 'wb'):
                    ii.set_state(ImageInfo.ImageState.DONE)
                break

            file_size = stat(ii.my_fullpath).st_size if path.isfile(ii.my_fullpath) else 0
            hkwargs = {'headers': {'Range': f'bytes={file_size:d}-'}} if file_size > 0 else {}  # type: Dict[str, Dict[str, str]]
            r = None
            async with await wrap_request(idwn.session, 'GET', ii.my_link, **hkwargs) as r:
                content_len = r.content_length or 0
                content_range_s = r.headers.get('Content-Range', '/').split('/', 1)
                content_range = int(content_range_s[1]) if len(content_range_s) > 1 and content_range_s[1].isnumeric() else 1
                if (content_len == 0 or r.status == 416) and file_size >= content_range:
                    Log.warn(f'{sname} is already completed, size: {file_size:d} ({file_size / Mem.MB:.2f} Mb)')
                    ii.set_state(ImageInfo.ImageState.DONE)
                    break
                if r.status == 404:
                    Log.error(f'Got 404 for {sname}...!')
                    retries = CONNECT_RETRIES_BASE - 1
                    ret = DownloadResult.FAIL_NOT_FOUND
                if r.content_type and 'text' in r.content_type:
                    Log.error(f'File not found at {ii.my_link}!')
                    raise FileNotFoundError(ii.my_link)

                ii.my_expected_size = file_size + content_len
                starting_str = f' <continuing at {file_size:d}>' if file_size else ''
                total_str = f' / {ii.my_expected_size / Mem.MB:.2f}' if file_size else ''
                Log.info(f'Saving{starting_str} {sname} {content_len / Mem.MB:.2f}{total_str} Mb to {sfilename}')

                idwn.add_to_writes(ii)
                ii.set_state(ImageInfo.ImageState.WRITING)
                status_checker = get_running_loop().create_task(check_image_download_status(ii.my_id, ii.my_fullpath, r))
                async with async_open(ii.my_fullpath, 'ab') as outf:
                    async for chunk in r.content.iter_chunked(512 * Mem.KB):
                        await outf.write(chunk)
                status_checker.cancel()
                idwn.remove_from_writes(ii)

                file_size = stat(ii.my_fullpath).st_size
                if ii.my_expected_size and file_size != ii.my_expected_size:
                    Log.error(f'Error: file size mismatch for {sfilename}: {file_size:d} / {ii.my_expected_size:d}')
                    raise IOError(ii.my_link)

                ii.set_state(ImageInfo.ImageState.DONE)
                break
        except Exception as e:
            import sys
            print(sys.exc_info()[0], sys.exc_info()[1])
            if (r is None or r.status != 403) and isinstance(e, ClientPayloadError) is False:
                retries += 1
                Log.error(f'{sfilename}: error #{retries:d}...')
            if r is not None and r.closed is False:
                r.close()
            # Network error may be thrown before item is added to active downloads
            if idwn.is_writing(ii):
                idwn.remove_from_writes(ii)
            if status_checker is not None:
                status_checker.cancel()
            if retries < CONNECT_RETRIES_BASE:
                ii.set_state(ImageInfo.ImageState.DOWNLOADING)
                await sleep(frand(1.0, 7.0))
            elif Config.keep_unfinished is False and path.isfile(ii.my_fullpath):
                Log.error(f'Failed to download {sfilename}. Removing unfinished file...')
                remove(ii.my_fullpath)

    ret = (ret if ret == DownloadResult.FAIL_NOT_FOUND else
           DownloadResult.SUCCESS if retries < CONNECT_RETRIES_BASE else
           DownloadResult.FAIL_RETRIES)

    if ret != DownloadResult.SUCCESS:
        ii.set_state(ImageInfo.ImageState.FAILED)

    return ret


def at_interrupt() -> None:
    idwn = ImageDownloadWorker.get()
    if idwn is not None:
        return idwn.at_interrupt()

#
#
#########################################
