# coding=UTF-8
"""
Author: trickerer (https://github.com/trickerer, https://github.com/trickerer01)
"""
#########################################
#
#

from base64 import b64decode
from datetime import datetime
from enum import IntEnum

APP_NAME = 'RC'
APP_VERSION = '1.0.100'

CONNECT_RETRIES_BASE = 50
CONNECT_TIMEOUT_BASE = 10
CONNECT_REQUEST_DELAY = 0.2

MAX_DEST_SCAN_SUB_DEPTH = 2
MAX_IMAGES_QUEUE_SIZE = 10
DOWNLOAD_STATUS_CHECK_TIMER = 60
DOWNLOAD_QUEUE_STALL_CHECK_TIMER = 30
DOWNLOAD_CONTINUE_FILE_CHECK_TIMER = 30

# SCREENSHOTS_COUNT = 10
FULLPATH_MAX_BASE_LEN = 240 - len('rc_9999999.jpg')

PREFIX = 'rc_'
SLASH = '/'
UTF8 = 'utf-8'
TAGS_CONCAT_CHAR = ','
DEFAULT_EXT = 'jpg'
EXTENSIONS_I = (DEFAULT_EXT, 'jpeg')
START_TIME = datetime.now()

SITE = b64decode('aHR0cHM6Ly9ydWxlMzRjb21pYy5wYXJ0eQ==').decode()
SITE_AJAX_REQUEST_SEARCH_PAGE = b64decode(
    'aHR0cHM6Ly9ydWxlMzRjb21pYy5wYXJ0eS9zZWFyY2gvP21vZGU9YXN5bmMmZnVuY3Rpb249Z2V0X2Jsb2NrJmJsb2NrX2lkPWxpc3RfYWxidW1zX2FsYnVtc19saXN0X3NlYX'
    'JjaF9yZXN1bHQmZmxhZzE9JnNvcnRfYnk9cG9zdF9kYXRlJnRhZ19pZHM9JXMmbW9kZWxfaWRzPSVzJmNhdGVnb3J5X2lkcz0lcyZxPSVzJmZyb21fYWxidW1zPSVk'
).decode()
"""Params required: **tags**, **artists**, **categories**, **search**, **page** - **str**, **str**, **str**, **str**, **int**\n
Ex. SITE_AJAX_REQUEST_SEARCH_PAGE % ('1,2', '3,4,5', '6', 'sfw', 1)"""
SITE_AJAX_REQUEST_ALBUM = b64decode('aHR0cHM6Ly9ydWxlMzRjb21pYy5wYXJ0eS9jb21pY3MvJWQvYS8=').decode()
"""Params required: **album_id** - **int**\n
Ex. SITE_AJAX_REQUEST_ALBUM % 11111"""
SITE_AJAX_REQUEST_UPLOADER_PAGE = b64decode(
    'aHR0cHM6Ly9ydWxlMzRjb21pYy5wYXJ0eS9jb21tdW5pdHkvJWQvdW5rL2NvbWljcy8/bW9kZT1hc3luYyZmdW5jdGlvbj1nZXRfYmxvY2smYmxvY2tfaWQ9bGlzdF9hbGJ1bX'
    'NfY3JlYXRlZF9hbGJ1bXMmc29ydF9ieT0mZnJvbV9hbGJ1bXM9JWQ=').decode()
"""Params required: **user_id**, **page** - **int**, **int**\n
Ex. SITE_AJAX_REQUEST_UPLOADER_PAGE % (158018, 1)"""

USER_AGENT = 'Mozilla/5.0 (X11; Linux x86_64; rv:102.0) Gecko/20100101 Goanna/6.6 Firefox/102.0 PaleMoon/33.0.1'
DEFAULT_HEADERS = {'User-Agent': USER_AGENT}

# untagged albums download policy
DOWNLOAD_POLICY_NOFILTERS = 'nofilters'
DOWNLOAD_POLICY_ALWAYS = 'always'
UNTAGGED_POLICIES = (DOWNLOAD_POLICY_NOFILTERS, DOWNLOAD_POLICY_ALWAYS)
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
    NONE = 0x00
    PREFIX = 0x01
    SCORE = 0x02
    TITLE = 0x04
    TAGS = 0x08
    ALL = PREFIX | SCORE | TITLE | TAGS
    """0x0F"""


NAMING_FLAGS = {
    'none': f'0x{NamingFlags.NONE:02X}',
    'prefix': f'0x{NamingFlags.PREFIX:02X}',
    'score': f'0x{NamingFlags.SCORE:02X}',
    'title': f'0x{NamingFlags.TITLE:02X}',
    'tags': f'0x{NamingFlags.TAGS:02X}',
    'full': f'0x{NamingFlags.ALL:02X}'
}
"""
{\n\n'none': '0x00',\n\n'prefix': '0x01',\n\n'score': '0x02',\n\n'title': '0x04',\n\n'tags': '0x08',\n\n'full': '0x0F'\n\n}
"""
NAMING_FLAGS_DEFAULT = NamingFlags.ALL
"""0x0F"""


