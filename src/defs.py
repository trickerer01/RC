# coding=UTF-8
"""
Author: trickerer (https://github.com/trickerer, https://github.com/trickerer01)
"""
#########################################
#
#

import sys
from argparse import Namespace
from base64 import b64decode
from datetime import datetime
from enum import IntEnum
from locale import getpreferredencoding
from re import compile as re_compile
from typing import Optional, List
from urllib.parse import urlparse

from aiohttp import ClientTimeout
from colorama import init as colorama_init, Fore

colorama_init()

APP_NAME = 'RC'
APP_VERSION = '1.0.100'

CONNECT_RETRIES_BASE = 50
CONNECT_TIMEOUT_BASE = 10
CONNECT_REQUEST_DELAY = 0.2

MAX_IMAGES_QUEUE_SIZE = 10
DOWNLOAD_STATUS_CHECK_TIMER = 60
DOWNLOAD_QUEUE_STALL_CHECK_TIMER = 30

SLASH = '/'
UTF8 = 'utf-8'
TAGS_CONCAT_CHAR = ','
EXTENSIONS_I = ('jpg', 'jpeg')
START_TIME = datetime.now()


class BaseConfig(object):
    """Parameters container for params used in both **pages** and **ids** modes"""
    def __init__(self) -> None:
        self.dest_base = None  # type: Optional[str]
        self.proxy = None  # type: Optional[str]
        self.un_album_policy = None  # type: Optional[str]
        self.download_mode = None  # type: Optional[str]
        self.continue_mode = None  # type: Optional[bool]
        self.keep_unfinished = None  # type: Optional[bool]
        self.save_tags = None  # type: Optional[bool]
        self.save_comments = None  # type: Optional[bool]
        self.extra_tags = None  # type: Optional[List[str]]
        self.scenario = None  # type: Optional['DownloadScenario'] # noqa F821
        self.naming_flags = self.logging_flags = 0
        self.start = self.end = self.start_id = self.end_id = 0
        self.timeout = None  # type: Optional[ClientTimeout]
        self.get_maxid = None  # type: Optional[bool]
        # extras (can't be set through cmdline arguments)
        self.nodelay = False

    def read(self, params: Namespace, pages: bool) -> None:
        self.dest_base = params.path
        self.proxy = params.proxy
        self.un_album_policy = params.untagged_policy
        self.download_mode = params.download_mode
        self.continue_mode = params.continue_mode
        self.keep_unfinished = params.keep_unfinished
        self.save_tags = params.dump_tags
        self.save_comments = params.dump_comments
        self.extra_tags = params.extra_tags
        self.scenario = params.download_scenario
        self.naming_flags = params.naming
        self.logging_flags = params.log_level
        self.start = params.start
        self.end = params.end
        self.start_id = params.stop_id if pages else self.start
        self.end_id = params.begin_id if pages else self.end
        self.timeout = ClientTimeout(total=None, connect=params.timeout or CONNECT_TIMEOUT_BASE)
        self.get_maxid = getattr(params, 'get_maxid') if hasattr(params, 'get_maxid') else self.get_maxid

    @property
    def utp(self) -> Optional[str]:
        return self.un_album_policy

    @property
    def dm(self) -> Optional[str]:
        return self.download_mode


Config = BaseConfig()

SITE = b64decode('aHR0cHM6Ly9ydWxlMzRjb21pYy5wYXJ0eQ==').decode()
SITE_AJAX_REQUEST_PAGE = b64decode(
    'aHR0cHM6Ly9ydWxlMzRjb21pYy5wYXJ0eS9hZHZhbmNlZC1zZWFyY2gvP21vZGU9YXN5bmMmZnVuY3Rpb249Z2V0X2Jsb2NrJmJsb2NrX2lkPWxpc3RfYWxidW1zX2FsYnVtc1'
    '9saXN0X3NlYXJjaF9yZXN1bHQmZmxhZzE9JnNvcnRfYnk9cG9zdF9kYXRlJnRhZ19pZHM9JXMmbW9kZWxfaWRzPSVzJmNhdGVnb3J5X2lkcz0lcyZxPSVzJmZyb21fYWxidW1z'
    'PSVk').decode()
