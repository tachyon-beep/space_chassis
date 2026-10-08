"""A reader for the subset of compose YAML this repository writes.

The topology checks must hold where Docker is not installed, and PyYAML is not
a dependency, so they read the files' own text. The subset is what
docker-compose.yml and scripts/build_compose.py emit: top-level keys at column
zero, service headings at two spaces, service keys at four, and below a key
either a block list (`- item`) or a mapping (`KEY: value`) at six. A list item
may itself be a mapping, the long syntax of a mount: `- key: value` at six,
its further keys at eight, and the children of one of those keys (`bind:`) at
ten. Inline `[a, b]` lists and quoted scalars are unwrapped. Comment and blank
lines are skipped. Under `logging:` alone, a mapping entry at six spaces whose value is empty (its
`options:`) holds a mapping of its own at eight. Anything else nested deeper than
six spaces, a build's `args:` for one, is ignored.
"""

import re

_TOP = re.compile(r"^([A-Za-z0-9_.-]+):(.*)$")
_SERVICE = re.compile(r"^  ([A-Za-z0-9_.-]+):(.*)$")
_KEY = re.compile(r"^    ([A-Za-z0-9_.-]+):(.*)$")
_ENTRY = re.compile(r"^      ([A-Za-z0-9_.-]+):(.*)$")
_ITEM_KEY = re.compile(r"^        ([A-Za-z0-9_.-]+):(.*)$")
_ITEM_CHILD = re.compile(r"^          ([A-Za-z0-9_.-]+):(.*)$")
_ENTRY_CHILD = re.compile(r"^        ([A-Za-z0-9_.-]+):(.*)$")
# The text after `- ` when a list item opens a mapping. A key admits no `/`,
# `$` or quote, and its colon ends the line or is followed by a space, so a
# short-syntax mount (`name:/path`), a tmpfs line (`/work:size=...`) and a
# quoted port mapping all stay scalars.
_ITEM_OPEN = re.compile(r"^([A-Za-z0-9_.-]+):(?:\s(.*))?$")


def _scalar(value):
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def _value(raw):
    raw = raw.strip()
    if raw.startswith("[") and raw.endswith("]"):
        return [_scalar(item) for item in raw[1:-1].split(",") if item.strip()]
    if raw == "{}":
        return {}
    return _scalar(raw)


def _sections(text):
    """Each top-level key's own lines, by key."""
    sections, current = {}, None
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        top = _TOP.match(line)
        if top:
            current = top.group(1)
            sections[current] = []
            continue
        if current is not None:
            sections[current].append(line)
    return sections


def services(text):
    """Each service under `services:`, as {name: {key: value}}.

    A value is a string for a scalar, a list for an inline or block list, and a
    dict for a block mapping. A list item is a string, or a dict when it is a
    mapping; a mapping item's key with children at ten spaces holds a dict.
    """
    found, service, key = {}, None, None
    # The mapping list item being read, and its key whose children sit at ten.
    item, field = None, None
    # The six-space mapping entry whose own mapping sits at eight.
    group = None
    for line in _sections(text).get("services", []):
        heading = _SERVICE.match(line)
        if heading:
            service, key, item, field, group = heading.group(1), None, None, None, None
            found[service] = {}
            continue
        if service is None:
            continue
        own = _KEY.match(line)
        if own:
            key, raw = own.group(1), own.group(2)
            item, field, group = None, None, None
            found[service][key] = _value(raw) if raw.strip() else None
            continue
        if key is None:
            continue
        if item is not None:
            child = _ITEM_CHILD.match(line)
            if child:
                if field is not None and item.get(field) is None:
                    item[field] = {}
                if field is not None and isinstance(item[field], dict):
                    item[field][child.group(1)] = _value(child.group(2))
                continue
            nested = _ITEM_KEY.match(line)
            if nested:
                field, raw = nested.group(1), nested.group(2)
                item[field] = _value(raw) if raw.strip() else None
                continue
        if group is not None:
            member = _ENTRY_CHILD.match(line)
            if member:
                if found[service][key][group] == "":
                    found[service][key][group] = {}
                found[service][key][group][member.group(1)] = _value(member.group(2))
                continue
        if not line.startswith("      ") or line.startswith("       "):
            continue
        item, field, group = None, None, None
        body = found[service]
        text_item = line.strip()
        if text_item.startswith("- "):
            if body[key] is None:
                body[key] = []
            opened = _ITEM_OPEN.match(text_item[2:])
            if opened:
                field, raw = opened.group(1), opened.group(2) or ""
                item = {field: _value(raw) if raw.strip() else None}
                body[key].append(item)
            else:
                body[key].append(_scalar(text_item[2:]))
            continue
        entry = _ENTRY.match(line)
        if entry:
            if body[key] is None:
                body[key] = {}
            body[key][entry.group(1)] = _value(entry.group(2))
            if key == "logging" and not entry.group(2).strip():
                group = entry.group(1)
    return found


def networks(text):
    """The names declared under the top-level `networks:` key."""
    names = []
    for line in _sections(text).get("networks", []):
        heading = _SERVICE.match(line)
        if heading:
            names.append(heading.group(1))
    return names


def merged(base, override):
    """The services of base with override applied the way compose merges them.

    A service only the override names is added. For one both name, lists are
    appended, mappings updated and scalars replaced, which is the part of
    compose's merge these checks rely on.
    """
    result = {name: dict(body) for name, body in services(base).items()}
    for name, body in services(override).items():
        target = result.setdefault(name, {})
        for key, value in body.items():
            current = target.get(key)
            if isinstance(current, list) and isinstance(value, list):
                target[key] = current + value
            elif isinstance(current, dict) and isinstance(value, dict):
                target[key] = {**current, **value}
            else:
                target[key] = value
    return result


def container_port(mapping):
    """The container side of a `host_ip:host_port:container_port` mapping.

    The host port may itself be an interpolation such as `${VAR:-8092}`, so the
    container port is whatever follows the last colon.
    """
    return mapping.rsplit(":", 1)[-1]


def mount_flags(body):
    """Each volume mount of one service as (source, target, read_only).

    A long-syntax mount is read from its keys. A short one is split from the
    right, because a source may be an interpolation such as `${VAR:-./path}`
    that carries a colon of its own.
    """
    mounts = []
    for entry in body.get("volumes") or []:
        if isinstance(entry, dict):
            mounts.append(
                (entry.get("source"), entry.get("target"), entry.get("read_only") == "true")
            )
            continue
        rest, _, last = entry.rpartition(":")
        mode = ""
        if rest and not last.startswith("/"):
            mode, entry = last, rest
        source, _, target = entry.rpartition(":")
        mounts.append((source, target, "ro" in mode.split(",")))
    return mounts
