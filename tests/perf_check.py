"""Measure scan_layer / check_hip on a large generated scene (not run by default).

Run (the last line is ``PERF nodes=... scan_layer=...s check_hip=...s``):

    "D:/Program Files/Side Effects Software/Houdini 21.0.512/bin/hython.exe" tests/perf_check.py [package_dir]

``package_dir`` is the directory that contains the ``hipcheck`` package;
default: the repo's ``python`` directory. Pass another one to time an older
copy of the package.
"""

import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, sys.argv[1] if len(sys.argv) > 1
                else os.path.join(ROOT, "python"))

import hou  # noqa: E402

from hipcheck import scan  # noqa: E402

NODES = 3000
FILES = 300


def main():
    build_start = time.time()
    hou.hipFile.clear(suppress_save_prompt=True)
    geo = hou.node("/obj").createNode("geo", "perf_geo")
    for flag in (hou.nodeFlag.Display, hou.nodeFlag.Render,
                 hou.nodeFlag.Template, hou.nodeFlag.Footprint):
        geo.setGenericFlag(flag, False)
    geo.createNode("null", "out_sink", run_init_scripts=False)

    previous = None
    for index in range(NODES):
        node = geo.createNode("xform", "x%04d" % index, run_init_scripts=False)
        if previous is not None:
            node.setInput(0, previous)
        previous = node

    for index in range(FILES):
        node = geo.createNode("file", "f%04d" % index, run_init_scripts=False)
        node.parm("filemode").set("read")
        node.parm("file").set("$HIP/perf_missing_$F4_%04d.bgeo" % index)
    print("BUILT nodes=%d in %.1fs" % (NODES + FILES, time.time() - build_start),
          flush=True)

    start = time.time()
    result = scan.scan_layer(geo)
    scan_seconds = time.time() - start
    print("SCANNED layer in %.3fs" % scan_seconds, flush=True)
    start = time.time()
    issues = scan.check_hip()
    check_seconds = time.time() - start

    print("PERF nodes=%d groups=%d grouped_nodes=%d issues=%d "
          "scan_layer=%.3fs check_hip=%.3fs"
          % (NODES + FILES, len(result["groups"]),
             sum(len(group["node_paths"]) for group in result["groups"]),
             len(issues), scan_seconds, check_seconds), flush=True)


if __name__ == "__main__":
    main()