"""Params required: **tags**, **artists**, **categories**, **search**, **page** - **str**, **str**, **str**, **str**, **int**\n
Ex. SITE_AJAX_REQUEST_PAGE % ('1,2', '3,4,5', '6', 'sfw', 1)"""
SITE_AJAX_REQUEST_ALBUM = b64decode('aHR0cHM6Ly9ydWxlMzRjb21pYy5wYXJ0eS9hbGJ1bXMvJWQvJXMv').decode()
"""Params required: **album_id**, **album_name** - **int**, **str**\n
Ex. SITE_AJAX_REQUEST_ALBUM % (11111, 'sfw')"""

USER_AGENT = 'Mozilla/5.0 (X11; Linux x86_64; rv:102.0) Gecko/20100101 Goanna/6.5 Firefox/102.0 PaleMoon/32.5.0'
HOST = urlparse(SITE).netloc
DEFAULT_HEADERS = {'User-Agent': USER_AGENT}

# language=PythonRegExp
REPLACE_SYMBOLS = r'[^0-9a-zA-Z.,_+%\-()\[\] ]+'
# language=PythonRegExp
NON_SEARCH_SYMBOLS = r'[^\da-zA-Z._+\-\[\]]'

# untagged albums download policy
DOWNLOAD_POLICY_NOFILTERS = 'nofilters'
DOWNLOAD_POLICY_ALWAYS = 'always'
UALBUM_POLICIES = (DOWNLOAD_POLICY_NOFILTERS, DOWNLOAD_POLICY_ALWAYS)
"""('nofilters','always')"""
DOWNLOAD_POLICY_DEFAULT = DOWNLOAD_POLICY_NOFILTERS
"""'nofilters'"""

# download (file creation) mode
DOWNLOAD_MODE_FULL = 'full'
DOWNLOAD_MODE_TOUCH = 'touch'
DOWNLOAD_MODE_SKIP = 'skip'
DOWNLOAD_MODES = (DOWNLOAD_MODE_FULL, DOWNLOAD_MODE_TOUCH, DOWNLOAD_MODE_SKIP)
"""('full','touch','skip')"""
DOWNLOAD_MODE_DEFAULT = DOWNLOAD_MODE_FULL
"""'full'"""

# search args combination logic rules
SEARCH_RULE_ALL = 'all'
SEARCH_RULE_ANY = 'any'
SEARCH_RULES = (SEARCH_RULE_ALL, SEARCH_RULE_ANY)
"""('all','any')"""
SEARCH_RULE_DEFAULT = SEARCH_RULE_ALL
"""'all'"""


class NamingFlags:
    NAMING_FLAG_NONE = 0x00
    NAMING_FLAG_PREFIX = 0x01
    NAMING_FLAG_TITLE = 0x02
    NAMING_FLAG_TAGS = 0x04
    NAMING_FLAGS_ALL = NAMING_FLAG_PREFIX | NAMING_FLAG_TITLE | NAMING_FLAG_TAGS
    """0x07"""


NAMING_FLAGS = {
    'none': f'0x{NamingFlags.NAMING_FLAG_NONE:02X}',
    'prefix': f'0x{NamingFlags.NAMING_FLAG_PREFIX:02X}',
    'title': f'0x{NamingFlags.NAMING_FLAG_TITLE:02X}',
    'tags': f'0x{NamingFlags.NAMING_FLAG_TAGS:02X}',
    'full': f'0x{NamingFlags.NAMING_FLAGS_ALL:02X}'
}
"""
{\n\n'none': '0x00',\n\n'prefix': '0x01',\n\n'title': '0x02',\n\n'tags': '0x04',\n\n'full': '0x07'\n\n}
"""
NAMING_FLAGS_DEFAULT = NamingFlags.NAMING_FLAGS_ALL
"""0x07"""


