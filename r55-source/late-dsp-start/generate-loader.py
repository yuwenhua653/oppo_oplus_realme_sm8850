#!/usr/bin/env python3
"""Reproduce the R55 loader from the exact R54 baseline and reviewed snippet."""
import argparse, difflib, hashlib, json, pathlib, re
HERE=pathlib.Path(__file__).resolve().parent
BASELINE_SHA='50ec79db22771b5ba8f702e8dbb5bf347c5ac18430bfaa225bdb26e34f92d071'
HELPER_SHA='d6f2cb2fcae6df19c8058ad8cb0d03c02b2d7ad25d0a867cef773bb5b44264b3'
CANDIDATE_SHA='0cd37062546401c370734974406e1a901e887a985c6ef9a5e1c7711588b38541'
ANCHOR="    say 'SELECTED_READY 213/213; display/GPU, DSP and audio dependency trial, not full hardware support'\n"
def sha(data): return hashlib.sha256(data).hexdigest()
def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--baseline',required=True,type=pathlib.Path); parser.add_argument('--output',required=True,type=pathlib.Path); args=parser.parse_args()
    before=args.baseline.read_bytes(); helper=(HERE/'late-dsp-start.sh').read_bytes()
    if sha(before)!=BASELINE_SHA: raise SystemExit('REFUSED: baseline SHA-256 differs from reviewed R54')
    if sha(helper)!=HELPER_SHA: raise SystemExit('REFUSED: helper SHA-256 differs from reviewed snippet')
    text=before.decode(); snippet=helper.decode()
    if text.count(ANCHOR)!=1: raise SystemExit('REFUSED: selected-ready anchor is not unique')
    candidate=text.replace(ANCHOR,ANCHOR+snippet).encode()
    if sha(candidate)!=CANDIDATE_SHA: raise SystemExit('REFUSED: candidate SHA-256 differs')
    unchanged_prefix=before.split(b'\nvendor)\n')[0]==candidate.split(b'\nvendor)\n')[0]
    calls=lambda blob:re.findall(rb'^\s*(?:load_one|require_live)\b[^\n]*',blob,re.M)
    unchanged_calls=calls(before)==calls(candidate)
    if not unchanged_prefix or not unchanged_calls: raise SystemExit('REFUSED: existing stage or module gates changed')
    args.output.parent.mkdir(parents=True,exist_ok=True); args.output.write_bytes(candidate); args.output.chmod(0o755)
    print(json.dumps({'status':'PASS','baseline_sha256':BASELINE_SHA,'helper_sha256':HELPER_SHA,'candidate_sha256':CANDIDATE_SHA,'prefix_before_vendor_identical':unchanged_prefix,'module_calls_identical':unchanged_calls,'output':str(args.output)},indent=2))
if __name__=='__main__': main()
