# coding=UTF-8
"""
Author: trickerer (https://github.com/trickerer, https://github.com/trickerer01)
"""
#########################################
#
#

from asyncio import run as run_async
from io import StringIO
from os import path, remove as remove_file, stat, removedirs
from tempfile import gettempdir
from unittest import TestCase
from unittest.mock import patch

from cmdargs import prepare_arglist
# noinspection PyProtectedMember
from config import BaseConfig
from defs import DOWNLOAD_MODE_TOUCH, SEARCH_RULE_DEFAULT
from downloader import AlbumDownloadWorker, ImageDownloadWorker
# noinspection PyProtectedMember
from ids import main as ids_main, main_sync as ids_main_sync
from logger import Log
# noinspection PyProtectedMember
from pages import main as pages_main, main_sync as pages_main_sync
# noinspection PyProtectedMember
from path_util import found_foldernames_dict
from rex import prepare_regex_fullmatch
# noinspection PyProtectedMember
from tagger import extract_id_or_group, normalize_wtag
from util import normalize_path
from version import APP_NAME, APP_VERSION

RUN_CONN_TESTS = 0


def set_up_test(log=False) -> None:
    AlbumDownloadWorker._instance = None
    ImageDownloadWorker._instance = None
    found_foldernames_dict.clear()
    Log._disabled = not log