class LoggingFlags(IntEnum):
    LOGGING_NONE = 0x000
    LOGGING_TRACE = 0x001
    LOGGING_DEBUG = 0x002
    LOGGING_INFO = 0x004
    LOGGING_WARN = 0x008
    LOGGING_ERROR = 0x010
    LOGGING_FATAL = 0x800
    # some extra logging flags are merged into normal flags for now
    LOGGING_EX_MISSING_TAGS = LOGGING_TRACE
    """0x001"""
    LOGGING_EX_EXCLUDED_TAGS = LOGGING_INFO
    """0x004"""
    LOGGING_ALL = LOGGING_FATAL | LOGGING_ERROR | LOGGING_WARN | LOGGING_INFO | LOGGING_DEBUG | LOGGING_TRACE
    """0x81F"""

    def __str__(self) -> str:
        return f'{self._name_} (0x{self.value:03X})'


LOGGING_FLAGS = {
    'error': f'0x{LoggingFlags.LOGGING_ERROR.value:03X}',
    'warn': f'0x{LoggingFlags.LOGGING_WARN.value:03X}',
    'info': f'0x{LoggingFlags.LOGGING_INFO.value:03X}',
    'debug': f'0x{LoggingFlags.LOGGING_DEBUG.value:03X}',
    'trace': f'0x{LoggingFlags.LOGGING_TRACE.value:03X}',
}
"""{\n\n'error': '0x010',\n\n'warn': '0x008',\n\n'info': '0x004',\n\n'debug': '0x002',\n\n'trace': '0x001'\n\n}"""
LOGGING_FLAGS_DEFAULT = LoggingFlags.LOGGING_INFO
"""0x004"""

ACTION_STORE_TRUE = 'store_true'
ACTION_STORE_FALSE = 'store_false'

