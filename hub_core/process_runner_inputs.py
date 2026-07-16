"""Input declaration resolution for the process-runner facade.

This module keeps project-contained inputs and launcher-authorized external raw
inputs on one fail-closed execution path.  The process runner retains the
historical private helper names as direct aliases.
"""

from pathlib import Path

from .external_raw_execution import (
    is_external_raw_declaration,
    materialize_external_raw_inputs,
)
from .project_paths import (
    resolve_project_input,
    resolve_project_root,
    revalidate_project_input,
    snapshot_project_input,
)
from .provenance_inputs import expand_project_input_groups


def contained_input_groups(project_dir, declarations):
    return expand_project_input_groups(project_dir, declarations)


def partition_input_declarations(declarations):
    project_inputs = [item for item in declarations if not is_external_raw_declaration(item)]
    external_inputs = [item for item in declarations if is_external_raw_declaration(item)]
    return project_inputs, external_inputs


def project_relative_inputs(project_dir, absolute_paths):
    root = resolve_project_root(project_dir)
    return [Path(path).resolve(strict=True).relative_to(root).as_posix() for path in absolute_paths]


def prefetch_and_revalidate_inputs(project_dir, declared_inputs, prefetcher):
    resolved = [
        resolve_project_input(project_dir, declaration, purpose="declared execution input")
        for declaration in declared_inputs
    ]
    prefetcher.ensure_local([str(path) for path in resolved])
    snapshots = [
        snapshot_project_input(project_dir, declaration, purpose="declared execution input")
        for declaration in declared_inputs
    ]
    return [
        revalidate_project_input(
            project_dir,
            declaration,
            expected_snapshot=snapshot,
            purpose="declared execution input",
        )
        for declaration, snapshot in zip(declared_inputs, snapshots, strict=True)
    ]


def resolve_execution_inputs(
    project_dir,
    config,
    declared_project_inputs,
    declared_external_inputs,
    prefetcher,
    external_raw_allowed_roots,
):
    resolved = prefetch_and_revalidate_inputs(project_dir, declared_project_inputs, prefetcher)
    external = materialize_external_raw_inputs(
        project_root=project_dir,
        config=config,
        declarations=declared_external_inputs,
        prefetcher=prefetcher,
        allowed_roots=external_raw_allowed_roots,
    )
    return [*resolved, *(item.path for item in external)]
