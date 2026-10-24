"""ELF parser reused from the verified r13 assembly refresh."""
import collections
import hashlib
import json
from pathlib import Path, PurePosixPath
import struct

def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def file_sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def norm(value):
    return value.replace('-', '_')


def safe(value):
    p = PurePosixPath(value)
    require(bool(value) and not p.is_absolute() and '..' not in p.parts
            and str(p) == value and '\\' not in value, 'Unsafe path: ' + value)
    return p


def jbytes(value):
    return (json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + '\n').encode()


def parse_elf(data):
    require(data[:6] == b'\x7fELF\x02\x01' and len(data) >= 64, 'Not ELF64 LE')
    require(struct.unpack_from('<HH', data, 16) == (1, 183), 'Not AArch64 relocatable ELF')
    off = struct.unpack_from('<Q', data, 40)[0]
    es, count, si = struct.unpack_from('<HHH', data, 58)
    require(es == 64 and 0 < si < count and off + count * es <= len(data), 'Bad sections')
    hs = [struct.unpack_from('<IIQQQQIIQQ', data, off+i*es) for i in range(count)]

    def section(h):
        require(h[1] != 8 and h[4]+h[5] <= len(data), 'Invalid section data')
        return data[h[4]:h[4]+h[5]]

    def string(b, o):
        require(0 <= o < len(b), 'Invalid string offset')
        return b[o:b.index(b'\0', o)].decode()

    ns = section(hs[si])
    byname = {string(ns, h[0]): h for h in hs}
    require(len(byname) == len(hs), 'Repeated ELF section')
    get = lambda n: section(byname[n]) if n in byname else b''
    info = collections.defaultdict(list)
    for v in get('.modinfo').split(b'\0'):
        if b'=' in v:
            k, val = v.decode().split('=', 1)
            info[k].append(val)

    def put(d, key, value):
        require(key and key not in d, 'Duplicate/empty symbol record: ' + key)
        d[key] = value

    basic, extended = {}, {}
    raw = get('__versions')
    require(len(raw) % 64 == 0, 'Bad basic CRC section')
    for i in range(0, len(raw), 64):
        put(basic, raw[i+8:i+64].split(b'\0')[0].decode(), struct.unpack_from('<Q', raw, i)[0])
    en, ec = get('__version_ext_names'), get('__version_ext_crcs')
    if en or ec:
        require(en.endswith(b'\0'), 'Bad extended names')
        names = en.rstrip(b'\0').split(b'\0')
        require(len(ec) == 4*len(names), 'Bad extended CRC count')
        for i, n in enumerate(names):
            put(extended, n.decode(), struct.unpack_from('<I', ec, i*4)[0])
        require(all(extended.get(s) == v for s, v in basic.items()), 'Basic/extended CRC disagreement')
    versions = extended or basic
    exports, export_crcs, strong, weak = set(), {}, set(), set()
    for h in hs:
        if h[1] != 2:
            continue
        require(h[6] < count and h[9] == 24 and h[5] % 24 == 0, 'Bad symbol table')
        strings, tab = section(hs[h[6]]), section(h)
        for i in range(0, len(tab), 24):
            no, st, _, ix, value, _ = struct.unpack_from('<IBBHQQ', tab, i)
            name = string(strings, no)
            if not ix and name:
                if st >> 4 == 1:
                    strong.add(name)
                elif st >> 4 == 2:
                    weak.add(name)
            if ix and st & 15 != 3 and name.startswith('__ksymtab_'):
                require(name[10:] not in exports, 'Duplicate ELF export')
                exports.add(name[10:])
            if ix and st & 15 != 3 and name.startswith('__crc_'):
                if ix == 0xfff1:
                    crc = value
                else:
                    require(ix < count, 'Bad export CRC section')
                    sn = string(ns, hs[ix][0])
                    require(sn in ('__kcrctab', '__kcrctab_gpl') and value+4 <= hs[ix][5], 'Unknown export CRC encoding')
                    require(not any(r[1] in (4, 9) and r[7] == ix and r[5] for r in hs), 'Relocated export CRC unsupported')
                    crc = struct.unpack_from('<I', section(hs[ix]), value)[0]
                put(export_crcs, name[6:], crc)
    require(exports == export_crcs.keys(), 'ELF export CRC set mismatch')
    require(strong <= versions.keys() and 'module_layout' in versions, 'Missing import CRC')
    require(not (versions.keys() - strong - weak - {'module_layout'}), 'Orphan import CRC')
    require(not weak, 'Unexpected weak import requires review')
    require(len(info['name']) == len(info['vermagic']) == 1, 'Ambiguous module identity')
    return {'name': info['name'][0], 'info': dict(info), 'imports': strong,
            'exports': exports, 'export_crcs': export_crcs, 'versions': versions,
            'basic_extended_equal': bool(basic) and basic == extended,
            'depends': sorted({norm(n) for d in info.get('depends', []) for n in d.split(',') if n}),
            'softdeps': info.get('softdep', [])}

