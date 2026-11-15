# Changelog

## Unreleased

- Bound Electron recovery process tools and revalidate observed backend process
  identity before orphan termination and escalation.
- Preserve unreadable or invalid session markers and refuse backend startup;
  failed update handoffs now leave a clear restart-required state.
