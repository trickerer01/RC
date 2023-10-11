# coding=UTF-8
"""
Author: trickerer (https://github.com/trickerer, https://github.com/trickerer01)
"""
#########################################
#
#

from argparse import ArgumentParser, Namespace, ArgumentError, ZERO_OR_MORE
from os import path
from typing import List, Sequence, Tuple

from defs import (
    Log, HelpPrintExitException, UTF8, APP_NAME, APP_VERSION, ACTION_STORE_TRUE, HELP_ARG_PATH, HELP_ARG_SEARCH_STR, HELP_ARG_PROXY,
    HELP_ARG_BEGIN_STOP_ID, HELP_ARG_GET_MAXID, HELP_ARG_EXTRA_TAGS, HELP_ARG_UTPOLICY, UALBUM_POLICIES, DOWNLOAD_POLICY_DEFAULT,
    DOWNLOAD_MODES, DOWNLOAD_MODE_DEFAULT, NAMING_FLAGS_DEFAULT, LOGGING_FLAGS_DEFAULT, HELP_ARG_DMMODE, HELP_ARG_DWN_SCENARIO,
    HELP_ARG_CMDFILE, HELP_ARG_NAMING, HELP_ARG_LOGGING, HELP_ARG_IDSEQUENCE, HELP_ARG_CONTINUE, HELP_ARG_UNFINISH, HELP_ARG_DUMP_INFO,
    HELP_ARG_TIMEOUT, HELP_ARG_VERSION, HELP_ARG_SEARCH_ACT, HELP_ARG_SEARCH_RULE, SEARCH_RULES, SEARCH_RULE_DEFAULT,
    HELP_ARG_NO_DEDUPLICATE,
)
from scenario import DownloadScenario
from tagger import valid_extra_tag, valid_tags, valid_artists, valid_categories
from validators import positive_nonzero_int, valid_path, valid_filepath_abs, valid_search_string, valid_proxy, naming_flags, log_level

__all__ = ('prepare_arglist_pages', 'prepare_arglist_ids', 'read_cmdfile', 'is_parsed_cmdfile')

UTP_DEFAULT = DOWNLOAD_POLICY_DEFAULT
"""'nofilters'"""
DM_DEFAULT = DOWNLOAD_MODE_DEFAULT
"""'full'"""
NAMING_DEFAULT = NAMING_FLAGS_DEFAULT
"""0x1F"""
LOGGING_DEFAULT = LOGGING_FLAGS_DEFAULT
"""0x004"""

PARSER_TITLE_FILE = 'file'
PARSER_TITLE_CMD = 'cmd'
EXISTING_PARSERS = {PARSER_TITLE_CMD, PARSER_TITLE_FILE}


def read_cmdfile(cmdfile_path: str) -> List[str]:
    """Read cmd args from a text file"""
    with open(cmdfile_path, 'rt', encoding=UTF8) as cmdfile:
        args = list()
        for line in cmdfile.readlines():
            line = line.strip(' \n\ufeff')
            if line != '':
                args.append(line)
        return args


def is_parsed_cmdfile(parse_result: Namespace) -> bool:
    """Determines if parsed cmdline points to a text file"""
    return hasattr(parse_result, 'path') and not hasattr(parse_result, 'extra_tags')


def validate_parsed(parser: ArgumentParser, args: Sequence[str], default_sub: ArgumentParser) -> Namespace:
    error_to_print = ''
    try:
        parsed, unks = parser.parse_known_args(args) if args[0] in EXISTING_PARSERS else default_sub.parse_known_args(args)
        if not is_parsed_cmdfile(parsed):
            for tag in unks:
                try:
                    assert valid_extra_tag(tag)
                except Exception:
                    error_to_print = f'\nInvalid extra tag: \'{tag}\'\n'
                    raise
            parsed.extra_tags += [tag.lower().replace(' ', '_') for tag in unks]
    except (ArgumentError, TypeError, Exception):
        # print('\n', e)
        parser.print_help()
        if error_to_print != '':
            Log.error(error_to_print)
        raise

    return parsed


def execute_parser(parser: ArgumentParser, default_sub: ArgumentParser, args: Sequence[str], pages: bool) -> Namespace:
    try:
        parsed = validate_parsed(parser, args, default_sub)
        if (not is_parsed_cmdfile(parsed)) and not (pages and parsed.get_maxid):
            if pages:
                if parsed.end < parsed.start + parsed.pages - 1:
                    parsed.end = parsed.start + parsed.pages - 1
            else:
                if parsed.use_id_sequence:
                    parsed.start = parsed.end = None
                elif parsed.end < parsed.start + parsed.count - 1:
                    parsed.end = parsed.start + parsed.count - 1
        return parsed
    except SystemExit:
        raise HelpPrintExitException
    except Exception:
        raise


def create_parsers() -> Tuple[ArgumentParser, ArgumentParser, ArgumentParser]:
    parser = ArgumentParser(add_help=False)
    subs = parser.add_subparsers()
    par_file = subs.add_parser(PARSER_TITLE_FILE, description='Run using text file containing cmdline', add_help=False)
    par_cmd = subs.add_parser(PARSER_TITLE_CMD, description='Run using normal cmdline', add_help=False)
    [p.add_argument('--help', action='help', help='Print this message') for p in (par_file, par_cmd)]
    [p.add_argument('--version', action='version', help=HELP_ARG_VERSION, version=f'{APP_NAME} {APP_VERSION}') for p in (par_file, par_cmd)]
    return parser, par_file, par_cmd


