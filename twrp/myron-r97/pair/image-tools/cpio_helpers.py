#!/usr/bin/env python3
"""Patch the pinned Myron recovery init.rc, preserving every other CPIO record.

Requires Python >=3.9 and liblz4.so with LZ4_compress_HC (tested 1.9.4).
No firmware is flashed and no kernel/module source is compiled.

The AVB parser uses the published AOSP AvbFooter, AvbVBMetaImageHeader and
AvbHashDescriptor layouts. Only algorithm NONE is accepted: this is the
existing image's algorithm, not a downgrade from a signed algorithm. The
existing VBMeta header, salt, flags, rollback values and other descriptors
remain byte-identical; the recovery payload size/digest and footer offsets
are the only AVB fields that change.
"""
import argparse
import ctypes
import ctypes.util
import hashlib
import json
from pathlib import Path
import struct

SOURCE_SHA256 = 'c5e870b08c7473b309a18f2801289d713c7309a4c90c7b379d587d959406dccd'
PARTITION_SIZE = 104857600
BUILD_ID = 'R17-LIVE-CONTROL-20261011-01'
TARGET_RC = 'system/etc/init/hw/init.rc'
LZ4_MAGIC = b'\x02\x21\x4c\x18'
LZ4_BLOCK = 8 * 1024 * 1024
MARKER_BLOCK = f'''\n# {BUILD_ID}: RAM-only live markers; existing recovery services are unchanged.
on early-init
    mkdir /dev/r17-live 0755 root root
    write /dev/r17-live/build-id {BUILD_ID}
    copy /proc/sys/kernel/random/boot_id /dev/r17-live/boot-id
    copy /proc/sys/kernel/osrelease /dev/r17-live/kernel-release
    write /dev/r17-live/stage-early early-init

on boot
    mkdir /dev/r17-live 0755 root root
    write /dev/r17-live/build-id {BUILD_ID}
    copy /proc/sys/kernel/random/boot_id /dev/r17-live/boot-id
    copy /proc/sys/kernel/osrelease /dev/r17-live/kernel-release
    write /dev/r17-live/stage-boot boot
'''.encode('ascii')
SOURCE_URLS = [
    'https://android.googlesource.com/platform/external/avb/+/refs/heads/main/libavb/avb_footer.h',
    'https://android.googlesource.com/platform/external/avb/+/refs/heads/main/libavb/avb_vbmeta_image.h',
    'https://android.googlesource.com/platform/external/avb/+/refs/heads/main/libavb/avb_hash_descriptor.h',
    'https://android.googlesource.com/platform/external/avb/+/refs/heads/main/avbtool.py',
]


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def align(value, boundary):
    return (value + boundary - 1) // boundary * boundary


def blob_info(data):
    return {'bytes': len(data), 'sha256': sha(data)}


class LegacyLz4:
    def __init__(self):
        self.lib = ctypes.CDLL(ctypes.util.find_library('lz4') or 'liblz4.so.1')
        self.lib.LZ4_decompress_safe.argtypes = [ctypes.c_char_p, ctypes.c_void_p, ctypes.c_int, ctypes.c_int]
        self.lib.LZ4_decompress_safe.restype = ctypes.c_int
        self.lib.LZ4_compressBound.argtypes = [ctypes.c_int]
        self.lib.LZ4_compressBound.restype = ctypes.c_int
        self.lib.LZ4_compress_HC.argtypes = [ctypes.c_char_p, ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int]
        self.lib.LZ4_compress_HC.restype = ctypes.c_int
        self.lib.LZ4_versionString.restype = ctypes.c_char_p
        self.version = self.lib.LZ4_versionString().decode('ascii')

    def decompress(self, compressed):
        require(compressed[:4] == LZ4_MAGIC, 'Ramdisk must use legacy LZ4')
        parts, position = [], 4
        while position < len(compressed):
            require(position + 4 <= len(compressed), 'Truncated LZ4 block header')
            size, = struct.unpack_from('<I', compressed, position)
            position += 4
            require(0 < size <= self.lib.LZ4_compressBound(LZ4_BLOCK), 'Invalid LZ4 block length')
            require(position + size <= len(compressed), 'Truncated LZ4 block')
            out = ctypes.create_string_buffer(LZ4_BLOCK)
            n = self.lib.LZ4_decompress_safe(compressed[position:position+size], out, size, LZ4_BLOCK)
            require(n > 0, 'LZ4 decompression failed')
            parts.append(out.raw[:n])
            position += size
        return b''.join(parts)

    def compress(self, raw, level):
        require(1 <= level <= 12, 'LZ4 HC compression level outside 1..12')
        parts = [LZ4_MAGIC]
        for position in range(0, len(raw), LZ4_BLOCK):
            block = raw[position:position+LZ4_BLOCK]
            bound = self.lib.LZ4_compressBound(len(block))
            out = ctypes.create_string_buffer(bound)
            size = self.lib.LZ4_compress_HC(block, out, len(block), bound, level)
            require(size > 0, 'LZ4 compression failed')
            parts.extend([struct.pack('<I', size), out.raw[:size]])
        return b''.join(parts)


