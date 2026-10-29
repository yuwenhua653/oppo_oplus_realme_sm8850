#!/usr/bin/env python3
"""Build pinned r13 USB diagnostic images; never connects to or flashes a device.

Uses the captured boot headers and AVB records as templates. All fields remain
byte-identical except changed payload lengths, hashes, signatures and offsets.
The boot signature is generated with the same public AOSP RSA4096 test key as
the captured boot. Top-level vbmeta is not modified; end-to-end trust is NOT
claimed. Legacy LZ4 uses liblz4 HC level 9 with 8 MiB blocks.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys

from cpio_helpers import LegacyLz4, align, blob_info, parse_cpio, require, sha
import avbtool
import isolation

BUILD_ID = 'R17-R13-USB-20261011-01'
KERNEL_RELEASE = '6.12.81-android16-6-maybe-dirty-4k'
PINNED = {
    'boot': (100663296, '225c40801ef77621b695fdd4cbf33e43c4350cd4ce41e600529ac768856434c6'),
    'vendor_boot': (100663296, '919fd35e11606e0b6f5e6e880a04267826601cd13b4982ab9ed8bd683cffe935'),
    'recovery': (104857600, 'c5e870b08c7473b309a18f2801289d713c7309a4c90c7b379d587d959406dccd'),
    'init_boot': (8388608, 'cfae242467af90e8507e916d65c03f123064b82658637b1f10ffe4ff96bf10ba'),
    'dtbo': (33554432, 'da72c9d42cd128b2cd6cf104a743b90d421d242b2d2d9b4371555ac99e86af41'),
    'vbmeta': (131072, '120551652e623417bd522b834ed0d05fda34c03a45d233ff2cc043a12da3fd14'),
    'vbmeta_system': (131072, '9ad88aa8f933002d061cd68b859eeafffe819aea15de9e81c633360d1df7b965'),
    'Image': (42506752, '2fa774b4ffdd75064fb733bb2cad071b02b1813ad5cd54bae32bda2247ef18a7'),
}
TARGET_RC = 'system/etc/init/hw/init.rc'
PUBLIC_KEY_SHA256 = '7728e30f50bfa5cea165f473175a08803f6a8346642b5aa10913e9d9e6defef6'


def json_write(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False, sort_keys=True)+'\n')


def read_pinned(path, key):
    data = path.read_bytes()
    require((len(data), sha(data)) == PINNED[key], 'Pinned input mismatch: '+key)
    return data


def parse_avb(image, partition):
    footer = image[-64:]
    require(footer[:4] == b'AVBf', partition+': missing AVB footer')
    major, minor, original_size, offset, size = struct.unpack_from('>IIQQQ', footer, 4)
    require((major, minor) == (1, 0) and not any(footer[36:]), 'Unsupported footer')
    require(original_size == offset and offset+size <= len(image)-64, 'Unexpected footer layout')
    require(not any(image[offset+size:-64]), 'Nonzero partition tail')
    vb = image[offset:offset+size]
    header = avbtool.AvbVBMetaHeader(vb[:256])
    expected_alg = 2 if partition == 'boot' else 0
    require(header.algorithm_type == expected_alg and header.flags == 0, 'Unexpected AVB algorithm/flags')
    require(256+header.authentication_data_block_size+header.auxiliary_data_block_size == size, 'VBMeta size mismatch')
    require(avbtool.verify_vbmeta_signature(header, vb), 'VBMeta authentication failed')
    aux_start = 256+header.authentication_data_block_size
    cursor = aux_start+header.descriptors_offset
    stop = cursor+header.descriptors_size
    require(stop <= len(vb), 'Descriptor block outside vbmeta')
    descriptors = []
    while cursor < stop:
        tag, following = struct.unpack_from('>QQ', vb, cursor)
        require(following % 8 == 0 and cursor+16+following <= stop, 'Descriptor bounds')
        raw = vb[cursor:cursor+16+following]
        d = {'tag': tag, 'offset': cursor, 'raw': raw}
        if tag == 2:
            h = avbtool.AvbHashDescriptor(raw)
            require(h.partition_name == partition and h.hash_algorithm == 'sha256', 'Hash descriptor mismatch')
            require(h.image_size == original_size and h.flags == 0, 'Hash descriptor size/flags mismatch')
            require(h.digest == hashlib.sha256(h.salt+image[:original_size]).digest(), 'Payload hash mismatch')
            d['parsed'] = h
        descriptors.append(d)
        cursor += len(raw)
    hashes = [d for d in descriptors if d['tag'] == 2]
    require(len(hashes) == 1, 'Expected exactly one payload descriptor')
    key = vb[aux_start+header.public_key_offset:aux_start+header.public_key_offset+header.public_key_size]
    if partition == 'boot':
        require(sha(key) == PUBLIC_KEY_SHA256, 'Unexpected original boot signing key')
    else:
        require(not key and header.authentication_data_block_size == 0, 'Unexpected NONE authentication material')
    return dict(footer=footer, original_size=original_size, offset=offset, size=size, vbmeta=vb,
                header=header, aux_start=aux_start, descriptors=descriptors, hash=hashes[0], key=key)


def avb_summary(a):
    h = a['header']; d = a['hash']['parsed']
    return dict(algorithm='SHA256_RSA4096' if h.algorithm_type == 2 else 'NONE',
                algorithm_type=h.algorithm_type, flags=h.flags, rollback_index=h.rollback_index,
                rollback_index_location=h.rollback_index_location, salt=d.salt.hex(),
                hash_descriptor_flags=d.flags, hash_algorithm=d.hash_algorithm,
                partition_name=d.partition_name, payload_bytes=d.image_size,
                digest=d.digest.hex(), vbmeta_offset=a['offset'], vbmeta_bytes=a['size'],
                public_key_sha256=sha(a['key']) if a['key'] else None,
                nonhash_descriptors=[blob_info(x['raw']) for x in a['descriptors'] if x['tag'] != 2],
                release_string=h.release_string)


def append_avb(payload, original, partition, key):
    a = parse_avb(original, partition)
    require(len(payload) % 4096 == 0, 'Payload must be page-aligned')
    require(len(payload)+align(a['size'], 4096)+4096 <= len(original), 'Payload exceeds partition')
    vb = bytearray(a['vbmeta']); h = a['header']; d = avbtool.AvbHashDescriptor(a['hash']['raw'])
    d.image_size = len(payload); d.digest = hashlib.sha256(d.salt+payload).digest()
    new_desc = d.encode()
    require(len(new_desc) == len(a['hash']['raw']), 'Descriptor size unexpectedly changed')
    pos = a['hash']['offset']
    vb[pos:pos+len(new_desc)] = new_desc
    if h.algorithm_type == 2:
        require(key.encode() == a['key'], 'Signing key differs byte-for-byte from captured boot')
        signed_data = bytes(vb[:256])+bytes(vb[a['aux_start']:])
        digest = hashlib.sha256(signed_data).digest()
        sig = key.sign('SHA256_RSA4096', signed_data)
        require(len(digest) == h.hash_size and len(sig) == h.signature_size, 'Auth length mismatch')
        vb[256+h.hash_offset:256+h.hash_offset+h.hash_size] = digest
        vb[256+h.signature_offset:256+h.signature_offset+h.signature_size] = sig
    footer = bytearray(a['footer'])
    struct.pack_into('>QQ', footer, 12, len(payload), len(payload))
    result = payload+bytes(vb)
    result += bytes(len(original)-64-len(result))+bytes(footer)
    after = parse_avb(result, partition)
    # Prove every other byte in VBMeta remains unchanged, including padding,
    # release string, algorithms, keys, rollback and property descriptors.
    restored = bytearray(after['vbmeta'])
    restored[pos:pos+len(new_desc)] = a['hash']['raw']
    if h.algorithm_type == 2:
        restored[256:256+h.authentication_data_block_size] = a['vbmeta'][256:256+h.authentication_data_block_size]
    require(restored == a['vbmeta'], 'Unexpected AVB metadata changed')
    footer_check = bytearray(after['footer']); footer_check[12:28] = a['footer'][12:28]
    require(footer_check == a['footer'], 'Unexpected footer fields changed')
    return result, {'original': avb_summary(a), 'test': avb_summary(after),
                    'all_other_vbmeta_bytes_preserved': True,
                    'full_chain_verification_claimed': False}


def cpio_record(name, data, fields):
    f = fields[:]; encoded = name.encode()+b'\0'
    f[6] = len(data); f[11] = len(encoded)
    header = b'070701'+b''.join(f'{x:08x}'.encode() for x in f)
    head = header+encoded; head += bytes(-len(head) % 4)
    result = head+data; result += bytes(-len(data) % 4)
    return result


def rebuild_cpio(original, remove, replacements, additions):
    entries = parse_cpio(original); names = {x['name'] for x in entries}
    require(set(replacements) <= names, 'Replacement path absent from input CPIO')
    kept, changes = [], []
    for e in entries[:-1]:
        n = e['name']
        if remove(e):
            changes.append(dict(name=n, action='removed', original=blob_info(e['data'])))
        elif n in replacements:
            require(e['fields'][1] & 0o170000 == 0o100000 and e['fields'][4] == 1,
                    'Replacement must be a singly linked regular file: '+n)
            data = replacements[n]
            kept.append(cpio_record(n, data, e['fields']))
            changes.append(dict(name=n, action='replaced', original=blob_info(e['data']), test=blob_info(data)))
        else:
            kept.append(original[e['start']:e['end']])
    inode = max(e['fields'][0] for e in entries)+1
    for n, data, mode in additions:
        require(n not in names or any(c['name'] == n and c['action'] == 'removed' for c in changes), 'Addition collides: '+n)
        fields = [inode, mode, 0, 0, 1, 0, len(data), 0, 0, 0, 0, len(n.encode())+1, 0]
        inode += 1
        kept.append(cpio_record(n, data, fields))
        changes.append(dict(name=n, action='added', test=blob_info(data), mode=oct(mode)))
    trailer = entries[-1]
    kept.append(original[trailer['start']:trailer['end']])
    result = b''.join(kept); result += bytes(-len(result) % 512)
    final = parse_cpio(result); final_map = {e['name']:e for e in final}
    removed_names = {c['name'] for c in changes if c['action'] == 'removed'}
    modified_names = set(replacements)
    for e in entries:
        if e['name'] in removed_names or e['name'] in modified_names:
            continue
        f = final_map[e['name']]
        require(original[e['start']:e['end']] == result[f['start']:f['end']], 'Unchanged CPIO record mutated: '+e['name'])
    return result, entries, final, changes


def android_header(image, expected_kernel):
    require(image[:8] == b'ANDROID!', 'Bad Android magic')
    k, r = struct.unpack_from('<II', image, 8)
    header_size, = struct.unpack_from('<I', image, 20)
    v, = struct.unpack_from('<I', image, 40)
    s, = struct.unpack_from('<I', image, 1580)
    require(v == 4 and header_size == 1584 and s == 0, 'Unexpected boot image version/signature')
    require(bool(k) == expected_kernel, 'Unexpected embedded kernel')
    return dict(kernel_bytes=k, ramdisk_bytes=r, header_bytes=header_size, header_version=v,
                boot_signature_bytes=s, os_version_raw=struct.unpack_from('<I', image, 16)[0],
                cmdline=image[44:1580].split(b'\0')[0].decode('ascii'))


def boot_payload(original, kernel):
    h = android_header(original, True)
    require(h['ramdisk_bytes'] == 0, 'Captured boot unexpectedly has a ramdisk')
    a = parse_avb(original, 'boot')
    require(align(4096+h['kernel_bytes'],4096) == a['original_size'], 'Unexpected boot payload layout')
    require(not any(original[4096+h['kernel_bytes']:a['original_size']]), 'Nonzero boot padding')
    header = bytearray(original[:4096]); struct.pack_into('<I', header, 8, len(kernel))
    payload = bytes(header)+kernel; payload += bytes(-len(payload) % 4096)
    return payload, h


def vendor_sections(original):
    require(original[:8] == b'VNDRBOOT', 'Bad vendor boot magic')
    version, page, _, _, r = struct.unpack_from('<IIIII', original, 8)
    header_size, dtb_size = struct.unpack_from('<II', original, 2096)
    table_size, num_entries, entry_size, bootconfig_size = struct.unpack_from('<IIII', original, 2112)
    require(version == 4 and page == 4096 and header_size == 2128, 'Unexpected vendor header')
    require((table_size, num_entries, entry_size) == (108, 1, 108), 'Unexpected vendor ramdisk table')
    positions = {'ramdisk':4096}
    positions['dtb'] = align(positions['ramdisk']+r,4096)
    positions['table'] = align(positions['dtb']+dtb_size,4096)
    positions['bootconfig'] = align(positions['table']+table_size,4096)
    sizes = {'ramdisk':r, 'dtb':dtb_size, 'table':table_size, 'bootconfig':bootconfig_size}
    sections = {n:original[positions[n]:positions[n]+sizes[n]] for n in positions}
    next_offset = [positions['dtb'], positions['table'], positions['bootconfig'], align(positions['bootconfig']+bootconfig_size,4096)]
    for n, end in zip(positions, next_offset):
        require(not any(original[positions[n]+sizes[n]:end]), 'Nonzero vendor padding: '+n)
    a = parse_avb(original, 'vendor_boot')
    require(next_offset[-1] == a['original_size'], 'Unexpected vendor payload layout')
    entry_r, offset_r, type_r = struct.unpack_from('<III', sections['table'])
    require((entry_r, offset_r, type_r) == (r,0,1), 'Unexpected vendor ramdisk entry')
    return sections, {n:dict(offset=positions[n], **blob_info(sections[n])) for n in positions}


def vendor_payload(original, ramdisk, sections):
    header = bytearray(original[:4096]); struct.pack_into('<I', header, 24, len(ramdisk))
    table = bytearray(sections['table']); struct.pack_into('<I', table, 0, len(ramdisk))
    payload = bytes(header)
    for data in [ramdisk, sections['dtb'], bytes(table), sections['bootconfig']]:
        payload += data; payload += bytes(-len(payload) % 4096)
    return payload


def recovery_payload(original, ramdisk):
    h = android_header(original, False)
    a = parse_avb(original, 'recovery')
    require(align(4096+h['ramdisk_bytes'],4096) == a['original_size'], 'Unexpected recovery payload layout')
    header = bytearray(original[:4096]); struct.pack_into('<I', header, 12, len(ramdisk))
    payload = bytes(header)+ramdisk; payload += bytes(-len(payload) % 4096)
    return payload, h


def inspect_generic_ramdisk(image, codec):
    """Read generic CPIO without rewriting its intentional duplicate dev entry."""
    header = android_header(image,False)
    raw = codec.decompress(image[4096:4096+header['ramdisk_bytes']])
    pos, records, seen = 0, [], set()
    while pos+110 <= len(raw):
        require(raw[pos:pos+6] == b'070701', 'Bad generic CPIO magic')
        fields = [int(raw[pos+6+i*8:pos+14+i*8],16) for i in range(13)]
        name_end = pos+110+fields[11]
        require(name_end <= len(raw) and raw[name_end-1] == 0, 'Generic CPIO name bounds')
        name = raw[pos+110:name_end-1].decode()
        start = align(name_end,4); end = align(start+fields[6],4)
        require(end <= len(raw), 'Generic CPIO data bounds')
        data = raw[start:start+fields[6]]
        classification = isolation.classify(name)
        require(classification == 'preserve' or name == 'system/etc/init/snapuserd.rc',
                'Unchanged generic ramdisk contains unreviewed action/module: '+name)
        if name == 'system/etc/init/snapuserd.rc':
            require(sha(data) == '3a6966f87823b2726a231e7244adf78ad91d581bf4e8b1580630ebb82cc6c498',
                    'Generic snapuserd rc differs from reviewed source')
            snapuserd_rc = data
        records.append(dict(name=name,mode=oct(fields[1]),duplicate=name in seen,
                            classification=classification,**blob_info(data)))
        seen.add(name);pos=end
        if name == 'TRAILER!!!':
            require(not any(raw[pos:]), 'Nonzero generic CPIO tail')
            return records, snapuserd_rc
    raise ValueError('Missing generic CPIO trailer')


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--original-dir', type=Path, required=True)
    ap.add_argument('--recovery', type=Path, required=True)
    ap.add_argument('--kernel', type=Path, required=True)
    ap.add_argument('--module-staging', type=Path, required=True, help='Directory containing lib/modules')
    ap.add_argument('--module-audit', type=Path, required=True, help='Audited build-order.json')
    ap.add_argument('--init-rc', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    args = ap.parse_args()
    out = args.out; (out/'test').mkdir(parents=True, exist_ok=True); (out/'evidence').mkdir(exist_ok=True)
    originals = {p:read_pinned(args.original_dir/(p+'.img'),p) for p in PINNED if p not in ['recovery','Image']}
    originals['recovery'] = read_pinned(args.recovery,'recovery')
    kernel = read_pinned(args.kernel,'Image')
    require(b'Linux version '+KERNEL_RELEASE.encode() in kernel, 'Expected r13 kernel release not found')
    audit = json.loads(args.module_audit.read_text())
    require(audit['count'] == 135 and audit['import_crcs_checked'] == 6476, 'Unexpected module audit scope')
    require(audit['kernel'] == {'bytes':len(kernel),'sha256':sha(kernel),'source':'objects/bazel-out/aarch64-fastbuild/bin/common/kernel_aarch64/Image'}, 'Audit kernel mismatch')
    expected_files = {m['filename']:{'bytes':m['bytes'],'sha256':m['sha256']} for m in audit['modules']}
    expected_files.update(audit['indexes'])
    module_dir = args.module_staging/'lib/modules'
    require({p.name for p in module_dir.iterdir()} == set(expected_files), 'Module staging file set mismatch')
    additions = []
    for name in sorted(expected_files):
        p = module_dir/name; require(p.is_file() and not p.is_symlink(), 'Module staging path not regular')
        data = p.read_bytes(); require(blob_info(data) == expected_files[name], 'Module staging hash mismatch: '+name)
        additions.append(('lib/modules/'+name, data, 0o100644))
    rc = args.init_rc.read_bytes()
    require(sha(rc) == '6631789e0a11de418bb33d0b82dc61638d5269ecb513b4090fd99cd3ed875112',
            'Diagnostic init rc differs from reviewed source')
    require(BUILD_ID.encode() in rc and b'service adbd ' in rc, 'Unexpected diagnostic rc')
    require(not any(line.strip().startswith((b'import ', b'insmod ', b'modprobe ', b'mount_all ', b'service recovery ')) for line in rc.splitlines()), 'Forbidden init rc command')
    codec = LegacyLz4(); key = avbtool.RSAPublicKey(str(Path(__file__).with_name('testkey_rsa4096.pem')))
    generic_records, generic_snapuserd_rc = inspect_generic_ramdisk(originals['init_boot'],codec)
    require(sha(key.encode()) == PUBLIC_KEY_SHA256, 'Public test key mismatch')
    results, evidence = {}, {}

    payload, header = boot_payload(originals['boot'], kernel)
    results['boot'], avb = append_avb(payload, originals['boot'], 'boot', key)
    new_header = android_header(results['boot'], True)
    expected_header = bytearray(results['boot'][:4096]); expected_header[8:12] = originals['boot'][8:12]
    require(bytes(expected_header) == originals['boot'][:4096], 'Unexpected boot header modification')
    evidence['boot'] = dict(original_header=header, test_header=new_header,
                            only_header_changed_field='kernel_size', kernel=blob_info(kernel), avb=avb)

    sections, old_sections = vendor_sections(originals['vendor_boot'])
    vendor_raw = codec.decompress(sections['ramdisk'])
    vendor_original_entries = parse_cpio(vendor_raw)
    require(all(isolation.classify(e['name']) in ['preserve','remove_module'] for e in vendor_original_entries),
            'Vendor CPIO unexpectedly contains init actions')
    vendor_additions = [('lib/modules',b'',0o40755)]+additions
    vendor_new, vb, va, vc = rebuild_cpio(vendor_raw, lambda e:isolation.classify(e['name']) == 'remove_module', {}, vendor_additions)
    vendor_compressed = codec.compress(vendor_new,9)
    require(codec.decompress(vendor_compressed) == vendor_new, 'Vendor LZ4 round trip')
    payload = vendor_payload(originals['vendor_boot'], vendor_compressed, sections)
    results['vendor_boot'], avb = append_avb(payload, originals['vendor_boot'], 'vendor_boot', key)
    new_sections, new_sections_info = vendor_sections(results['vendor_boot'])
    require(new_sections['dtb'] == sections['dtb'] and new_sections['bootconfig'] == sections['bootconfig'], 'DTB/bootconfig changed')
    table_check = bytearray(new_sections['table']); table_check[:4] = sections['table'][:4]
    require(bytes(table_check) == sections['table'], 'Unexpected vendor table changes')
    header_check = bytearray(results['vendor_boot'][:4096]); header_check[24:28] = originals['vendor_boot'][24:28]
    require(bytes(header_check) == originals['vendor_boot'][:4096], 'Unexpected vendor header changes')
    old_vendor_kos = [e['name'] for e in vb if e['name'].endswith('.ko')]
    final_vendor_kos = {e['name']:blob_info(e['data']) for e in va if e['name'].endswith('.ko')}
    require(final_vendor_kos == {'lib/modules/'+m['filename']:{'bytes':m['bytes'],'sha256':m['sha256']} for m in audit['modules']}, 'Final vendor KO set mismatch')
    evidence['vendor_boot'] = dict(original_sections=old_sections, test_sections=new_sections_info,
        cpio_original=blob_info(vendor_raw), cpio_test=blob_info(vendor_new),
        original_cpio_records=len(vb), test_cpio_records=len(va), original_KO_count=len(old_vendor_kos),
        test_KO_count=len(final_vendor_kos), all_test_KOs_match_audit=True,
        preserved_DTB_and_bootconfig_bytes=True, changed_header_field='vendor_ramdisk_size',
        changed_table_field='vendor_ramdisk_size', avb=avb)
    json_write(out/'evidence/vendor-cpio-changes.json',vc)
    json_write(out/'evidence/installed-modules.json',final_vendor_kos)

    rh = android_header(originals['recovery'],False)
    recovery_raw = codec.decompress(originals['recovery'][4096:4096+rh['ramdisk_bytes']])
    re = parse_cpio(recovery_raw)
    replacements = {e['name']:isolation.INERT_RC for e in re if isolation.classify(e['name']) == 'neutralize'}
    replacements.update({e['name']:rc for e in re if isolation.classify(e['name']) == 'replacement'})
    def old_module_entry(e):
        return isolation.classify(e['name']) == 'remove_module'
    recovery_new, rb, ra, rc_changes = rebuild_cpio(recovery_raw,old_module_entry,replacements,[])
    require(sum(e['name'].endswith('.ko') for e in rb) == 106, 'Unexpected original Recovery module count')
    require(not any(old_module_entry(e) for e in ra), 'Old recovery module/index retained')
    recovery_compressed = codec.compress(recovery_new,9)
    require(codec.decompress(recovery_compressed) == recovery_new,'Recovery LZ4 round trip')
    payload, header = recovery_payload(originals['recovery'],recovery_compressed)
    results['recovery'],avb = append_avb(payload,originals['recovery'],'recovery',key)
    header_check = bytearray(results['recovery'][:4096]); header_check[12:16] = originals['recovery'][12:16]
    require(bytes(header_check) == originals['recovery'][:4096], 'Unexpected recovery header changes')
    before_map = {e['name']:e for e in rb}; after_map = {e['name']:e for e in ra}
    preserved_executables = {}
    for name in ['init','system/bin/init','system/bin/ueventd','system/bin/adbd','system/bin/recovery']:
        require(before_map[name]['data'] == after_map[name]['data'], 'Runtime binary/symlink changed: '+name)
        preserved_executables['/'+name] = dict(**blob_info(after_map[name]['data']),mode=oct(after_map[name]['fields'][1]))
    evidence['recovery'] = dict(original_header=header,test_header=android_header(results['recovery'],False),
        only_header_changed_field='ramdisk_size', cpio_original=blob_info(recovery_raw),cpio_test=blob_info(recovery_new),
        original_cpio_records=len(rb),test_cpio_records=len(ra),original_KO_count=106,test_KO_count=0,
        disabled_init_rcs=sorted(n for n in replacements if n != TARGET_RC),
        main_init_rc=dict(path='/'+TARGET_RC,original_sha256=sha(before_map[TARGET_RC]['data']),test_sha256=sha(rc)),
        preserved_runtime_executables=preserved_executables, avb=avb)
    json_write(out/'evidence/recovery-cpio-changes.json',rc_changes)
    json_write(out/'evidence/unchanged-init-boot-cpio.json',generic_records)
    (out/'evidence/generic-snapuserd.rc').write_bytes(generic_snapuserd_rc)
    (out/'evidence/test-init.rc').write_bytes(rc)
    (out/'evidence/original-init.rc').write_bytes(before_map[TARGET_RC]['data'])
    verification = {}
    for part,data in results.items():
        path = out/'test'/(part+'.img'); path.write_bytes(data)
        cmd = [sys.executable,str(Path(__file__).with_name('avbtool.py')),'verify_image','--image',str(path)]
        if part == 'boot': cmd += ['--key',str(Path(__file__).with_name('testkey_rsa4096.pem'))]
        p = subprocess.run(cmd,capture_output=True,text=True)
        verification[part] = dict(returncode=p.returncode,stdout=p.stdout,stderr=p.stderr)
        require(p.returncode == 0, 'Official AVB verification failed: '+part)
    json_write(out/'evidence/official-avb-verification.json',verification)
    evidence.update(build_id=BUILD_ID,expected_kernel_release=KERNEL_RELEASE,
        input_originals={p:blob_info(d) for p,d in originals.items()},
        outputs={p:blob_info(d) for p,d in results.items()},
        unchanged_partitions=['init_boot','dtbo','vbmeta','vbmeta_system'],
        generic_ramdisk_review=dict(modules=0,unchanged=True,
            allowed_init_rc_exception='system/etc/init/snapuserd.rc',
            exception_sha256=sha(generic_snapuserd_rc),
            exception_note='Generic ramdisk may overlay the neutralized Recovery copy. Both snapuserd services are disabled, no diagnostic action starts them, and the sole stopped-property action only sets snapuserd.ready=false.'),
        compression=dict(format='legacy LZ4',block_bytes=8*1024*1024,hc_level=9,library_version=codec.version),
        module_audit_sha256=sha(args.module_audit.read_bytes()),
        all_unmodified_CPIO_records_preserved_byte_for_byte=True,
        only_modified_partitions=['boot','vendor_boot','recovery'],
        hardware_tested=False,android_boot_verified=False,full_AVB_chain_verification_claimed=False,
        AVB_scope='Captured top-level vbmeta flags already equal 3 and are not changed. Changed vendor_boot cannot match its unchanged top-level descriptor. Per-image footer validation does not prove end-to-end trust.')
    json_write(out/'evidence/image-validation.json',evidence)
    print(json.dumps(dict(outputs=evidence['outputs'],build_id=BUILD_ID,hardware_tested=False),indent=2))


if __name__ == '__main__':
    main()
