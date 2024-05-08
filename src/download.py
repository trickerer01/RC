# coding=UTF-8
"""
Author: trickerer (https://github.com/trickerer, https://github.com/trickerer01)
"""
#########################################
#
#

from asyncio import Task, CancelledError, sleep, get_running_loop
from os import path, stat, remove, makedirs, listdir
from random import uniform as frand
from typing import Optional, List, Dict

from aiofile import async_open
from aiohttp import ClientSession, ClientResponse, ClientPayloadError

from config import Config
from defs import (
    Mem, NamingFlags, DownloadResult, CONNECT_RETRIES_BASE, SITE_AJAX_REQUEST_ALBUM, DOWNLOAD_POLICY_ALWAYS, DOWNLOAD_MODE_TOUCH, PREFIX,
    DOWNLOAD_MODE_SKIP, TAGS_CONCAT_CHAR, DOWNLOAD_STATUS_CHECK_TIMER,
    FULLPATH_MAX_BASE_LEN, CONNECT_REQUEST_DELAY,
)
from downloader import AlbumDownloadWorker, ImageDownloadWorker
from fetch_html import fetch_html, wrap_request, make_session
from iinfo import AlbumInfo, ImageInfo, export_album_info, get_min_max_ids
from logger import Log
from path_util import folders_already_exists, try_rename
from rex import re_replace_symbols, re_read_href, re_album_foldername, re_media_filename
from scenario import DownloadScenario
from tagger import filtered_tags, is_filtered_out_by_extra_tags
from util import has_naming_flag, format_time, normalize_path

__all__ = ('download', 'at_interrupt')


async def download(sequence: List[AlbumInfo], filtered_count: int, session: ClientSession = None) -> None:
    minid, maxid = get_min_max_ids(sequence)
    eta_min = int(2.0 + (CONNECT_REQUEST_DELAY + 0.3 + 0.05) * len(sequence))
    Log.info(f'\nOk! {len(sequence):d} ids (+{filtered_count:d} filtered out), bound {minid:d} to {maxid:d}. Working...\n'
             f'\nThis will take at least {eta_min:d} seconds{f" ({format_time(eta_min)})" if eta_min >= 60 else ""}!\n')
    async with session or make_session() as session:
        with AlbumDownloadWorker(sequence, process_album, session) as adwn:
            with ImageDownloadWorker(download_image, session) as idwn:
                await adwn.run()
                await idwn.run()
    export_album_info(sequence)


