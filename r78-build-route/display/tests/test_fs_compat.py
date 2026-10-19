#!/usr/bin/env python3
"""Focused host C check using unchanged locked Linux 6.12 FS declarations.

The complete file_operations declaration and actual vfs_llseek implementation
come from checksum-verified upstream files. The production initializer and
callback signatures are extracted without inventing missing kernel API names.
This is not a full kernel/module build or a test of callback implementations.
"""
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile


HERE = Path(__file__).resolve().parent
FIXTURES = HERE / "fixtures"
SOURCE = (HERE.parent / "payload/qcom/opensource/display-drivers/msm/dsi/"
          "myron_mi_clone.c")


def require(pattern, text, label):
    matches = list(re.finditer(pattern, text, re.MULTILINE))
    if len(matches) != 1:
        raise RuntimeError(f"Expected exactly one real {label}, found {len(matches)}")
    return matches[0].group(0)


def locked_sources():
    provenance = json.loads((FIXTURES / "FS-PROVENANCE.json").read_text())
    if provenance["commit"] != "41a2024a9e2eb66ab0643a865d74943b4ee3cff8":
        raise RuntimeError("Unexpected common kernel revision")
    sources = {}
    for entry in provenance["fixtures"]:
        data = (FIXTURES / entry["fixture"]).read_bytes()
        if hashlib.sha256(data).hexdigest() != entry["sha256"]:
            raise RuntimeError(f"Locked FS fixture checksum mismatch: {entry['fixture']}")
        sources[entry["path"]] = data.decode()
    # Missing provenance entries are errors, never substituted with fake APIs.
    return sources["include/linux/fs.h"], sources["fs/read_write.c"]


PREAMBLE = r'''
#define _GNU_SOURCE
#include <assert.h>
#include <errno.h>
#include <stddef.h>
#include <stdint.h>
#include <sys/types.h>
/* Host-only type/annotation scaffolding, not replacement FS API definitions. */
#define __bitwise
#define __force
#define __user
#define __randomize_layout
#define THIS_MODULE ((struct module *)0)
typedef unsigned int fmode_t;
typedef unsigned int __poll_t;
typedef void *fl_owner_t;
typedef struct poll_table_struct poll_table;
'''


FILE_SCAFFOLD = r'''
/* Only fields read by the real vfs_llseek are needed by this host test. */
struct file {
    fmode_t f_mode;
    const struct file_operations *f_op;
    loff_t f_pos;
};
'''


MAIN = r'''
int main(void)
{
    /* Linux do_dentry_open clears FMODE_LSEEK when ->llseek is NULL.
     * Model its resulting mode here; do not claim to compile the open path.
     * Preserve PREAD/PWRITE: the production open behavior is unchanged.
     */
    const fmode_t opened_modes[] = {
        FMODE_READ,
        FMODE_READ | FMODE_PREAD,
        FMODE_READ | FMODE_PWRITE,
        FMODE_READ | FMODE_PREAD | FMODE_PWRITE
    };
    const loff_t offsets[] = {-1, 0, 4096};
    assert(myron_clone_fops.llseek == NULL);
    for (size_t mode = 0; mode < sizeof(opened_modes) / sizeof(opened_modes[0]); ++mode) {
        struct file file = {opened_modes[mode], &myron_clone_fops, 17};
        assert(!(file.f_mode & FMODE_LSEEK));
        for (int whence = 0; whence < 3; ++whence) {
            for (size_t offset = 0; offset < sizeof(offsets) / sizeof(offsets[0]); ++offset) {
                assert(vfs_llseek(&file, offsets[offset], whence) == -ESPIPE);
                assert(file.f_pos == 17);
                assert(file.f_mode == opened_modes[mode]);
            }
        }
    }
    return 0;
}
'''


def compile_result(options, path, output):
    return subprocess.run(options + [str(path), "-o", str(output)],
                          capture_output=True, text=True)


