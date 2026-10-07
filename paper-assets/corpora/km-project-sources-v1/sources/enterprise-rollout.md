# Enterprise Rollout

1. Initialize the KB with `km init <kb-path>` and confirm `index.json`, `config.json`, `.staging/`, and `.sources/` are present.
2. Register enterprise sources with least-privilege credentials:
   `km --kb-path <kb-path> source add-confluence ...`
   `km --kb-path <kb-path> source add-notion ...`
3. Pull sources until `km --kb-path <kb-path> source status` shows current cursors and no `last_error`.
4. Review staged modules and reject anything without clear provenance.
5. Run `km --kb-path <kb-path> eval run <suite.json>` and require acceptable hit rate plus failure decomposition.
6. Inspect `km --kb-path <kb-path> ops` and exported backlogs before enabling production agents.
7. Enable auth middleware only after signed-token validation passes in staging.
8. Keep `km --kb-path <kb-path> rebuild` and enterprise test suite in the release gate.

Record the following with every cutover:

- release version
- matrix summary path
- support bundle path
- backup bundle path
- operator on call
- rollback owner
