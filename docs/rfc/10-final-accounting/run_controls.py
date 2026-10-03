#!/usr/bin/env python3
"""Run both verifiers from a clean shared clone, plus the negative controls, and write raw/controls/*.txt.

Stdlib only; run under the lane's hostless wrapper:

  CONTROL_WORKDIR=<scratch dir outside the repo> CUA_LOOP_STATE=<STATE.json> [CUA_PRIVACY_NAMES_FILE=<file>] \
      python3 docs/rfc/10-final-accounting/run_controls.py <commit> <main clone> <out dir>

Every planted file (mutated STATE copy, private-name and autolink plants) is written under CONTROL_WORKDIR, never in
the repository or the artifact mirror, and removed at the end. Mutations of the deliverable JSON are applied inside
the throwaway clone and reverted after each control. Logs carry the control name, exit code, FAIL lines and the
summary line; they never print a planted value.
"""
import binascii
import json
import os
import shutil
import socket
import subprocess
import sys

REL10 = "docs/rfc/10-final-accounting/verify_artifacts.py"
REL74 = "docs/rfc/74-posting-queue/verify_artifacts.py"
ACC = "docs/rfc/10-final-accounting/accounting.json"
QUE = "docs/rfc/74-posting-queue/queue.json"


def run(cmd, cwd=None, env=None):
    return subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True)


def first_numeric_pointer(node):
    """Path to the first {value, from} pointer with a numeric value and a stated rounding."""
    if isinstance(node, dict):
        if "value" in node and "from" in node and isinstance(node["from"], dict):
            v = node["value"]
            if isinstance(v, (int, float)) and not isinstance(v, bool) and node["from"].get("round") is not None:
                return []
        for k, v in node.items():
            if k == "from":
                continue
            p = first_numeric_pointer(v)
            if p is not None:
                return [k] + p
    elif isinstance(node, list):
        for i, v in enumerate(node):
            p = first_numeric_pointer(v)
            if p is not None:
                return [i] + p
    return None


def get(node, path):
    for k in path:
        node = node[k]
    return node