def main():
    fs_header, read_write = locked_sources()
    if re.search(r"\bno_llseek\b", fs_header):
        raise RuntimeError("Unexpected no_llseek declaration in locked kernel")
    fops_type = require(r"struct file_operations \{[\s\S]*?\n\} __randomize_layout;",
                        fs_header, "file_operations declaration")
    fop_flags_type = require(r"^typedef unsigned int __bitwise fop_flags_t;",
                            fs_header, "fop_flags_t declaration")
    mode_macros = "\n".join(require(rf"^#define {name}\s+[^\n]+", fs_header, name)
                            for name in ("FMODE_READ", "FMODE_LSEEK", "FMODE_PREAD", "FMODE_PWRITE"))
    vfs = require(r"^loff_t vfs_llseek\(struct file \*file, loff_t offset, int whence\)"
                  r"\n\{[^}]*\n\}", read_write, "vfs_llseek implementation")
    source = SOURCE.read_text()
    initializer = require(r"^static const struct file_operations myron_clone_fops = "
                          r"\{[\s\S]*?^\};", source, "production file_operations initializer")
    if not re.search(r"^\s*\.llseek\s*=\s*NULL,", initializer, re.MULTILINE):
        raise RuntimeError("Production llseek must be explicitly NULL")
    # The entire kernel structure is retained, including unused members. Opaque
    # forward declarations suffice because all external struct uses are pointers.
    external_types = sorted(set(re.findall(r"\bstruct (\w+)", fops_type)) - {"file_operations"})
    forward = "\n".join(f"struct {name};" for name in external_types)
    callbacks = []
    for member, name in re.findall(r"^\s*\.(\w+)\s*=\s*(\w+)\s*,", initializer, re.MULTILINE):
        if member in ("owner", "llseek"):
            continue
        declaration = require(rf"^static (?:int|long|ssize_t|__poll_t) {name}\([^)]*\)",
                              source, f"production {member} callback signature")
        callbacks.append(declaration + " { return 0; }")
    if len(callbacks) != 6:
        raise RuntimeError("Expected all six real clone callback signatures")
    unit = (PREAMBLE + forward + "\n" + fop_flags_type + "\n" + fops_type + "\n"
            + mode_macros + "\n" + FILE_SCAFFOLD + "\n" + "\n".join(callbacks)
            + "\n" + initializer + "\n" + vfs + "\n" + MAIN)
    compiler = shutil.which("cc")
    if compiler is None:
        raise RuntimeError("A host C compiler (cc) is required")
    common_options = [compiler, "-std=c11", "-Wall", "-Wextra", "-Werror",
                      "-Wno-unused-parameter", "-Wno-unused-function",
                      "-fsanitize=undefined", "-fno-sanitize-recover=all"]
    with tempfile.TemporaryDirectory(prefix="r78-fs-compat-") as temporary:
        directory = Path(temporary)
        current = directory / "current.c"
        current.write_text(unit)
        old_initializer, count = re.subn(r"(\.llseek\s*=\s*)NULL\b", r"\1no_llseek", initializer)
        if count != 1:
            raise RuntimeError("Failed to construct exactly one old unsupported initializer")
        old = directory / "old.c"
        old.write_text(unit.replace(initializer, old_initializer, 1))
        for compat in (False, True):
            options = common_options + (["-DCONFIG_COMPAT=1"] if compat else [])
            executable = directory / ("current-compat" if compat else "current-native")
            result = compile_result(options, current, executable)
            if result.returncode:
                raise RuntimeError("Real file_operations compatibility failed:\n" + result.stderr)
            subprocess.run([str(executable)], check=True, capture_output=True, text=True)
            rejected = compile_result(options, old, directory / "old")
            if rejected.returncode == 0 or "no_llseek" not in rejected.stderr:
                raise RuntimeError("Old no_llseek compile failure was not reproduced")
    print(json.dumps({"passed": True,
                      "file_operations": "complete locked kernel declaration",
                      "callback_signatures_checked": 6,
                      "configs": ["native", "CONFIG_COMPAT"],
                      "old_no_llseek_compile": "rejected in both configs",
                      "production_null_llseek_compile": "passed in both configs",
                      "real_vfs_llseek_espipe_cases": 72,
                      "scope": "focused host C test; not full kernel/module compilation"}, indent=2))


if __name__ == "__main__":
    main()