def parse_cpio(raw):
    entries, position, names = [], 0, set()
    while position + 110 <= len(raw):
        start = position
        require(raw[start:start+6] == b'070701', 'Expected newc CPIO without CRC')
        fields = [int(raw[start+6+i*8:start+14+i*8], 16) for i in range(13)]
        namesize, size = fields[11], fields[6]
        require(namesize > 0, 'Empty CPIO name')
        name_end = start + 110 + namesize
        require(name_end <= len(raw) and raw[name_end-1] == 0, 'Invalid CPIO name')
        name = raw[start+110:name_end-1].decode('utf-8')
        require(name not in names, 'Duplicate CPIO entry: ' + name)
        names.add(name)
        data_start = align(name_end, 4)
        end = align(data_start + size, 4)
        require(end <= len(raw), 'Truncated CPIO record')
        entries.append({'name': name, 'fields': fields, 'start': start, 'data_start': data_start,
                        'end': end, 'data': raw[data_start:data_start+size]})
        position = end
        if name == 'TRAILER!!!':
            require(not any(raw[end:]), 'Unexpected nonzero data after CPIO trailer')
            return entries
    raise ValueError('Missing CPIO trailer')


def patch_cpio(raw):
    entries = parse_cpio(raw)
    target = next((e for e in entries if e['name'] == TARGET_RC), None)
    require(target is not None, 'Recovery init.rc was not found')
    require(target['fields'][1] & 0o170000 == 0o100000, 'init.rc must be a regular file')
    require(target['fields'][4] == 1, 'Do not patch a multiply-linked init.rc')
    require(BUILD_ID.encode() not in target['data'], 'Input is already instrumented')
    original_rc = target['data']
    require(original_rc.endswith(b'\n'), 'Original init.rc must end in newline')
    patched_rc = original_rc + MARKER_BLOCK
    start, data_start, end = target['start'], target['data_start'], target['end']
    header = bytearray(raw[start:data_start])
    header[54:62] = f'{len(patched_rc):08x}'.encode('ascii')
    record = bytes(header) + patched_rc + b'\0' * (-len(patched_rc) % 4)
    patched = raw[:start] + record + raw[end:entries[-1]['end']]
    patched += b'\0' * (-len(patched) % 512)
    modified = parse_cpio(patched)
    require([e['name'] for e in entries] == [e['name'] for e in modified], 'CPIO entry order changed')
    changes = []
    for before, after in zip(entries, modified):
        bf, af = before['fields'][:], after['fields'][:]
        if before['name'] == TARGET_RC:
            bf[6] = af[6]
        require(bf == af, 'CPIO metadata changed: ' + before['name'])
        if before['data'] != after['data']:
            changes.append(before['name'])
        if before['name'] != TARGET_RC:
            require(raw[before['start']:before['end']] == patched[after['start']:after['end']],
                    'Original CPIO record bytes changed: ' + before['name'])
    require(changes == [TARGET_RC], 'CPIO semantic changes exceed init.rc')
    return patched, entries, modified, original_rc, patched_rc