def main():
    commit, main_clone, out_dir = sys.argv[1:4]
    work = os.environ["CONTROL_WORKDIR"]
    state = os.environ["CUA_LOOP_STATE"]
    os.makedirs(work, exist_ok=True)
    clone = os.path.join(work, "clean-clone")
    plants = os.path.join(work, "plants")
    for d in (clone, plants):
        shutil.rmtree(d, ignore_errors=True)
    os.makedirs(plants)
    r = run(["git", "clone", "-q", "--shared", "--no-checkout", main_clone, clone])
    assert r.returncode == 0, r.stderr
    r = run(["git", "-C", clone, "checkout", "-q", "--detach", commit])
    assert r.returncode == 0, r.stderr
    head = run(["git", "-C", clone, "rev-parse", "HEAD"]).stdout.strip()
    base_env = dict(os.environ)

    def verify(rel, env_over=None, extra=()):
        env = dict(base_env)
        env.update(env_over or {})
        return run([sys.executable, rel] + (["--extra-md"] + list(extra) if extra else []), cwd=clone, env=env)

    def log(name, res, note, rel):
        lines = [l for l in res.stdout.splitlines() if l.startswith("FAIL") or l.startswith("verify_artifacts:")]
        txt = "control: %s\ncommit: %s\nverifier: %s\nexpect: %s\nexit: %d\n%s\n" % (
            name, head, rel, note, res.returncode, "\n".join(lines))
        with open(os.path.join(out_dir, name + ".txt"), "w") as f:
            f.write(txt)
        return res.returncode

    def reset():
        run(["git", "-C", clone, "checkout", "-q", "--", "."])

    os.makedirs(out_dir, exist_ok=True)
    results = {}
    results["c00-clean-verify10"] = log("c00-clean-verify10", verify(REL10), "exit 0, FAIL 0", REL10)
    results["c01-clean-verify74"] = log("c01-clean-verify74", verify(REL74), "exit 0, FAIL 0", REL74)

    # c02: mutated STATE copy (one more reached request) -> gate inputs changed
    st = json.load(open(state))
    st["provider_budget"]["used_requests_reached_provider"] += 1
    mut = os.path.join(plants, "STATE-mutated.json")
    with open(mut, "w") as f:
        json.dump(st, f)
    os.chmod(mut, 0o600)
    results["c02-state-mutated"] = log("c02-state-mutated", verify(REL74, {"CUA_LOOP_STATE": mut}),
                                       "exit 1, F.state_extract_gate_inputs_unchanged FAIL", REL74)

    # c03 / c04: planted private name (the host name, plain and hex) in a file outside the repository
    host = socket.gethostname().split(".")[0]
    p1 = os.path.join(plants, "plant-name.md")
    with open(p1, "w") as f:
        f.write("planted control line: %s\n" % host)
    results["c03-private-name"] = log("c03-private-name", verify(REL10, extra=[p1]), "exit 1, H.extra plant-name.md FAIL",
                                      REL10)
    p2 = os.path.join(plants, "plant-name-hex.md")
    with open(p2, "w") as f:
        f.write("planted control line: %s\n" % binascii.hexlify(host.encode()).decode())
    results["c04-private-name-hex"] = log("c04-private-name-hex", verify(REL10, extra=[p2]),
                                          "exit 1, H.extra plant-name-hex.md FAIL (encoded)", REL10)

    # c05: planted upstream autolink
    p3 = os.path.join(plants, "plant-autolink.md")
    with open(p3, "w") as f:
        f.write("see trycua/cua#" + "4316 for the guard\n")
    results["c05-upstream-autolink"] = log("c05-upstream-autolink", verify(REL10, extra=[p3]),
                                           "exit 1, G.autolinks plant-autolink.md FAIL", REL10)

    # c06 / c07: a number off by one unit (in the last stated decimal) in each deliverable
    for name, rel_json, rel_v, check in (("c06-accounting-number-off-by-one", ACC, REL10, "A.acc.value"),
                                         ("c07-queue-number-off-by-one", QUE, REL74, "A.queue.value")):
        path = os.path.join(clone, rel_json)
        doc = json.load(open(path))
        ptr = first_numeric_pointer(doc)
        node = get(doc, ptr)
        nd = node["from"]["round"]
        node["value"] = round(node["value"] + 10 ** (-nd), nd) if nd else node["value"] + 1
        with open(path, "w") as f:
            json.dump(doc, f, indent=1)
        results[name] = log(name, verify(rel_v), "exit 1, %s FAIL at /%s" % (check, "/".join(map(str, ptr))),
                            rel_v)
        reset()

    # c08: READY NOW flipped on one entry
    path = os.path.join(clone, QUE)
    q = json.load(open(path))
    q["items"][0]["ready_now"]["READY_NOW"] = True
    with open(path, "w") as f:
        json.dump(q, f, indent=1)
    results["c08-ready-now-flipped"] = log("c08-ready-now-flipped", verify(REL74), "exit 1, E.READY_NOW FAIL", REL74)
    reset()

    # c09: bare number in free text
    q = json.load(open(path))
    q["items"][0]["fields"]["missing_evidence"].append("Seven of 37 rows still need a recheck.")
    with open(path, "w") as f:
        json.dump(q, f, indent=1)
    results["c09-bare-number"] = log("c09-bare-number", verify(REL74), "exit 1, D.no_bare_numbers FAIL", REL74)
    reset()

    results["c10-clean-again"] = log("c10-clean-again", verify(REL10), "exit 0, FAIL 0", REL10)
    shutil.rmtree(plants, ignore_errors=True)
    shutil.rmtree(clone, ignore_errors=True)
    print(json.dumps({"commit": head, "exit_codes": results}, indent=1))


if __name__ == "__main__":
    main()