HELP_ARG_VERSION = 'Show program\'s version number and exit'
HELP_ARG_GET_MAXID = 'Print maximum id and exit'
HELP_ARG_BEGIN_STOP_ID = 'Album id lower / upper bounds filter to only download albums where \'begin_id >= album_id >= stop_id\''
HELP_ARG_IDSEQUENCE = (
    'Use album id sequence instead of range. This disables start / count / end id parametes and expects an id sequence instead of'
    ' extra tags. Sequence structure: (id=<id1>~id=<id2>~id=<id3>~...~id=<idN>)'
)
HELP_ARG_PATH = 'Download destination. Default is current folder'
HELP_ARG_SEARCH_RULE = (
    f'Multiple search args of the same type combine logic. Default is \'{SEARCH_RULE_DEFAULT}\'.'
    f' Example: while searching for tags \'sfw,side_view\','
    f' \'{SEARCH_RULE_ANY}\' will search for any of those tags, \'{SEARCH_RULE_ALL}\' will only return results matching both'
)
HELP_ARG_SEARCH_ACT = (
    'Native search by tag(s) / artist(s) / category(ies). Spaces must be replced with \'_\', concatenate with \',\'.'
    ' Example: \'-search_tag 1girl,side_view -search_art artist_name -search_cat category_name\''
)
HELP_ARG_SEARCH_STR = 'Native search using string query (matching any word). Spaces must be replced with \'-\'. Ex. \'after-hours\''
HELP_ARG_PROXY = 'Proxy to use. Example: http://127.0.0.1:222'
HELP_ARG_UTPOLICY = (
    f'Untagged albums download policy. By default these albums are ignored if you use extra \'tags\' / \'-tags\'.'
    f' Use \'{DOWNLOAD_POLICY_ALWAYS}\' to override'
)
HELP_ARG_DMMODE = '[Debug] Download (file creation) mode'
HELP_ARG_EXTRA_TAGS = (
    'All remaining \'args\' and \'-args\' count as tags to require or exclude. All spaces must be replaced with \'_\'.'
    ' Albums containing any of \'-tags\', or not containing all \'tags\' will be skipped.'
    ' Supports wildcards, \'or\' groups and \'negative\' groups (check README for more info).'
    ' Only existing tags are allowed unless wildcards are used'
)
HELP_ARG_DWN_SCENARIO = (
    'Download scenario. This allows to scan for tags and sort albums accordingly in a single pass.'
    ' Useful when you have several queries you need to process for same id range.'
    ' Format:'
    ' "{SUBDIR1}: tag1 tag2; {SUBDIR2}: tag3 tag4".'
    ' You can also use following arguments in each subquery: -utp, -seq.'
    ' Example:'
    ' \'python ids.py -path ... -start ... -end ... --download-scenario'
    ' "1g: 1girl; 2g: 2girls -utp always"\''
)
HELP_ARG_CMDFILE = (
    'Full path to file containing cmdline arguments. Useful when cmdline length exceeds maximum for your OS.'
    ' Windows: ~32000, MinGW: ~4000 to ~32000, Linux: ~127000+. Check README for more info'
)
HELP_ARG_NAMING = (
    f'Album folder naming flags: {str(NAMING_FLAGS).replace(" ", "").replace(":", "=")}.'
    f' You can combine them via names \'prefix|title\', otherwise it has to be an int or a hex number.'
    f' Default is \'full\''
)
HELP_ARG_LOGGING = (
    f'Logging level: {{{str(list(LOGGING_FLAGS.keys())).replace(" ", "")[1:-1]}}}.'
    f' All messages equal or above this level will be logged. Default is \'info\''
)
HELP_ARG_DUMP_INFO = 'Save tags / comments to text file (separately)'
HELP_ARG_CONTINUE = 'Try to continue unfinished files, may be slower if most files already exist'
HELP_ARG_UNFINISH = 'Do not clean up unfinished files on interrupt'
HELP_ARG_TIMEOUT = 'Connection timeout (in seconds)'
HELP_ARG_NO_DEDUPLICATE = (
    'Disable deduplication of search results (by name).'
    ' By default exact matches will be dropped except the latest one (highest album id)'
)

re_media_filename = re_compile(fr'^(?:rc_)?(\d+).+?\.(?:{"|".join(EXTENSIONS_I)})$')
re_replace_symbols = re_compile(REPLACE_SYMBOLS)


class Log:
    """
    Basic logger supporting different log levels, colors and extra logging flags\n
    **Static**
    """
    COLORS = {
        LoggingFlags.LOGGING_TRACE: Fore.WHITE,
        LoggingFlags.LOGGING_DEBUG: Fore.LIGHTWHITE_EX,
        LoggingFlags.LOGGING_INFO: Fore.LIGHTCYAN_EX,
        LoggingFlags.LOGGING_WARN: Fore.LIGHTYELLOW_EX,
        LoggingFlags.LOGGING_ERROR: Fore.LIGHTYELLOW_EX,
        LoggingFlags.LOGGING_FATAL: Fore.LIGHTRED_EX
    }

    @staticmethod
    def log(text: str, flags: LoggingFlags) -> None:
        # if flags & LoggingFlags.LOGGING_FATAL == 0 and Config.logging_flags & flags != flags:
        if flags < Config.logging_flags:
            return

        for f in reversed(Log.COLORS.keys()):
            if f & flags:
                text = f'{Log.COLORS[f]}{text}{Fore.RESET}'
                break

        try:
            print(text)
        except UnicodeError:
            try:
                print(text.encode(UTF8).decode())
            except Exception:
                try:
                    print(text.encode(UTF8).decode(getpreferredencoding()))
                except Exception:
                    print('<Message was not logged due to UnicodeError>')
            finally:
                print('Previous message caused UnicodeError...')

    @staticmethod
    def fatal(text: str) -> None:
        return Log.log(text, LoggingFlags.LOGGING_FATAL)

    @staticmethod
    def error(text: str, extra_flags=LoggingFlags.LOGGING_NONE) -> None:
        return Log.log(text, LoggingFlags.LOGGING_ERROR | extra_flags)

    @staticmethod
    def warn(text: str, extra_flags=LoggingFlags.LOGGING_NONE) -> None:
        return Log.log(text, LoggingFlags.LOGGING_WARN | extra_flags)

    @staticmethod
    def info(text: str, extra_flags=LoggingFlags.LOGGING_NONE) -> None:
        return Log.log(text, LoggingFlags.LOGGING_INFO | extra_flags)

    @staticmethod
    def debug(text: str, extra_flags=LoggingFlags.LOGGING_NONE) -> None:
        return Log.log(text, LoggingFlags.LOGGING_DEBUG | extra_flags)

    @staticmethod
    def trace(text: str, extra_flags=LoggingFlags.LOGGING_NONE) -> None:
        return Log.log(text, LoggingFlags.LOGGING_TRACE | extra_flags)