def add_common_args(parser_or_group: ArgumentParser) -> None:
    parser_or_group.add_argument('-path', default=valid_path(path.abspath(path.curdir)), help=HELP_ARG_PATH, type=valid_path)
    parser_or_group.add_argument('-utp', '--untagged-policy', default=UTP_DEFAULT, help=HELP_ARG_UTPOLICY, choices=UALBUM_POLICIES)
    parser_or_group.add_argument('-proxy', metavar='#type://a.d.d.r:port', default=None, help=HELP_ARG_PROXY, type=valid_proxy)
    parser_or_group.add_argument('-timeout', metavar='#seconds', default=0, help=HELP_ARG_TIMEOUT, type=positive_nonzero_int)
    parser_or_group.add_argument('-continue', '--continue-mode', action=ACTION_STORE_TRUE, help=HELP_ARG_CONTINUE)
    parser_or_group.add_argument('-unfinish', '--keep-unfinished', action=ACTION_STORE_TRUE, help=HELP_ARG_UNFINISH)
    parser_or_group.add_argument('-naming', default=NAMING_DEFAULT, help=HELP_ARG_NAMING, type=naming_flags)
    parser_or_group.add_argument('-log', '--log-level', default=LOGGING_DEFAULT, help=HELP_ARG_LOGGING, type=log_level)
    parser_or_group.add_argument('-tdump', '--dump-tags', action=ACTION_STORE_TRUE, help='')
    parser_or_group.add_argument('-cdump', '--dump-comments', action=ACTION_STORE_TRUE, help=HELP_ARG_DUMP_INFO)
    parser_or_group.add_argument('-dmode', '--download-mode', default=DM_DEFAULT, help=HELP_ARG_DMMODE, choices=DOWNLOAD_MODES)
    parser_or_group.add_argument('-script', '--download-scenario', default=None, help=HELP_ARG_DWN_SCENARIO, type=DownloadScenario)
    parser_or_group.add_argument(dest='extra_tags', nargs=ZERO_OR_MORE, help=HELP_ARG_EXTRA_TAGS, type=valid_extra_tag)


def prepare_arglist_ids(args: Sequence[str]) -> Namespace:
    parser, par_file, par_cmd = create_parsers()

    par_file.add_argument('-path', metavar='#filepath', required=True, help=HELP_ARG_CMDFILE, type=valid_filepath_abs)
    arggr_start_or_seq = par_cmd.add_mutually_exclusive_group(required=True)
    arggr_count_or_end = par_cmd.add_mutually_exclusive_group()
    arggr_start_or_seq.add_argument('-start', metavar='#number', help='Start album id. Required', type=positive_nonzero_int)
    arggr_count_or_end.add_argument('-count', metavar='#number', default=1, help='Ids count to process', type=positive_nonzero_int)
    arggr_count_or_end.add_argument('-end', metavar='#number', default=1, help='End album id', type=positive_nonzero_int)
    arggr_start_or_seq.add_argument('-seq', '--use-id-sequence', action=ACTION_STORE_TRUE, help=HELP_ARG_IDSEQUENCE)

    add_common_args(par_cmd)
    return execute_parser(parser, par_cmd, args, False)


def prepare_arglist_pages(args: Sequence[str]) -> Namespace:
    parser, par_file, par_cmd = create_parsers()

    par_file.add_argument('-path', metavar='#filepath', required=True, help=HELP_ARG_CMDFILE, type=valid_filepath_abs)
    par_cmd.add_argument('-start', metavar='#number', default=1, help="Start page number. Default is '1'", type=positive_nonzero_int)
    arggr_count_or_end = par_cmd.add_mutually_exclusive_group(required=True)
    arggr_count_or_end.add_argument('-get_maxid', action=ACTION_STORE_TRUE, help=HELP_ARG_GET_MAXID)
    arggr_count_or_end.add_argument('-pages', metavar='#number', help='Pages count to process', type=positive_nonzero_int)
    arggr_count_or_end.add_argument('-end', metavar='#number', default=1, help='End page number', type=positive_nonzero_int)
    par_cmd.add_argument('-stop_id', metavar='#number', default=1, help='', type=positive_nonzero_int)
    par_cmd.add_argument('-begin_id', metavar='#number', default=10**9, help=HELP_ARG_BEGIN_STOP_ID, type=positive_nonzero_int)
    par_cmd.add_argument('-search', metavar='#string', default='', help=HELP_ARG_SEARCH_STR, type=valid_search_string)
    par_cmd.add_argument('-search_tag', metavar='#tag[,tag...]', default='', help='', type=valid_tags)
    par_cmd.add_argument('-search_art', metavar='#artist[,artist...]', default='', help='', type=valid_artists)
    par_cmd.add_argument('-search_cat', metavar='#catergory[,category...]', default='', help=HELP_ARG_SEARCH_ACT, type=valid_categories)
    par_cmd.add_argument('-search_rule_tag', default=SEARCH_RULE_DEFAULT, help='', choices=SEARCH_RULES)
    par_cmd.add_argument('-search_rule_art', default=SEARCH_RULE_DEFAULT, help='', choices=SEARCH_RULES)
    par_cmd.add_argument('-search_rule_cat', default=SEARCH_RULE_DEFAULT, help=HELP_ARG_SEARCH_RULE, choices=SEARCH_RULES)
    par_cmd.add_argument('-nodedup', '--no-deduplicate-names', action=ACTION_STORE_TRUE, help=HELP_ARG_NO_DEDUPLICATE)
    par_cmd.epilog = 'Note that search obeys \'AND\' rule: (ANY/ALL tag(s)) AND (ANY/ALL artist(s)) AND (ANY/ALL category(ies))'

    add_common_args(par_cmd)
    return execute_parser(parser, par_cmd, args, True)

#
#
#########################################