async def process_album(ai: AlbumInfo) -> DownloadResult:
    adwn, idwn = AlbumDownloadWorker.get(), ImageDownloadWorker.get()
    scenario = Config.scenario  # type: Optional[DownloadScenario]
    sname = ai.sname
    my_tags = 'no_tags'
    rating = ai.rating
    score = ''

    ai.set_state(AlbumInfo.State.ACTIVE)
    a_html = await fetch_html(SITE_AJAX_REQUEST_ALBUM % ai.id, session=adwn.session)
    if a_html is None:
        Log.error(f'Error: unable to retreive html for {sname}! Aborted!')
        return DownloadResult.FAIL_RETRIES

    if a_html.find('title', string='404 Not Found'):
        Log.error(f'Got error 404 for {sname}, skipping...')
        return DownloadResult.FAIL_SKIPPED

    if not ai.title:
        titleh1 = a_html.find('h1', class_='title_video')  # not a mistake
        ai.title = titleh1.text if titleh1 else ''
    try:
        votes_int = int(a_html.find('span', class_='set-votes').text[1:-1].replace(' likes', '').replace(' like', ''))
        rating_float = float(a_html.find('span', class_='set-rating').text[:-1])
        rating = str(int(rating_float) or '')
        score = f'{round((votes_int * rating_float) / 100.0):d}'
    except Exception:
        Log.warn(f'Warning: cannot extract score for {sname}.')
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
    tags = [str(elem.string) for elem in tdiv.parent.find_all('a')] if tdiv else ['']
    tags_raw = [tag.replace(' ', '_').lower() for tag in tags if len(tag) > 0]
    for add_tag in [ca.replace(' ', '_') for ca in my_categories + my_authors if len(ca) > 0]:
        if add_tag not in tags_raw:
            tags_raw.append(add_tag)
    if is_filtered_out_by_extra_tags(ai, tags_raw, Config.extra_tags, Config.id_sequence, ai.subfolder):
        Log.info(f'Info: album {sname} is filtered out by{" outer" if scenario is not None else ""} extra tags, skipping...')
        return DownloadResult.FAIL_SKIPPED
    for vsrs, csri, srn, pc in zip((score, rating), (Config.min_score, Config.min_rating), ('score', 'rating'), ('', '%')):
        if len(vsrs) > 0 and csri is not None:
            try:
                if int(vsrs) < csri:
                    Log.info(f'Info: album {sname} has low {srn} \'{vsrs}{pc}\' (required {csri:d}), skipping...')
                    return DownloadResult.FAIL_SKIPPED
            except Exception:
                pass
    if scenario is not None:
        matching_sq = scenario.get_matching_subquery(ai, tags_raw, score, rating)
        utpalways_sq = scenario.get_utp_always_subquery() if tdiv is None else None
        if matching_sq:
            ai.subfolder = matching_sq.subfolder
        elif utpalways_sq:
            ai.subfolder = utpalways_sq.subfolder
        else:
            Log.info(f'Info: unable to find matching or utp scenario subquery for {sname}, skipping...')
            return DownloadResult.FAIL_SKIPPED
    elif tdiv is None and len(Config.extra_tags) > 0 and Config.utp != DOWNLOAD_POLICY_ALWAYS:
        Log.warn(f'Warning: could not extract tags from {sname}, skipping due to untagged albums download policy...')
        return DownloadResult.FAIL_SKIPPED
    if Config.save_tags:
        ai.tags = ' '.join(sorted(tags_raw))
    if Config.save_descriptions or Config.save_comments:
        cidivs = a_html.find_all('div', class_='comment-info')
        cudivs = [cidiv.find('a') for cidiv in cidivs]
        ctdivs = [cidiv.find('div', class_='coment-text') for cidiv in cidivs]
        desc_em = a_html.find('em')  # exactly one
        uploader_div = a_html.find('div', string=' Uploaded By: ')
        my_uploader = uploader_div.parent.find('a', class_='name').text.lower().strip() if uploader_div else 'unknown'
        has_description = (cudivs[-1].text.lower() == my_uploader) if (cudivs and ctdivs) else False  # first comment by uploader
        if cudivs and ctdivs:
            assert len(ctdivs) == len(cudivs)
        if Config.save_descriptions:
            desc_comment = (f'{cudivs[-1].text}:\n' + ctdivs[-1].get_text('\n').strip()) if has_description else ''
            desc_base = (f'\n{my_uploader}:\n' + desc_em.get_text('\n') + '\n') if desc_em else ''
            ai.description = desc_base or (f'\n{desc_comment}\n' if desc_comment else '')
        if Config.save_comments:
            comments_list = [f'{cudivs[i].text}:\n' + ctdivs[i].get_text('\n').strip() for i in range(len(ctdivs) - int(has_description))]
            ai.comments = ('\n' + '\n\n'.join(comments_list) + '\n') if comments_list else ''
    my_tags = filtered_tags(sorted(tags_raw)) or my_tags

    rc_ = PREFIX if has_naming_flag(NamingFlags.PREFIX) else ''

    try:
        expected_pages_count = int(a_html.find('div', class_='label', string='Pages:').next_sibling.string)
    except Exception:
        Log.error(f'Cannot find expected pages count section for {sname}, failed!')
        return DownloadResult.FAIL_RETRIES
    album_th = a_html.find('a', class_='th', href=re_read_href)
    try:
        read_href_1 = str(album_th.get('href'))[:-1]
    except Exception:
        Log.error(f'Error: cannot find download section for {sname}! Aborted!')
        return DownloadResult.FAIL_RETRIES
    try:
        preview_href_1 = str(album_th.parent.find('img').get('data-original', ''))
        ai.preview_link = preview_href_1
    except Exception:
        Log.error(f'Error: cannot find preview section for {sname}! Aborted!')
        return DownloadResult.FAIL_RETRIES

    if Config.include_previews:
        pii = ImageInfo(ai, ai.id, ai.preview_link, f'{rc_}!{ai.id}_{ai.preview_link[ai.preview_link.rfind("/") + 1:]}')
        ai.images.append(pii)

    r_html = await fetch_html(f'{read_href_1[:read_href_1.rfind("/")]}/0/', session=adwn.session)
    if r_html is None:
        Log.error(f'Error: unable to retreive html for {sname} page 1! Aborted!')
        return DownloadResult.FAIL_RETRIES

    file_links = [str(elem.get('data-src')) for elem in r_html.find_all('img', class_='hidden')]
    if len(file_links) != expected_pages_count:
        Log.error(f'Error: {sname} expected {expected_pages_count:d} pages but found {len(file_links):d} links! Aborted!')
        return DownloadResult.FAIL_RETRIES

    for ilink in file_links:
        iid, iext = tuple(ilink[:-1][ilink[:-1].rfind('/') + 1:].split('.', 1))
        ii = ImageInfo(ai, int(iid), ilink, f'{rc_}{iid}.{iext}')
        ai.images.append(ii)

    fname_part2 = ''
    my_score = (f'{f"+" if score.isnumeric() else ""}{score}' if len(score) > 0
                else '' if len(rating) > 0 else 'unk')
    my_rating = (f'{", " if  len(my_score) > 0 else ""}{rating}{"%" if rating.isnumeric() else ""}' if len(rating) > 0
                 else '' if len(my_score) > 0 else 'unk')
    fname_part1 = (
        f'{rc_}{ai.id:d}'
        f'{f"_({my_score}{my_rating})" if has_naming_flag(NamingFlags.SCORE) else ""}'
        f'{f"_[{ai.images_count:d}]_{ai.title}" if ai.title and has_naming_flag(NamingFlags.TITLE) else ""}'
    )
    # <fname_part1>_(<TAGS...>)
    extra_len = 1 + 2 + 1  # 1 underscore + 2 brackets + 1 extra slash
    if has_naming_flag(NamingFlags.TAGS):
        while len(my_tags) > max(0, FULLPATH_MAX_BASE_LEN - (len(ai.my_folder) + len(fname_part1) + len(fname_part2) + extra_len)):
            my_tags = my_tags[:max(0, my_tags.rfind(TAGS_CONCAT_CHAR))]
        fname_part1 += f'_({my_tags})' if len(my_tags) > 0 else ''
    if len(my_tags) == 0 and len(fname_part1) > max(0, FULLPATH_MAX_BASE_LEN - (len(ai.my_folder) + len(fname_part2) + extra_len)):
        fname_part1 = fname_part1[:max(0, FULLPATH_MAX_BASE_LEN - (len(ai.my_folder) + len(fname_part2) + extra_len))]
    fname_part1 = re_replace_symbols.sub('_', fname_part1).strip()
    fname_mid = ''
    ai.name = f'{fname_part1}{fname_mid}{fname_part2}'

    existing_folder = folders_already_exists(ai.id)
    if existing_folder:
        existing_folder_name = path.split(existing_folder)[1]
        if Config.continue_mode:
            if existing_folder_name != ai.name:
                old_pages_count = int(re_album_foldername.fullmatch(existing_folder_name).group(2))
                if old_pages_count > expected_pages_count:
                    Log.warn(f'{sname} (or similar) found but its pages count is greater ({old_pages_count} vs {ai.images_count})! '
                             f'Preserving old name.')
                    ai.name = existing_folder_name
                else:
                    Log.info(f'{sname} (or similar) found. Enforcing new name (was \'{existing_folder_name}\').')
                    if not try_rename(normalize_path(existing_folder), ai.my_folder):
                        Log.warn(f'Warning: folder {ai.my_folder} already exists! Old folder will be preserved.')
        else:
            existing_files = list(filter(lambda x: re_media_filename.fullmatch(x), listdir(existing_folder)))
            ai_filenames = [imi.filename for imi in ai.images]
            if (len(existing_files) == ai.images_count and all(filename in ai_filenames for filename in existing_files)):
                Log.info(f'Album {sname} (or similar) found and all its {len(ai.images):d} images already exist. Skipped.')
                ai.images.clear()
                return DownloadResult.FAIL_ALREADY_EXISTS
            Log.info(f'{sname} (or similar) found but its image set differs! Enforcing new name (was \'{existing_folder_name}\')')
            if not try_rename(normalize_path(existing_folder), ai.my_folder):
                Log.warn(f'Warning: folder {ai.my_folder} already exists! Old folder will be preserved.')
    elif Config.continue_mode is False and path.isdir(ai.my_folder) and all(path.isfile(imi.my_fullpath) for imi in ai.images):
        Log.info(f'Album {sname} and all its {len(ai.images):d} images already exist. Skipped.')
        ai.images.clear()
        return DownloadResult.FAIL_ALREADY_EXISTS

    Log.info(f'{sname}: {ai.images_count:d} images')
    [idwn.store_image_info(ii) for ii in ai.images]

    ai.set_state(AlbumInfo.State.SCANNED)
    return DownloadResult.SUCCESS


