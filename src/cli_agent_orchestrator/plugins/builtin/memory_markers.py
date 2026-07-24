"""Validation helpers for CAO-managed provider instruction-file blocks."""


class MalformedMemoryMarkersError(RuntimeError):
    """Raised when CAO block ownership cannot be determined safely."""


def strip_managed_blocks(content: str, begin_marker: str, end_marker: str) -> str:
    """Remove well-formed managed blocks or reject ambiguous marker layouts.

    The exception text is intentionally constant and content-free so callers
    can safely surface it in lifecycle logs without leaking instructions.
    """

    output: list[str] = []
    cursor = 0
    while True:
        begin = content.find(begin_marker, cursor)
        end_before_begin = content.find(end_marker, cursor)

        if begin == -1:
            if end_before_begin != -1:
                raise MalformedMemoryMarkersError("malformed CAO memory markers")
            output.append(content[cursor:])
            return "".join(output)

        if end_before_begin != -1 and end_before_begin < begin:
            raise MalformedMemoryMarkersError("malformed CAO memory markers")

        end = content.find(end_marker, begin + len(begin_marker))
        nested_begin = content.find(begin_marker, begin + len(begin_marker))
        if end == -1 or (nested_begin != -1 and nested_begin < end):
            raise MalformedMemoryMarkersError("malformed CAO memory markers")

        output.append(content[cursor:begin])
        cursor = end + len(end_marker)