class LoggingFlags(IntEnum):
    NONE = 0x000
    TRACE = 0x001
    DEBUG = 0x002
    INFO = 0x004
    WARN = 0x008
    ERROR = 0x010
    FATAL = 0x800
    # some extra logging flags are merged into normal flags for now
    EX_MISSING_TAGS = TRACE
    """0x001"""
    EX_EXCLUDED_TAGS = INFO
    """0x004"""
    EX_LOW_SCORE = INFO
    """0x004"""
    # unused
    ALL = FATAL | ERROR | WARN | INFO | DEBUG | TRACE
    """0x81F"""

    def __str__(self) -> str:
        return f'{self.name} (0x{self.value:03X})'


LOGGING_FLAGS = {
    'error': f'0x{LoggingFlags.ERROR.value:03X}',
    'warn': f'0x{LoggingFlags.WARN.value:03X}',
    'info': f'0x{LoggingFlags.INFO.value:03X}',
    'debug': f'0x{LoggingFlags.DEBUG.value:03X}',
    'trace': f'0x{LoggingFlags.TRACE.value:03X}',
}
"""{\n\n'error': '0x010',\n\n'warn': '0x008',\n\n'info': '0x004',\n\n'debug': '0x002',\n\n'trace': '0x001'\n\n}"""
LOGGING_FLAGS_DEFAULT = LoggingFlags.INFO
"""0x004"""

ACTION_STORE_TRUE = 'store_true'

HELP_ARG_VERSION = 'Show program\'s version number and exit'
HELP_ARG_GET_MAXID = 'Print maximum id and exit'
HELP_ARG_BEGIN_STOP_ID = 'Album id lower / upper bounds filter to only download albums where \'begin_id >= album_id >= stop_id\''
HELP_ARG_IDSEQUENCE = (
    'Use album id sequence instead of range. This disables start / count / end id parametes and expects an id sequence among'
    ' extra tags. Sequence structure: (id=<id1>~id=<id2>~id=<id3>~...~id=<idN>)'
)
HELP_ARG_PATH = 'Download destination. Default is current folder'
HELP_ARG_SESSION_ID = (
    '\'PHPSESSID\' cookie. Comments as well as some tags to search for are hidden behind login wall.'
    ' Using this cookie from logged in account resolves that problem'
)
HELP_ARG_SEARCH_RULE = (
    f'Multiple search args of the same type combine logic. Default is \'{SEARCH_RULE_DEFAULT}\'.'
    f' Example: while searching for tags \'sfw,side_view\','
    f' \'{SEARCH_RULE_ANY}\' will search for any of those tags, \'{SEARCH_RULE_ALL}\' will only return results matching both'
)
HELP_ARG_SEARCH_ACT = (
    'Native search by tag(s) / artist(s) / category(ies). Spaces must be replced with \'_\', concatenate with \',\'.'
    ' Example: \'-search_tag 1girl,side_view -search_art artist_name -search_cat category_name\'.'
    ' Note that search obeys \'AND\' rule: search string AND ANY_OF/ALL the tags AND ANY_OF/ALL the artists AND ANY_OF/ALL the categories'
)
HELP_ARG_SEARCH_STR = 'Native search using string query (matching any word). Spaces must be replced with \'-\'. Ex. \'after-hours\''
HELP_ARG_PROXY = 'Proxy to use. Example: http://127.0.0.1:222'
HELP_ARG_UTPOLICY = (
    f'Untagged albums download policy. By default these albums are ignored if you use extra \'tags\' / \'-tags\'.'
    f' \'{DOWNLOAD_POLICY_ALWAYS}\' to override'
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
HELP_ARG_STORE_CONTINUE_CMDFILE = (
    'Store and automatically update cmd file which allows to later continue with unfinished download queue (using ids module, file mode)'
)
HELP_ARG_MINRATING = (
    'Rating percentage filter, 0-100.'
    ' Albums having rating below this value will be skipped, unless rating extraction fails - in that case album always gets a pass'
)
HELP_ARG_MINSCORE = (
    'Score filter (likes minus dislikes).'
    ' Albums having score below this value will be skipped, unless score extraction fails - in that case album always gets a pass'
)
HELP_ARG_CMDFILE = (
    'Full path to file containing cmdline arguments. Useful when cmdline length exceeds maximum for your OS.'
    ' Windows: ~32000, MinGW: ~4000 to ~32000, Linux: ~127000+. Check README for more info'
)
HELP_ARG_NAMING = (
    f'Album folder naming flags: {str(NAMING_FLAGS).replace(" ", "").replace(":", "=")}.'
    f' You can combine them via names \'prefix|score|title\', otherwise it has to be an int or a hex number.'
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
HELP_ARG_THROTTLE = 'Download speed threshold (in KB/s) to assume throttling, drop connection and retry'
HELP_ARG_UPLOADER = 'Uploader user id (integer, filters still apply)'
# HELP_ARG_MODEL = 'Artist name (download directly from artist\'s page)'
HELP_ARG_ALLOW_DUPLICATE_NAMES = (
    'Disable deduplication of search results (by name).'
    ' By default exact matches will be dropped except the latest one (highest album id)'
)
HELP_ARG_INCLUDE_PREVIEWS = 'Download album preview (not affected by download mode)'


class DownloadResult(IntEnum):
    SUCCESS = 0
    FAIL_NOT_FOUND = 1
    FAIL_RETRIES = 2
    FAIL_ALREADY_EXISTS = 3
    FAIL_SKIPPED = 4

    def __str__(self) -> str:
        return f'{self.name} (0x{self.value:d})'


class Mem:
    KB = 1024
    MB = KB * 1024
    GB = MB * 1024

#
#
#########################################
