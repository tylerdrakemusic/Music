# OG Lyric Integrity Policy

Status: Active
Scope: ❤Music repository
Owner: Tyler James Drake

## Purpose

Protect original lyric ideas and hooks so first-arrival language is preserved with high integrity.

## Core Rule

If a lyric line is marked OG, the original wording is the source of truth.

Edits to OG lines are not allowed by default. Any rewrite must happen as a separate variant, not a replacement.

## OG Classification

A line is OG when one or more of the following is true:

1. It arrived as a full hook or key phrase in a single pass.
2. It is tagged as transcendent or first-flash language.
3. Tyler explicitly says keep the original.

## Handling Standard

1. Capture OG lines verbatim in project docs.
2. Keep OG and variant text in separate sections.
3. Never overwrite OG text during cleanup, refactor, or formatting passes.
4. Preserve punctuation and casing unless Tyler requests a change.
5. If a collaborator proposes edits, store proposals as Variant A, Variant B, etc.

## Repository Implementation

1. Store protected originals in docs/transcendent or dedicated protocol docs.
2. Require commit message tag OG-LYRIC when adding or updating protected OG entries.

## Review Gate

Before merging changes touching lyrics:

1. Confirm OG lines are unchanged.
2. Confirm any alternate versions are additive, not destructive.
3. Confirm file history retains first protected wording.

## Current Protected OG Hook Seed

I hold my sigil because I'm brave.
What's so bad about red?

This seed line is locked as OG and should remain intact across future lyric iterations.
