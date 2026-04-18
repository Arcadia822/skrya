# Remove Plane And Symphony Design

**Date:** 2026-04-18

## Goal

Remove all Plane- and Symphony-related code, skills, docs, temporary assets, and run artifacts from this repository so the workspace is once again clearly centered on topic-driven briefing and analysis.

## Scope

This change removes:

1. Plane and Symphony infrastructure, bootstrap scripts, and workflow contracts.
2. Plane and Symphony skills, helper scripts, references, and assets.
3. Orchestrator code and tests that only exist to support Plane/Symphony.
4. Generated run artifacts and temporary source trees that only exist because of Plane/Symphony work.
5. Documentation and metadata that still describe the repository as a Plane/Symphony project.

## Non-Goals

1. Redesign the topic-driven briefing system itself.
2. Add new product features beyond cleanup and narrative correction.
3. Re-architect unrelated parts of the repository.

## Desired End State

After this change:

1. The repository reads as a topic-driven briefing workspace at first glance.
2. The remaining skills focus on topic curation, digest generation, and deep analysis.
3. There are no active Plane/Symphony entry points, references, or stale generated artifacts in normal project paths.
4. README, workflow docs, and design docs no longer send a new user down the wrong mental model.

## Removal Strategy

1. Delete Plane/Symphony-only directories and files.
2. Rewrite top-level docs and metadata so they describe the topic workflow.
3. Remove or replace references to deleted files.
4. Run a repository-wide search for `plane`, `symphony`, and related paths to catch leftovers.

## Risks

1. A broad text search can catch false positives inside unrelated temporary or generated content, so deletion should follow clear ownership boundaries.
2. The repo may still contain old design history mentioning Plane/Symphony. We should keep only what still helps explain the current product.
3. Removing top-level automation code changes the repository identity, so README and package metadata need to be updated in the same pass.

## Success Criteria

This cleanup is complete when:

1. A new reader opening the repo sees a topic-driven briefing project, not an orchestrator bootstrap.
2. No first-party code, docs, or skills in the workspace depend on Plane or Symphony.
3. Repository scans no longer show Plane/Symphony references outside intentionally preserved historical notes, if any remain.
