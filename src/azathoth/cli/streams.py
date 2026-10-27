"""Standard stream configuration for the command-line application.

Azathoth renders results with `ensure_ascii=False`, so workflow output in any
language reaches the operator unescaped. Python encodes standard output with
the locale's code page when it is redirected on Windows, and a code page such
as cp1252 cannot represent most of Unicode: a result could fail to print, or
reach a file in an encoding nothing else expects. The CLI therefore always
writes UTF-8.
"""

import codecs
import io
from typing import TextIO

UTF8 = "utf-8"


def use_utf8_streams(
    *streams: TextIO,
) -> None:
    """Switch each text stream that encodes with anything but UTF-8 to UTF-8.

    Streams already writing UTF-8 are left untouched. Streams that are not
    `io.TextIOWrapper` instances, such as `io.StringIO`, hold text rather than
    bytes and have no encoding to change.
    """

    for stream in streams:
        if not isinstance(stream, io.TextIOWrapper):
            continue

        if codecs.lookup(stream.encoding).name == UTF8:
            continue

        stream.reconfigure(encoding=UTF8)
