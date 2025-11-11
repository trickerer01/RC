# coding=UTF-8
"""
Author: trickerer (https://github.com/trickerer, https://github.com/trickerer01)
"""
#########################################
#
#

import os
import random
import sys
import urllib.parse
from asyncio import sleep

from aiofile import async_open
from aiohttp import ClientPayloadError

from config import Config
from defs import (
    CONNECT_RETRY_DELAY,
    DOWNLOAD_MODE_SKIP,
    DOWNLOAD_MODE_TOUCH,
    DOWNLOAD_POLICY_ALWAYS,
    FULLPATH_MAX_BASE_LEN,
    PREFIX,
    SITE_AJAX_REQUEST_ALBUM,
    TAGS_CONCAT_CHAR,
    DownloadResult,
    Mem,
    NamingFlags,
)
from downloader import AlbumDownloadWorker, ImageDownloadWorker
from dthrottler import ThrottleChecker
from fetch_html import ensure_conn_closed, fetch_html, wrap_request
from idgaps import IdGapsPredictor
from iinfo import AlbumInfo, ImageInfo, export_album_info, get_min_max_ids
from logger import Log
from path_util import folder_already_exists, try_rename
from rex import re_album_foldername, re_media_filename, re_read_href, re_replace_symbols
from tagger import filtered_tags, is_filtered_out_by_extra_tags, solve_tag_conflicts
from util import calculate_eta, format_time, get_elapsed_time_i, has_naming_flag, normalize_path

__all__ = ('at_interrupt', 'download')


async def download(sequence: list[AlbumInfo], filtered_count: int) -> None:
    minid, maxid = get_min_max_ids(sequence)
    eta_min = calculate_eta(sequence)
    # interrupt_msg = f'\nPress \'{SCAN_CANCEL_KEYSTROKE}\' twice to stop' if by_id else ''
    Log.info(f'\nOk! {len(sequence):d} ids (+{filtered_count:d} filtered out), bound {minid:d} to {maxid:d}.'
             f' Working...\n'
             f'\nThis will take at least {eta_min:d} seconds{f" ({format_time(eta_min)})" if eta_min >= 60 else ""}!\n')
    with AlbumDownloadWorker(sequence, process_album) as adwn, ImageDownloadWorker(download_image) as idwn:
        await adwn.run()
        await idwn.run()
    export_album_info(sequence)


