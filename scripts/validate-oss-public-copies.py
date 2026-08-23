#!/usr/bin/env python3
"""Fail-closed validation for every public OSS-copy configuration artifact."""

from __future__ import annotations

import argparse
import difflib
import html
import re
import string
import subprocess
import sys
import unicodedata
from datetime import date, datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote


FORBIDDEN_PUBLIC_KEYS = {
    "uuid",
    "password",
    "obfs-password",
    "short-id",
    "client-fingerprint",
    "reality-opts",
}
URL_DECODE_MAX_PASSES = 8
MARKDOWN_ENTITY_REFERENCE = re.compile(
    r"&(?:#[xX][0-9A-Fa-f]{1,6}|#[0-9]{1,7}|[A-Za-z][A-Za-z0-9]+);"
)
MARKDOWN_FENCE_OPEN = re.compile(r"^ {0,3}(`{3,}|~{3,})([^\r\n]*)$")
HTML_TAG_NAME = re.compile(r"[A-Za-z][A-Za-z0-9-]*\Z")
HTML_BLOCK_RAW_START = re.compile(
    r"^ {0,3}<(script|pre|style|textarea)(?:[\t />]|$)",
    re.IGNORECASE,
)
HTML_BLOCK_TAG_START = re.compile(
    r"^ {0,3}</?(?:address|article|aside|base|basefont|blockquote|body|caption|"
    r"center|col|colgroup|dd|details|dialog|dir|div|dl|dt|fieldset|figcaption|"
    r"figure|footer|form|frame|frameset|h[1-6]|head|header|hr|html|iframe|"
    r"legend|li|link|main|menu|menuitem|nav|noframes|ol|optgroup|option|p|"
    r"param|search|section|summary|table|tbody|td|tfoot|th|thead|title|tr|"
    r"track|ul)(?:[\t />]|$)",
    re.IGNORECASE,
)
HTML_LINE_ENDING = r"(?:\r\n|\n|\r)"
HTML_REQUIRED_WHITESPACE = (
    rf"(?:[ \t]+(?:{HTML_LINE_ENDING}[ \t]*)?|"
    rf"[ \t]*{HTML_LINE_ENDING}[ \t]*)"
)
HTML_OPTIONAL_WHITESPACE = rf"[ \t]*(?:{HTML_LINE_ENDING}[ \t]*)?"
HTML_ATTRIBUTE_NAME = r"[A-Za-z_:][A-Za-z0-9_.:-]*"
HTML_UNQUOTED_ATTRIBUTE_VALUE = r"[^ \t\r\n\"'=<>`]+"
HTML_ATTRIBUTE_VALUE = (
    rf"(?:{HTML_UNQUOTED_ATTRIBUTE_VALUE}|'[^']*'|\"[^\"]*\")"
)
HTML_ATTRIBUTE = (
    rf"{HTML_REQUIRED_WHITESPACE}{HTML_ATTRIBUTE_NAME}"
    rf"(?:{HTML_OPTIONAL_WHITESPACE}={HTML_OPTIONAL_WHITESPACE}{HTML_ATTRIBUTE_VALUE})?"
)
HTML_OPEN_TAG = re.compile(
    rf"<[A-Za-z][A-Za-z0-9-]*(?:{HTML_ATTRIBUTE})*{HTML_OPTIONAL_WHITESPACE}/?>"
)
HTML_CLOSING_TAG = re.compile(
    rf"</[A-Za-z][A-Za-z0-9-]*{HTML_OPTIONAL_WHITESPACE}>"
)
HTML_DECLARATION = re.compile(r"<![A-Z][^>]*>")
MARKDOWN_ATX_HEADING = re.compile(r"^ {0,3}#{1,6}(?:[\t ]+|$)")
RAW_HTML_HEADING_TAG = re.compile(
    r"</?h[12](?=[\t\f \r\n/>]|$)",
    re.IGNORECASE,
)
MARKDOWN_LIST_ITEM = re.compile(
    r"^(?P<indent> {0,3})"
    r"(?:(?P<bullet>[*+-])|(?P<ordered>[0-9]{1,9}[.)]))"
    r"(?:(?P<whitespace>[\t ]+)(?P<content>.*)|(?P<empty>))$"
)
MARKDOWN_BLOCKQUOTE = re.compile(r"^ {0,3}>")
MARKDOWN_SETEXT_UNDERLINE = re.compile(r"^ {0,3}(?:=+|-+)[\t ]*$")
MARKDOWN_THEMATIC_BREAK = re.compile(
    r"^ {0,3}(?:(?:\*[\t ]*){3,}|(?:_[\t ]*){3,}|(?:-[\t ]*){3,})$"
)

TOOL_SOURCE_PATHS = {
    "publish.ps1",
    "publish-oss-copy.ps1",
    "scripts/validate-oss-public-copies.py",
}

# These exact source lines define the scanners themselves.  Build them from
# split literals so this validator does not need to exempt its own allowlist.
TOOL_SOURCE_ALLOWED_LINES = {
    "publish.ps1": {
        (
            "$leak = Select-String -LiteralPath $Pub -Pattern "
            "'apiserver\\.zodnext', 'reality-" "opts', '^\\s*uuid" ":', "
            "'^\\s*password" ":', 'obfs-password'"
        ),
    },
    "scripts/validate-oss-public-copies.py": {
        '    re.compile(r"xtls-' 'rprx-vision", re.IGNORECASE),',
    },
}

SENSITIVE_ASSIGNMENT = re.compile(
    r"""
    (?<![A-Za-z0-9_-])
    [\"'`]?(?:uuid|password|obfs-password|short-id|client-fingerprint|reality-opts)[\"'`]?
    [^\S\r\n]*[:=][^\S\r\n]*(?!\s|$)\S+
    """,
    re.IGNORECASE | re.MULTILINE | re.VERBOSE,
)

KNOWN_PRIVATE_MARKERS = (
    re.compile(r"apiserver\.zodnext", re.IGNORECASE),
    re.compile(r"xtls-rprx-vision", re.IGNORECASE),
    re.compile(r"^#__SECRET_(?:START|END)__$", re.MULTILINE),
)

OSS_RULE_ROOT = "https://cclsst.oss-cn-shenzhen.aliyuncs.com/rules/"
FIRST_PARTY_OSS_LIST_URL = re.compile(
    r"https?://cclsst\.oss-cn-shenzhen\.aliyuncs\.com(?::[0-9]+)?/"
    r"[^\s\"'<>]*?\.list",
    re.IGNORECASE,
)
FIRST_PARTY_REPO_LIST_URL = re.compile(
    r"https?://[^\s\"'<>]*andyyippro/rule(?:@|/)[^\s\"'<>]*?"
    r"\.list",
    re.IGNORECASE,
)
FIRST_PARTY_REPO_INI_URL = re.compile(
    r"https?://[^\s\"'<>]*andyyippro/rule(?:@|/)[^\s\"'<>]*?"
    r"\.ini",
    re.IGNORECASE,
)

EXPECTED_RULE_FILES = {
    "nmi": [
        "JapanSites.list",
        "LocalDirect.list",
        "ProxyLiteNew.list",
        "VendorVideoSites.list",
    ],
    "cmi": [
        "HongKongSites.list",
        "JapanSites.list",
        "ProxyLiteNew.list",
        "SingaporeSites.list",
    ],
    "qichiyu": [
        "HongKongSites.list",
        "JapanSites.list",
        "LocalDirect.list",
        "ProxyLiteNew.list",
        "SingaporeSites.list",
        "UpdateHosts.list",
    ],
    "qichiyubeifen": [
        "JapanSites.list",
        "LocalDirect.list",
        "ProxyLiteNew.list",
        "UpdateHosts.list",
    ],
    "bei260317": [
        "JapanSites.list",
        "LocalDirect.list",
        "ProxyLiteNew.list",
        "SingaporeSites.list",
        "UpdateHosts.list",
    ],
    "changelog": [],
}