def inspect_avb(image):
    footer = image[-64:]
    require(footer[:4] == b'AVBf', 'Missing AVB footer')
    major, minor, original_size, offset, size = struct.unpack_from('>IIQQQ', footer, 4)
    require((major, minor) == (1, 0) and not any(footer[36:]), 'Unknown AVB footer')
    require(original_size <= offset and offset+size <= len(image)-64, 'AVB footer out of bounds')
    vbmeta = image[offset:offset+size]
    require(vbmeta[:4] == b'AVB0' and len(vbmeta) >= 256, 'Invalid VBMeta header')
    authentication_size, auxiliary_size, algorithm = struct.unpack_from('>QQI', vbmeta, 12)
    require(algorithm == 0, 'STOP: signed AVB algorithm is unsupported; do not replace it with NONE')
    require(authentication_size == 0, 'NONE image unexpectedly has authentication data')
    require(256+authentication_size+auxiliary_size == size, 'Invalid VBMeta size')
    require(not any(struct.unpack_from('>QQQQ', vbmeta, 32)), 'NONE image unexpectedly has hash/signature fields')
    public_size, = struct.unpack_from('>Q', vbmeta, 72)
    require(public_size == 0, 'NONE image unexpectedly has a public key')
    descriptors_offset, descriptors_size, rollback, flags, location = struct.unpack_from('>QQQII', vbmeta, 96)
    require(flags == 0, 'Unexpected verification flags in captured recovery')
    require(descriptors_offset+descriptors_size <= auxiliary_size, 'AVB descriptors out of bounds')
    cursor = 256 + authentication_size + descriptors_offset
    stop, descriptors = cursor + descriptors_size, []
    while cursor < stop:
        require(cursor+16 <= stop, 'Truncated AVB descriptor')
        tag, following = struct.unpack_from('>QQ', vbmeta, cursor)
        require(following % 8 == 0 and cursor+16+following <= stop, 'Invalid AVB descriptor size')
        raw = vbmeta[cursor:cursor+16+following]
        desc = {'tag': tag, 'offset': cursor, 'raw': raw}
        if tag == 2:
            require(len(raw) >= 132, 'Truncated AVB hash descriptor')
            image_size, = struct.unpack_from('>Q', raw, 16)
            hash_algorithm = raw[24:56].split(b'\0')[0].decode('ascii')
            name_len, salt_len, digest_len, desc_flags = struct.unpack_from('>IIII', raw, 56)
            require(132+name_len+salt_len+digest_len <= len(raw), 'AVB hash data truncated')
            require(not any(raw[72:132]), 'Unknown AVB hash descriptor reserved bytes')
            name = raw[132:132+name_len].decode('utf-8')
            salt = raw[132+name_len:132+name_len+salt_len]
            digest_offset = 132+name_len+salt_len
            digest = raw[digest_offset:digest_offset+digest_len]
            require(hash_algorithm == 'sha256' and digest_len == 32, 'Unsupported recovery hash scheme')
            require(image_size <= offset, 'AVB payload overlaps VBMeta')
            computed = hashlib.sha256(salt+image[:image_size]).digest()
            require(digest == computed, 'AVB payload hash does not match descriptor')
            desc.update(image_size=image_size, hash_algorithm=hash_algorithm, name=name, salt=salt,
                        digest=digest, digest_offset=digest_offset, flags=desc_flags)
        descriptors.append(desc)
        cursor += len(raw)
    hashes = [d for d in descriptors if d['tag'] == 2]
    require(len(hashes) == 1 and hashes[0]['name'] == 'recovery', 'Expected one recovery hash descriptor')
    require(hashes[0]['image_size'] == original_size, 'Footer size and hash descriptor size differ')
    return {'footer': footer, 'original_size': original_size, 'offset': offset, 'size': size,
            'vbmeta': vbmeta, 'descriptors': descriptors, 'hash': hashes[0], 'algorithm': algorithm,
            'rollback_index': rollback, 'flags': flags, 'rollback_index_location': location}


def avb_summary(parsed):
    h = parsed['hash']
    return {'algorithm': 'NONE', 'algorithm_type': parsed['algorithm'], 'flags': parsed['flags'],
            'rollback_index': parsed['rollback_index'], 'rollback_index_location': parsed['rollback_index_location'],
            'vbmeta_offset': parsed['offset'], 'vbmeta_bytes': parsed['size'],
            'payload_bytes': parsed['original_size'], 'partition_name': h['name'],
            'hash_algorithm': h['hash_algorithm'], 'hash_descriptor_flags': h['flags'],
            'salt': h['salt'].hex(), 'digest': h['digest'].hex(), 'payload_hash_verified': True,
            'descriptor_count': len(parsed['descriptors']),
            'other_descriptor_sha256': [sha(d['raw']) for d in parsed['descriptors'] if d['tag'] != 2]}


