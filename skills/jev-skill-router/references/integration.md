# Integration notes

The router is a plain Python script; wire it into any agent or harness.

## opencode plugin

`integrations/opencode/jev-skill-router.ts` registers a `jev_route_skill(task)` tool
that calls `scripts/skill_router.py --load` and returns the selected skill's full
instructions. Recommended companion setting (removes the built-in skill catalog from
the main model context):

```json
{
  "agent": { "build": { "tools": { "skill": false } } }
}
```

The plugin expects the repository at the opencode project root:

```
<project>/.venv/bin/python <project>/script-router path
```

Adjust the two path constants at the top of the plugin file if your layout differs.

## MCP server

The companion repo ships a Jev MCP server with `scan_injection` / `bash_risk` /
`rank_candidates`. Skill routing can be exposed the same way by wrapping
`route()` from `scripts/skill_router.py` in an MCP tool.

## Routing policy

- Load the routed skill only when `confidence >= 0.5` and `skill != "none"`.
- On low confidence, surface `alternatives` to the model instead of forcing a choice.
- Log `skill`, `confidence`, and `catalog_size` for later threshold tuning.