EXPECTED_RULE_LINES = {
    "nmi": [
        '  ProxyLiteNew / Domain: {<<: *class, url: "' + OSS_RULE_ROOT + 'ProxyLiteNew.list"}',
        '  Japan / Domain: {<<: *class, url: "' + OSS_RULE_ROOT + 'JapanSites.list"}',
        '  VendorVideo / Domain: {<<: *class, url: "' + OSS_RULE_ROOT + 'VendorVideoSites.list"}',
        '  LocalDirect / Domain: {<<: *class, url: "' + OSS_RULE_ROOT + 'LocalDirect.list"}',
    ],
    "cmi": [
        '  HongKong / Domain: {<<: *class, interval: 3600, url: "' + OSS_RULE_ROOT + 'HongKongSites.list"}',
        '  ProxyLiteNew / Domain: {<<: *class, interval: 3600, url: "' + OSS_RULE_ROOT + 'ProxyLiteNew.list"}',
        '  Japan / Domain: {<<: *class, interval: 3600, url: "' + OSS_RULE_ROOT + 'JapanSites.list"}',
        '  Singapore / Domain: {<<: *class, interval: 3600, url: "' + OSS_RULE_ROOT + 'SingaporeSites.list"}',
    ],
    "qichiyu": [
        "ruleset=🆙 更新专用," + OSS_RULE_ROOT + "UpdateHosts.list",
        "ruleset=🇯🇵 日本节点," + OSS_RULE_ROOT + "JapanSites.list",
        "ruleset=🇭🇰 香港节点,clash-classic:" + OSS_RULE_ROOT + "HongKongSites.list",
        "ruleset=🇭🇰🇸🇬 港新节点,clash-classic:" + OSS_RULE_ROOT + "ProxyLiteNew.list",
        "ruleset=🇸🇬 新加坡节点,clash-classic:" + OSS_RULE_ROOT + "SingaporeSites.list",
        "ruleset=🎯 全球直连," + OSS_RULE_ROOT + "LocalDirect.list",
    ],
    "qichiyubeifen": [
        "ruleset=🆙 更新专用," + OSS_RULE_ROOT + "UpdateHosts.list",
        "ruleset=🇯🇵 日本节点," + OSS_RULE_ROOT + "JapanSites.list",
        "ruleset=🇸🇬 新加坡节点," + OSS_RULE_ROOT + "ProxyLiteNew.list",
        "ruleset=🎯 全球直连," + OSS_RULE_ROOT + "LocalDirect.list",
    ],
    "bei260317": [
        "ruleset=🆙 更新专用," + OSS_RULE_ROOT + "UpdateHosts.list",
        "ruleset=🇯🇵 日本节点," + OSS_RULE_ROOT + "JapanSites.list",
        "ruleset=🇭🇰🇸🇬 港新节点,clash-classic:" + OSS_RULE_ROOT + "ProxyLiteNew.list",
        "ruleset=🇸🇬 新加坡节点,clash-classic:" + OSS_RULE_ROOT + "SingaporeSites.list",
        "ruleset=🎯 全球直连," + OSS_RULE_ROOT + "LocalDirect.list",
    ],
}

INI_SELF_LINKS = {
    "qichiyu": "https://raw.githubusercontent.com/andyyippro/rule/main/qichiyu-oss.ini",
    "qichiyubeifen": "https://raw.githubusercontent.com/andyyippro/rule/main/qichiyubeifen-oss.ini",
    "bei260317": "https://raw.githubusercontent.com/andyyippro/rule/main/bei260317-oss.ini",
}

IPXIE_URL = "https://cdn.jsdelivr.net/gh/andyyippro/rule@main/ipxie.yaml"
CHANGELOG_TITLE = "# nmi-oss 独立副本更新日志"
VERSION_NUMBER_PATTERN = r"(?:0|[1-9][0-9]*)"
VERSION_CORE_PATTERN = (
    rf"v{VERSION_NUMBER_PATTERN}\."
    rf"{VERSION_NUMBER_PATTERN}\."
    rf"{VERSION_NUMBER_PATTERN}"
)
NMI_CURRENT_VERSION = re.compile(
    rf"# 当前版本：({VERSION_CORE_PATTERN})"
)
NMI_UPDATED_AT = re.compile(
    r"# 更新时间：([0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2})"
)
NMI_HASH_MARKER = re.compile(
    r"# NMI_OSS_NODES_SHA256: ([0-9a-f]{64})"
)
CHANGELOG_CURRENT_VERSION = re.compile(
    rf"当前版本：({VERSION_CORE_PATTERN})"
)


class PublicCopyValidationError(Exception):
    """Raised without embedding potentially sensitive source content."""


class MarkdownHtmlSemanticCollector(HTMLParser):
    def __init__(self, *, collect_all_data: bool = False) -> None:
        super().__init__(convert_charrefs=True)
        self.attribute_values: list[str] = []
        self.text_parts: list[str] = []
        self.collect_all_data = collect_all_data

    def collect_attributes(self, attrs: list[tuple[str, str | None]]) -> None:
        self.attribute_values.extend(value for _, value in attrs if value is not None)

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        if not HTML_TAG_NAME.fullmatch(tag):
            return
        self.collect_attributes(attrs)

    def handle_startendtag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        if not HTML_TAG_NAME.fullmatch(tag):
            return
        self.collect_attributes(attrs)

    def handle_data(self, data: str) -> None:
        if self.collect_all_data:
            self.text_parts.append(data)

    def semantic_views(self) -> list[str]:
        views = list(self.attribute_values)
        if self.text_parts:
            views.append("".join(self.text_parts))
        return views


