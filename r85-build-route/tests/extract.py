"""Read selected production-C functions without rewriting their bodies."""
import re


def span(source, name, last=False):
    candidates = []
    pattern = r'^static\s+[^;{}]*?\b' + re.escape(name) + r'\s*\([^;{}]*\)'
    for match in re.finditer(pattern, source, re.M):
        opening = source.find('{', match.end())
        if opening != -1 and ';' not in source[match.end():opening]:
            candidates.append((match.start(), opening))
    if not candidates:
        raise ValueError('Missing production definition: ' + name)
    start, opening = candidates[-1 if last else 0]
    position = opening
    depth = 0
    state = 'code'
    while position < len(source):
        char = source[position]
        pair = source[position:position + 2]
        if state == 'code':
            if pair == '/*':
                state = 'comment'
                position += 2
                continue
            if pair == '//':
                state = 'line'
                position += 2
                continue
            if char in ('"', "'"):
                state = char
            elif char == '{':
                depth += 1
            elif char == '}':
                depth -= 1
                if depth == 0:
                    return start, position + 1
        elif state == 'comment':
            if pair == '*/':
                state = 'code'
                position += 2
                continue
        elif state == 'line':
            if char == '\n':
                state = 'code'
        else:
            if char == '\\':
                position += 2
                continue
            if char == state:
                state = 'code'
        position += 1
    raise ValueError('Unterminated production function: ' + name)


def function(source, name, last=False):
    start, end = span(source, name, last=last)
    return source[start:end]


def section(source, begin, end):
    start = source.index(begin)
    return source[start:source.index(end, start) + len(end)]