class CmdTests(TestCase):
    def test_output_version_pages(self):
        set_up_test()
        with patch('sys.stdout', new_callable=StringIO) as stdout:
            run_async(pages_main(['--version']))
            self.assertEqual(f'{APP_NAME} {APP_VERSION}', stdout.getvalue().strip('\n'))
        print(f'{self._testMethodName} passed')

    def test_output_version_ids(self):
        set_up_test()
        with patch('sys.stdout', new_callable=StringIO) as stdout:
            run_async(ids_main(['--version']))
            self.assertEqual(f'{APP_NAME} {APP_VERSION}', stdout.getvalue().strip('\n'))
        print(f'{self._testMethodName} passed')

    # @mock_stderr
    # def test_cmd_base(self, stderr: StringIO):
    #     set_up_test()
    #     self.assertRaises(HelpPrintExitException, prepare_arglist, ['cmd', '--help'], True)
    #     self.assertRaises(HelpPrintExitException, prepare_arglist, ['cmd', '-start', '1'], True)
    #     self.assertRaises(HelpPrintExitException, prepare_arglist, ['cmd', '-start', '1', '-pages'], True)
    #     self.assertNotEqual('', stderr.getvalue().strip('\n'))

    def test_cmd_pages(self):
        set_up_test()
        parsed1 = prepare_arglist(['cmd', '-get_maxid'], True)
        c1 = BaseConfig()
        c1.read(parsed1, True)
        self.assertTrue(c1.get_maxid)
        parsed2 = prepare_arglist(['-start', '2', '-pages', '1', '-uploader', '1234', '(2d~3d)', '--skip-empty-lists', '-script',
                                   'a: 2d; b: 3d; c: a2 -2d; d: * -utp always', '-naming', 'prefix|score', '-log', 'warn'], True)
        c2 = BaseConfig()
        c2.read(parsed2, True)
        self.assertEqual(3, c2.naming_flags)
        self.assertEqual(8, c2.logging_flags)
        self.assertEqual(1, len(c2.extra_tags))
        self.assertEqual(4, len(c2.scenario))
        self.assertEqual(1234, c2.uploader)
        self.assertEqual('', c2.search)
        self.assertEqual(SEARCH_RULE_DEFAULT, c2.search_rule_art)
        self.assertIsNone(c2.use_id_sequence)
        self.assertTrue(c2.skip_empty_lists)
        parsed3 = prepare_arglist(['-start', '3', '-pages', '2', '-dnoempty',
                                   '-minscore', '12', '-continue', '-unfinish', '-tdump', '-cdump'], True)
        c3 = BaseConfig()
        c3.read(parsed3, True)
        # self.assertEqual('commodified', c3.playlist_name)
        self.assertEqual(3, c3.start)
        self.assertEqual(4, c3.end)
        # self.assertEqual(QUALITIES[3], c3.quality)
        # self.assertEqual(QUALITY_480P, c3.quality)
        # self.assertEqual('480p', c3.quality)
        self.assertEqual(12, c3.min_score)
        self.assertTrue(c3.continue_mode)
        self.assertTrue(c3.keep_unfinished)
        self.assertTrue(c3.save_tags)
        # self.assertTrue(c3.save_descriptions)
        self.assertTrue(c3.save_comments)
        # self.assertTrue(c3.save_screenshots)
        self.assertTrue(c3.skip_empty_lists)
        parsed5 = prepare_arglist(['-search_tag', '6*,5???*', '-search_rule_tag', 'any',
                                   '-search_art', '*ikan', '-search_rule_art', 'any',
                                   '-search_cat', 'ali??_*', '-search_rule_cat', 'any',
                                   '-start', '3', '-pages', '2'], True)
        c5 = BaseConfig()
        c5.read(parsed5, True)
        self.assertEqual('2007,3364,4326,4867,9244,9363', c5.search_tags)
        self.assertEqual('1338,4834,5129,5163', c5.search_arts)
        self.assertEqual('315,685,979', c5.search_cats)
        self.assertEqual('any', c5.search_rule_tag)
        self.assertEqual('any', c5.search_rule_art)
        self.assertEqual('any', c5.search_rule_cat)
        self.assertEqual(3, c5.start)
        self.assertEqual(4, c5.end)
        # self.assertEqual(QUALITIES[2], c5.quality)
        # self.assertEqual('720p', c5.quality)
        print(f'{self._testMethodName} passed')

    def test_cmd_ids(self):
        set_up_test()
        parsed1 = prepare_arglist(['cmd', '-seq', '(id=23~id=982)'], False)
        c1 = BaseConfig()
        c1.read(parsed1, False)
        self.assertEqual(1, len(c1.extra_tags))
        c1.id_sequence = extract_id_or_group(c1.extra_tags)
        self.assertTrue(c1.use_id_sequence)
        self.assertEqual(0, len(c1.extra_tags))
        self.assertEqual(2, len(c1.id_sequence))
        parsed2 = prepare_arglist(['-start', '1000', '-end', '999', '(69~9s)', '(2d~3d)', '-dmode', 'touch', '--store-continue-cmdfile',
                                   '-lookahead', '100',
                                   '-script', 'a: 2d; b: 3d; c: a2 -2d; d: * -utp always', '-naming', '0x8', '-log', 'trace'], False)
        c2 = BaseConfig()
        c2.read(parsed2, False)
        self.assertEqual(8, c2.naming_flags)
        self.assertEqual(1, c2.logging_flags)
        self.assertEqual(2, len(c2.extra_tags))
        self.assertEqual(4, len(c2.scenario))
        self.assertEqual(100, c2.lookahead)
        self.assertEqual(DOWNLOAD_MODE_TOUCH, c2.download_mode)
        self.assertTrue(c2.store_continue_cmdfile)
        print(f'{self._testMethodName} passed')

    def test_cmd_wtags(self):
        set_up_test()
        parsed1 = prepare_arglist(['-start', '1', '-pages', '5',
                                   '-*`[1`-5`]`+`(finger`{1`,3`}|girl`)s`?`.`*',
                                   '-*`[1`-5`]`+`(finger`{1`,3`}`|`girl`)s`?`.`*``'], True)
        c2 = BaseConfig()
        c2.read(parsed1, True)
        self.assertEqual(r'^\-.*[1-5]+(?:finger{1,3}|girl)s?.*$', prepare_regex_fullmatch(normalize_wtag(c2.extra_tags[0])).pattern)
        self.assertEqual(r'^\-.*[1-5]+(?:finger{1,3}|girl)s?.*$', prepare_regex_fullmatch(normalize_wtag(c2.extra_tags[1])).pattern)
        print(f'{self._testMethodName} passed')


