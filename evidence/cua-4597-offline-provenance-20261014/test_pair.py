"""Characterization plus a separately labelled proposed, unapproved parity assertion."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
import release_attribution
import release_channels

PACKET = Path(__file__).resolve().parent
ROOT = Path(os.environ["CUA_ATTRIBUTION_SOURCE"])
OUTPUT = Path(os.environ["CUA_ATTRIBUTION_OUTPUT"])
SHA = "c8edda06be53e13a759c69de125ce37189023954"
PARENT = "1553a3f360ea12155be3bc77e27c427ca62f967a"


def snapshot(name):
    return json.loads((PACKET / "metadata" / name).read_text())["data"]


class RecordedGitHub:
    """No HTTP client: exact requests return unchanged captured API objects."""

    def __init__(self):
        self.calls = []

    def pull(self, repository, number):
        assert (repository, number) == ("trycua/cua", 4500)
        self.calls.append(["pull", repository, number])
        return snapshot("4500.json")

    def pull_commits(self, repository, number):
        assert (repository, number) == ("trycua/cua", 4500)
        self.calls.append(["pull_commits", repository, number])
        return snapshot("4500-commits.json")

    def issue(self, repository, number):
        assert (repository, number) == ("trycua/cua", 4477)
        self.calls.append(["issue", repository, number])
        return snapshot("4477.json")


@pytest.fixture
def paired():
    registry = json.loads((ROOT / ".github/releases/components.json").read_text())
    component = registry["components"]["cua-driver-rs"]
    paths = sorted(set(component["changeDetectionPaths"] + registry["sharedChangePaths"]))
    excludes = sorted(set(component["changeDetectionExcludePaths"]))
    companions = sorted(set(component["changeDetectionCompanionPaths"]))
    config_path = ROOT / ".github/release-attribution-config.json"
    config = json.loads(config_path.read_text())
    pull = snapshot("4500.json")
    commit_rows = snapshot("4500-commits.json")
    assert pull["merge_commit_sha"] == SHA
    assert pull["commits"] == len(commit_rows) == 5
    assert pull["merged_by"]["login"] == "ddupont808"
    assert any(
        (row.get("author") or {}).get("login") == "ddupont808"
        and row["commit"]["author"]["name"].strip().lower() == "dillon dupont"
        for row in commit_rows
    )
    unresolved = release_channels.nightly_attribution_preflight(
        root=ROOT, previous_tag=PARENT, source_ref=SHA, paths=paths,
        exclude_paths=excludes, exclude_companion_paths=companions, config_path=config_path,
    )
    records = release_attribution.commits_in_range(
        ROOT, PARENT, SHA, paths, excludes, companions
    )
    assert len(records) == 1 and records[0].sha == SHA
    client = RecordedGitHub()
    contributors, issues, visual = release_attribution._change_contributors(
        pull, records[0], client, "trycua/cua", config
    )
    observation = {
        "range": PARENT + ".." + SHA,
        "record_count": len(records),
        "commit_subject": records[0].subject,
        "preflight_unresolved": unresolved,
        "manifest_contributors": contributors,
        "linked_issues": issues,
        "release_visual": visual,
        "recorded_api_calls": client.calls,
        "requirement_status": "Parity is a proposed consistency expectation, not maintainer-approved policy",
    }
    (OUTPUT / "observation.json").write_text(json.dumps(observation, indent=2) + "\n")
    print("OBSERVATION", json.dumps(observation, sort_keys=True))
    return observation


def test_current_paired_behavior(paired):
    assert paired["preflight_unresolved"] == [{
        "sha": SHA, "name": "Dillon DuPont", "email": "dillondupont808@gmail.com"
    }]
    assert {"login": "ddupont808", "role": "coauthor", "external": False} in paired["manifest_contributors"]
    assert {"login": "wszkxlllll", "role": "author", "external": True} in paired["manifest_contributors"]
    assert {"login": "wszkxlllll", "role": "reporter", "external": True} in paired["manifest_contributors"]
    assert paired["linked_issues"] == [4477]
    assert paired["recorded_api_calls"] == [
        ["pull_commits", "trycua/cua", 4500], ["issue", "trycua/cua", 4477]
    ]


def test_PROPOSED_consistency_expectation(paired):
    assert paired["preflight_unresolved"] == [], (
        "PROPOSED EXPECTATION ONLY: this metadata-resolvable identity would not be held "
        "if preflight and manifest shared the accepted provenance rule; no maintainer "
        "requirement or permission to change identity/admission policy is implied"
    )

