# NFL Step 1 startup

Before simulation preparation or its progress bar, the app loaded four seasonal history CSVs serially, built player roles, then loaded the matchup schedule/context. On a cold Streamlit cache, each history request could independently wait for its network timeout. This is a confirmed silent startup path, not evidence that it caused every reported slow build.

The four history downloads now overlap in a four-thread I/O pool. Responses are consumed in the original 2026, 2025, 2024, 2023 order with identical CSV parsing, season assignment, timeouts, empty-season handling and per-season error fallback. The existing 24-hour Streamlit cache remains. Matchup schedule loading is unchanged.

A progress bar appears before history loading. It labels history loading, role preparation, matchup schedule/context, then simulation preparation. Startup history and total preparation seconds are displayed before fitting and saved in session state as `nfl_startup_<platform>` for diagnosis. No fitting iterations, model parameters, sample counts or historical eligibility rules change.

Validation: 17 tests pass across startup history, the NFL engine and prepared-build boundary. A four-party barrier proves concurrent requests without a timing-based assertion. The resulting DataFrame matches the former serial parsing exactly. Partial failures and completely unavailable history retain the same ordered fallback. Existing full-path tests verify warm simulation preparation remains reusable. Live-host startup latency has not been measured; a delay already labeled as projection fitting is outside this optimization.
