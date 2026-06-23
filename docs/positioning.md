# Positioning

FigOps is not just a plotting helper. It is a local-first figure operations layer for research
teams that need reproducible figures, explicit contracts, and MCP-native automation.

## FigOps vs Generic Plotting MCP

A generic plotting MCP usually accepts data and emits an image. FigOps adds the operational layer
around that render:

- project-level `project_config.yaml` contracts
- CSV schema and semantic checks
- public journal style targets
- runtime provenance and artifact manifests
- explicit write-tool and root-access policy
- local release gates for public-core hygiene

Use FigOps when the important question is not only "can I draw this?" but "can I rerun, audit,
and trust this figure later?"

## FigOps vs figure recipe tools

Figure recipe tools are useful for repeatable plotting code, but they often stop at script reuse.
FigOps keeps recipes inside a broader execution contract:

- analysis, plot, and diagram steps share one orchestration surface
- public-safe examples demonstrate full project reruns
- manifests connect outputs to code, config, environment, and render jobs
- MCP clients can discover the same tool surface humans use locally

Use FigOps when a figure is part of a research workflow rather than a one-off image export.

## Public-Core Scope

The public core focuses on reusable orchestration, MCP tooling, data contracts, public journal style
targets, and synthetic examples. Project-specific datasets, private manuscript assets, credentials,
and internal style packs are outside this distribution unless they are explicitly included with their
own notices.
