# FigOps Public Release Status

- Inventory valid: yes
- Package distribution allowed: yes
- Repository public release allowed: no
- Release gate: blocked
- Total blockers: 30
- Auto-fixable blockers: 0
- Confirmation-required blockers: 30

Decision record: [public-release-decision-record.md](./public-release-decision-record.md)

## Next Actions

| Family | Count | Status | Confirmation | Action |
| --- | ---: | --- | --- | --- |
| post_tag_metadata | 1 | requires_release_decision | yes | Choose the next release version, then bump pyproject and changelog together. |
| private_marker | 22 | requires_decision | yes | Sanitize or relocate files that contain real project identifiers or private style names. |
| private_workflow_doc | 6 | requires_decision | yes | Move internal workflow documents out of the public repository candidate. |
| style_pack | 1 | requires_decision | yes | Split or remove internal style packs from the public repository candidate. |
