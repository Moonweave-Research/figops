# FigOps Public Release Status

- Inventory valid: yes
- Package distribution allowed: yes
- Repository technically eligible for public release: no
- Repository publication authorized: yes
- Repository release allowed: no
- Authorization evidence references: 1
- Technical release gate: blocked
- Technical blockers: 1
- Auto-fixable technical blockers: 0
- Confirmation-required technical blockers: 1

Repository publication authorization is recorded in the authoritative inventory approval fields with validated HTTPS evidence references. The technical gate remains independent evidence; a release is allowed only when both authorization and technical eligibility are yes.

Decision record: [public-release-decision-record.md](./public-release-decision-record.md)

## Technical Gate Next Actions

| Family | Count | Status | Confirmation | Action |
| --- | ---: | --- | --- | --- |
| post_tag_metadata | 1 | requires_release_decision | yes | Choose the next release version, then bump pyproject and changelog together. |
