#!/usr/bin/env python3
"""Compile and execute the real, extracted WLAN NSS and HT-IE functions.

Only surrounding kernel/QDF facilities are stubbed. This is a host semantic
regression, not a firmware, wire-layout, kernel-build or radio interoperability
test. Both locked preimage and candidate are executed; the preimage must
reproduce the asymmetric-band HT MCS leak and retain unrestricted 2G STA NSS.
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
SME = Path("qcom/opensource/wlan/qcacld-3.0/core/sme/src/common/sme_api.c")
LIM = Path("qcom/opensource/wlan/qcacld-3.0/core/mac/src/pe/lim/lim_utils.c")
FUNCTIONS = {
    str(SME): ("sme_get_nss_chain_shift", "sme_check_nss_chain_ini_param",
               "sme_fill_nss_chain_params", "sme_validate_from_ini_config",
               "sme_update_vdev_type_nss"),
    str(LIM): ("lim_populate_mcs_set_ht_per_vdev", "lim_send_ht_caps_ie"),
}


def extract(source, name):
    pattern = (r"^(?:static\s+)?(?:void|uint8_t|QDF_STATUS)\s+" +
               re.escape(name) + r"\s*\([^;{}]*\)\s*\{")
    matches = list(re.finditer(pattern, source, re.M))
    if len(matches) != 1:
        raise AssertionError(f"Expected exactly one definition of {name}: {len(matches)}")
    match = matches[0]
    start = source.index("{", match.start())
    depth = 1
    end = start + 1
    while depth:
        if source[end] == "{":
            depth += 1
        elif source[end] == "}":
            depth -= 1
        end += 1
    return source[match.start():end]


PRELUDE = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
typedef int QDF_STATUS;
#define QDF_STATUS_SUCCESS 0
#define QDF_STATUS_E_FAILURE 1
#define QDF_IS_STATUS_ERROR(x) ((x) != QDF_STATUS_SUCCESS)
#define QDF_IS_STATUS_SUCCESS(x) ((x) == QDF_STATUS_SUCCESS)
#define QDF_MIN(a,b) ((a) < (b) ? (a) : (b))
#ifndef WLAN_MAX_VDEV_NSS
#define WLAN_MAX_VDEV_NSS 2
#endif
#define NSS_1x1_MODE 1
#define sme_err(...) ((void)0)
#define sme_debug(...) ((void)0)
#define pe_err(...) ((void)0)
enum QDF_OPMODE {QDF_STA_MODE, QDF_SAP_MODE, QDF_P2P_GO_MODE,
 QDF_P2P_CLIENT_MODE, QDF_IBSS_MODE, QDF_P2P_DEVICE_MODE, QDF_OCB_MODE,
 QDF_TDLS_MODE, QDF_NAN_DISC_MODE, QDF_NDI_MODE};
enum nss_chains_band_info {NSS_CHAINS_BAND_2GHZ, NSS_CHAINS_BAND_5GHZ,
 NSS_CHAINS_BAND_MAX};
enum coex_btc_chain_mode {WLAN_COEX_BTC_CHAIN_MODE_UNSETTLED,
 WLAN_COEX_BTC_CHAIN_MODE_FDD, WLAN_COEX_BTC_CHAIN_MODE_HYBRID};
struct wlan_mlme_nss_chains {
 uint32_t rx_nss[2], tx_nss[2], num_rx_chains[2], num_tx_chains[2];
 uint32_t num_tx_chains_11a, num_tx_chains_11b, num_tx_chains_11g;
 uint32_t disable_rx_mrc[2], disable_tx_mrc[2];
};
struct vdev_type_nss {
 uint8_t sta, sap, p2p_go, p2p_cli, p2p_dev, ibss, tdls, ocb, nan, ndi;
};
struct mlme_cfg_stub {
 struct wlan_mlme_nss_chains nss_chains_ini_cfg;
 struct {struct {bool enable_mimo;} vht_cap_info;} vht_caps;
 struct {bool as_enabled;} gen;
};
struct mac_context {
 struct mlme_cfg_stub *mlme_cfg;
 void *psoc;
 struct vdev_type_nss vdev_type_nss_2g, vdev_type_nss_5g;
 struct {struct {bool channelBondingMode5GHz;} configParam;} roam;
};
typedef struct mac_context *mac_handle_t;
#define MAC_CONTEXT(x) (x)
static enum coex_btc_chain_mode test_btc;
static bool test_btc_error;
static QDF_STATUS ucfg_coex_psoc_get_btc_chain_mode(
 void *psoc, enum coex_btc_chain_mode *mode) {
 (void)psoc;
 *mode = test_btc;
 return test_btc_error ? QDF_STATUS_E_FAILURE : QDF_STATUS_SUCCESS;
}
/* Object and IE stubs provide observability; tested functions remain exact. */
struct wlan_objmgr_vdev {struct wlan_mlme_nss_chains ini;};
static struct wlan_objmgr_vdev test_vdev;
static bool test_vdev_missing, test_ini_missing;
static int test_refs;
#define WLAN_MLME_SB_ID 1
static struct wlan_objmgr_vdev *wlan_objmgr_get_vdev_by_id_from_psoc(
 void *psoc, uint8_t id, int ref) {
 (void)psoc; (void)id; (void)ref;
 if (test_vdev_missing) return NULL;
 test_refs++;
 return &test_vdev;
}
static void wlan_objmgr_vdev_release_ref(struct wlan_objmgr_vdev *vdev, int ref) {
 (void)vdev; (void)ref; test_refs--;
}
static struct wlan_mlme_nss_chains *mlme_get_ini_vdev_config(
 struct wlan_objmgr_vdev *vdev) {return test_ini_missing ? NULL : &vdev->ini;}
/* These named fields model mutation, not the production on-air bit layout. */
typedef struct sHtCaps {
 uint8_t supportedMCSSet[16];
 uint8_t advCodingCap, supportedChannelWidthSet, shortGI40MHz;
 uint8_t txBF, implicitTxBF, explicitCSITxBF;
} tHtCaps;
#define DOT11F_IE_HTCAPS_MIN_LEN ((unsigned)sizeof(tHtCaps))
#define DOT11F_EID_HTCAPS 45
#define CHAN_ENUM_2437 2437
#define CHAN_ENUM_5320 5320
#define CDS_BAND_2GHZ 0
#define CDS_BAND_5GHZ 1
static uint8_t test_global_mcs1;
static bool test_width_2g, test_nan_bf;
static int test_ie_fail_band = -1;
static tHtCaps sent_caps[2];
static unsigned sent_count[2], init_count;
static void lim_set_ht_caps(struct mac_context *mac, uint8_t *bytes, unsigned len) {
 (void)mac; assert(len == DOT11F_IE_HTCAPS_MIN_LEN + 2);
 tHtCaps *cap = (tHtCaps *)(bytes + 2);
 memset(cap, 0, sizeof(*cap));
 cap->supportedMCSSet[0] = 0xff;
 cap->supportedMCSSet[1] = test_global_mcs1;
 cap->txBF = 1; cap->implicitTxBF = 1; cap->explicitCSITxBF = 1;
 init_count++;
}
static bool lim_get_rx_ldpc(struct mac_context *mac, int channel) {
 (void)mac; return channel == CHAN_ENUM_5320;
}
static bool lim_get_sta_cb_mode_for_24ghz(struct mac_context *mac, uint8_t id) {
 (void)mac; (void)id; return test_width_2g;
}
static bool ucfg_nan_is_beamforming_supported(void *psoc) {
 (void)psoc; return test_nan_bf;
}
static QDF_STATUS lim_send_ie(struct mac_context *mac, uint8_t id, int eid,
 int band, uint8_t *buf, unsigned len) {
 (void)mac; (void)id;
 assert(eid == DOT11F_EID_HTCAPS && band >= 0 && band < 2);
 assert(len == sizeof(tHtCaps));
 memcpy(&sent_caps[band], buf, sizeof(tHtCaps));
 sent_count[band]++;
 return band == test_ie_fail_band ? QDF_STATUS_E_FAILURE : QDF_STATUS_SUCCESS;
}
'''

TESTS = r'''
static uint32_t packed(unsigned n) {
 uint32_t result = 0;
 for (unsigned shift = 0; shift <= 24; shift += 3) result |= n << shift;
 return result;
}
static void init_cfg(struct mlme_cfg_stub *cfg) {
 memset(cfg, 0, sizeof(*cfg));
 cfg->vht_caps.vht_cap_info.enable_mimo = true;
 for (unsigned b = 0; b < 2; b++) {
  cfg->nss_chains_ini_cfg.rx_nss[b] = packed(2);
  cfg->nss_chains_ini_cfg.tx_nss[b] = packed(2);
  cfg->nss_chains_ini_cfg.num_rx_chains[b] = packed(2);
  cfg->nss_chains_ini_cfg.num_tx_chains[b] = packed(2);
  cfg->nss_chains_ini_cfg.disable_rx_mrc[b] = 11 + b;
  cfg->nss_chains_ini_cfg.disable_tx_mrc[b] = 21 + b;
 }
 cfg->nss_chains_ini_cfg.num_tx_chains_11a = packed(2);
 cfg->nss_chains_ini_cfg.num_tx_chains_11b = packed(2);
 cfg->nss_chains_ini_cfg.num_tx_chains_11g = packed(2);
 test_btc = WLAN_COEX_BTC_CHAIN_MODE_UNSETTLED;
 test_btc_error = false;
}
static unsigned checks;
static void test_fill_matrix(void) {
 struct mlme_cfg_stub cfg;
 struct mac_context mac = {.mlme_cfg = &cfg};
 struct wlan_mlme_nss_chains out;
 const uint8_t rf_options[] = {1, 2, 4};
 for (unsigned n = 1; n <= 4; n++)
 for (unsigned rf_i = 0; rf_i < sizeof(rf_options); rf_i++)
 for (unsigned mimo = 0; mimo <= 1; mimo++)
 for (unsigned mode = QDF_STA_MODE; mode <= QDF_NDI_MODE; mode++)
 for (unsigned btc = 0; btc <= 2; btc++) {
  init_cfg(&cfg);
  cfg.vht_caps.vht_cap_info.enable_mimo = mimo;
  test_btc = (enum coex_btc_chain_mode)btc;
  for (unsigned b = 0; b < 2; b++) {
   cfg.nss_chains_ini_cfg.tx_nss[b] = packed(n);
   cfg.nss_chains_ini_cfg.rx_nss[b] = packed(n);
  }
  struct mlme_cfg_stub before = cfg;
  memset(&out, 0, sizeof(out));
  /* Explicitly test 5G immediately after 2G on the SAME destination. */
  for (unsigned b = 0; b < 2; b++) {
   sme_fill_nss_chain_params(&mac, &out, (enum QDF_OPMODE)mode,
                            (enum nss_chains_band_info)b, rf_options[rf_i]);
   unsigned expected = QDF_MIN(QDF_MIN(n, rf_options[rf_i]), WLAN_MAX_VDEV_NSS);
   if (!mimo || (!b && btc) || (CANDIDATE && !b && mode == QDF_STA_MODE))
    expected = 1;
   assert(out.rx_nss[b] == expected && out.tx_nss[b] == expected);
   assert(out.num_rx_chains[b] == QDF_MIN(2, rf_options[rf_i]));
   assert(out.num_tx_chains[b] == QDF_MIN(2, rf_options[rf_i]));
   assert(out.disable_rx_mrc[b] == 11 + b);
   assert(out.disable_tx_mrc[b] == 21 + b);
   assert(out.num_tx_chains_11a == QDF_MIN(2, rf_options[rf_i]));
   assert(out.num_tx_chains_11b == QDF_MIN(2, rf_options[rf_i]));
   assert(out.num_tx_chains_11g == QDF_MIN(2, rf_options[rf_i]));
   checks++;
  }
  assert(memcmp(&cfg, &before, sizeof(cfg)) == 0);
 }
 /* Existing NDI antenna-sharing cap and failed coex read retain semantics. */
 init_cfg(&cfg); cfg.gen.as_enabled = true; test_btc_error = true;
 test_btc = WLAN_COEX_BTC_CHAIN_MODE_FDD;
 sme_fill_nss_chain_params(&mac, &out, QDF_NDI_MODE, NSS_CHAINS_BAND_2GHZ, 2);
 assert(out.rx_nss[0] == 1);
 sme_fill_nss_chain_params(&mac, &out, QDF_NDI_MODE, NSS_CHAINS_BAND_5GHZ, 2);
 assert(out.rx_nss[1] == 2);
 sme_fill_nss_chain_params(&mac, &out, QDF_SAP_MODE, NSS_CHAINS_BAND_2GHZ, 2);
 assert(out.rx_nss[0] == 2);
 /* Simulate a later global packed NSS write: refill must enforce the policy. */
 init_cfg(&cfg);
 cfg.nss_chains_ini_cfg.rx_nss[0] = packed(4);
 cfg.nss_chains_ini_cfg.tx_nss[0] = packed(4);
 sme_fill_nss_chain_params(&mac, &out, QDF_STA_MODE, NSS_CHAINS_BAND_2GHZ, 4);
 assert(out.rx_nss[0] == (CANDIDATE ? 1 : WLAN_MAX_VDEV_NSS));
 assert(out.tx_nss[0] == (CANDIDATE ? 1 : WLAN_MAX_VDEV_NSS));
 /* Active dynamic update cannot exceed the newly stored instance INI cap. */
 struct wlan_mlme_nss_chains requested = out;
 requested.rx_nss[0] = requested.tx_nss[0] = 2;
 assert(sme_validate_from_ini_config(&requested, &out, NSS_CHAINS_BAND_2GHZ)
        == (CANDIDATE ? QDF_STATUS_E_FAILURE : QDF_STATUS_SUCCESS));
 checks += 5;
}
static void test_table(void) {
 struct mlme_cfg_stub cfg;
 struct mac_context mac = {.mlme_cfg = &cfg};
 for (unsigned n = 1; n <= 4; n++) {
  init_cfg(&cfg);
  cfg.nss_chains_ini_cfg.rx_nss[0] = packed(n);
  cfg.nss_chains_ini_cfg.rx_nss[1] = packed(n);
  for (unsigned b = 0; b < 2; b++) {
   sme_update_vdev_type_nss(&mac, 4, (enum nss_chains_band_info)b);
   struct vdev_type_nss *table = b ? &mac.vdev_type_nss_5g : &mac.vdev_type_nss_2g;
   assert(table->sta == ((CANDIDATE && !b) ? 1 : n));
   assert(table->sap == n && table->p2p_go == n && table->p2p_cli == n);
   assert(table->p2p_dev == n && table->ibss == n && table->tdls == n);
   assert(table->ocb == n && table->nan == n && table->ndi == n);
   checks++;
  }
 }
}
static void reset_ht(void) {
 memset(&test_vdev, 0, sizeof(test_vdev));
 memset(sent_caps, 0, sizeof(sent_caps));
 memset(sent_count, 0, sizeof(sent_count));
 test_refs = 0; test_vdev_missing = false; test_ini_missing = false;
 init_count = 0; test_ie_fail_band = -1;
 test_global_mcs1 = 0xff; test_width_2g = false; test_nan_bf = true;
}
static void test_ht_ie(void) {
 struct mlme_cfg_stub cfg;
 struct mac_context mac = {.mlme_cfg = &cfg};
 init_cfg(&cfg); mac.roam.configParam.channelBondingMode5GHz = true;
 /* Reproduce baseline's existing asymmetric-band buffer contamination. */
 reset_ht(); test_vdev.ini.rx_nss[0] = 1; test_vdev.ini.rx_nss[1] = 2;
 assert(lim_send_ht_caps_ie(&mac, QDF_STA_MODE, 0) == QDF_STATUS_SUCCESS);
 assert(sent_caps[0].supportedMCSSet[0] == 0xff);
 assert(sent_caps[0].supportedMCSSet[1] == 0);
 assert(sent_caps[1].supportedMCSSet[1] == (CANDIDATE ? 0xff : 0));
 assert(!sent_caps[0].advCodingCap && sent_caps[1].advCodingCap);
 assert(!sent_caps[0].supportedChannelWidthSet && sent_caps[1].supportedChannelWidthSet);
 assert(!sent_caps[0].shortGI40MHz && sent_caps[1].shortGI40MHz);
 assert(sent_count[0] == 1 && sent_count[1] == 1 && test_refs == 0);
 checks++;
 /* End-to-end from the real fill function into the real HT sender. */
 reset_ht();
 for (unsigned b = 0; b < 2; b++)
  sme_fill_nss_chain_params(&mac, &test_vdev.ini, QDF_STA_MODE,
                           (enum nss_chains_band_info)b, 2);
 assert(lim_send_ht_caps_ie(&mac, QDF_STA_MODE, 0) == QDF_STATUS_SUCCESS);
 assert(sent_caps[0].supportedMCSSet[1] == (CANDIDATE ? 0 : 0xff));
 assert(sent_caps[1].supportedMCSSet[1] == 0xff);
 checks++;
 /* Existing single-stream/global restrictions must never invent MCS support. */
 reset_ht(); test_vdev.ini.rx_nss[0] = 2; test_vdev.ini.rx_nss[1] = 1;
 assert(lim_send_ht_caps_ie(&mac, QDF_STA_MODE, 0) == QDF_STATUS_SUCCESS);
 assert(sent_caps[0].supportedMCSSet[1] == 0xff && !sent_caps[1].supportedMCSSet[1]);
 checks++;
 reset_ht(); test_global_mcs1 = 0;
 test_vdev.ini.rx_nss[0] = 2; test_vdev.ini.rx_nss[1] = 2;
 assert(lim_send_ht_caps_ie(&mac, QDF_STA_MODE, 0) == QDF_STATUS_SUCCESS);
 assert(!sent_caps[0].supportedMCSSet[1] && !sent_caps[1].supportedMCSSet[1]);
 checks++;
 /* Resetting the HT baseline must preserve the existing NAN BF restriction. */
 reset_ht(); test_nan_bf = false;
 test_vdev.ini.rx_nss[0] = 2; test_vdev.ini.rx_nss[1] = 2;
 assert(lim_send_ht_caps_ie(&mac, QDF_NDI_MODE, 0) == QDF_STATUS_SUCCESS);
 for (unsigned b = 0; b < 2; b++)
  assert(!sent_caps[b].txBF && !sent_caps[b].implicitTxBF && !sent_caps[b].explicitCSITxBF);
 checks++;
 /* Existing send failures and missing object cleanup retain behavior. */
 reset_ht(); test_ie_fail_band = 1;
 assert(lim_send_ht_caps_ie(&mac, QDF_STA_MODE, 0) == QDF_STATUS_E_FAILURE);
 assert(test_refs == 0);
 reset_ht(); test_vdev_missing = true;
 assert(lim_send_ht_caps_ie(&mac, QDF_STA_MODE, 0) == QDF_STATUS_SUCCESS);
 assert(test_refs == 0);
 reset_ht(); test_ini_missing = true;
 assert(lim_send_ht_caps_ie(&mac, QDF_STA_MODE, 0) == QDF_STATUS_SUCCESS);
 assert(test_refs == 0);
 checks += 3;
}
int main(void) {
 test_fill_matrix(); test_table(); test_ht_ie();
 printf("%s checks=%u\n", CANDIDATE ? "CANDIDATE_PASS" : "BASELINE_REPRODUCED", checks);
 return 0;
}
'''


def extracted_chunk(source, relative):
    # Preserve the upstream copyright and permission notice in every excerpt.
    if not source.startswith("/*"):
        raise AssertionError("Expected upstream file permission notice")
    pieces = [source[:source.index("*/") + 2]]
    if relative == str(SME):
        macro_start = source.index("#define STA_NSS_CHAINS_SHIFT")
        macro_end = source.index("\n\n", macro_start)
        pieces.append(source[macro_start:macro_end])
    pieces += [extract(source, function) for function in FUNCTIONS[relative]]
    return "\n\n".join(pieces) + "\n"


def pinned_chunks(root, name, workspace, fixtures_only):
    fixture_dir = root / "tests/fixtures"
    manifest = json.loads((fixture_dir / "NSS-FIXTURE-PROVENANCE.json").read_text())
    chunks, inputs = [], []
    for entry in manifest["variants"][name]:
        rel = entry["source_relative_path"]
        if workspace is not None and name == "payload":
            path = workspace / "vendor/qcom/sm8850-modules" / rel
            if not path.is_file():
                raise AssertionError(f"Prepared source missing: {path}")
            use_full = True
        else:
            path = root / name / rel
            use_full = path.is_file() and not fixtures_only
        if use_full:
            data = path.read_bytes()
            digest = hashlib.sha256(data).hexdigest()
            if digest != entry["source_sha256"] or len(data) != entry["source_bytes"]:
                raise AssertionError(f"Pinned source mismatch: {path}")
            chunk = extracted_chunk(data.decode(), rel)
            input_kind = "prepared_actual_source" if workspace and name == "payload" else "actual_full_source"
        else:
            path = fixture_dir / entry["fixture_file"]
            chunk = path.read_text()
            input_kind = "pinned_extracted_source_fixture"
        chunk_digest = hashlib.sha256(chunk.encode()).hexdigest()
        if chunk_digest != entry["fixture_sha256"]:
            raise AssertionError(f"Extracted function pin mismatch: {path}")
        chunks.append(chunk)
        inputs.append({"path": str(path), "kind": input_kind,
                       "source_sha256": entry["source_sha256"],
                       "source_bytes": entry["source_bytes"],
                       "executed_function_fixture_sha256": chunk_digest})
    return chunks, inputs


def run_variant(root, name, compiler, workspace=None, fixtures_only=False):
    chunks, inputs = pinned_chunks(root, name, workspace, fixtures_only)
    unit = "\n".join([f"#define CANDIDATE {int(name == 'payload')}", PRELUDE,
                       *chunks, TESTS])
    with tempfile.TemporaryDirectory(prefix="myron-nss-test-") as temp:
        source = Path(temp) / "test.c"
        binary = Path(temp) / "test"
        source.write_text(unit)
        profiles = []
        # Exact upstream Kbuild defaults to 2; the source also supports a 4-SS
        # build override. Exercise both instead of silently assuming one.
        for maximum in (2, 4):
            command = [compiler, "-std=c11", "-Wall", "-Wextra", "-Werror",
                       f"-DWLAN_MAX_VDEV_NSS={maximum}",
                       "-fsanitize=undefined", "-fno-sanitize-recover=all",
                       str(source), "-o", str(binary)]
            compiled = subprocess.run(command, capture_output=True, text=True, timeout=30)
            if compiled.returncode:
                raise AssertionError(compiled.stderr)
            result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=10)
            if result.returncode:
                raise AssertionError(f"{name}: {result.stdout}\n{result.stderr}")
            profiles.append({"WLAN_MAX_VDEV_NSS": maximum, "output": result.stdout.strip()})
    return {"variant": name, "status": "PASS", "profiles": profiles,
            "inputs": inputs,
            "compiled_actual_functions": 7, "sanitizer": "undefined"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--compiler", default=os.environ.get("CC", "cc"))
    parser.add_argument("--workspace", type=Path,
                        help="Prepared kernel workspace: require and execute real candidate source")
    parser.add_argument("--fixtures-only", action="store_true",
                        help="Execute shipped pinned function fixtures (baseline only with --workspace)")
    args = parser.parse_args()
    results = [run_variant(args.root, name, args.compiler, args.workspace, args.fixtures_only)
               for name in ("preimage", "payload")]
    print(json.dumps({"status": "PASS", "results": results,
                      "scope": "Extracted actual C semantics; no firmware or radio execution"}, indent=2))


if __name__ == "__main__":
    main()
