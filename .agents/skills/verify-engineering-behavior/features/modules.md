# Module updates

## Sub-features

Successful updates remain schema-valid; content edits preserve incoming graph links; invalid edits preserve the previous saved state.

## How to get to it (user POV)

Use PUT `/api/modules/{category}/{id}` for content edits; graph consumers read the updated index.

## Driving it with the helper

The helper saves source→target modules through public storage operations, changes the target summary and inspects the real persisted index. Run tests/test_http_server.py for actual HTTP patch semantics, including omitted values, empty strings and rejected nulls.

## Gotchas

The helper's storage scenario alone does not prove HTTP behavior. Require the HTTP suite when updating the route or update model; do not weaken the scenario if the graph disappears.
