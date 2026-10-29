"""Shared cpio-entry policy for the R17 r13 USB-only diagnostic image.

This module does not unpack, modify, flash or execute images. Builders may call
classify(name) for EVERY entry of EVERY component ramdisk before overlaying.
"""
from pathlib import PurePosixPath

MAIN_RC = "system/etc/init/hw/init.rc"
BUILD_ID = "R17-R13-USB-20261011-01"
INERT_RC = b"# Disabled in R17-R13-USB-20261011-01; no actions or services.\n"


def classify(name):
    """Return replacement, neutralize, remove_module, or preserve.

    Normalize cpio's optional ./ prefix only; reject unsafe paths upstream.
    The main init rc is supplied after all component archives are merged.
    """
    while name.startswith("./"):
        name = name[2:]
    p = PurePosixPath(name)
    if p.is_absolute() or ".." in p.parts:
        raise ValueError("Unsafe cpio entry: " + name)
    if name == MAIN_RC or name == "init.rc":
        return "replacement"
    # Android automatically scans these trees even without an explicit import.
    if name.endswith(".rc") and any(name.startswith(t + "/etc/init/") for t in
                                    ("system", "system_ext", "vendor", "odm", "product")):
        return "neutralize"
    # No root recovery/init imports may survive in a future fallback init path.
    if len(p.parts) == 1 and p.name.startswith("init.") and p.name.endswith(".rc"):
        return "neutralize"
    # Remove original module trees, including symlinks and metadata files, from
    # recovery/vendor/generic ramdisks. Only the separately audited r13 tree may
    # be inserted afterwards, so duplicate cpio entries cannot restore old KOs.
    if any(p.parts[i:i + 2] == ("lib", "modules") for i in range(len(p.parts) - 1)):
        return "remove_module"
    if p.name.endswith((".ko", ".ko.xz", ".ko.gz", ".ko.zst")):
        return "remove_module"
    return "preserve"