async def check_image_download_status(ii: ImageInfo, init_size: int, resp: ClientResponse) -> None:
    idwn = ImageDownloadWorker.get()
    sname = ii.sname
    dest = ii.my_fullpath
    check_timer = float(DOWNLOAD_STATUS_CHECK_TIMER)
    slow_con_dwn_threshold = max(1, DOWNLOAD_STATUS_CHECK_TIMER * Config.throttle * Mem.KB)
    last_size = init_size
    try:
        while True:
            await sleep(check_timer)
            if not idwn.is_writing(dest):  # finished already
                Log.error(f'{sname} status checker is still running for finished download!')
                break
            file_size = stat(dest).st_size if path.isfile(dest) else 0
            if file_size < last_size + slow_con_dwn_threshold:
                last_speed = (file_size - last_size) / Mem.KB / DOWNLOAD_STATUS_CHECK_TIMER
                Log.warn(f'{sname} status check failed at {file_size:d} ({last_speed:.2f} KB/s)! Interrupting current try...')
                resp.connection.transport.abort()  # abort download task (forcefully - close connection)
                break
            last_size = file_size
    except CancelledError:
        pass


async def download_image(ii: ImageInfo) -> DownloadResult:
    idwn = ImageDownloadWorker.get()
    sname = f'{ii.album.sname}/{ii.sname}'
    sfilename = f'{ii.album.my_sfolder_full}{ii.filename}'
    retries = 0
    ret = DownloadResult.SUCCESS
    skip = Config.dm == DOWNLOAD_MODE_SKIP and not ii.is_preview
    status_checker = None  # type: Optional[Task]

    if skip is True:
        ii.set_state(ImageInfo.State.DONE)
        ret = DownloadResult.FAIL_SKIPPED
    else:
        ii.set_state(ImageInfo.State.DOWNLOADING)
        if not path.isdir(ii.my_folder):
            try:
                makedirs(ii.my_folder)
            except Exception:
                raise IOError(f'ERROR: Unable to create subfolder \'{ii.my_folder}\'!')
        else:
            rc_curfile = path.isfile(ii.my_fullpath)
            if rc_curfile and Config.continue_mode is False:
                Log.info(f'{ii.filename} already exists. Skipped.')
                ii.set_state(ImageInfo.State.DONE)
                return DownloadResult.FAIL_ALREADY_EXISTS

    while (not skip) and retries < CONNECT_RETRIES_BASE:
        try:
            file_exists = path.isfile(ii.my_fullpath)
            file_size = stat(ii.my_fullpath).st_size if file_exists else 0

            if Config.dm == DOWNLOAD_MODE_TOUCH and not ii.is_preview:
                if file_exists:
                    Log.info(f'{sname} already exists, size: {file_size:d} ({file_size / Mem.MB:.2f} Mb)')
                    ii.set_state(ImageInfo.State.DONE)
                    return DownloadResult.FAIL_ALREADY_EXISTS
                else:
                    Log.info(f'Saving<touch> {sname} {0.0:.2f} Mb to {sfilename}')
                    with open(ii.my_fullpath, 'wb'):
                        ii.set_state(ImageInfo.State.DONE)
                break

            hkwargs = {'headers': {'Range': f'bytes={file_size:d}-'}} if file_size > 0 else {}  # type: Dict[str, Dict[str, str]]
            r = None
            async with await wrap_request(idwn.session, 'GET', ii.link, **hkwargs) as r:
                content_len = r.content_length or 0
                content_range_s = r.headers.get('Content-Range', '/').split('/', 1)
                content_range = int(content_range_s[1]) if len(content_range_s) > 1 and content_range_s[1].isnumeric() else 1
                if (content_len == 0 or r.status == 416) and file_size >= content_range:
                    Log.warn(f'{sname} is already completed, size: {file_size:d} ({file_size / Mem.MB:.2f} Mb)')
                    ii.set_state(ImageInfo.State.DONE)
                    ret = DownloadResult.FAIL_ALREADY_EXISTS
                    break
                if r.status == 404:
                    Log.error(f'Got 404 for {sname}...!')
                    retries = CONNECT_RETRIES_BASE - 1
                    ret = DownloadResult.FAIL_NOT_FOUND
                if r.content_type and 'text' in r.content_type:
                    Log.error(f'File not found at {ii.link}!')
                    raise FileNotFoundError(ii.link)

                ii.expected_size = file_size + content_len
                starting_str = f' <continuing at {file_size:d}>' if file_size else ''
                total_str = f' / {ii.expected_size / Mem.MB:.2f}' if file_size else ''
                Log.info(f'Saving{starting_str} {sname} {content_len / Mem.MB:.2f}{total_str} Mb to {sfilename}')

                idwn.add_to_writes(ii)
                ii.set_state(ImageInfo.State.WRITING)
                status_checker = get_running_loop().create_task(check_image_download_status(ii, file_size, r))
                async with async_open(ii.my_fullpath, 'ab') as outf:
                    async for chunk in r.content.iter_chunked(256 * Mem.KB):
                        await outf.write(chunk)
                status_checker.cancel()
                idwn.remove_from_writes(ii)

                file_size = stat(ii.my_fullpath).st_size
                if ii.expected_size and file_size != ii.expected_size:
                    Log.error(f'Error: file size mismatch for {sfilename}: {file_size:d} / {ii.expected_size:d}')
                    raise IOError(ii.link)

                ii.set_state(ImageInfo.State.DONE)
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
                ii.set_state(ImageInfo.State.DOWNLOADING)
                await sleep(frand(1.0, 7.0))
            elif Config.keep_unfinished is False and path.isfile(ii.my_fullpath):
                Log.error(f'Failed to download {sfilename}. Removing unfinished file...')
                remove(ii.my_fullpath)

    ret = (ret if ret in (DownloadResult.FAIL_NOT_FOUND, DownloadResult.FAIL_SKIPPED, DownloadResult.FAIL_ALREADY_EXISTS) else
           DownloadResult.SUCCESS if retries < CONNECT_RETRIES_BASE else
           DownloadResult.FAIL_RETRIES)

    if ret not in (DownloadResult.SUCCESS, DownloadResult.FAIL_SKIPPED, DownloadResult.FAIL_ALREADY_EXISTS):
        ii.set_state(ImageInfo.State.FAILED)

    return ret


def at_interrupt() -> None:
    idwn = ImageDownloadWorker.get()
    if idwn is not None:
        return idwn.at_interrupt()

#
#
#########################################
