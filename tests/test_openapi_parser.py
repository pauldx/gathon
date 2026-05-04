"""Tests for gathon.multimodal_graph.openapi_parser."""

from gathon.multimodal_graph.openapi_parser import parse_openapi


def test_parse_basic_spec(tmp_path):
    spec = tmp_path / "api.yaml"
    spec.write_text("""\
openapi: "3.0.0"
info:
  title: Test API
paths:
  /users.list:
    get:
      summary: List users
      tags: [users]
      responses:
        "200":
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/UserList"
  /users.create:
    post:
      summary: Create user
      requestBody:
        content:
          application/json:
            schema:
              $ref: "#/components/schemas/UserCreate"
components:
  schemas:
    UserList:
      type: object
      properties:
        users:
          type: array
        next_cursor:
          type: string
    UserCreate:
      type: object
      properties:
        name:
          type: string
        email:
          type: string
""")
    nodes, edges = parse_openapi(spec)

    kinds = {n.kind for n in nodes}
    assert "ConfigFile" in kinds
    assert "Endpoint" in kinds
    assert "APIResource" in kinds

    endpoints = [n for n in nodes if n.kind == "Endpoint"]
    assert len(endpoints) == 2
    endpoint_names = {e.name for e in endpoints}
    assert "GET /users.list" in endpoint_names
    assert "POST /users.create" in endpoint_names

    schemas = [n for n in nodes if n.kind == "APIResource"]
    assert len(schemas) == 2

    ref_edges = [e for e in edges if e.kind == "REFERENCES"]
    assert len(ref_edges) >= 2


def test_parse_empty_spec(tmp_path):
    spec = tmp_path / "empty.yaml"
    spec.write_text("openapi: '3.0.0'\ninfo:\n  title: Empty\n")
    nodes, edges = parse_openapi(spec)
    assert len(nodes) == 1
    assert nodes[0].kind == "ConfigFile"


def test_schema_cross_refs(tmp_path):
    spec = tmp_path / "refs.yaml"
    spec.write_text("""\
openapi: "3.0.0"
info:
  title: Ref Test
components:
  schemas:
    Parent:
      type: object
      properties:
        child:
          $ref: "#/components/schemas/Child"
    Child:
      type: object
      properties:
        name:
          type: string
""")
    nodes, edges = parse_openapi(spec)
    ref_edges = [e for e in edges if e.kind == "REFERENCES"]
    assert any(
        "schema:Child" in e.target_qualified for e in ref_edges
    )