class DownloadTests(TestCase):
    def test_ids_touch(self):
        if not RUN_CONN_TESTS:
            return
        set_up_test()
        tempdir = normalize_path(gettempdir())
        tempdir_id = '33123'
        tempfile_ids = ('951685', '951686')
        tempfile_ext = 'jpg'
        tempfile_fullpaths = [f'{tempdir}{tempdir_id}/{tfid}.{tempfile_ext}' for tfid in tempfile_ids]
        arglist1 = ['-path', tempdir, '-start', tempdir_id, '-dmode', 'touch', '-naming', 'none', '-log', 'trace']
        ids_main_sync(arglist1)
        self.assertTrue(path.isfile(tempfile_fullpaths[0]))
        self.assertTrue(path.isfile(tempfile_fullpaths[1]))
        st1 = stat(tempfile_fullpaths[0])
        st2 = stat(tempfile_fullpaths[1])
        self.assertEqual(0, st1.st_size)
        self.assertEqual(0, st2.st_size)
        remove_file(tempfile_fullpaths[0])
        remove_file(tempfile_fullpaths[1])
        self.assertTrue(path.isdir(f'{tempdir}{tempdir_id}'))
        removedirs(f'{tempdir}{tempdir_id}')
        print(f'{self._testMethodName} passed')

    def test_pages_touch(self):
        if not RUN_CONN_TESTS:
            return
        set_up_test()
        tempdir = normalize_path(gettempdir())
        tempdir_id = '325'
        tempfile_ids = ('6397', '6398')
        tempfile_ext = 'jpg'
        tempfile_fullpaths = [f'{tempdir}{tempdir_id}/{tfid}.{tempfile_ext}' for tfid in tempfile_ids]
        arglist1 = ['-path', tempdir, '-pages', '999', '-dmode', 'touch', '-naming', 'none', '-log', 'trace',
                    '-begin_id', tempdir_id, '-stop_id', tempdir_id, '-search_tag', 'blood,piercing', '-search_art', 'shadman']
        pages_main_sync(arglist1)
        self.assertTrue(path.isfile(tempfile_fullpaths[0]))
        self.assertTrue(path.isfile(tempfile_fullpaths[1]))
        st1 = stat(tempfile_fullpaths[0])
        st2 = stat(tempfile_fullpaths[1])
        self.assertEqual(0, st1.st_size)
        self.assertEqual(0, st2.st_size)
        remove_file(tempfile_fullpaths[0])
        remove_file(tempfile_fullpaths[1])
        self.assertTrue(path.isdir(f'{tempdir}{tempdir_id}'))
        removedirs(f'{tempdir}{tempdir_id}')
        print(f'{self._testMethodName} passed')

    def test_ids_full(self):
        if not RUN_CONN_TESTS:
            return
        set_up_test()
        tempdir = normalize_path(gettempdir())
        tempdir_id = '2151'
        tempfile_ids = ('37758', '37759')
        tempfile_ext = 'jpg'
        tempfile_fullpaths = [f'{tempdir}{tempdir_id}/{tfid}.{tempfile_ext}' for tfid in tempfile_ids]
        arglist1 = ['-path', tempdir, '-start', tempdir_id, '-dmode', 'full', '-naming', 'none', '-log', 'trace']
        ids_main_sync(arglist1)
        self.assertTrue(path.isfile(tempfile_fullpaths[0]))
        self.assertTrue(path.isfile(tempfile_fullpaths[1]))
        st1 = stat(tempfile_fullpaths[0])
        st2 = stat(tempfile_fullpaths[1])
        self.assertGreater(st1.st_size, 0)
        self.assertGreater(st2.st_size, 0)
        remove_file(tempfile_fullpaths[0])
        remove_file(tempfile_fullpaths[1])
        self.assertTrue(path.isdir(f'{tempdir}{tempdir_id}'))
        removedirs(f'{tempdir}{tempdir_id}')
        print(f'{self._testMethodName} passed')

    def test_pages_full(self):
        if not RUN_CONN_TESTS:
            return
        set_up_test()
        tempdir = normalize_path(gettempdir())
        tempdir_id = '2545'
        tempfile_ids = ('44712', '44713')
        tempfile_ext = 'jpg'
        tempfile_fullpaths = [f'{tempdir}{tempdir_id}/{tfid}.{tempfile_ext}' for tfid in tempfile_ids]
        arglist1 = ['-path', tempdir, '-pages', '999', '-dmode', 'full', '-naming', 'none', '-log', 'trace',
                    '-begin_id', tempdir_id, '-stop_id', tempdir_id, '-search_tag', 'desiree', '-search_art', 'darkyamatoman']
        pages_main_sync(arglist1)
        self.assertTrue(path.isfile(tempfile_fullpaths[0]))
        self.assertTrue(path.isfile(tempfile_fullpaths[1]))
        st1 = stat(tempfile_fullpaths[0])
        st2 = stat(tempfile_fullpaths[1])
        self.assertGreater(st1.st_size, 0)
        self.assertGreater(st2.st_size, 0)
        remove_file(tempfile_fullpaths[0])
        remove_file(tempfile_fullpaths[1])
        self.assertTrue(path.isdir(f'{tempdir}{tempdir_id}'))
        removedirs(f'{tempdir}{tempdir_id}')
        print(f'{self._testMethodName} passed')

#
#
#########################################
