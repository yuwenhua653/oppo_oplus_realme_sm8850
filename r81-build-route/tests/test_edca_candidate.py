#!/usr/bin/env python3
"""Execute pinned actual EDCA and CSA C functions with host dependency stubs.

This verifies host field selection and cache invalidation, not firmware, ABI,
AP interoperability or radio performance. Both baseline and candidate execute.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
BASE = "qcom/opensource/wlan/qcacld-3.0/"
FUNCTIONS = {
    BASE + "core/mac/src/pe/sch/sch_beacon_process.c": ("sch_beacon_edca_process",),
    BASE + "core/mac/src/pe/lim/lim_utils.c": ("lim_switch_channel_cback",),
}


def extract(source, name):
    pattern = (r"^(?:static\s+)?(?:void|uint8_t|QDF_STATUS)\s+" +
               re.escape(name) + r"\s*\([^;{}]*\)\s*\{")
    matches = list(re.finditer(pattern, source, re.M))
    if len(matches) != 1:
        raise AssertionError(f"Expected one definition of {name}: {len(matches)}")
    m = matches[0]
    pos = source.index("{", m.start())
    depth = 1
    end = pos + 1
    while depth:
        if source[end] == "{":
            depth += 1
        elif source[end] == "}":
            depth -= 1
        end += 1
    return source[m.start():end]


PRELUDE = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef int QDF_STATUS;
#define QDF_STATUS_SUCCESS 0
#define QDF_STATUS_E_FAILURE 1
#define QDF_IS_STATUS_ERROR(x) ((x) != QDF_STATUS_SUCCESS)
#define pe_err(...) ((void)0)
#define pe_debug(...) ((void)0)
static unsigned info_events;
#define pe_info_rl(...) ((void)++info_events)
enum QDF_OPMODE {QDF_STA_MODE, QDF_SAP_MODE, QDF_P2P_GO_MODE,
 QDF_P2P_CLIENT_MODE, QDF_IBSS_MODE, QDF_P2P_DEVICE_MODE, QDF_OCB_MODE,
 QDF_TDLS_MODE, QDF_NAN_DISC_MODE, QDF_NDI_MODE, QDF_MONITOR_MODE};
enum {QCA_WLAN_AC_BE, QCA_WLAN_AC_BK, QCA_WLAN_AC_VI, QCA_WLAN_AC_VO,
 QCA_WLAN_AC_ALL};
/* Named fields model mutations; they do not model the production wire ABI. */
typedef struct {
 struct {uint8_t aci, aifsn, acm;} aci;
 struct {uint8_t min, max;} cw;
 uint16_t txoplimit;
 uint8_t no_ack;
} tSirMacEdcaParamRecord;
typedef struct {
 struct {uint8_t count:4;} qosInfo;
 tSirMacEdcaParamRecord acbe, acbk, acvi, acvo;
} tSirMacEdcaParamSetIE;
struct wlan_channel {int ch_freq, ch_width, ch_freq_seg1, ch_cfreq1,
 ch_freq_seg2, ch_cfreq2, ch_phymode;};
struct wlan_objmgr_vdev {bool follow;
 struct {struct wlan_channel *des_chan;} vdev_mlme;};
struct vdev_mlme_obj {struct wlan_objmgr_vdev *vdev;};
struct pe_session {
 struct wlan_objmgr_vdev *vdev;
 enum QDF_OPMODE opmode;
 uint32_t curr_op_freq, curr_req_chan_freq;
 uint8_t gLimEdcaParamSetCount, vdev_id, peSessionId, smeSessionId;
 tSirMacEdcaParamRecord gLimEdcaParams[4];
 struct {int sec_ch_offset;} gLimChannelSwitch;
 unsigned char bssId[6];
};
struct mlme_config {
 struct {
  bool enable_edca_params;
  struct {uint8_t vo_aifs, vo_cwmin, vo_cwmax;} edca_ac_vo;
  struct {uint8_t vi_aifs, vi_cwmin, vi_cwmax;} edca_ac_vi;
  struct {uint8_t bk_aifs, bk_cwmin, bk_cwmax;} edca_ac_bk;
  struct {uint8_t be_aifs, be_cwmin, be_cwmax;} edca_ac_be;
 } edca_params;
};
struct mac_context {struct mlme_config *mlme_cfg;};
static bool mlme_get_follow_ap_edca_flag(struct wlan_objmgr_vdev *vdev)
 {return vdev->follow;}
/* Regulatory dependency stub covers representative valid bands plus unknown. */
static bool wlan_reg_is_24ghz_ch_freq(uint32_t freq)
 {return freq >= 2412 && freq <= 2484;}
struct scheduler_msg {int type; void *bodyptr; int bodyval;};
struct switch_channel_ind {
 int messageType, length, freq, sessionId;
 struct {int ch_width, sec_ch_offset, center_freq_seg0, mhz_freq_seg0,
 center_freq_seg1, mhz_freq_seg1;} chan_params;
 int ch_phymode;
 QDF_STATUS status;
 struct {unsigned char bytes[6];} bssid;
};
#define REASON_CHANNEL_SWITCH_FAILED 1
#define eLIM_HOST_DISASSOC 2
#define eWNI_SME_SWITCH_CHL_IND 3
#define CH_WIDTH_20MHZ 20
#define QDF_MAC_ADDR_SIZE 6
#define MTRACE(...) ((void)0)
#define qdf_mem_copy memcpy
static struct vdev_mlme_obj *test_mlme;
static bool fail_restore, fail_alloc;
static unsigned torn_down, restored, notified, started;
static void lim_tear_down_link_with_ap(struct mac_context *m, int id, int r, int t)
 {(void)m; (void)id; (void)r; (void)t; torn_down++;}
static struct vdev_mlme_obj *wlan_vdev_mlme_get_cmpt_obj(struct wlan_objmgr_vdev *v)
 {(void)v; return test_mlme;}
static QDF_STATUS lim_restore_pre_channel_switch_state(struct mac_context *m,
 struct pe_session *s) {(void)m; (void)s; restored++;
 return fail_restore ? QDF_STATUS_E_FAILURE : QDF_STATUS_SUCCESS;}
static void *qdf_mem_malloc(size_t n) {return fail_alloc ? NULL : calloc(1,n);}
static void sys_process_mmh_msg(struct mac_context *m, struct scheduler_msg *msg)
 {(void)m; assert(msg->type == eWNI_SME_SWITCH_CHL_IND);
 assert(((struct switch_channel_ind *)msg->bodyptr)->status == QDF_STATUS_SUCCESS);
 notified++; free(msg->bodyptr);}
static void lim_switch_channel_vdev_started(struct pe_session *s)
 {(void)s; started++;}
'''

TESTS = r'''
static unsigned checks;
static struct mlme_config cfg;
static struct mac_context mac;
static struct wlan_objmgr_vdev vdev;
static struct wlan_channel chan;
static struct vdev_mlme_obj mlme;
static struct pe_session session;
static tSirMacEdcaParamSetIE ap;
static tSirMacEdcaParamRecord *ap_ac(unsigned ac) {
 switch(ac) {case 0:return &ap.acbe; case 1:return &ap.acbk;
 case 2:return &ap.acvi; default:return &ap.acvo;}
}
static void init_case(void) {
 memset(&cfg,0,sizeof(cfg)); memset(&session,0,sizeof(session));
 memset(&vdev,0,sizeof(vdev)); memset(&chan,0,sizeof(chan));
 memset(&ap,0,sizeof(ap));
 cfg.edca_params.enable_edca_params=true;
 cfg.edca_params.edca_ac_be.be_aifs=2;
 cfg.edca_params.edca_ac_bk.bk_aifs=2;
 cfg.edca_params.edca_ac_vi.vi_aifs=2;
 cfg.edca_params.edca_ac_vo.vo_aifs=2;
 cfg.edca_params.edca_ac_be.be_cwmin=2;
 cfg.edca_params.edca_ac_bk.bk_cwmin=2;
 cfg.edca_params.edca_ac_vi.vi_cwmin=2;
 cfg.edca_params.edca_ac_vo.vo_cwmin=2;
 cfg.edca_params.edca_ac_be.be_cwmax=3;
 cfg.edca_params.edca_ac_bk.bk_cwmax=3;
 cfg.edca_params.edca_ac_vi.vi_cwmax=3;
 cfg.edca_params.edca_ac_vo.vo_cwmax=3;
 mac.mlme_cfg=&cfg; session.vdev=&vdev; session.curr_op_freq=2437;
 session.vdev_id=7; session.opmode=QDF_STA_MODE;
 for(unsigned ac=0;ac<4;ac++) {
  tSirMacEdcaParamRecord *r=ap_ac(ac);
  r->aci.aci=ac; r->aci.aifsn=3+ac; r->aci.acm=ac&1;
  r->cw.min=4+ac; r->cw.max=10+ac; r->txoplimit=31+19*ac;
  r->no_ack=ac&1;
 }
 ap.qosInfo.count=5; session.gLimEdcaParamSetCount=5;
 session.curr_req_chan_freq=5180; chan.ch_freq=5180; chan.ch_width=40;
 vdev.vdev_mlme.des_chan=&chan; mlme.vdev=&vdev; test_mlme=&mlme;
 fail_restore=false; fail_alloc=false;
 torn_down=restored=notified=started=info_events=0;
}
static void check_edca(bool overridden) {
 for(unsigned ac=0;ac<4;ac++) {
  tSirMacEdcaParamRecord expected=*ap_ac(ac);
  if(overridden) {expected.aci.aifsn=2;expected.cw.min=2;expected.cw.max=3;}
  assert(memcmp(&expected,&session.gLimEdcaParams[ac],sizeof(expected))==0);
  checks++;
 }
 assert(session.gLimEdcaParamSetCount==ap.qosInfo.count);
}
static void test_policy_matrix(void) {
 const uint32_t freqs[]={0,2412,2437,2484,5180,5955};
 for(unsigned mode=0;mode<=QDF_MONITOR_MODE;mode++)
 for(unsigned f=0;f<sizeof(freqs)/sizeof(freqs[0]);f++)
 for(unsigned enabled=0;enabled<2;enabled++)
 for(unsigned follow=0;follow<2;follow++)
 for(unsigned count=0;count<16;count++) {
  init_case();session.opmode=mode;session.curr_op_freq=freqs[f];
  cfg.edca_params.enable_edca_params=enabled;vdev.follow=follow;
  ap.qosInfo.count=count;
  struct mlme_config before_cfg=cfg;
  tSirMacEdcaParamSetIE before_ap=ap;
  struct wlan_objmgr_vdev before_vdev=vdev;
  assert(sch_beacon_edca_process(&mac,&ap,&session)==QDF_STATUS_SUCCESS);
  bool scoped=(mode==QDF_STA_MODE && f>=1 && f<=3);
  check_edca(enabled && !follow && !(CANDIDATE && scoped));
  assert(memcmp(&cfg,&before_cfg,sizeof(cfg))==0);
  assert(memcmp(&ap,&before_ap,sizeof(ap))==0);
  assert(memcmp(&vdev,&before_vdev,sizeof(vdev))==0);
  assert(info_events==(unsigned)(CANDIDATE && scoped));
 }
 init_case();mac.mlme_cfg=NULL;
 struct pe_session before=session;
 assert(sch_beacon_edca_process(&mac,&ap,&session)==QDF_STATUS_E_FAILURE);
 assert(memcmp(&before,&session,sizeof(session))==0);checks++;
}
static void test_csa_status_and_roles(void) {
 for(unsigned mode=0;mode<=QDF_MONITOR_MODE;mode++)
 for(unsigned failure=0;failure<6;failure++) {
  init_case();session.opmode=mode;
  if(failure==2)test_mlme=NULL;
  if(failure==3)vdev.vdev_mlme.des_chan=NULL;
  if(failure==4)fail_restore=true;
  if(failure==5)fail_alloc=true;
  lim_switch_channel_cback(&mac,failure==1?QDF_STATUS_E_FAILURE:QDF_STATUS_SUCCESS,
                          NULL,&session);
  bool completed_policy=(failure==0 || failure==5);
  assert(session.gLimEdcaParamSetCount==
         ((CANDIDATE && mode==QDF_STA_MODE && completed_policy)?255:5));
  assert(torn_down==(unsigned)(failure==1));
  assert(notified==(unsigned)(failure==0));
  assert(started==(unsigned)(failure==0));
  checks++;
 }
}
static void test_unchanged_ap_count_across_csa(void) {
 const uint32_t hops[]={2437,5180,2437,5955,2437};
 init_case(); session.curr_op_freq=hops[0];
 assert(sch_beacon_edca_process(&mac,&ap,&session)==QDF_STATUS_SUCCESS);
 for(unsigned h=1;h<sizeof(hops)/sizeof(hops[0]);h++) {
  session.curr_req_chan_freq=hops[h];chan.ch_freq=hops[h];
  lim_switch_channel_cback(&mac,QDF_STATUS_SUCCESS,NULL,&session);
  /* This is the existing beacon/probe consumer condition, not a new hook. */
  bool refresh=ap.qosInfo.count!=session.gLimEdcaParamSetCount;
  assert(refresh==(bool)CANDIDATE);
  if(refresh)assert(sch_beacon_edca_process(&mac,&ap,&session)==QDF_STATUS_SUCCESS);
  check_edca(!(CANDIDATE && hops[h]==2437));
 }
}
int main(void) {
 test_policy_matrix();test_csa_status_and_roles();test_unchanged_ap_count_across_csa();
 printf("%s_PASS checks=%u\n",CANDIDATE?"CANDIDATE":"BASELINE",checks);
 return 0;
}
'''


def pin(data):
    return {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def get_chunks(root, variant, workspace, fixtures_only):
    provenance = json.loads((root / "tests/fixtures/EDCA-FIXTURE-PROVENANCE.json").read_text())
    chunks, inputs = [], []
    for rel, names in FUNCTIONS.items():
        row = provenance[variant][rel]
        path = root / variant / rel
        actual = path.is_file() and not fixtures_only
        if workspace and variant == "payload":
            path = workspace / "vendor/qcom/sm8850-modules" / rel
            actual = True
        if actual:
            data = path.read_bytes()
            assert pin(data) == row["source"], f"Source pin mismatch: {path}"
            chunk = "\n\n".join(extract(data.decode(), name) for name in names) + "\n"
            kind = "prepared_actual_source" if workspace and variant == "payload" else "actual_full_source"
        else:
            path = root / "tests/fixtures" / row["fixture_file"]
            chunk = path.read_text()
            kind = "pinned_extracted_source_fixture"
        assert pin(chunk.encode()) == row["fixture"], f"Function pin mismatch: {path}"
        chunks.append(chunk)
        inputs.append({"path": str(path), "kind": kind, "source": row["source"],
                       "executed_functions": list(names), "fixture": row["fixture"]})
    return chunks, inputs


def run_variant(root, variant, compiler, workspace, fixtures_only):
    chunks, inputs = get_chunks(root, variant, workspace, fixtures_only)
    unit = "\n".join([f"#define CANDIDATE {int(variant == 'payload')}", PRELUDE, *chunks, TESTS])
    with tempfile.TemporaryDirectory(prefix="myron-edca-test-") as temp:
        source, binary = Path(temp) / "test.c", Path(temp) / "test"
        source.write_text(unit)
        cmd = [compiler, "-std=c11", "-Wall", "-Wextra", "-Werror",
               "-Wno-unused-parameter", "-Wno-unused-function",
               "-fsanitize=undefined", "-fno-sanitize-recover=all", str(source), "-o", str(binary)]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode:
            raise AssertionError(result.stderr)
        result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=10)
        if result.returncode:
            raise AssertionError(variant + ": " + result.stdout + result.stderr)
    return {"variant": variant, "status": "PASS", "output": result.stdout.strip(),
            "inputs": inputs, "compiled_actual_functions": 2, "sanitizer": "undefined"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--compiler", default=os.environ.get("CC", "cc"))
    parser.add_argument("--workspace", type=Path)
    parser.add_argument("--fixtures-only", action="store_true")
    args = parser.parse_args()
    results = [run_variant(args.root, v, args.compiler, args.workspace, args.fixtures_only)
               for v in ("preimage", "payload")]
    print(json.dumps({"status": "PASS", "results": results,
                      "scope": "Actual host EDCA selection and CSA invalidation; no radio/firmware execution"}, indent=2))


if __name__ == "__main__":
    main()
