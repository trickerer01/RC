# coding=UTF-8
"""
Author: trickerer (https://github.com/trickerer, https://github.com/trickerer01)
"""
#########################################
#
#

from argparse import ArgumentParser, ZERO_OR_MORE
from typing import List, Optional

from defs import UALBUM_POLICIES, DOWNLOAD_POLICY_DEFAULT, DOWNLOAD_POLICY_ALWAYS, ACTION_STORE_TRUE
from logger import Log
from tagger import valid_extra_tag, try_parse_id_or_group, is_filtered_out_by_extra_tags

__all__ = ('DownloadScenario')

UTP_DEFAULT = DOWNLOAD_POLICY_DEFAULT
"""'nofilters'"""
UTP_ALWAYS = DOWNLOAD_POLICY_ALWAYS
"""'always'"""


class SubQueryParams(object):
    def __init__(self, subfolder: str, extra_tags: List[str], utp: str, use_id_sequence: bool) -> None:
        self.subfolder = subfolder or ''  # type: str
        self.extra_tags = extra_tags or list()  # type: List[str]
        self.untagged_policy = utp or ''  # type: str
        self.use_id_sequence = use_id_sequence or False  # type: bool

    @property
    def utp(self) -> str:
        return self.untagged_policy

    def __repr__(self) -> str:
        return (
            f'sub: \'{self.subfolder}\', '
            f'utp: \'{self.utp}\', '
            f'use_id_sequence: \'{self.use_id_sequence}\', '
            f'tags: \'{str(self.extra_tags)}\''
        )


class DownloadScenario(object):
    def __init__(self, fmt_str: str) -> None:
        assert fmt_str

        self.queries = list()  # type: List[SubQueryParams]

        parser = ArgumentParser(add_help=False)
        parser.add_argument('-seq', '--use-id-sequence', action=ACTION_STORE_TRUE, help='')
        parser.add_argument('-utp', '--untagged-policy', default=UTP_DEFAULT, help='', choices=UALBUM_POLICIES)
        parser.add_argument(dest='extra_tags', nargs=ZERO_OR_MORE, help='', type=valid_extra_tag)

        for query_raw in fmt_str.split('; '):
            error_to_print = ''
            try:
                subfolder, args = query_raw.split(': ')
                parsed, unks = parser.parse_known_args(args.split())
                for tag in unks:
                    try:
                        assert valid_extra_tag(tag)
                        if parsed.use_id_sequence is True:
                            assert len(unks) == 1
                            assert try_parse_id_or_group([tag]) is not None
                    except Exception:
                        error_to_print = f'\nInvalid extra tag: \'{tag}\'\n'
                        raise
                parsed.extra_tags += [tag.lower().replace(' ', '_') for tag in unks]
                if parsed.untagged_policy == UTP_ALWAYS and self.has_subquery(utp=UTP_ALWAYS):
                    error_to_print = f'Scenario can only have one subquery with untagged album policy \'{UTP_ALWAYS}\'!'
                    raise ValueError
                self.add_subquery(SubQueryParams(subfolder, parsed.extra_tags, parsed.untagged_policy, parsed.use_id_sequence))
            except Exception:
                if error_to_print != '':
                    Log.error(error_to_print)
                raise

        assert len(self) > 0

    def __len__(self) -> int:
        return len(self.queries)

    def add_subquery(self, subquery: SubQueryParams) -> None:
        self.queries.append(subquery)

    def has_subquery(self, **kwargs) -> bool:
        for sq in self.queries:
            all_matched = True
            for k, v in kwargs.items():
                if not (hasattr(sq, k) and getattr(sq, k) == v):
                    all_matched = False
                    break
            if all_matched is True:
                return True
        return False

    def get_matching_subquery(self, idi: int, tags_raw: List[str]) -> Optional[SubQueryParams]:
        for sq in self.queries:
            if not is_filtered_out_by_extra_tags(idi, tags_raw, sq.extra_tags, sq.use_id_sequence, sq.subfolder):
                return sq
        return None

    def get_utp_always_subquery(self) -> Optional[SubQueryParams]:
        return next(filter(lambda sq: sq.utp == UTP_ALWAYS, self.queries), None)

#
#
#########################################
