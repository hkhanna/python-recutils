"""External and remote descriptors (manual chapter 9).

External descriptors are built appending a file path to the %rec field
value:

    %rec: FSD_Entry /path/to/file.rec

URLs can be used as sources as well, in which case we talk about remote
descriptors:

    %rec: Department http://www.myorg.com/Org.rec

The local record descriptor can provide additional fields to "expand"
the record type.
"""

from __future__ import annotations

import re
import urllib.request

from .parser import Field, RecordDescriptor, RecordSet, parse

_URL_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*://")


class ExternalDescriptorError(Exception):
    """Raised when an external descriptor cannot be fetched or parsed."""


def _fetch_source(source: str) -> str:
    if _URL_RE.match(source):
        try:
            with urllib.request.urlopen(source) as response:
                return response.read().decode("utf-8")
        except Exception as exc:
            raise ExternalDescriptorError(
                f"cannot fetch remote descriptor '{source}': {exc}"
            ) from exc
    try:
        with open(source, "r") as f:
            return f.read()
    except OSError as exc:
        raise ExternalDescriptorError(
            f"cannot read external descriptor '{source}': {exc}"
        ) from exc


def _resolve_descriptor(
    descriptor: RecordDescriptor, visited: frozenset[str]
) -> RecordDescriptor:
    source = descriptor.external_source
    if source is None:
        return descriptor
    if source in visited:
        raise ExternalDescriptorError(
            f"circular reference in external descriptor '{source}'"
        )

    record_type = descriptor.record_type
    text = _fetch_source(source)
    try:
        external_sets = parse(text)
    except Exception as exc:
        raise ExternalDescriptorError(
            f"invalid rec data in external descriptor '{source}': {exc}"
        ) from exc

    # A record descriptor for the type may not exist in the external
    # file; in that case the local descriptor is used unchanged.
    external_fields: list[Field] = []
    for rs in external_sets:
        if rs.descriptor is not None and rs.record_type == record_type:
            resolved = _resolve_descriptor(rs.descriptor, visited | {source})
            external_fields = [f for f in resolved.fields if f.name != "%rec"]
            break

    if not external_fields:
        return descriptor

    # The external fields are included and the local record descriptor
    # provides additional fields expanding the record type.
    merged: list[Field] = []
    for field in descriptor.fields:
        merged.append(field)
        if field.name == "%rec":
            merged.extend(external_fields)
    return RecordDescriptor(fields=merged)


def resolve_external_descriptors(
    record_sets: list[RecordSet], no_external: bool = False
) -> list[RecordSet]:
    """Resolve external/remote descriptors in the given record sets.

    Returns record sets whose descriptors include the fields provided by
    their external sources.  When no_external is True the record sets
    are returned unchanged.
    """
    if no_external:
        return record_sets
    result = []
    for rs in record_sets:
        if rs.descriptor is not None and rs.descriptor.external_source:
            descriptor = _resolve_descriptor(rs.descriptor, frozenset())
            result.append(RecordSet(descriptor=descriptor, records=rs.records))
        else:
            result.append(rs)
    return result