def rebuild_image(original, ramdisk, avb):
    require(original[:8] == b'ANDROID!', 'Not an Android boot image')
    kernel_size, old_size = struct.unpack_from('<II', original, 8)
    header_size, = struct.unpack_from('<I', original, 20)
    header_version, = struct.unpack_from('<I', original, 40)
    signature_size, = struct.unpack_from('<I', original, 1580)
    require(kernel_size == 0 and header_version == 4 and header_size == 1584 and signature_size == 0,
            'Expected v4 kernel-less recovery image without boot signature')
    require(align(4096+old_size, 4096) == avb['original_size'], 'Unexpected original payload layout')
    require(not any(original[4096+old_size:avb['offset']]), 'Nonzero bytes between ramdisk and VBMeta')
    header = bytearray(original[:4096])
    struct.pack_into('<I', header, 12, len(ramdisk))
    payload = bytes(header) + ramdisk
    payload += b'\0' * (-len(payload) % 4096)
    require(len(payload)+align(avb['size'],4096)+4096 <= len(original), 'STOP: rebuilt image does not fit partition')
    vbmeta = bytearray(avb['vbmeta'])
    hd = avb['hash']
    struct.pack_into('>Q', vbmeta, hd['offset']+16, len(payload))
    new_digest = hashlib.sha256(hd['salt']+payload).digest()
    ds = hd['offset']+hd['digest_offset']
    vbmeta[ds:ds+len(new_digest)] = new_digest
    footer = bytearray(avb['footer'])
    struct.pack_into('>QQ', footer, 12, len(payload), len(payload))
    result = payload + bytes(vbmeta)
    result += b'\0' * (len(original)-64-len(result)) + bytes(footer)
    verified = inspect_avb(result)
    expected_header = bytearray(result[:4096]); expected_header[12:16] = original[12:16]
    require(bytes(expected_header) == original[:4096], 'Boot header changed beyond ramdisk_size')
    expected_vbmeta = bytearray(verified['vbmeta'])
    expected_vbmeta[hd['offset']+16:hd['offset']+24] = avb['vbmeta'][hd['offset']+16:hd['offset']+24]
    expected_vbmeta[ds:ds+32] = avb['vbmeta'][ds:ds+32]
    require(bytes(expected_vbmeta) == avb['vbmeta'], 'AVB data changed beyond recovery size/digest')
    expected_footer = bytearray(verified['footer']); expected_footer[12:28] = avb['footer'][12:28]
    require(bytes(expected_footer) == avb['footer'], 'AVB footer changed beyond payload size/offset')
    return result, verified


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False)+'\n', encoding='utf-8')


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--recovery', required=True, type=Path)
    ap.add_argument('--baseline-manifest', required=True, type=Path)
    ap.add_argument('--metadata-dir', required=True, type=Path)
    ap.add_argument('--out', required=True, type=Path)
    ap.add_argument('--lz4-level', type=int, default=9)
    args = ap.parse_args()
    original = args.recovery.read_bytes()
    require(len(original) == PARTITION_SIZE and sha(original) == SOURCE_SHA256, 'Pinned recovery image mismatch')
    avb = inspect_avb(original)
    size, = struct.unpack_from('<I', original, 12)
    codec = LegacyLz4()
    cpio = codec.decompress(original[4096:4096+size])
    patched, before, after, original_rc, patched_rc = patch_cpio(cpio)
    compressed = codec.compress(patched, args.lz4_level)
    require(codec.decompress(compressed) == patched, 'LZ4 round trip failed')
    result, new_avb = rebuild_image(original, compressed, avb)
    out = args.out
    for part in ['test', 'restore', 'evidence']:
        (out/part).mkdir(parents=True, exist_ok=True)
    entries = {e['name']: e for e in before}
    runtime_hashes = {}
    runtime_observations = {}
    for line in (args.metadata_dir/'runtime-binary-sha256.txt').read_text().splitlines():
        if not line.strip():
            continue
        digest, path = line.split(None, 1)
        name = path.strip().lstrip('/')
        require(name in entries, 'Captured executable path is absent from recovery: '+name)
        if entries[name]['fields'][1] & 0o170000 == 0o120000:
            runtime_observations['/'+name] = {'captured_runtime_sha256':digest,
                'recovery_cpio_symlink_target':entries[name]['data'].decode('utf-8'),
                'note':'Runtime hash is not the raw symlink data hash. Root init can originate from merged boot ramdisks.'}
            continue
        require(sha(entries[name]['data']) == digest,
                'Captured runtime executable does not match recovery CPIO: '+name)
        runtime_hashes['/'+name] = digest
    require(set(runtime_hashes) == {'/system/bin/init','/system/bin/recovery','/system/bin/adbd'},
            'Expected the three captured regular recovery executables')
    module_hashes = {e['name']:sha(e['data']) for e in before if e['name'].endswith('.ko')}
    expected_kernel = (args.metadata_dir/'kernel-release.txt').read_text().strip()
    require(expected_kernel and '\n' not in expected_kernel and '\r' not in expected_kernel, 'Invalid kernel release')
    baseline = json.loads(args.baseline_manifest.read_text())
    original_hashes = {k: baseline['original'][k] for k in ['boot','vendor_boot','init_boot','dtbo','vbmeta','vbmeta_system']}
    original_hashes['recovery'] = blob_info(original)
    manifest = {'schema':1, 'build_id':BUILD_ID, 'product':'myron', 'kind':'recovery-live-control',
        'captured_slot':'a', 'hardware_tested':False, 'android_boot_verified':False,
        'original':original_hashes, 'test':{'recovery':blob_info(result)},
        'paths':{'test_recovery':'test/recovery.img','restore_recovery':'restore/recovery.img'},
        'marker':{'directory':'/dev/r17-live','build_id':BUILD_ID,
                  'files':['build-id','boot-id','kernel-release','stage-early','stage-boot']},
        'expected_kernel_release':expected_kernel,
        'init_rc':{'path':'/'+TARGET_RC,'original_sha256':sha(original_rc),'test_sha256':sha(patched_rc)},
        'runtime_executable_hashes':runtime_hashes,
        'preserved_module_count':len(module_hashes),
        'avb':{'original':avb_summary(avb),'test':avb_summary(new_avb)},
        'note':'Live recovery marker control using captured original kernel and userspace. Not a new kernel or proof of Android boot.'}
    evidence = {'source_recovery':blob_info(original),'test_recovery':blob_info(result),
        'cpio_original':blob_info(cpio),'cpio_test':blob_info(patched),
        'cpio_record_count_including_trailer':len(before),
        'semantic_changes':[TARGET_RC], 'all_other_record_bytes_preserved':True,
        'all_metadata_except_modified_file_size_preserved':True,
        'boot_header_only_changed_field':'ramdisk_size',
        'original_ramdisk_bytes':size,'test_ramdisk_bytes':len(compressed),
        'compression':{'format':'legacy LZ4','block_bytes':LZ4_BLOCK,'hc_level':args.lz4_level,'library_version':codec.version,'round_trip_verified':True},
        'avb_header_and_nonhash_descriptors_preserved':True,
        'avb_hash_only_changed_fields':['image_size','digest'],
        'avb_footer_only_changed_fields':['original_image_size','vbmeta_offset'],
        'avb_sources':SOURCE_URLS, 'avb':manifest['avb'],
        'runtime_executable_hashes_match_captured_device':runtime_hashes,
        'other_runtime_executable_observations':runtime_observations,
        'preserved_module_count':len(module_hashes),
        'hardware_tested':False,
        'reproduction':['python3 src/build_control.py --recovery /path/to/recovery_a.img --baseline-manifest /path/to/r17/manifest.json --metadata-dir /path/to/recovery-source/metadata --out /path/to/package --lz4-level '+str(args.lz4_level)]}
    (out/'test/recovery.img').write_bytes(result)
    (out/'restore/recovery.img').write_bytes(original)
    write_json(out/'manifest.json', manifest)
    write_json(out/'evidence/image-validation.json', evidence)
    write_json(out/'evidence/preserved-modules.json', module_hashes)
    (out/'evidence/marker-init.rc').write_bytes(MARKER_BLOCK)
    (out/'evidence/original-init.rc').write_bytes(original_rc)
    (out/'evidence/test-init.rc').write_bytes(patched_rc)
    print(json.dumps({'output':str(out),'image':manifest['test']['recovery'],'modules_preserved':len(module_hashes),
                      'cpio_entries':len(before),'ramdisk_bytes':len(compressed),'avb_algorithm':'NONE'},indent=2))


if __name__ == '__main__':
    main()
