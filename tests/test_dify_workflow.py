"""The Dify workflow DSL, checked mechanically.

A DSL file is submitted and imported by hand, so nothing about it is exercised
by running the app. These tests stand in for that: they check the things that
make an import fail or a run break silently — the fields Dify's importer
requires, a graph whose edges and variable references actually resolve, code
nodes whose declared outputs match what their Python returns, HTTP nodes that
point at endpoints `service/tool_api.py` really serves, and request bodies
that are still valid JSON once Dify has substituted the variables.

It also checks that the file carries no secret, because this file is the
artifact that gets handed in (hard rule 8).
"""
from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

import service.tool_api as api                     # noqa: E402

DSL = REPO / "dify" / "course-planner.yml"
REFERENCE = re.compile(r"\{\{#([A-Za-z0-9_.]+)#\}\}")
BUILT_IN = {"sys", "env", "conversation"}


@pytest.fixture(scope="module")
def dsl() -> dict:
    return yaml.safe_load(DSL.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def nodes(dsl) -> dict[str, dict]:
    return {n["id"]: n for n in dsl["workflow"]["graph"]["nodes"]}


def strings(value) -> list[str]:
    """Every string anywhere inside a node, so no reference is missed."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [s for v in value.values() for s in strings(v)]
    if isinstance(value, list):
        return [s for v in value for s in strings(v)]
    return []


# ------------------------------------------------- what the importer needs --

def test_the_file_has_what_difys_importer_requires(dsl):
    assert set(dsl) >= {"app", "kind", "version", "workflow"}
    assert dsl["kind"] == "app"
    # The importer raises "Invalid version type, expected str" on a bare float,
    # so 0.1.5 unquoted would fail before anything else was read.
    assert isinstance(dsl["version"], str), "version must be a quoted string"
    assert dsl["app"]["mode"] == "workflow"
    assert isinstance(dsl["workflow"], dict)
    assert {"graph", "features"} <= set(dsl["workflow"])
    assert {"nodes", "edges"} <= set(dsl["workflow"]["graph"])


def test_a_workflow_app_carries_no_answer_node(nodes):
    """`answer` belongs to advanced-chat; in a workflow app it is rejected."""
    kinds = {n["data"]["type"] for n in nodes.values()}
    assert "answer" not in kinds
    assert "start" in kinds and "end" in kinds


def test_there_is_one_start_and_one_end(nodes):
    """One start is Dify's rule. One end is ours: no real export was found
    with two, so the graph converges before it finishes rather than relying
    on behaviour that could not be verified."""
    counts = {kind: sum(1 for n in nodes.values() if n["data"]["type"] == kind)
              for kind in ("start", "end")}
    assert counts == {"start": 1, "end": 1}


def test_every_node_has_the_envelope_a_real_export_has(nodes):
    for node_id, node in nodes.items():
        missing = {"data", "id", "position", "type", "width", "height"} - set(node)
        assert not missing, f"{node_id} is missing {missing}"
        assert node["type"] == "custom", f"{node_id} is not a custom node"
        assert {"title", "type"} <= set(node["data"]), node_id


# ----------------------------------------------------------- the graph --

def test_every_edge_joins_two_real_nodes_and_names_their_types(dsl, nodes):
    for edge in dsl["workflow"]["graph"]["edges"]:
        assert edge["source"] in nodes, edge["id"]
        assert edge["target"] in nodes, edge["id"]
        assert edge["data"]["sourceType"] == nodes[edge["source"]]["data"]["type"]
        assert edge["data"]["targetType"] == nodes[edge["target"]]["data"]["type"]


def test_the_graph_runs_from_start_to_end_without_a_cycle(dsl, nodes):
    edges = dsl["workflow"]["graph"]["edges"]
    after: dict[str, list[str]] = {}
    for edge in edges:
        after.setdefault(edge["source"], []).append(edge["target"])

    start = next(i for i, n in nodes.items() if n["data"]["type"] == "start")
    end = next(i for i, n in nodes.items() if n["data"]["type"] == "end")

    seen, order, stack = set(), [], [start]
    while stack:
        node_id = stack.pop()
        if node_id in seen:
            continue
        seen.add(node_id)
        order.append(node_id)
        stack.extend(after.get(node_id, []))

    assert end in seen, "the end node is unreachable from start"
    assert seen == set(nodes), f"orphaned nodes: {set(nodes) - seen}"
    assert len(order) == len(set(order)), "a node was reached twice — a cycle"


def upstream_of(dsl, nodes) -> dict[str, set[str]]:
    """Everything that must have run before a node, by id."""
    before: dict[str, list[str]] = {}
    for edge in dsl["workflow"]["graph"]["edges"]:
        before.setdefault(edge["target"], []).append(edge["source"])

    resolved: dict[str, set[str]] = {}

    def walk(node_id: str) -> set[str]:
        if node_id not in resolved:
            resolved[node_id] = set()
            for parent in before.get(node_id, []):
                resolved[node_id] |= {parent} | walk(parent)
        return resolved[node_id]

    return {node_id: walk(node_id) for node_id in nodes}


def test_every_variable_reference_points_upstream(dsl, nodes):
    """A reference to a node that has not run yet is empty at runtime, and
    Dify does not refuse the import for it — it just quietly produces nothing.
    """
    upstream = upstream_of(dsl, nodes)
    for node_id, node in nodes.items():
        for text in strings(node["data"]):
            for reference in REFERENCE.findall(text):
                target = reference.split(".")[0]
                if target in BUILT_IN:
                    continue
                assert target in nodes, \
                    f"{node_id} references unknown node {target}"
                assert target in upstream[node_id], \
                    f"{node_id} references {target}, which is not upstream"


def test_every_value_selector_points_upstream_at_a_real_node(dsl, nodes):
    upstream = upstream_of(dsl, nodes)
    for node_id, node in nodes.items():
        for entry in (node["data"].get("variables") or []) + \
                     (node["data"].get("outputs") or []
                      if isinstance(node["data"].get("outputs"), list) else []):
            selector = entry.get("value_selector") or []
            if not selector or selector[0] in BUILT_IN:
                continue
            assert selector[0] in nodes, f"{node_id} -> {selector}"
            assert selector[0] in upstream[node_id], f"{node_id} -> {selector}"


# ------------------------------------------------------- the code nodes --

def code_nodes(nodes) -> list[tuple[str, dict]]:
    return [(i, n["data"]) for i, n in nodes.items()
            if n["data"]["type"] == "code"]


def test_each_code_node_declares_the_outputs_its_python_returns(nodes):
    for node_id, data in code_nodes(nodes):
        tree = ast.parse(data["code"])
        main = next((f for f in ast.walk(tree)
                     if isinstance(f, ast.FunctionDef) and f.name == "main"),
                    None)
        assert main is not None, f"{node_id} has no main()"

        returned = set()
        for node in ast.walk(main):
            if isinstance(node, ast.Return) and isinstance(node.value, ast.Dict):
                keys = {k.value for k in node.value.keys
                        if isinstance(k, ast.Constant)}
                assert keys, f"{node_id} returns a dict with computed keys"
                returned |= keys

        declared = set(data["outputs"])
        assert returned == declared, \
            f"{node_id}: returns {sorted(returned)}, declares {sorted(declared)}"


def test_every_return_in_a_code_node_carries_all_of_its_outputs(nodes):
    """A branch that omits one output leaves it empty downstream."""
    for node_id, data in code_nodes(nodes):
        declared = set(data["outputs"])
        main = next(f for f in ast.walk(ast.parse(data["code"]))
                    if isinstance(f, ast.FunctionDef) and f.name == "main")
        for node in ast.walk(main):
            if isinstance(node, ast.Return) and isinstance(node.value, ast.Dict):
                keys = {k.value for k in node.value.keys
                        if isinstance(k, ast.Constant)}
                assert keys == declared, \
                    f"{node_id}: a return gives {sorted(keys)}, not {sorted(declared)}"


def test_each_code_nodes_inputs_match_its_function_signature(nodes):
    for node_id, data in code_nodes(nodes):
        main = next(f for f in ast.walk(ast.parse(data["code"]))
                    if isinstance(f, ast.FunctionDef) and f.name == "main")
        parameters = [a.arg for a in main.args.args]
        wired = [v["variable"] for v in data["variables"]]
        assert sorted(parameters) == sorted(wired), \
            f"{node_id}: main({parameters}) but the node wires {wired}"


def test_the_code_nodes_only_import_the_standard_library(nodes):
    """Dify's sandbox is not this repo. Nothing here may import `planner`."""
    allowed = {"json", "re"}
    for node_id, data in code_nodes(nodes):
        for node in ast.walk(ast.parse(data["code"])):
            if isinstance(node, ast.Import):
                names = {a.name.split(".")[0] for a in node.names}
                assert names <= allowed, f"{node_id} imports {names - allowed}"
            if isinstance(node, ast.ImportFrom) and node.module:
                root = node.module.split(".")[0]
                assert root in allowed, f"{node_id} imports from {root}"


# ------------------------------------------------------- the HTTP nodes --

def http_nodes(nodes) -> list[tuple[str, dict]]:
    return [(i, n["data"]) for i, n in nodes.items()
            if n["data"]["type"] == "http-request"]


def test_every_http_node_calls_an_endpoint_the_service_serves(nodes):
    served = {route.path for route in api.ROUTES}
    for node_id, data in http_nodes(nodes):
        path = data["url"].split("#}}")[-1]
        assert path in served, f"{node_id} posts to {path}, which is not served"
        assert data["method"] == "post"
        assert "post" in {m.lower() for m in
                          next(r for r in api.ROUTES
                               if r.path == path).methods}


def test_every_http_node_sends_the_token_from_the_start_node(nodes):
    for node_id, data in http_nodes(nodes):
        assert "Authorization:Bearer {{#" in data["headers"], node_id
        assert ".tool_token#}}" in data["headers"], node_id


def test_each_request_body_is_still_valid_json_once_dify_fills_it_in(nodes):
    """The bodies embed variables raw, so a missing quote only shows up at
    runtime as a 400 from the service. Substituting real values proves the
    template, not just that it looks right."""
    profile = json.dumps({"cohort": "2026-27", "major": "COMP"})
    plan = json.dumps([{"code": "COMP 2011", "term": "Y1 Fall",
                        "status": "planned"}])
    fill = {"profile_json": profile, "major": "COMP",
            "tool_token": "token", "tool_base": "http://localhost:8601",
            "plan_json": plan, "result": "{}", "body": "{}",
            "text": "", "rationale": "", "verdict": "clean",
            "errors_text": "", "source": "model"}

    for node_id, data in http_nodes(nodes):
        for part in data["body"]["data"]:
            filled = REFERENCE.sub(
                lambda m: fill[m.group(1).split(".")[-1]], part["value"])
            try:
                parsed = json.loads(filled)
            except json.JSONDecodeError as exc:
                pytest.fail(f"{node_id} body is not JSON once filled: {exc}\n"
                            f"{filled}")
            assert isinstance(parsed, dict), node_id


# ------------------------------------------------ the OpenAPI schema --

@pytest.fixture(scope="module")
def spec() -> dict:
    return json.loads((REPO / "dify" / "openapi.json").read_text("utf-8"))


def test_the_openapi_schema_documents_only_paths_the_service_serves(spec):
    """It is imported into Dify to build the tools, so a path that does not
    exist becomes a tool that always fails."""
    served = {route.path: {m.lower() for m in route.methods}
              for route in api.ROUTES}
    assert set(spec["paths"]) <= set(served)
    for path, operations in spec["paths"].items():
        assert set(operations) <= served[path], path


def test_every_tool_is_documented_and_nothing_else_is(spec):
    """`/debug/echo` is served but deliberately absent: it exists to diagnose
    a 401, and it has no business becoming a tool a model can call."""
    tools = {route.path for route in api.ROUTES
             if route.path.startswith("/tools/")}
    assert tools <= set(spec["paths"]), tools - set(spec["paths"])
    assert "/debug/echo" not in spec["paths"]


def test_every_documented_operation_has_an_id_dify_can_name_a_tool_with(spec):
    ids = [op["operationId"] for ops in spec["paths"].values()
           for op in ops.values()]
    assert len(ids) == len(set(ids))
    assert all(re.fullmatch(r"[a-z_]+", name) for name in ids), ids


def test_the_open_endpoint_is_the_only_one_without_auth(spec):
    for path, operations in spec["paths"].items():
        for method, operation in operations.items():
            if path == "/health":
                assert operation.get("security") == []
            else:
                assert "security" not in operation, \
                    f"{method} {path} opts out of the global bearer scheme"


# ------------------------------------------------------------- secrets --

def test_the_submitted_file_holds_no_secret(dsl):
    """The token is a run-time input, not a value in the file. This is the
    artifact that gets handed in, so a literal key here would be shipped."""
    raw = DSL.read_text(encoding="utf-8")
    assert "sk-ant" not in raw
    assert not re.search(r"Bearer\s+[A-Za-z0-9_\-]{16,}", raw), \
        "a literal bearer token is in the file"
    assert dsl["workflow"]["environment_variables"] == [], \
        "env vars would carry values into the export"
    start = next(n for n in dsl["workflow"]["graph"]["nodes"]
                 if n["data"]["type"] == "start")
    names = {v["variable"] for v in start["data"]["variables"]}
    assert {"tool_base", "tool_token"} <= names,         "the address and token must stay run-time inputs, never values here"
    assert {"major", "cohort", "workload_min", "workload_max", "spread",
            "free_terms"} <= names, "the form has to ask for the profile"
    assert "profile_json" not in names,         "a reviewer answers questions; the profile is built from the answers"
