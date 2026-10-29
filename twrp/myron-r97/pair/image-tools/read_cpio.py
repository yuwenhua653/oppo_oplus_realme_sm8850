import ctypes,ctypes.util,struct
def need(ok,msg):
    if not ok:raise AssertionError(msg)
def extract(p):
    raw = p.read_bytes()
    need(raw[:8] in (b'VNDRBOOT',b'ANDROID!'), 'magic')
    if raw[:8]==b'VNDRBOOT':
        page=struct.unpack_from('<I',raw,12)[0];length=struct.unpack_from('<I',raw,24)[0]
    else:
        need(struct.unpack_from('<I',raw,8)[0]==0,'kernel-less recovery')
        page=4096;length=struct.unpack_from('<I',raw,12)[0]
    need(page == 4096, 'page')
    rd = raw[page:page + length]
    need(rd[:4] == bytes.fromhex('02214c18'), 'legacy lz4')
    lib = ctypes.CDLL(ctypes.util.find_library('lz4'))
    lib.LZ4_decompress_safe.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int, ctypes.c_int]
    lib.LZ4_decompress_safe.restype = ctypes.c_int
    expanded = bytearray()
    offset = 4
    while offset < len(rd):
        size = struct.unpack_from('<I', rd, offset)[0]
        offset += 4
        need(size > 0 and offset + size <= len(rd), 'block bound')
        src = ctypes.create_string_buffer(rd[offset:offset + size])
        dst = ctypes.create_string_buffer(8 * 1024 * 1024)
        n = lib.LZ4_decompress_safe(src, dst, size, len(dst))
        need(0 < n <= len(dst), 'decoded size')
        expanded.extend(dst.raw[:n])
        offset += size
    result = {}
    offset = 0
    while True:
        need(expanded[offset:offset + 6] == b'070701', 'newc magic')
        fields = [int(expanded[offset + 6 + i * 8:offset + 14 + i * 8], 16) for i in range(13)]
        size, namesize = (fields[6], fields[11])
        need(namesize > 0 and expanded[offset + 110 + namesize - 1] == 0, 'name bound')
        name = expanded[offset + 110:offset + 110 + namesize - 1].decode()
        start = offset + 110 + namesize + 3 & ~3
        end = start + size + 3 & ~3
        need(name not in result and end <= len(expanded), 'entry unique and bounded')
        result[name] = {'fields': fields, 'data': bytes(expanded[start:start + size]), 'record': bytes(expanded[offset:end])}
        offset = end
        if name == 'TRAILER!!!':
            break
    need(not any(expanded[offset:]), 'zero cpio tail')
    return (raw, result)
