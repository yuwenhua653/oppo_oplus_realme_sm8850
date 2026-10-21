#!/usr/bin/env python3
"""Execute frozen author fault-injection fixtures against composed production C."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
from extract import function, section

HERE = Path(__file__).resolve().parent
FLAGS = ['cc', '-std=gnu11', '-O1', '-g', '-Wall', '-Wextra', '-Werror',
         '-Wstrict-prototypes', '-Wno-unused-function', '-fsanitize=address,undefined',
         '-fno-omit-frame-pointer', '-no-pie']
CONTROL_FUNCTIONS = ['checksum', 'fg_set_fastcharge_mode', 'StringToHex', 'fg_sha256_auth',
                     'get_verify_digest', 'set_verify_digest', 'fg_set_force_report_full']
MAC_SHARED = ['__fg_read_block', '__fg_write_block', 'checksum', 'fg_write_read_block']
MAC_NEW = ['fg_mac_read_frame_locked', 'fg_mac_read_block_variable']
MAC_POST = ['fg_mac_read_block', 'fg_mac_read_block_checked', 'fg_mac_write_block',
            'fg_get_manu_info', 'fg_get_manufacture_data', '__fg_mac_read_block', 'fg_get_temp_max',
            'fg_read_max_cell_volt', 'fg_get_calibration_ffc_iterm', 'fg_get_calibration_charge_energy',
            'fg_get_real_supplement_energy', 'fg_read_tsim', 'fg_read_tambient', 'fg_read_tremq',
            'fg_read_tfullchgq', 'fg_get_temp_min']


def pin(data):
    return {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


def assemble(kind, source, header, original):
    if kind == 'mac':
        names = MAC_SHARED + ([] if original else MAC_NEW) + MAC_POST
        if not original:
            names.insert(names.index('fg_mac_write_block'), 'fg_mac_write_block_locked')
        bodies = {name: function(source, name, last=name in ('__fg_read_block', '__fg_write_block'))
                  for name in names}
        declarations = '\n'.join([section(header, 'enum bq_fg_mac_cmd {', '};'),
                                  section(header, 'enum fg_vendor {', '};'),
                                  section(header, 'enum manu_macro {', '};'),
                                  section(header, '#define TERMINATION_BYTE', '\n};'),
                                  section(header, 'static struct manu_data manu_info', '\n};')])
        code = (HERE / 'mac/prefix.c').read_text() + '\n' + declarations + '\n'
        code += '\n\n'.join(bodies.values()) + '\n' + (HERE / 'mac/cases.c').read_text()
        if original:
            code = '#define ORIGINAL_NEGATIVE 1\n' + code
        flags = ['-Wno-pointer-sign', '-Wno-missing-field-initializers', '-ftrivial-auto-var-init=pattern']
    elif kind == 'probe':
        names = ['fg_read_vendor', 'fg_read_one_probe_ok', 'bq_parse_dt']
        if not original:
            names.append('bq_setup_co_gpio')
        names += ['fg_set_term_config', 'bq_fg_probe']
        bodies = {name: function(source, name) for name in names}
        executable_bodies = dict(bodies)
        # Both original and final production use the same conditional probe
        # signature. Select the retained6.12 one-argument branch for this host.
        body = bodies['bq_fg_probe']
        executable_bodies['bq_fg_probe'] = 'static int bq_fg_probe(struct i2c_client *client)\n' + body[body.index('{'):]
        code = (HERE / 'probe/fixture.c').read_text().replace('/* PRODUCTION_FUNCTIONS */',
                                                             '\n\n'.join(executable_bodies.values()))
        flags = ['-Wno-unused-parameter', '-Wno-misleading-indentation']
    else:
        bodies = {name: function(source, name) for name in CONTROL_FUNCTIONS}
        code = (HERE / 'control/host.h').read_text() + '\n' + '\n\n'.join(bodies.values())
        code += '\n' + (HERE / 'control/tests.inc').read_text()
        flags = ['-pthread'] + (['-Wno-pointer-sign'] if original else [])
    return code, flags, {name: pin(body.encode()) for name, body in bodies.items()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--suite', choices=('mac', 'probe', 'control'), required=True)
    parser.add_argument('--source', required=True, type=Path)
    parser.add_argument('--before', required=True, type=Path)
    parser.add_argument('--header', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    env = dict(os.environ, ASAN_OPTIONS='detect_leaks=0:abort_on_error=1',
               UBSAN_OPTIONS='halt_on_error=1:print_stacktrace=1')
    commands = []
    functions = {}
    def run(argv, expected_failure=False):
        result = subprocess.run(list(map(str, argv)), capture_output=True, text=True, env=env, timeout=60)
        commands.append({'argv': list(map(str, argv)), 'returncode': result.returncode,
                         'stdout': result.stdout, 'stderr': result.stderr})
        if expected_failure:
            if result.returncode == 0 or 'CHECK FAILED' not in result.stderr:
                raise RuntimeError('Original source did not reproduce its specific semantic assertion: ' + str(argv))
        elif result.returncode != 0:
            raise RuntimeError(str(argv) + '\n' + result.stdout + result.stderr)
        return result
    for kind, path in (('candidate', args.source), ('original', args.before)):
        code, flags, functions[kind] = assemble(args.suite, path.read_text(), args.header.read_text(), kind == 'original')
        c_file = out / (kind + '.c')
        c_file.write_text(code)
        run(FLAGS + flags + ['-o', out / (kind + '-tests'), c_file])
    positive = run([out / 'candidate-tests'])
    if args.suite == 'mac':
        run([out / 'original-tests'])
        negatives = 'Three original transport/frame defects are asserted by the unchanged ORIGINAL_NEGATIVE fixture.'
    elif args.suite == 'probe':
        run([out / 'original-tests', '--original-negative'])
        negatives = 'Four original probe/vendor defects are asserted by the unchanged --original-negative fixture.'
    else:
        negatives = []
        for case in ('busy-drop', 'short-auth', 'digest-publication', 'auth-error-propagation'):
            run([out / 'candidate-tests', case])
            run([out / 'original-tests', case], expected_failure=True)
            negatives.append({'case': case, 'candidate': 'PASS', 'original': 'EXPECTED_PRODUCTION_ASSERTION_FAILURE'})
    report = {'schema': 1, 'status': 'PASS_COMPOSED_PRODUCTION_C_AND_ORIGINAL_NEGATIVES', 'suite': args.suite,
              'source': pin(args.source.read_bytes()), 'before': pin(args.before.read_bytes()),
              'header': pin(args.header.read_bytes()), 'production_function_pins': functions,
              'stdout': positive.stdout, 'original_negative_proof': negatives,
              'Werror_ASan_UBSan': True, 'LeakSanitizer': False, 'hardware_tested': False,
              'commands': commands}
    (out / 'RESULT.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    print(positive.stdout, end='')


if __name__ == '__main__':
    main()
