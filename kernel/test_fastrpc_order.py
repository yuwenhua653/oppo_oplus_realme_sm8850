#!/usr/bin/env python3
"""Regression coverage for the R123 FastRPC sibling-order fix, without dtc."""
import copy
import hashlib
from pathlib import Path
import struct
import tempfile
import unittest

import source_dt as dt


# Keep fixtures independent of the production policy constants: changing a
# reviewed parent or count must require an intentional test update.
DOMAINS = (
    ('remoteproc-adsp@03000000', 'remoteproc_adsp_glink', 6),
    ('remoteproc-cdsp@32300000', 'remoteproc_cdsp_glink', 11),
)


def cell(number):
    return struct.pack('>I', number)


def node(name, properties=None, children=None):
    return [name, properties or {}, children or []]


def flatten(tree):
    yield tree
    for child in tree[2]:
        yield from flatten(child)


def encode(tree):
    """Small test-only FDT writer; includes arbitrary reserve and trailing bytes."""
    names = sorted({key for _, props, _ in flatten(tree) for key in props})
    strings = b''
    offsets = {}
    for name in names:
        offsets[name] = len(strings)
        strings += name.encode() + b'\0'

    def padded(value):
        return value + b'\0' * (-len(value) % 4)

    def tokens(item):
        name, props, children = item
        data = cell(1) + padded(name.encode() + b'\0')
        for key, value in props.items():
            data += cell(3) + cell(len(value)) + cell(offsets[key]) + padded(value)
        data += b''.join(tokens(child) for child in children)
        return data + cell(2)

    structure = tokens(tree) + cell(9)
    reserve = struct.pack('>4Q', 0x12340000, 0x1000, 0, 0)
    struct_offset = 40 + len(reserve)
    strings_offset = struct_offset + len(structure)
    total = strings_offset + len(strings)
    header = struct.pack('>10I', 0xd00dfeed, total, struct_offset,
                         strings_offset, 40, 17, 16, 7,
                         len(strings), len(structure))
    return header + reserve + structure + strings + b'preserved trailing bytes'


def compute_nodes(count, reverse=False):
    children = [node('compute-cb@%d' % number, {
        'compatible': b'qcom,fastrpc-compute-cb\0',
        'reg': cell(number),
        'phandle': cell(0x100 + number),
        'test-payload': bytes([number, 0, 0xff]),
    }, [node('nested', {'bytes': bytes([number, 0x42])})])
        for number in range(1, count + 1)]
    return children[::-1] if reverse else children


def runtime(reverse=False):
    children = [node('untouched-before', {'marker': b'first\0'})]
    for name, _, count in DOMAINS:
        parent = node('qcom,fastrpc', {'compatible': b'qcom,fastrpc\0'},
                      compute_nodes(count, reverse))
        children.append(node(name, {'reg': cell(count)},
                             [node('glink-edge', children=[parent])]))
    children.append(node('untouched-after', {'marker': b'last\0'}))
    return node('', {'compatible': b'test,myron\0'},
                [node('soc', children=children)])


def overlay(reverse=False):
    fragments, fixups = [], {}
    for index, (_, symbol, count) in enumerate(DOMAINS):
        fragment = 'fragment@%d' % index
        fixups[symbol] = ('/' + fragment + ':target:0\0').encode()
        fragments.append(node(fragment, {'target': cell(0xffffffff)}, [
            node('__overlay__', children=[node('qcom,fastrpc', {
                'compatible': b'qcom,fastrpc\0'}, compute_nodes(count, reverse))])]))
    return node('', children=fragments + [node('__fixups__', fixups)])


def fastrpc_parents(tree):
    return [item for item in flatten(tree) if item[0] == 'qcom,fastrpc']


class FastRpcOrderTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / 'canoe-dsp.dtbo'
        self.path.write_bytes(encode(overlay()))
        self.files = {'canoe-dsp.dtbo': self.path}
        self.spec = {'file': 'canoe.dtb', 'overlays': ['canoe-dsp.dtbo']}
        self.profile = {
            'device': 'Redmi K90PM / myron', 'bases': [self.spec],
            'reviewed_fastrpc_child_order': [
                {'parent': '/soc/' + name + '/glink-edge/qcom,fastrpc',
                 'overlay_target_symbol': symbol,
                 'children': ['compute-cb@%d' % i for i in range(1, count + 1)]}
                for name, symbol, count in DOMAINS],
        }

    def restore(self, data, profile=None):
        return dt.restore_fastrpc_order(data, profile or self.profile,
                                       self.spec, self.files)

    def test_reversed_domains_restore_exact_expected_bytes(self):
        before = encode(runtime(reverse=True))
        expected = encode(runtime())
        self.assertEqual(len(dt.fastrpc_order_errors(before, self.profile)), 2)
        after, proof = self.restore(before)
        # This checks the entire header, reserve map, properties, phandles,
        # nested descendants, unrelated siblings, string table and suffix.
        self.assertEqual(after, expected)
        self.assertFalse(dt.fastrpc_order_errors(after, self.profile))
        self.assertTrue(all(row['changed'] for row in proof['changes']))
        self.assertEqual(proof['source_proof']['sha256'],
                         hashlib.sha256(self.path.read_bytes()).hexdigest())
        self.assertEqual(self.restore(after)[0], after)

    def test_already_correct_domains_are_byte_identical(self):
        before = encode(runtime())
        after, proof = self.restore(before)
        self.assertEqual(after, before)
        self.assertFalse(any(row['changed'] for row in proof['changes']))

    def test_unreviewed_runtime_child_sets_and_orders_fail(self):
        for domain in range(2):
            for fault in ('mixed', 'missing', 'extra', 'wrong-compatible'):
                with self.subTest(domain=domain, fault=fault):
                    tree = runtime(reverse=True)
                    parent = fastrpc_parents(tree)[domain]
                    if fault == 'mixed':
                        parent[2][0], parent[2][1] = parent[2][1], parent[2][0]
                    elif fault == 'missing':
                        parent[2].pop()
                    elif fault == 'extra':
                        parent[2].append(node('unexpected-child'))
                    else:
                        parent[2][0][1]['compatible'] = b'unreviewed,child\0'
                    with self.assertRaises(ValueError):
                        self.restore(encode(tree))

    def test_runtime_parent_compatible_is_required(self):
        for domain in range(2):
            with self.subTest(domain=domain):
                tree = runtime(reverse=True)
                fastrpc_parents(tree)[domain][1]['compatible'] = b'unreviewed,parent\0'
                with self.assertRaises(ValueError):
                    self.restore(encode(tree))

    def test_source_order_and_fixup_are_verified(self):
        for fault in ('reversed-source', 'wrong-target', 'missing-fixup',
                      'ambiguous-fixup', 'wrong-source-compatible'):
            with self.subTest(fault=fault):
                tree = overlay(reverse=fault == 'reversed-source')
                if fault == 'wrong-target':
                    tree[2][0][1]['target'] = cell(1)
                elif fault == 'missing-fixup':
                    del tree[2][-1][1]['remoteproc_adsp_glink']
                elif fault == 'ambiguous-fixup':
                    tree[2][-1][1]['remoteproc_adsp_glink'] += b'/fragment@1:target:0\0'
                elif fault == 'wrong-source-compatible':
                    fastrpc_parents(tree)[0][1]['compatible'] = b'unreviewed,parent\0'
                self.path.write_bytes(encode(tree))
                with self.assertRaises(ValueError):
                    self.restore(encode(runtime(reverse=True)))

    def test_unreviewed_policy_device_and_overlay_fail(self):
        for fault in ('policy', 'device', 'base', 'missing-overlay', 'duplicate-overlay'):
            with self.subTest(fault=fault):
                profile = copy.deepcopy(self.profile)
                if fault == 'policy':
                    profile['reviewed_fastrpc_child_order'][1]['children'].reverse()
                elif fault == 'device':
                    profile['device'] = 'another-device'
                elif fault == 'base':
                    profile['bases'] = []
                else:
                    profile['bases'][0]['overlays'] = ([] if fault == 'missing-overlay'
                                                      else ['canoe-dsp.dtbo'] * 2)
                # Passing the profile's own changed base tests overlay admission,
                # rather than only rejection of a mismatched base object.
                spec = profile['bases'][0] if profile['bases'] else self.spec
                with self.assertRaises(ValueError):
                    dt.restore_fastrpc_order(encode(runtime(reverse=True)), profile,
                                            spec, self.files)


if __name__ == '__main__':
    unittest.main()
