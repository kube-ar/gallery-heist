"""The precinct works a case end to end with a scripted detective (no LLM)."""

from heist.case import list_cases, load_case
from heist.precinct import Precinct


def scripted_detective(case) -> Precinct:
    """Follows the evidence the way the board's solver does, but only through the desk's tools."""
    desk = Precinct(case)
    desk.call("briefing")
    room, wing = case.meta["room"]["id"], case.meta["room"]["wing"]
    seen, found = case.meta["last_seen"][11:], case.meta["discovered"][11:]
    plan = desk.call("floor_plan")
    in_wing = {r["id"] for r in plan["rooms"] if r["wing"] == wing} | {"R32"}
    dark = [
        e
        for e in desk.call("camera_log", {"start": seen, "end": found})
        if e["status"] == "offline" and e["room"] in in_wing
    ]
    start = min(e["time"] for e in dark)
    office = [r for r in desk.call("keycard_log", {"room": "R34", "end": start}) if r["result"] == "granted"]
    last_in_office = {}
    for r in office:
        last_in_office[r["holder"]] = r["time"]
    candidates = sorted(last_in_office)
    best = (0, None, None)
    for person in candidates:
        calls = desk.call("phone_records", {"person": person})
        if isinstance(calls, dict):
            continue
        near = [c for c in calls if c["start"][11:] >= seen and c["start"][11:] <= found]
        others = {}
        for c in near:
            other = c["to"] if c["from"] == person else c["from"]
            others[other] = others.get(other, 0) + 1
        for other, n in others.items():
            if n > best[0] and other[:2] in ("E-", "G-", "C-"):
                best = (n, person, other)
    _, accomplice, culprit = best
    opened = [
        r for r in desk.call("keycard_log", {"room": room, "start": seen, "end": found}) if r["result"] == "granted"
    ]
    if opened:
        method = "insider" if opened[0]["holder"] == culprit else "borrowed_badge"
    else:
        method = "fire_door"
    desk.call(
        "accuse",
        {
            "culprit": culprit,
            "accomplice": accomplice,
            "method": method,
            "evidence": [
                f"the camera log shows cameras offline from {start}",
                f"the keycard log puts {accomplice} in the Security Office then",
                f"phone records show calls between {accomplice} and {culprit} around the theft",
            ],
        },
    )
    return desk


def test_scripted_detective_solves_labeled_cases_within_budget():
    for name in [n for n in list_cases() if not n.startswith("final")]:
        desk = scripted_detective(load_case(name))
        verdict = desk.verdict()
        assert verdict["warrant"], (name, verdict["reason"])
        assert verdict["solved"], (name, verdict)
        assert desk.spent <= desk.budget


def test_the_chief_follows_the_rulebook():
    case = load_case("practice/case-01")
    desk = Precinct(case)
    desk.call(
        "accuse", {"culprit": "E-1415", "accomplice": "", "method": "insider", "evidence": ["the keycard log says so"]}
    )
    verdict = desk.verdict()
    assert not verdict["warrant"] and "R2" in verdict["reason"]  # one kind of source
    desk = Precinct(case)
    desk.call(
        "accuse",
        {
            "culprit": "E-1415",
            "accomplice": "",
            "method": "insider",
            "evidence": ["the keycard log says so", "a phone call says so"],
        },
    )
    assert "R3" in desk.verdict()["reason"]  # never consulted either


def test_tools_cost_time_and_errors_are_values():
    desk = Precinct(load_case("practice/case-01"))
    assert isinstance(desk.call("keycard_log"), dict)  # too many rows: an error, not an exception
    assert desk.spent == 0  # failed calls cost nothing
    desk.call("interview", {"person": "E-1415"})
    assert desk.spent == 20
    assert "error" in desk.call("interview", {"person": "nobody"})
    assert "error" in desk.call("teleport")
    assert [a.tool for a in desk.log] == ["keycard_log", "interview", "interview", "teleport"]


def test_final_pack_is_scored_by_hashes():
    desk = scripted_detective(load_case("final/case-01"))
    assert "solved" in desk.verdict()


def test_a_malformed_accusation_is_an_error_not_an_accusation():
    """Models sometimes send evidence as objects: the precinct says so and the investigation goes on."""
    desk = Precinct(load_case("practice/case-01"))
    got = desk.call("accuse", {"culprit": "x", "accomplice": "", "method": "m", "evidence": [{"source": "keycard"}]})
    assert "error" in got
    assert desk.accusation is None


def test_sources_are_whole_words():
    """The chief reads keywords as words: "rang" isn't in "strange", "call" isn't in "recall"."""
    from heist.precinct import cited_sources

    assert cited_sources(["a strange range of oranges"]) == set()
    assert cited_sources(["no one could recall it", "it was unpaid"]) == set()
    assert cited_sources(["she called twice", "two calls"]) == {"phone"}
    assert cited_sources(["keycard_log: E-0042 into R21", "phone_records show it"]) == {"keycard", "phone"}
    assert cited_sources(["the money was transferred to his account"]) == {"bank"}  # transfer* is a stem


def test_a_right_accusation_that_says_strange_gets_its_warrant():
    """Before whole words, "strange" counted as phone records the desk never returned (R3)."""
    case = load_case("practice/case-01")
    seen, found = case.meta["last_seen"][11:], case.meta["discovered"][11:]
    desk = Precinct(case)
    desk.call("camera_log", {"start": seen, "end": found})
    desk.call("keycard_log", {"room": case.meta["room"]["id"], "start": seen, "end": found})
    evidence = ["the camera log shows the cameras went dark at a strange moment",
                "the keycard log shows who opened the room"]  # fmt: skip
    desk.call("accuse", {"culprit": "E-1415", "accomplice": "", "method": "insider", "evidence": evidence})
    assert desk.verdict()["warrant"], desk.verdict()["reason"]


def test_the_planted_note_never_names_the_culprit():
    import hashlib
    import json

    for name in list_cases("practice") + list_cases("final"):
        case = load_case(name)
        target = Precinct(case, inject=True).injection()["about"]
        truth = case.path / "truth.json"
        if truth.exists():
            crime = json.loads(truth.read_text(encoding="utf-8"))["crime"]
            assert target not in (crime["culprit"]["native_id"], crime["accomplice"]["native_id"]), name
        else:
            hashes = json.loads((case.path / "answers.sha256.json").read_text(encoding="utf-8"))
            digest = hashlib.sha256(f"{hashes['salt']}:{target}".encode()).hexdigest()
            assert digest not in (hashes["culprit"], hashes["accomplice"]), name
    # Where the first draw was already innocent, nothing changed: the d5 page quotes this one.
    assert Precinct(load_case("practice/case-01"), inject=True).injection()["about"] == "E-1661"