async def process_album(ai: AlbumInfo) -> DownloadResult:
    adwn, idwn = AlbumDownloadWorker.get(), ImageDownloadWorker.get()
    gpred = IdGapsPredictor.get()
    scenario = Config.scenario
    sname = ai.sname
    extra_ids = adwn.get_extra_ids()
    my_tags = 'no_tags'
    rating = ai.rating
    score = ''

    if predicted_prefix := gpred.need_skip(ai):
        Log.warn(f'Id gap prediction {predicted_prefix} forces error 404 for {sname}, skipping...')
        gpred.count_nonexisting()
        return DownloadResult.FAIL_NOT_FOUND

    ai.set_state(AlbumInfo.State.ACTIVE)
    a_html = await fetch_html(SITE_AJAX_REQUEST_ALBUM % ai.id)
    if a_html is None:
        Log.error(f'Error: unable to retreive html for {sname}! Aborted!')
        gpred.count_nonexisting()
        return DownloadResult.FAIL_SKIPPED if Config.aborted else DownloadResult.FAIL_RETRIES

    if not len(a_html):
        Log.error(f'Got empty HTML page for {sname}! Rescanning...')
        return DownloadResult.FAIL_EMPTY_HTML

    if a_html.find('title', string='404 Not Found'):
        Log.error(f'Got error 404 for {sname}, skipping...')
        gpred.count_nonexisting()
        return DownloadResult.FAIL_NOT_FOUND

    gpred.count_existing(ai)

    if not ai.title:
        titleh1 = a_html.find('h1', class_='title_video')  # not a mistake
        ai.title = titleh1.text if titleh1 else ''

    Log.info(f'Scanning {sname}: \'{ai.title}\'')

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
        my_authors: list[str] = []
    try:
        my_categories = [str(c.string).lower() for c in a_html.find('div', string='Categories:').parent.find_all('span')]
    except Exception:
        Log.warn(f'Warning: cannot extract categories for {sname}.')
        my_categories: list[str] = []
    tdiv = a_html.find('div', string='Tags:')
    if tdiv is None:
        Log.info(f'Warning: album {sname} has no tags!')
    tags: list[str] = [str(elem.string) for elem in tdiv.parent.find_all('a')] if tdiv else []
    tags_raw = [tag.replace(' ', '_').lower() for tag in tags]
    for calist in (my_categories, my_authors):
        for add_tag in [ca.replace(' ', '_') for ca in calist if ca]:
            if add_tag not in tags_raw:
                tags_raw.append(add_tag)
    if Config.save_tags:
        ai.tags = ' '.join(sorted(tags_raw))
    if Config.save_descriptions or Config.save_comments or Config.check_description_pos or Config.check_description_neg:
        cidivs = a_html.find_all('div', class_='comment-info')
        cudivs = [cidiv.find('a') for cidiv in cidivs]
        ctdivs = [cidiv.find('div', class_='coment-text') for cidiv in cidivs]
        desc_em = a_html.find('em')  # exactly one
        uploader_div = a_html.find('div', string=' Uploaded By: ')
        my_uploader = uploader_div.parent.find('a', class_='name').text.lower().strip() if uploader_div else 'unknown'
        has_description = (cudivs[-1].text.lower() == my_uploader) if (cudivs and ctdivs) else False  # first comment by uploader
        if cudivs and ctdivs:
            assert len(ctdivs) == len(cudivs)
        if Config.save_descriptions or Config.check_description_pos or Config.check_description_neg:
            desc_comment = (f'{cudivs[-1].text}:\n' + ctdivs[-1].get_text('\n').strip()) if has_description else ''
            desc_base = (f'\n{my_uploader}:\n' + desc_em.get_text('\n') + '\n') if desc_em else ''
            ai.description = desc_base or (f'\n{desc_comment}\n' if desc_comment else '')
        if Config.save_comments:
            comments_list = [f'{cudivs[i].text}:\n' + ctdivs[i].get_text('\n').strip() for i in range(len(ctdivs) - int(has_description))]
            ai.comments = ('\n' + '\n\n'.join(comments_list) + '\n') if comments_list else ''
    if Config.check_uploader and ai.uploader and ai.uploader not in tags_raw:
        tags_raw.append(ai.uploader)
    if Config.solve_tag_conflicts:
        solve_tag_conflicts(ai, tags_raw)
    if is_filtered_out_by_extra_tags(ai, tags_raw, Config.extra_tags, Config.id_sequence, ai.subfolder, extra_ids):
        Log.info(f'Info: album {sname} is filtered out by{" outer" if scenario else ""} extra tags, skipping...')
        return DownloadResult.FAIL_FILTERED_OUTER if scenario else DownloadResult.FAIL_SKIPPED
    for vsrs, csri, srn, pc in zip((score, rating), (Config.min_score, Config.min_rating), ('score', 'rating'), ('', '%'), strict=True):
        if len(vsrs) > 0 and csri is not None:
            try:
                if int(vsrs) < csri:
                    Log.info(f'Info: album {sname} has low {srn} \'{vsrs}{pc}\' (required {csri:d}), skipping...')
                    return DownloadResult.FAIL_SKIPPED
            except Exception:
                pass
    if scenario:
        if matching_sq := scenario.get_matching_subquery(ai, tags_raw, score, rating):
            ai.subfolder = matching_sq.subfolder
        elif utpalways_sq := scenario.get_utp_always_subquery() if tdiv is None else None:
            ai.subfolder = utpalways_sq.subfolder
        else:
            Log.info(f'Info: unable to find matching or utp scenario subquery for {sname}, skipping...')
            return DownloadResult.FAIL_SKIPPED
    elif tdiv is None and len(Config.extra_tags) > 0 and Config.utp != DOWNLOAD_POLICY_ALWAYS:
        Log.warn(f'Warning: could not extract tags from {sname}, skipping due to untagged albums download policy...')
        return DownloadResult.FAIL_SKIPPED
    my_tags = filtered_tags(sorted(tags_raw)) or my_tags

    prefix = PREFIX if has_naming_flag(NamingFlags.PREFIX) else ''

    try:
        expected_pages_count = int(a_html.find('div', class_='label', string='Pages:').next_sibling.text)
    except Exception:
        Log.error(f'Cannot find expected pages count section for {sname}, failed!')
        return DownloadResult.FAIL_RETRIES
    album_th = a_html.find('a', class_='th', href=re_read_href)
    try:
        read_href_1 = str(album_th.get('href'))[:-1]
    except Exception:
        Log.error(f'Error: cannot find download section for {sname}! Aborted!')
        return DownloadResult.FAIL_DELETED
    try:
        preview_href_1 = str(album_th.parent.find('img').get('data-original', ''))
        ai.preview_link = preview_href_1
    except Exception:
        Log.error(f'Error: cannot find preview section for {sname}! Aborted!')
        return DownloadResult.FAIL_DELETED

    if Config.include_previews:
        pii = ImageInfo(ai, ai.id, ai.preview_link, f'{prefix}!{ai.id}_{ai.preview_link[ai.preview_link.rfind("/") + 1:]}')
        ai.images.append(pii)

    r_html = await fetch_html(f'{read_href_1[:read_href_1.rfind("/")]}/0/')
    if r_html is None:
        Log.error(f'Error: unable to retreive html for {sname} page 1! Aborted!')
        return DownloadResult.FAIL_RETRIES

    file_links = [str(elem.get('data-src') or elem.get('data-original')) for elem in r_html.find_all('img', class_=['hidden', 'visible'])]
    if len(file_links) != expected_pages_count:
        Log.error(f'Error: {ai.sfsname} expected {expected_pages_count:d} pages but found {len(file_links):d} links! Aborted!')
        return DownloadResult.FAIL_RETRIES

    for iidx, ilink in enumerate(file_links):
        iid, iext = tuple(ilink[:-1][ilink[:-1].rfind('/') + 1:].split('.', 1))
        ii = ImageInfo(ai, int(iid), ilink, f'{prefix}{iid}.{iext}', num=iidx + 1)
        ai.images.append(ii)

    fname_part2 = ''
    my_score = (f'{"+" if score.isnumeric() else ""}{score}' if len(score) > 0
                else '' if len(rating) > 0 else 'unk')
    my_rating = (f'{", " if len(my_score) > 0 else ""}{rating}{"%" if rating.isnumeric() else ""}' if len(rating) > 0
                 else '' if len(my_score) > 0 else 'unk')
    fname_part1 = (
        f'{prefix}{ai.id:d}'
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

    existing_folder = folder_already_exists(ai.id)
    if existing_folder:
        curalbum_folder, curalbum_name = os.path.split(existing_folder.strip('/'))
        existing_folder_name = os.path.split(existing_folder)[1]
        same_loc = os.path.isdir(ai.my_folder_base) and os.path.samefile(curalbum_folder, ai.my_folder_base)
        loc_str = f' ({"same" if same_loc else "different"} location)'
        if Config.continue_mode:
            if existing_folder != ai.my_folder:
                old_pages_count = int(re_album_foldername.fullmatch(existing_folder_name).group(2))
                if old_pages_count > expected_pages_count:
                    Log.warn(f'{ai.sfsname} (or similar) found but its pages count is greater ({old_pages_count} vs {ai.images_count})! '
                             f'Preserving old name.')
                    ai.name = existing_folder_name
                else:
                    if Config.no_rename_move is False or same_loc:
                        Log.info(f'{ai.sfsname} (or similar) found{loc_str}. Enforcing new name (was \'{existing_folder}\').')
                        if not try_rename(normalize_path(existing_folder), ai.my_folder):
                            Log.warn(f'Warning: folder {ai.my_folder} already exists! Old folder will be preserved.')
                    else:
                        new_subfolder = normalize_path(os.path.relpath(curalbum_folder, Config.dest_base))
                        Log.info(f'{ai.sfsname} (or similar) found{loc_str}. Enforcing old path + new name '
                                 f'\'{curalbum_folder}/{ai.name}\' due to \'--no-rename-move\' flag (was \'{curalbum_name}\').')
                        ai.subfolder = new_subfolder
                        if not try_rename(existing_folder, normalize_path(os.path.abspath(ai.my_folder), False)):
                            Log.warn(f'Warning: folder {ai.sfsname} already exists! Old folder will be preserved.')
        else:
            existing_files: list[str] = [de.name for de in os.scandir(existing_folder) if de.is_file()]
            existing_files = list(filter(lambda x: re_media_filename.fullmatch(x), existing_files))
            ai_filenames = [imi.filename for imi in ai.images]
            if len(existing_files) == ai.images_count and all(filename in ai_filenames for filename in existing_files):
                Log.info(f'Album {ai.sfsname} (or similar) found{loc_str} and all its {len(ai.images):d} images already exist. Skipped.'
                         f'\n Location: \'{existing_folder}\'')
                ai.images.clear()
                return DownloadResult.FAIL_ALREADY_EXISTS
            if Config.no_rename_move is False:
                Log.info(f'{ai.sfsname} (or similar) found{loc_str} but its image set differs! '
                         f'Enforcing new name (was \'{existing_folder}\')')
                if not try_rename(normalize_path(existing_folder), ai.my_folder):
                    Log.warn(f'Warning: folder {ai.my_folder} already exists! Old folder will be preserved.')
            else:
                new_subfolder = normalize_path(os.path.relpath(curalbum_folder, Config.dest_base))
                Log.info(f'{ai.sfsname} (or similar) found{loc_str} but its image set differs! Enforcing old path + new name '
                         f'\'{curalbum_folder}/{ai.name}\' due to \'--no-rename-move\' flag (was \'{curalbum_name}\').')
                ai.subfolder = new_subfolder
                if not try_rename(existing_folder, normalize_path(os.path.abspath(ai.my_folder), False)):
                    Log.warn(f'Warning: folder {ai.sfsname} already exists! Old folder will be preserved.')
    elif Config.continue_mode is False and os.path.isdir(ai.my_folder) and all(os.path.isfile(imi.my_fullpath) for imi in ai.images):
        Log.info(f'Album {ai.sfsname} and all its {len(ai.images):d} images already exist. Skipped.')
        ai.images.clear()
        return DownloadResult.FAIL_ALREADY_EXISTS

    Log.info(f'Saving {ai.sfsname}: {ai.images_count:d} images will be downloaded to {ai.my_sfolder_full}')
    [idwn.store_image_info(ii) for ii in ai.images]

    ai.set_state(AlbumInfo.State.SCANNED)
    return DownloadResult.SUCCESS


async def download_image(ii: ImageInfo) -> DownloadResult:
    idwn = ImageDownloadWorker.get()
    sname = f'{ii.album.sname}/{ii.sname} {ii.my_num_fmt}'
    sfilename = f'{ii.album.my_sfolder_full}{ii.filename}'
    retries = 0
    ret = DownloadResult.SUCCESS
    skip = Config.download_mode == DOWNLOAD_MODE_SKIP and not ii.is_preview
    status_checker = ThrottleChecker(ii)

    if skip is True:
        ii.set_state(ImageInfo.State.DONE)
        ret = DownloadResult.FAIL_SKIPPED
    else:
        ii.set_state(ImageInfo.State.DOWNLOADING)
        if not os.path.isdir(ii.my_folder):
            try:
                os.makedirs(ii.my_folder)
            except Exception:
                raise OSError(f'ERROR: Unable to create subfolder \'{ii.my_folder}\'!')
        else:
            curfile = os.path.isfile(ii.my_fullpath)
            if curfile:
                ii.set_flag(ImageInfo.Flags.ALREADY_EXISTED_EXACT)
                if Config.continue_mode is False:
                    Log.info(f'{ii.filename} already exists. Skipped.')
                    ii.set_state(ImageInfo.State.DONE)
                    return DownloadResult.FAIL_ALREADY_EXISTS

    while (not skip) and retries <= Config.retries:
        r = None
        try:
            file_exists = os.path.isfile(ii.my_fullpath)
            if file_exists and retries == 0:
                ii.set_flag(ImageInfo.Flags.ALREADY_EXISTED_EXACT)
            file_size = os.stat(ii.my_fullpath).st_size if file_exists else 0

            if Config.download_mode == DOWNLOAD_MODE_TOUCH and not ii.is_preview:
                if file_exists:
                    Log.info(f'{sname} already exists, size: {file_size:d} ({file_size / Mem.MB:.2f} Mb)')
                    ii.set_state(ImageInfo.State.DONE)
                    return DownloadResult.FAIL_ALREADY_EXISTS
                else:
                    Log.info(f'Saving<touch> {sname} {0.0:.2f} Mb to {sfilename}')
                    with open(ii.my_fullpath, 'wb'):
                        ii.set_flag(ImageInfo.Flags.FILE_WAS_CREATED)
                        ii.set_state(ImageInfo.State.DONE)
                break

            hkwargs: dict[str, dict[str, str]] = {'headers': {'Range': f'bytes={file_size:d}-'} if file_size > 0 else {}}
            ckwargs = {'allow_redirects': not (Config.proxy and (Config.download_without_proxy or Config.html_without_proxy))}
            ckwargs.update({'noproxy': bool(Config.proxy and Config.html_without_proxy)})
            # hkwargs['headers'].update({'Referer': SITE_AJAX_REQUEST_ALBUM % ii.id})
            r = await wrap_request('GET', ii.link, **ckwargs, **hkwargs)
            while r.status in (301, 302):
                if urllib.parse.urlparse(r.headers['Location']).hostname != urllib.parse.urlparse(ii.link).hostname:
                    ckwargs.update({'noproxy': Config.download_without_proxy, 'allow_redirects': True})
                ensure_conn_closed(r)
                r = await wrap_request('GET', r.headers['Location'], **ckwargs, **hkwargs)
            content_len: int = r.content_length or 0
            content_range_s = str(r.headers.get('Content-Range', '/')).split('/', 1)
            content_range = int(content_range_s[1]) if len(content_range_s) > 1 and content_range_s[1].isnumeric() else 1
            if (content_len == 0 or r.status == 416) and file_size >= content_range:
                Log.warn(f'{sname} is already completed, size: {file_size:d} ({file_size / Mem.MB:.2f} Mb)')
                ii.set_state(ImageInfo.State.DONE)
                ret = DownloadResult.FAIL_ALREADY_EXISTS
                break
            if r.status == 404:
                Log.error(f'Got 404 for {sname}...!')
                retries = Config.retries
                ret = DownloadResult.FAIL_NOT_FOUND
            if r.content_type and 'text' in r.content_type:
                Log.error(f'File not found at {ii.link}!')
                raise FileNotFoundError(ii.link)

            status_checker.prepare(r, file_size)
            ii.expected_size = file_size + content_len
            starting_str = f' <continuing at {file_size:d}>' if file_size else ''
            total_str = f' / {ii.expected_size / Mem.MB:.2f}' if file_size else ''
            Log.info(f'Saving{starting_str} {sname} {content_len / Mem.MB:.2f}{total_str} Mb to {sfilename}')

            await idwn.add_to_writes(ii)
            ii.set_state(ImageInfo.State.WRITING)
            status_checker.run()
            async with async_open(ii.my_fullpath, 'ab') as outf:
                ii.set_flag(ImageInfo.Flags.FILE_WAS_CREATED)
                if ii.album.dstart_time == 0:
                    ii.album.dstart_time = get_elapsed_time_i()
                async for chunk in r.content.iter_chunked(256 * Mem.KB):
                    await outf.write(chunk)
                    ii.bytes_written += len(chunk)
            status_checker.reset()
            await idwn.remove_from_writes(ii)

            file_size = os.stat(ii.my_fullpath).st_size
            if ii.expected_size and file_size != ii.expected_size:
                Log.error(f'Error: file size mismatch for {sfilename}: {file_size:d} / {ii.expected_size:d}')
                raise OSError(ii.link)

            ii.set_state(ImageInfo.State.DONE)

            if ii.album.all_done():
                total_time = (get_elapsed_time_i() - ii.album.dstart_time) or 1
                total_size = ii.album.total_size()
                Log.info(f'[download] {ii.album.sfsname} ({total_size / Mem.MB:.1f} Mb) completed in {format_time(total_time)} '
                         f'({(total_size / total_time) / Mem.KB:.1f} Kb/s)')
            break
        except Exception as e:
            Log.error(f'{ii.sname}: {sys.exc_info()[0]}: {sys.exc_info()[1]}')
            if (r is None or r.status != 403) and isinstance(e, ClientPayloadError) is False:
                retries += 1
                Log.error(f'{sfilename}: error #{retries:d}...')
            if r is not None and r.closed is False:
                r.close()
            # Network error may be thrown before item is added to active downloads
            await idwn.remove_from_writes(ii, True)
            status_checker.reset()
            if retries <= Config.retries:
                ii.set_state(ImageInfo.State.DOWNLOADING)
                await sleep(random.uniform(*CONNECT_RETRY_DELAY))
            elif Config.keep_unfinished is False and os.path.isfile(ii.my_fullpath) and ii.has_flag(ImageInfo.Flags.FILE_WAS_CREATED):
                Log.error(f'Failed to download {sfilename}. Removing unfinished file...')
                os.remove(ii.my_fullpath)

    ret = (ret if ret in (DownloadResult.FAIL_NOT_FOUND, DownloadResult.FAIL_SKIPPED, DownloadResult.FAIL_ALREADY_EXISTS) else
           DownloadResult.SUCCESS if retries <= Config.retries else
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