def prefixp() -> str:
    return 'rc_'


def format_time(seconds: int) -> str:
    """Formats time from seconds to format: **hh:mm:ss**"""
    mm, ss = divmod(seconds, 60)
    hh, mm = divmod(mm, 60)
    return f'{hh:02d}:{mm:02d}:{ss:02d}'


def get_elapsed_time_i() -> int:
    """Returns time since launch in **seconds**"""
    return (datetime.now() - START_TIME).seconds


def get_elapsed_time_s() -> str:
    """Returns time since launch in format: **hh:mm:ss**"""
    return format_time((datetime.now() - START_TIME).seconds)


def unquote(string: str) -> str:
    """Removes all leading/trailing single/double quotes. Non-matching quotes are removed too"""
    try:
        while True:
            found = False
            if len(string) > 1 and string[0] in ['\'', '"']:
                string = string[1:]
                found = True
            if len(string) > 1 and string[-1] in ['\'', '"']:
                string = string[:-1]
                found = True
            if not found:
                break
        return string
    except Exception:
        raise ValueError


def normalize_path(basepath: str, append_slash=True) -> str:
    """Converts path string to universal slash-concatenated string, enclosing slash is optional"""
    normalized_path = basepath.replace('\\', SLASH)
    if append_slash and len(normalized_path) != 0 and normalized_path[-1] != SLASH:
        normalized_path += SLASH
    return normalized_path


def normalize_filename(filename: str, base_path: str) -> str:
    """Returns full path to a file, normalizing base path and removing disallowed symbols from file name"""
    return normalize_path(base_path) + re_replace_symbols.sub('_', filename)


def has_naming_flag(flag: int) -> bool:
    return not not (Config.naming_flags & flag)


def calc_sleep_time(base_time: float) -> float:
    """Returns either base_time for full download or shortened time otherwise"""
    return base_time if Config.download_mode == DOWNLOAD_MODE_FULL else max(1.0, base_time / 3.0)


def at_startup() -> None:
    """Reports python version and run options"""
    Log.debug(f'Python {sys.version}\nCommand-line args: {" ".join(sys.argv)}')


class DownloadResult(IntEnum):
    DOWNLOAD_SUCCESS = 0
    DOWNLOAD_FAIL_NOT_FOUND = 1
    DOWNLOAD_FAIL_RETRIES = 2
    DOWNLOAD_FAIL_ALREADY_EXISTS = 3
    DOWNLOAD_FAIL_SKIPPED = 4

    def __str__(self) -> str:
        return f'{self._name_} (0x{self.value:d})'


class Mem:
    KB = 1024
    MB = KB * 1024
    GB = MB * 1024


class HelpPrintExitException(Exception):
    pass

#
#
#########################################
