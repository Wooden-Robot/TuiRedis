# Changelog

All notable changes to this project will be documented in this file.

## [0.7.0] - 2026-03-14

### Added
- Added Redis Sentinel support through master discovery in both the TUI connection screen and CLI.
- Added support for multiple Sentinel nodes through `sentinel_nodes` profiles and repeated `--sentinel-node` CLI flags.
- Added failover-aware retry behavior for Sentinel connections after connection resets, timeouts, and `READONLY` responses.
- Added explicit Redis Cluster connection mode through `RedisCluster`.
- Added cluster-aware key scanning across the cluster and aggregated server-info/keyspace/dbsize summaries.
- Added loading indicators and stale-response dropping for async key loading, pagination, server info, and key-detail requests.
- Added safer profile handling with opt-in secret persistence and clearer persistence failure feedback.
- Added changelog files in English and Chinese.

### Changed
- Changed standalone DB handling to detect the configured database count dynamically instead of assuming `0..15`.
- Changed the main UI to move blocking Redis operations off the Textual event loop.
- Changed cluster mode behavior to disable DB switching, reject raw `SELECT`, and label Server Info as an aggregated cluster view.
- Changed Sentinel mode behavior to clearly distinguish control-plane limitations in the UI.
- Changed `iredis` launching to validate executable availability before trying to spawn it.
- Changed profile deduplication to include credential and Redis-mode-specific fields.

### Fixed
- Fixed false-success DB switching feedback when `SELECT` failed.
- Fixed `iredis` URL construction for passwords containing reserved URL characters.
- Fixed silent connection-profile save/delete failures that previously looked successful in the UI.
- Fixed several race conditions where stale async responses could overwrite newer UI state.
- Fixed compatibility issues caused by partially initialized `RedisClient` instances in edge-case tests and teardown paths.
