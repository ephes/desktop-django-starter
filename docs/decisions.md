# Decisions

Status: initial repo-local decision log

## D-001: This repo is specification-first

Implementation follows only after the minimum starter boundaries are written down.

## D-002: The starter is attendee-facing and minimal

The repo should optimize for teachability and adaptation, not product depth.

## D-003: `djdesk` is reference material, not the baseline

We may borrow packaging and lifecycle patterns from the `djdesk` repo, but we are not trimming `djdesk` into the starter.

## D-004: The example app stays generic

The starter should use a simple single-user CRUD example instead of a domain-heavy or flashy demo.

## D-005: Background tasks are deferred

The first implementation will not include a worker framework or queue. If later needed, add one local background-task path only after the minimal starter is stable.

## D-006: Windows is a required proof point

Starter v1 must demonstrate that the packaged app can launch on Windows with a bundled Python runtime and writable local data storage.

## D-007: Manual updates are acceptable for v1

The repo should document signing, notarization, and release expectations, but auto-update infrastructure is not required in the first implementation.

## D-008: Coding agents are a first-class audience

The repo should be consumable both by humans and by coding agents working in other Django repositories.

## D-009: The update story must include air-gapped environments

The starter does not need a full auto-updater in v1, but it does need a documented offline/manual update path for controlled environments.

## D-010: GitHub Actions is the baseline CI

Cross-platform validation should run on GitHub-hosted Linux, macOS, and Windows runners from the start.

## D-011: Tasks demo uses stub threading, not django.tasks

The `tasks_demo` app is an optional post-v1 extension that demonstrates background task visualization. It uses `threading.Thread` with simulated delays rather than `django.tasks` or any queue framework. Real async worker integration is deferred to a follow-up slice. The frontend (pulse-ring animation, polling, task state display) is the point of this demo.