def read_bytes(path: str, from_index: bool) -> bytes:
    if from_index:
        process = subprocess.run(
            ["git", "show", f":{path}"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if process.returncode != 0:
            raise PublicCopyValidationError("unable to read staged public copy")
        return process.stdout
    try:
        return Path(path).read_bytes()
    except OSError as exc:
        raise PublicCopyValidationError("unable to read public copy") from exc


def decode_utf8_bytes(data: bytes) -> str:
    if data.startswith(b"\xef\xbb\xbf"):
        raise PublicCopyValidationError("UTF-8 BOM is not allowed")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise PublicCopyValidationError("invalid UTF-8") from exc


def decode_utf8(path: str, from_index: bool) -> str:
    return decode_utf8_bytes(read_bytes(path, from_index))


def read_head_bytes(path: str) -> bytes:
    head = subprocess.run(
        ["git", "rev-parse", "--verify", "HEAD^{commit}"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if head.returncode != 0:
        return b""

    listing = subprocess.run(
        ["git", "ls-tree", "-z", "HEAD", "--", path],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if listing.returncode != 0:
        raise PublicCopyValidationError("unable to inspect committed public text")
    if not listing.stdout:
        return b""

    process = subprocess.run(
        ["git", "cat-file", "blob", f"HEAD:{path}"],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if process.returncode != 0:
        raise PublicCopyValidationError("unable to read committed public text")
    return process.stdout


def load_unique_yaml(text: str):
    try:
        import yaml
        from yaml.constructor import ConstructorError
        from yaml.resolver import BaseResolver
    except ImportError as exc:
        raise PublicCopyValidationError("YAML parser is unavailable") from exc

    class UniqueKeyLoader(yaml.SafeLoader):
        pass

    def construct_unique_mapping(loader, node, deep: bool = False):
        seen: set[object] = set()
        for key_node, _ in node.value:
            if key_node.tag == "tag:yaml.org,2002:merge":
                continue
            key = loader.construct_object(key_node, deep=False)
            try:
                duplicate = key in seen
                seen.add(key)
            except TypeError as exc:
                raise ConstructorError(
                    "while constructing a mapping",
                    node.start_mark,
                    "found an unhashable mapping key",
                    key_node.start_mark,
                ) from exc
            if duplicate:
                raise ConstructorError(
                    "while constructing a mapping",
                    node.start_mark,
                    "found a duplicate mapping key",
                    key_node.start_mark,
                )
        return yaml.SafeLoader.construct_mapping(loader, node, deep=deep)

    UniqueKeyLoader.add_constructor(
        BaseResolver.DEFAULT_MAPPING_TAG,
        construct_unique_mapping,
    )
    try:
        return yaml.load(text, Loader=UniqueKeyLoader)
    except yaml.YAMLError as exc:
        raise PublicCopyValidationError("invalid or duplicate-key YAML") from exc


def collect_public_yaml_strings(value) -> list[str]:
    strings: list[str] = []
    active_containers: set[int] = set()

    def visit(current) -> None:
        if isinstance(current, (dict, list)):
            identity = id(current)
            if identity in active_containers:
                raise PublicCopyValidationError("recursive YAML structure")
            active_containers.add(identity)
            try:
                if isinstance(current, dict):
                    for key, child in current.items():
                        if isinstance(key, str):
                            normalized_key = (
                                unicodedata.normalize("NFKC", key).strip().casefold()
                            )
                            if normalized_key in FORBIDDEN_PUBLIC_KEYS:
                                raise PublicCopyValidationError(
                                    "sensitive YAML mapping key"
                                )
                            strings.append(key)
                        visit(child)
                else:
                    for child in current:
                        visit(child)
            finally:
                active_containers.remove(identity)
        elif isinstance(current, str):
            strings.append(current)

    visit(value)
    return strings


def assert_public_text_safe(text: str) -> None:
    normalized = unicodedata.normalize("NFKC", text)
    if SENSITIVE_ASSIGNMENT.search(normalized):
        raise PublicCopyValidationError("sensitive assignment")
    if any(pattern.search(normalized) for pattern in KNOWN_PRIVATE_MARKERS):
        raise PublicCopyValidationError("known private marker")


def is_backslash_escaped(text: str, index: int) -> bool:
    backslashes = 0
    index -= 1
    while index >= 0 and text[index] == "\\":
        backslashes += 1
        index -= 1
    return backslashes % 2 == 1


def find_markdown_html_token_end(text: str, start: int) -> int | None:
    if text.startswith("<!-->", start):
        return start + len("<!-->")
    if text.startswith("<!--->", start):
        return start + len("<!--->")
    if text.startswith("<!--", start):
        end = text.find("-->", start + len("<!--"))
        if end < 0:
            return None
        comment = text[start + len("<!--"):end]
        if (
            comment.startswith(">")
            or comment.startswith("->")
            or comment.endswith("-")
            or "--" in comment
        ):
            return None
        return end + len("-->")
    if text.startswith("<![CDATA[", start):
        end = text.find("]]>", start + len("<![CDATA["))
        return None if end < 0 else end + len("]]>")
    if text.startswith("<?", start):
        end = text.find("?>", start + len("<?"))
        return None if end < 0 else end + len("?>")

    for pattern in (HTML_DECLARATION, HTML_OPEN_TAG, HTML_CLOSING_TAG):
        match = pattern.match(text, start)
        if match is not None:
            return match.end()
    return None


def mark_range(flags: list[bool], start: int, end: int) -> None:
    for index in range(start, end):
        flags[index] = True


def mask_flagged_text(text: str, flags: list[bool]) -> str:
    return "".join(
        character if not flags[index] or character in "\r\n" else " "
        for index, character in enumerate(text)
    )


def strip_markdown_blockquote_prefixes_with_depth(line: str) -> tuple[str, int]:
    depth = 0
    while True:
        match = re.match(r"^ {0,3}>[\t ]?", line)
        if match is None:
            return line, depth
        line = line[match.end():]
        depth += 1


def strip_markdown_blockquote_prefixes(line: str) -> str:
    return strip_markdown_blockquote_prefixes_with_depth(line)[0]


def indentation_columns(text: str) -> int:
    column = 0
    for character in text:
        if character == "\t":
            column += 4 - column % 4
        else:
            column += 1
    return column


def strip_indent_columns(line: str, required_columns: int) -> str | None:
    if required_columns == 0:
        return line
    column = 0
    index = 0
    while index < len(line) and column < required_columns:
        character = line[index]
        if character == " ":
            column += 1
        elif character == "\t":
            column += 4 - column % 4
        else:
            return None
        index += 1
    return line[index:] if column >= required_columns else None


def markdown_list_item_can_interrupt(line: str) -> bool:
    match = MARKDOWN_LIST_ITEM.fullmatch(line)
    if match is None or MARKDOWN_THEMATIC_BREAK.fullmatch(line):
        return False
    if not (match.group("content") or "").strip():
        return False
    ordered = match.group("ordered")
    return ordered is None or int(ordered[:-1]) == 1


def markdown_list_marker_kind(match: re.Match[str]) -> str:
    bullet = match.group("bullet")
    return bullet if bullet is not None else match.group("ordered")[-1]


def strip_markdown_container_prefixes(
    line: str,
    *,
    paragraph_continuation: bool = False,
) -> tuple[str, int, int, tuple[tuple[int, str], ...]]:
    line, blockquote_depth = strip_markdown_blockquote_prefixes_with_depth(line)
    continuation_indent = 0
    list_contexts: list[tuple[int, str]] = []
    while True:
        match = MARKDOWN_LIST_ITEM.fullmatch(line)
        if match is None or MARKDOWN_THEMATIC_BREAK.fullmatch(line):
            return line, continuation_indent, blockquote_depth, tuple(list_contexts)
        if paragraph_continuation and not markdown_list_item_can_interrupt(line):
            return line, continuation_indent, blockquote_depth, tuple(list_contexts)

        marker = match.group("indent") + (
            match.group("bullet") or match.group("ordered")
        )
        whitespace = match.group("whitespace") or ""
        if not whitespace:
            continuation_indent += indentation_columns(marker) + 1
            list_contexts.append(
                (continuation_indent, markdown_list_marker_kind(match))
            )
            return "", continuation_indent, blockquote_depth, tuple(list_contexts)
        whitespace_columns = indentation_columns(whitespace)
        consumed_whitespace = whitespace if whitespace_columns <= 4 else whitespace[:1]
        consumed = marker + consumed_whitespace
        continuation_indent += indentation_columns(consumed)
        list_contexts.append((continuation_indent, markdown_list_marker_kind(match)))
        line, nested_depth = strip_markdown_blockquote_prefixes_with_depth(
            line[len(consumed):]
        )
        blockquote_depth += nested_depth
        paragraph_continuation = False


def markdown_html_block_start(
    line: str,
    in_paragraph: bool,
) -> tuple[str, re.Pattern[str] | None] | None:
    stripped = line.lstrip(" ")
    if len(line) - len(stripped) > 3:
        return None

    raw_match = HTML_BLOCK_RAW_START.match(line)
    if raw_match is not None:
        tag = re.escape(raw_match.group(1))
        return "terminator", re.compile(rf"</{tag}[\t ]*>", re.IGNORECASE)
    if stripped.startswith("<!--"):
        return "terminator", re.compile(r"-->")
    if stripped.startswith("<?"):
        return "terminator", re.compile(r"\?>")
    if stripped.startswith("<![CDATA["):
        return "terminator", re.compile(r"\]\]>")
    if re.match(r"<![A-Z]", stripped):
        return "terminator", re.compile(r">")
    if HTML_BLOCK_TAG_START.match(line):
        return "blank", None
    if in_paragraph:
        return None

    token_start = len(line) - len(stripped)
    token_end = find_markdown_html_token_end(line, token_start)
    if token_end is not None and not line[token_end:].strip():
        return "blank", None
    return None


def markdown_line_interrupts_paragraph(line: str) -> bool:
    return bool(
        MARKDOWN_ATX_HEADING.match(line)
        or markdown_list_item_can_interrupt(line)
        or MARKDOWN_BLOCKQUOTE.match(line)
        or MARKDOWN_THEMATIC_BREAK.fullmatch(line)
        or MARKDOWN_FENCE_OPEN.fullmatch(line)
        or markdown_html_block_start(line, True) is not None
    )


def classify_markdown_blocks(
    text: str,
) -> tuple[
    list[bool],
    list[bool],
    list[str],
    list[tuple[tuple[int, str], ...]],
    list[int],
    dict[int, tuple[str, int, tuple[tuple[int, str], ...], bool]],
]:
    code_flags = [False] * len(text)
    raw_html_flags = [False] * len(text)
    list_contexts_by_position: list[tuple[tuple[int, str], ...]] = [()] * len(text)
    quote_contexts_by_position = [0] * len(text)
    line_contexts: dict[
        int,
        tuple[str, int, tuple[tuple[int, str], ...], bool],
    ] = {}
    fence: tuple[str, int, int, int] | None = None
    fence_info_strings: list[str] = []
    html_block: tuple[str, re.Pattern[str] | None, int, int] | None = None
    in_indented_code = False
    in_paragraph = False
    paragraph_quote_depth = 0
    active_list_contexts: list[tuple[int, str]] = []
    offset = 0

    for line_with_end in text.splitlines(keepends=True):
        line = line_with_end.rstrip("\r\n")
        quote_stripped_line, leading_quote_depth = (
            strip_markdown_blockquote_prefixes_with_depth(line)
        )
        list_base_line = quote_stripped_line
        inherited_indent = 0
        inherited_list_contexts: list[tuple[int, str]] = []
        sibling_list_item = False
        if active_list_contexts:
            previous_list_contexts = list(active_list_contexts)
            for level_index in range(len(active_list_contexts) - 1, -1, -1):
                candidate_indent = active_list_contexts[level_index][0]
                continued_line = strip_indent_columns(
                    quote_stripped_line,
                    candidate_indent,
                )
                if continued_line is not None:
                    list_base_line = continued_line
                    inherited_indent = candidate_indent
                    continued_match = MARKDOWN_LIST_ITEM.fullmatch(continued_line)
                    sibling_list_item = bool(
                        continued_match is not None
                        and level_index + 1 < len(previous_list_contexts)
                        and markdown_list_marker_kind(continued_match)
                        == previous_list_contexts[level_index + 1][1]
                    )
                    lazy_deeper_continuation = bool(
                        level_index + 1 < len(previous_list_contexts)
                        and in_paragraph
                        and not sibling_list_item
                        and not markdown_line_interrupts_paragraph(continued_line)
                    )
                    inherited_list_contexts = (
                        previous_list_contexts
                        if lazy_deeper_continuation
                        else previous_list_contexts[:level_index + 1]
                    )
                    active_list_contexts = list(inherited_list_contexts)
                    break
            else:
                continued_line = None

            if continued_line is None and not line.strip():
                list_base_line = ""
                inherited_indent = active_list_contexts[-1][0]
                inherited_list_contexts = list(active_list_contexts)
            elif continued_line is None:
                sibling_match = MARKDOWN_LIST_ITEM.fullmatch(quote_stripped_line)
                sibling_list_item = bool(
                    sibling_match is not None
                    and markdown_list_marker_kind(sibling_match)
                    == active_list_contexts[0][1]
                )
                if sibling_list_item or not (
                    in_paragraph
                    and not markdown_line_interrupts_paragraph(quote_stripped_line)
                ):
                    active_list_contexts = []
                else:
                    inherited_list_contexts = list(active_list_contexts)
        (
            block_line,
            nested_indent,
            nested_quote_depth,
            nested_list_contexts,
        ) = (
            strip_markdown_container_prefixes(
                list_base_line,
                paragraph_continuation=(in_paragraph and not sibling_list_item),
            )
        )
        quote_depth = leading_quote_depth + nested_quote_depth
        continuation_indent = inherited_indent + nested_indent
        if nested_list_contexts:
            active_list_contexts = inherited_list_contexts + [
                (inherited_indent + relative_indent, marker_kind)
                for relative_indent, marker_kind in nested_list_contexts
            ]
        elif inherited_list_contexts:
            active_list_contexts = list(inherited_list_contexts)
        line_end = offset + len(line_with_end)
        blank = not block_line.strip()
        line_list_contexts = tuple(active_list_contexts)
        starts_list_item = bool(nested_list_contexts)
        interrupts_existing_paragraph = (
            starts_list_item or markdown_line_interrupts_paragraph(block_line)
        )
        logical_quote_depth = quote_depth
        if (
            in_paragraph
            and paragraph_quote_depth > quote_depth
            and not blank
            and not interrupts_existing_paragraph
        ):
            logical_quote_depth = paragraph_quote_depth
        line_contexts[offset] = (
            block_line,
            logical_quote_depth,
            line_list_contexts,
            starts_list_item,
        )
        for position in range(offset, line_end):
            list_contexts_by_position[position] = line_list_contexts
            quote_contexts_by_position[position] = logical_quote_depth

        if fence is not None:
            (
                fence_character,
                fence_length,
                fence_container_indent,
                fence_quote_depth,
            ) = fence
            closing_line = strip_indent_columns(
                quote_stripped_line,
                fence_container_indent,
            )
            quote_container_ended = quote_depth < fence_quote_depth
            list_container_ended = (
                fence_container_indent > 0
                and closing_line is None
                and bool(line.strip())
            )
            if quote_container_ended or list_container_ended:
                fence = None
                in_paragraph = False
                paragraph_quote_depth = 0
            else:
                mark_range(code_flags, offset, line_end)
                closing = None
                if closing_line is not None:
                    closing = re.fullmatch(
                        rf" {{0,3}}{re.escape(fence_character)}{{{fence_length},}}[\t ]*",
                        closing_line,
                    )
                if closing is not None:
                    fence = None
                    in_paragraph = False
                    paragraph_quote_depth = 0
                offset = line_end
                continue

        if html_block is not None:
            (
                mode,
                terminator,
                html_container_indent,
                html_quote_depth,
            ) = html_block
            html_line = strip_indent_columns(
                quote_stripped_line,
                html_container_indent,
            )
            quote_container_ended = quote_depth < html_quote_depth
            list_container_ended = (
                html_container_indent > 0
                and html_line is None
                and bool(line.strip())
            )
            if quote_container_ended or list_container_ended:
                html_block = None
                in_paragraph = False
                paragraph_quote_depth = 0
            elif mode == "blank" and blank:
                html_block = None
                in_paragraph = False
                paragraph_quote_depth = 0
            else:
                mark_range(raw_html_flags, offset, line_end)
                if mode == "terminator" and terminator is not None and terminator.search(line):
                    html_block = None
                    in_paragraph = False
                    paragraph_quote_depth = 0
                offset = line_end
                continue

        if in_indented_code:
            if blank or block_line.startswith("    ") or block_line.startswith("\t"):
                mark_range(code_flags, offset, line_end)
                offset = line_end
                continue
            in_indented_code = False
            in_paragraph = False
            paragraph_quote_depth = 0

        fence_match = MARKDOWN_FENCE_OPEN.fullmatch(block_line)
        if fence_match is not None:
            fence_run, info = fence_match.groups()
            if fence_run[0] == "~" or "`" not in info:
                mark_range(code_flags, offset, line_end)
                fence = (
                    fence_run[0],
                    len(fence_run),
                    continuation_indent,
                    quote_depth,
                )
                if info.strip("\t "):
                    fence_info_strings.append(info.strip("\t "))
                in_paragraph = False
                paragraph_quote_depth = 0
                offset = line_end
                continue

        block_start = markdown_html_block_start(block_line, in_paragraph)
        if block_start is not None:
            mark_range(raw_html_flags, offset, line_end)
            mode, terminator = block_start
            if mode == "terminator" and terminator is not None and terminator.search(line):
                html_block = None
                in_paragraph = False
                paragraph_quote_depth = 0
            else:
                html_block = (
                    mode,
                    terminator,
                    continuation_indent,
                    quote_depth,
                )
                in_paragraph = False
                paragraph_quote_depth = 0
            offset = line_end
            continue

        if not in_paragraph and (
            block_line.startswith("    ") or block_line.startswith("\t")
        ):
            mark_range(code_flags, offset, line_end)
            in_indented_code = True
            in_paragraph = False
            paragraph_quote_depth = 0
            offset = line_end
            continue

        if (
            blank
            or MARKDOWN_ATX_HEADING.match(block_line)
            or MARKDOWN_SETEXT_UNDERLINE.fullmatch(block_line)
            or MARKDOWN_THEMATIC_BREAK.fullmatch(block_line)
        ):
            in_paragraph = False
            paragraph_quote_depth = 0
        else:
            in_paragraph = True
            paragraph_quote_depth = logical_quote_depth
        offset = line_end

    return (
        code_flags,
        raw_html_flags,
        fence_info_strings,
        list_contexts_by_position,
        quote_contexts_by_position,
        line_contexts,
    )


def mask_markdown_code_contexts(
    text: str,
) -> tuple[str, list[bool], list[str]]:
    (
        code_flags,
        raw_html_flags,
        fence_info_strings,
        list_contexts_by_position,
        quote_contexts_by_position,
        line_contexts,
    ) = classify_markdown_blocks(text)
    masked = mask_flagged_text(text, code_flags)
    characters = list(masked)
    index = 0

    def inline_block_limit(start: int, opener_start: int) -> int:
        opener_line_start = max(
            masked.rfind("\n", 0, opener_start),
            masked.rfind("\r", 0, opener_start),
        ) + 1
        opener_line_end_match = re.search(r"\r\n|\n|\r", masked[opener_start:])
        opener_line_end = (
            len(masked)
            if opener_line_end_match is None
            else opener_start + opener_line_end_match.start()
        )
        opener_block_line = line_contexts[opener_line_start][0]
        if MARKDOWN_ATX_HEADING.match(opener_block_line):
            return opener_line_end
        opener_quote_depth = quote_contexts_by_position[opener_start]
        opener_list_contexts = list_contexts_by_position[opener_start]

        line_end = re.search(r"\r\n|\n|\r", masked[start:])
        while line_end is not None:
            boundary = start + line_end.start()
            next_start = start + line_end.end()
            next_end_match = re.search(r"\r\n|\n|\r", masked[next_start:])
            next_end = (
                len(masked)
                if next_end_match is None
                else next_start + next_end_match.start()
            )
            next_line = masked[next_start:next_end]
            quote_stripped_next_line = strip_markdown_blockquote_prefixes(next_line)
            if opener_list_contexts:
                matched_list_level: int | None = None
                continued_list_line: str | None = None
                for level_index in range(len(opener_list_contexts) - 1, -1, -1):
                    continued_list_line = strip_indent_columns(
                        quote_stripped_next_line,
                        opener_list_contexts[level_index][0],
                    )
                    if continued_list_line is not None:
                        matched_list_level = level_index
                        break
                list_boundary_line = (
                    quote_stripped_next_line
                    if continued_list_line is None
                    else continued_list_line
                )
                list_boundary_match = MARKDOWN_LIST_ITEM.fullmatch(
                    list_boundary_line
                )
                if list_boundary_match is not None:
                    existing_sibling_kind = (
                        opener_list_contexts[0][1]
                        if matched_list_level is None
                        else (
                            opener_list_contexts[matched_list_level + 1][1]
                            if matched_list_level + 1 < len(opener_list_contexts)
                            else None
                        )
                    )
                    if (
                        markdown_list_item_can_interrupt(list_boundary_line)
                        or markdown_list_marker_kind(list_boundary_match)
                        == existing_sibling_kind
                    ):
                        return next_start
            candidate_line = next_line
            next_quote_depth = 0
            if opener_quote_depth:
                candidate_line, next_quote_depth = (
                    strip_markdown_blockquote_prefixes_with_depth(next_line)
                )
                if opener_list_contexts:
                    for list_indent, _ in reversed(opener_list_contexts):
                        continued_line = strip_indent_columns(
                            candidate_line,
                            list_indent,
                        )
                        if continued_line is not None:
                            candidate_line, nested_quote_depth = (
                                strip_markdown_blockquote_prefixes_with_depth(
                                    continued_line
                                )
                            )
                            next_quote_depth += nested_quote_depth
                            break
                if next_quote_depth > opener_quote_depth:
                    return next_start

            if not candidate_line.strip():
                return boundary
            if (
                MARKDOWN_ATX_HEADING.match(candidate_line)
                or markdown_list_item_can_interrupt(candidate_line)
                or (
                    opener_quote_depth == 0
                    and MARKDOWN_BLOCKQUOTE.match(candidate_line)
                )
                or MARKDOWN_SETEXT_UNDERLINE.fullmatch(candidate_line)
                or MARKDOWN_THEMATIC_BREAK.fullmatch(candidate_line)
                or MARKDOWN_FENCE_OPEN.fullmatch(candidate_line)
                or markdown_html_block_start(candidate_line, False) is not None
            ):
                return next_start
            if next_end_match is None:
                return len(masked)
            start = next_start
            line_end = next_end_match
        return len(masked)

    while index < len(masked):
        if raw_html_flags[index]:
            index += 1
            continue
        if masked[index] == "<" and not is_backslash_escaped(masked, index):
            token_end = find_markdown_html_token_end(masked, index)
            if token_end is not None:
                index = token_end
                continue
        if masked[index] != "`" or is_backslash_escaped(masked, index):
            index += 1
            continue

        opener_end = index + 1
        while opener_end < len(masked) and masked[opener_end] == "`":
            opener_end += 1
        opener_length = opener_end - index
        search = opener_end
        search_limit = inline_block_limit(opener_end, index)
        closing_end: int | None = None
        while search < search_limit and not raw_html_flags[search]:
            next_tick = masked.find("`", search, search_limit)
            if next_tick < 0 or raw_html_flags[next_tick]:
                break
            if any(raw_html_flags[search:next_tick]):
                break
            run_end = next_tick + 1
            while run_end < len(masked) and masked[run_end] == "`":
                run_end += 1
            if (
                run_end - next_tick == opener_length
                and not is_backslash_escaped(masked, next_tick)
            ):
                closing_end = run_end
                break
            search = run_end
        if closing_end is None:
            index = opener_end
            continue
        mark_range(code_flags, index, closing_end)
        for position in range(index, closing_end):
            if characters[position] not in "\r\n":
                characters[position] = " "
        index = closing_end

    return "".join(characters), raw_html_flags, fence_info_strings


def remove_markdown_html_tokens(text: str) -> str:
    parts: list[str] = []
    index = 0
    while index < len(text):
        if text[index] != "<" or is_backslash_escaped(text, index):
            parts.append(text[index])
            index += 1
            continue
        token_end = find_markdown_html_token_end(text, index)
        if token_end is None:
            parts.append(text[index])
            index += 1
            continue
        index = token_end
    return "".join(parts)


def mask_escaped_markdown_html_tokens(text: str) -> str:
    characters = list(text)
    for index, character in enumerate(text):
        if character != "<" or not is_backslash_escaped(text, index):
            continue
        if find_markdown_html_token_end(text, index) is not None:
            characters[index] = " "
    return "".join(characters)


def flagged_segments(text: str, flags: list[bool]) -> list[str]:
    segments: list[str] = []
    start: int | None = None
    for index, flagged in enumerate(flags):
        if flagged and start is None:
            start = index
        elif not flagged and start is not None:
            segments.append(text[start:index])
            start = None
    if start is not None:
        segments.append(text[start:])
    return segments


def normalize_commonmark_escapes_and_entities(text: str) -> str:
    escaped_parts: list[str] = []
    index = 0
    while index < len(text):
        if (
            text[index] == "\\"
            and index + 1 < len(text)
            and text[index + 1] in string.punctuation
        ):
            escaped_parts.append(f"&#{ord(text[index + 1])};")
            index += 2
        else:
            escaped_parts.append(text[index])
            index += 1
    escaped_text = "".join(escaped_parts)
    return MARKDOWN_ENTITY_REFERENCE.sub(
        lambda match: html.unescape(match.group(0)),
        escaped_text,
    )


def normalize_markdown_scan_text(text: str) -> str:
    return normalize_commonmark_escapes_and_entities(
        remove_markdown_html_tokens(text)
    )


def append_unique_view(views: list[str], view: str) -> None:
    if view and view not in views:
        views.append(view)


def split_markdown_rendered_units(text: str) -> list[str]:
    units: list[str] = []
    current: list[str] = []
    current_quote_depth: int | None = None
    current_list_contexts: tuple[tuple[int, str], ...] | None = None
    line_contexts = classify_markdown_blocks(text)[-1]

    def flush() -> None:
        nonlocal current_quote_depth, current_list_contexts
        if current:
            units.append("\n".join(current))
            current.clear()
        current_quote_depth = None
        current_list_contexts = None

    offset = 0
    for line_with_end in text.splitlines(keepends=True):
        line = line_with_end.rstrip("\r\n")
        (
            block_line,
            quote_depth,
            list_contexts,
            starts_list_item,
        ) = line_contexts[offset]
        if not block_line.strip():
            flush()
            offset += len(line_with_end)
            continue
        if current and (
            quote_depth != current_quote_depth
            or list_contexts != current_list_contexts
        ):
            flush()
        if MARKDOWN_SETEXT_UNDERLINE.fullmatch(block_line) and current:
            current.append(line)
            flush()
            offset += len(line_with_end)
            continue
        if (
            MARKDOWN_ATX_HEADING.match(block_line)
            or MARKDOWN_THEMATIC_BREAK.fullmatch(block_line)
        ):
            flush()
            units.append(line)
            offset += len(line_with_end)
            continue
        if starts_list_item:
            flush()
        current.append(line)
        current_quote_depth = quote_depth
        current_list_contexts = list_contexts
        offset += len(line_with_end)
    flush()
    return units


def append_rendered_whitespace_views(
    views: list[str],
    text: str,
    *,
    split_markdown_blocks: bool = False,
) -> None:
    append_unique_view(views, text)
    line_normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    units = (
        split_markdown_rendered_units(line_normalized)
        if split_markdown_blocks
        else [line_normalized]
    )
    for unit in units:
        collapsed = re.sub(r"\s+", " ", unit).strip()
        append_unique_view(views, collapsed)


def append_markdown_rendered_whitespace_views(
    views: list[str],
    markdown_source: str,
) -> None:
    # CommonMark determines block structure before resolving backslash escapes,
    # character references, or inline HTML.  Splitting normalized text would
    # let those inline constructs manufacture a heading/list/quote boundary.
    append_unique_view(views, normalize_markdown_scan_text(markdown_source))
    line_normalized = markdown_source.replace("\r\n", "\n").replace("\r", "\n")
    for source_unit in split_markdown_rendered_units(line_normalized):
        normalized_unit = normalize_markdown_scan_text(source_unit)
        collapsed = re.sub(r"\s+", " ", normalized_unit).strip()
        append_unique_view(views, collapsed)


def collect_markdown_semantic_views(text: str) -> list[str]:
    code_masked, raw_html_flags, fence_info_strings = mask_markdown_code_contexts(text)
    markdown_source = mask_flagged_text(code_masked, raw_html_flags)
    views: list[str] = []
    append_markdown_rendered_whitespace_views(views, markdown_source)
    for info_string in fence_info_strings:
        append_rendered_whitespace_views(
            views,
            normalize_commonmark_escapes_and_entities(info_string),
        )

    inline_html_source = mask_escaped_markdown_html_tokens(markdown_source)
    parser = MarkdownHtmlSemanticCollector()
    try:
        parser.feed(inline_html_source)
        parser.close()
    except Exception as exc:
        raise PublicCopyValidationError("invalid Markdown HTML") from exc
    for view in parser.semantic_views():
        append_rendered_whitespace_views(views, view)

    for raw_html_block in flagged_segments(code_masked, raw_html_flags):
        parser = MarkdownHtmlSemanticCollector(collect_all_data=True)
        try:
            parser.feed(raw_html_block)
            parser.close()
        except Exception as exc:
            raise PublicCopyValidationError("invalid Markdown HTML") from exc
        for view in parser.semantic_views():
            append_rendered_whitespace_views(views, view)
    return views


def assert_public_markdown_safe(text: str) -> list[str]:
    views = collect_markdown_semantic_views(text)
    for view in views:
        assert_public_text_safe(view)
    return views


def normalize_url_scan_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text)
    for _ in range(URL_DECODE_MAX_PASSES):
        decoded = unicodedata.normalize("NFKC", unquote(normalized))
        if decoded == normalized:
            return normalized
        normalized = decoded
    raise PublicCopyValidationError("URL encoding nesting exceeds validation limit")


def is_yaml_path(path: str) -> bool:
    return Path(path).suffix.lower() in {".yaml", ".yml"}


def validate_yaml_only(path: str, from_index: bool) -> None:
    text = decode_utf8(path, from_index)
    load_unique_yaml(text)


def validate_public(path: str, from_index: bool) -> tuple[str, list[str]]:
    text = decode_utf8(path, from_index)
    assert_public_text_safe(text)
    semantic_views: list[str] = []
    if is_yaml_path(path):
        semantic_text = "\n".join(
            collect_public_yaml_strings(load_unique_yaml(text))
        )
        assert_public_text_safe(semantic_text)
        semantic_views.append(semantic_text)
    elif Path(path).suffix.lower() == ".md":
        semantic_views = assert_public_markdown_safe(text)
    return text, semantic_views


def validate_staged_public_text(path: str) -> None:
    text = decode_utf8(path, True)
    if Path(path).suffix.lower() != ".md":
        assert_public_text_safe(text)
        return

    committed_text = decode_utf8_bytes(read_head_bytes(path))
    committed_lines = committed_text.splitlines(keepends=True)
    staged_lines = text.splitlines(keepends=True)
    matcher = difflib.SequenceMatcher(
        None,
        committed_lines,
        staged_lines,
        autojunk=False,
    )
    for tag, _, _, staged_start, staged_end in matcher.get_opcodes():
        if tag in {"insert", "replace"}:
            assert_public_text_safe("".join(staged_lines[staged_start:staged_end]))

    # Full-document semantics retain unchanged fence and HTML context, while
    # the raw scan above applies only to newly public literal source lines.
    assert_public_markdown_safe(text)


def sanitize_tool_source_text(path: str, text: str) -> str:
    allowed_lines = TOOL_SOURCE_ALLOWED_LINES.get(path, set())
    sanitized_lines: list[str] = []
    for line_with_end in text.splitlines(keepends=True):
        line = line_with_end.rstrip("\r\n")
        if line in allowed_lines:
            line_ending = line_with_end[len(line):]
            sanitized_lines.append(line_ending)
        else:
            sanitized_lines.append(line_with_end)
    return "".join(sanitized_lines)


def validate_staged_tool_source(path: str) -> None:
    text = decode_utf8(path, True)
    assert_public_text_safe(sanitize_tool_source_text(path, text))


def validate_index_public_changes() -> None:
    process = subprocess.run(
        [
            "git",
            "diff",
            "--cached",
            "--no-renames",
            "--name-only",
            "-z",
            "--diff-filter=ACMRT",
            "--",
            ".",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if process.returncode != 0:
        raise PublicCopyValidationError("unable to enumerate staged public text")
    for encoded_path in process.stdout.split(b"\0"):
        if not encoded_path:
            continue
        try:
            path = encoded_path.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise PublicCopyValidationError("invalid staged path encoding") from exc
        if path in TOOL_SOURCE_PATHS:
            validate_staged_tool_source(path)
        else:
            validate_staged_public_text(path)


def require_exact_line(text: str, expected: str) -> None:
    if sum(line == expected for line in text.splitlines()) != 1:
        raise PublicCopyValidationError("required public-copy line is missing or duplicated")


def top_level_markdown_block_lines(text: str) -> list[tuple[int, str, str]]:
    (
        code_flags,
        raw_html_flags,
        _,
        _,
        _,
        line_contexts,
    ) = classify_markdown_blocks(text)
    lines: list[tuple[int, str, str]] = []
    offset = 0
    for line_with_end in text.splitlines(keepends=True):
        line = line_with_end.rstrip("\r\n")
        block_line, quote_depth, list_contexts, starts_list_item = line_contexts[
            offset
        ]
        visible_top_level = bool(
            quote_depth == 0
            and not list_contexts
            and not starts_list_item
            and not code_flags[offset]
            and not raw_html_flags[offset]
        )
        if visible_top_level:
            lines.append((offset, line, block_line))
        offset += len(line_with_end)
    return lines


def top_level_markdown_lines(text: str) -> list[tuple[int, str, str]]:
    code_masked, _, _ = mask_markdown_code_contexts(text)
    return [
        (offset, line, block_line)
        for offset, line, block_line in top_level_markdown_block_lines(text)
        if code_masked[offset : offset + len(line)] == line
    ]


def canonical_atx_heading(line: str) -> tuple[int, str] | None:
    source_match = re.fullmatch(
        r" {0,3}(#{1,6})(?:[\t ]+(.*)|[\t ]*)",
        line.rstrip("\r\n"),
    )
    if source_match is None:
        return None
    marker, content = source_match.groups()
    content = "" if content is None else content
    closing_match = re.search(r"[\t ]+(#+)[\t ]*$", content)
    if closing_match is not None and not is_backslash_escaped(
        content,
        closing_match.start(1),
    ):
        content = content[: closing_match.start()]
    normalized = normalize_commonmark_escapes_and_entities(
        remove_markdown_html_tokens(content)
    )
    return len(marker), re.sub(r"\s+", " ", normalized).strip()


def top_level_atx_headings(text: str) -> list[tuple[int, str, str]]:
    headings: list[tuple[int, str, str]] = []
    for _, _, block_line in top_level_markdown_block_lines(text):
        heading = canonical_atx_heading(block_line)
        if heading is not None:
            headings.append((heading[0], heading[1], block_line))
    return headings


def assert_changelog_uses_only_atx_headings(text: str) -> None:
    if any(
        (
            ord(character) < 0x20
            and character not in "\t\r\n"
        )
        or 0x7F <= ord(character) <= 0x9F
        or character in "\u2028\u2029"
        for character in text
    ):
        raise PublicCopyValidationError(
            "copy changelog contains an unsupported control or line separator"
        )
    (
        code_flags,
        raw_html_flags,
        _,
        _,
        _,
        line_contexts,
    ) = classify_markdown_blocks(text)
    previous_paragraph_line = False
    offset = 0
    for line_with_end in text.splitlines(keepends=True):
        block_line, quote_depth, list_contexts, starts_list_item = line_contexts[
            offset
        ]
        visible_top_level = bool(
            quote_depth == 0
            and not list_contexts
            and not starts_list_item
            and not code_flags[offset]
            and not raw_html_flags[offset]
        )
        if (
            visible_top_level
            and previous_paragraph_line
            and MARKDOWN_SETEXT_UNDERLINE.fullmatch(block_line)
        ):
            raise PublicCopyValidationError(
                "copy changelog must not use Setext headings"
            )
        previous_paragraph_line = bool(
            visible_top_level
            and block_line.strip()
            and not MARKDOWN_ATX_HEADING.match(block_line)
            and not MARKDOWN_SETEXT_UNDERLINE.fullmatch(block_line)
            and not MARKDOWN_THEMATIC_BREAK.fullmatch(block_line)
            and not MARKDOWN_FENCE_OPEN.fullmatch(block_line)
            and markdown_html_block_start(block_line, False) is None
        )
        offset += len(line_with_end)

    code_masked, raw_html_flags, _ = mask_markdown_code_contexts(text)
    if any(
        RAW_HTML_HEADING_TAG.search(raw_html_block)
        for raw_html_block in flagged_segments(code_masked, raw_html_flags)
    ):
        raise PublicCopyValidationError(
            "copy changelog must not use HTML headings"
        )
    index = 0
    while index < len(code_masked):
        token_start = code_masked.find("<", index)
        if token_start < 0:
            break
        if not raw_html_flags[token_start] and is_backslash_escaped(
            code_masked,
            token_start,
        ):
            index = token_start + 1
            continue
        token_end = find_markdown_html_token_end(code_masked, token_start)
        if token_end is None:
            index = token_start + 1
            continue
        tag_match = re.match(
            r"</?([A-Za-z][A-Za-z0-9-]*)",
            code_masked[token_start:token_end],
        )
        if tag_match is not None and tag_match.group(1).casefold() in {"h1", "h2"}:
            raise PublicCopyValidationError(
                "copy changelog must not use HTML headings"
            )
        index = token_end


def require_top_level_markdown_line(
    text: str,
    expected: str,
    *,
    atx_heading: bool = False,
    first_line: bool = False,
) -> None:
    valid_offsets = []
    for offset, line, block_line in top_level_markdown_lines(text):
        if line == expected:
            if block_line == expected and (
                not atx_heading or MARKDOWN_ATX_HEADING.match(block_line)
            ):
                valid_offsets.append(offset)

    if len(valid_offsets) != 1:
        raise PublicCopyValidationError("required Markdown line is not top-level content")
    if first_line and valid_offsets[0] != 0:
        raise PublicCopyValidationError("required Markdown title is not the first line")


def validate_copy_set(paths: list[str], from_index: bool) -> None:
    names = ("nmi", "cmi", "qichiyu", "qichiyubeifen", "bei260317", "changelog")
    if len(paths) != len(names):
        raise PublicCopyValidationError("incomplete public-copy set")

    texts: dict[str, str] = {}
    semantic_url_texts: dict[str, list[str]] = {}
    for name, path in zip(names, paths, strict=True):
        text, semantic_views = validate_public(path, from_index)
        texts[name] = text
        semantic_url_texts[name] = [
            normalize_url_scan_text(view) for view in semantic_views
        ]
    if Path(paths[5]).suffix.lower() != ".md":
        raise PublicCopyValidationError("copy changelog must use .md suffix")
    require_exact_line(texts["changelog"], CHANGELOG_TITLE)
    require_top_level_markdown_line(
        texts["changelog"],
        CHANGELOG_TITLE,
        atx_heading=True,
        first_line=True,
    )
    assert_changelog_uses_only_atx_headings(texts["changelog"])
    expected_title_heading = canonical_atx_heading(CHANGELOG_TITLE)
    changelog_headings = top_level_atx_headings(texts["changelog"])
    if (
        expected_title_heading is None
        or sum(
            (level, heading_text) == expected_title_heading
            for level, heading_text, _ in changelog_headings
        )
        != 1
        or sum(level == 1 for level, _, _ in changelog_headings) != 1
    ):
        raise PublicCopyValidationError("copy changelog title is missing or duplicated")

    nmi_lines = texts["nmi"].splitlines()
    nmi_version_indices = [
        index
        for index, line in enumerate(nmi_lines)
        if line.lstrip("\t ").startswith("# 当前版本：")
    ]
    nmi_timestamp_indices = [
        index
        for index, line in enumerate(nmi_lines)
        if line.lstrip("\t ").startswith("# 更新时间：")
    ]
    nmi_hash_indices = [
        index
        for index, line in enumerate(nmi_lines)
        if line.lstrip("\t ").startswith("# NMI_OSS_NODES_SHA256:")
    ]
    placeholder = "#__NODES_OSS__"
    if texts["nmi"].count(placeholder) != 1:
        raise PublicCopyValidationError("public nmi placeholder token mismatch")
    require_exact_line(texts["nmi"], placeholder)
    placeholder_index = nmi_lines.index(placeholder)
    if (
        len(nmi_version_indices) != 1
        or len(nmi_timestamp_indices) != 1
        or len(nmi_hash_indices) != 1
    ):
        raise PublicCopyValidationError("public nmi version metadata mismatch")
    version_index = nmi_version_indices[0]
    timestamp_index = nmi_timestamp_indices[0]
    hash_index = nmi_hash_indices[0]
    version_match = NMI_CURRENT_VERSION.fullmatch(nmi_lines[version_index])
    timestamp_match = NMI_UPDATED_AT.fullmatch(nmi_lines[timestamp_index])
    hash_match = NMI_HASH_MARKER.fullmatch(nmi_lines[hash_index])
    if version_match is None or timestamp_match is None or hash_match is None:
        raise PublicCopyValidationError("public nmi header metadata format mismatch")
    if (
        timestamp_index != version_index + 1
        or hash_index != timestamp_index + 1
        or hash_index >= placeholder_index
        or any(
            line and not line.startswith("#")
            for line in nmi_lines[: hash_index + 1]
        )
    ):
        raise PublicCopyValidationError("public nmi metadata is outside the header")
    nmi_versions = [version_match.group(1)]
    nmi_timestamps = [timestamp_match.group(1)]

    current_versions = []
    changelog_version_labels = []
    for _, line, _ in top_level_markdown_block_lines(texts["changelog"]):
        normalized_line = normalize_commonmark_escapes_and_entities(
            remove_markdown_html_tokens(line)
        ).rstrip("\t ")
        if normalized_line.startswith("当前版本："):
            changelog_version_labels.append(normalized_line)
    if len(changelog_version_labels) != 1:
        raise PublicCopyValidationError("copy changelog current version label mismatch")
    for line in changelog_version_labels:
        version_match = CHANGELOG_CURRENT_VERSION.fullmatch(line)
        if version_match:
            current_versions.append(version_match.group(1))
    if len(current_versions) != 1:
        raise PublicCopyValidationError("copy changelog current version mismatch")
    changelog_current_line = f"当前版本：{current_versions[0]}"
    require_top_level_markdown_line(texts["changelog"], changelog_current_line)
    if current_versions[0] != nmi_versions[0]:
        raise PublicCopyValidationError("copy version metadata drift")

    release_heading = re.compile(
        rf"## ({VERSION_CORE_PATTERN}) - "
        r"([0-9]{4}-[0-9]{2}-[0-9]{2})"
    )
    release_dates: dict[str, tuple[str, date]] = {}
    for heading_level, _, heading_source in changelog_headings:
        if heading_level != 2:
            continue
        heading_match = release_heading.fullmatch(heading_source)
        if heading_match is None:
            raise PublicCopyValidationError("copy changelog release heading format mismatch")
        release_version, release_date_source = heading_match.groups()
        if release_version in release_dates:
            raise PublicCopyValidationError("copy changelog release version is duplicated")
        try:
            release_date = datetime.strptime(release_date_source, "%Y-%m-%d").date()
        except ValueError as exc:
            raise PublicCopyValidationError("copy version date is invalid") from exc
        release_dates[release_version] = (release_date_source, release_date)
    current_release = release_dates.get(current_versions[0])
    if current_release is None:
        raise PublicCopyValidationError("copy changelog version heading mismatch")
    current_release_date_source, current_release_date = current_release
    changelog_heading = f"## {current_versions[0]} - {current_release_date_source}"
    require_top_level_markdown_line(
        texts["changelog"],
        changelog_heading,
        atx_heading=True,
    )
    try:
        nmi_updated_date = datetime.strptime(
            nmi_timestamps[0],
            "%Y-%m-%d %H:%M:%S",
        ).date()
    except ValueError as exc:
        raise PublicCopyValidationError("copy version date is invalid") from exc
    if nmi_updated_date != current_release_date:
        raise PublicCopyValidationError("copy version date drift")
    url_texts = {name: normalize_url_scan_text(text) for name, text in texts.items()}

    nmi_bytes = read_bytes(paths[0], from_index)
    if b"\r" in nmi_bytes:
        raise PublicCopyValidationError("public nmi must use LF line endings")

    for name, expected_files in EXPECTED_RULE_FILES.items():
        expected_urls = sorted(OSS_RULE_ROOT + rule_file for rule_file in expected_files)
        scan_views = [url_texts[name]]
        scan_views.extend(semantic_url_texts[name])
        for scan_text in scan_views:
            actual_urls = sorted(FIRST_PARTY_OSS_LIST_URL.findall(scan_text))
            if actual_urls != expected_urls:
                raise PublicCopyValidationError("first-party OSS rule URL set mismatch")
            if FIRST_PARTY_REPO_LIST_URL.search(scan_text):
                raise PublicCopyValidationError("non-OSS first-party rule URL")

    for name, expected_lines in EXPECTED_RULE_LINES.items():
        for expected_line in expected_lines:
            require_exact_line(texts[name], expected_line)

    nmi_interval = "  class: &class {type: http, interval: 3600, behavior: classical, format: text}"
    require_exact_line(texts["nmi"], nmi_interval)

    for rule_file in EXPECTED_RULE_FILES["cmi"]:
        fragment = f'interval: 3600, url: "{OSS_RULE_ROOT}{rule_file}"'
        if texts["cmi"].count(fragment) != 1:
            raise PublicCopyValidationError("cmi provider interval mismatch")

    for name, self_link in INI_SELF_LINKS.items():
        require_exact_line(texts[name], ";" + self_link)
        if FIRST_PARTY_REPO_INI_URL.findall(url_texts[name]) != [self_link]:
            raise PublicCopyValidationError("first-party INI self-link mismatch")
        expected_ipxie_count = 1 if name in {"qichiyu", "bei260317"} else 0
        if texts[name].count(IPXIE_URL) != expected_ipxie_count:
            raise PublicCopyValidationError("ipxie exception count mismatch")

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(add_help=True)
    parser.add_argument(
        "--index",
        action="store_true",
        help="read every supplied path from the Git index",
    )
    parser.add_argument(
        "--yaml-only",
        action="append",
        default=[],
        metavar="PATH",
        help="strictly parse YAML without applying public-secret checks",
    )
    parser.add_argument(
        "--public",
        action="append",
        default=[],
        metavar="PATH",
        help="validate a public YAML, INI, or Markdown artifact",
    )
    parser.add_argument(
        "--copy-set",
        action="append",
        default=[],
        nargs=6,
        metavar="PATH",
        help="validate nmi, cmi, three INIs, and changelog as one fixed copy set",
    )
    parser.add_argument(
        "--stdin-public-text",
        action="store_true",
        help="validate public text read from standard input without echoing it",
    )
    parser.add_argument(
        "--index-public-changes",
        action="store_true",
        help="validate each staged public text file independently from the Git index",
    )
    args = parser.parse_args()
    if (
        not args.yaml_only
        and not args.public
        and not args.copy_set
        and not args.stdin_public_text
        and not args.index_public_changes
    ):
        parser.error("at least one validation input is required")
    return args


def main() -> int:
    args = parse_args()
    try:
        for path in args.yaml_only:
            validate_yaml_only(path, args.index)
        for path in args.public:
            validate_public(path, args.index)
        for paths in args.copy_set:
            validate_copy_set(paths, args.index)
        if args.index_public_changes:
            validate_index_public_changes()
        if args.stdin_public_text:
            stdin_text = decode_utf8_bytes(sys.stdin.buffer.read())
            assert_public_text_safe(stdin_text)
            assert_public_markdown_safe(stdin_text)
    except PublicCopyValidationError:
        print("OSS public-copy validation failed; source content is hidden.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
