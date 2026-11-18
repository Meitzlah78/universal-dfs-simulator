# NBA destination-slate preparation

Slate switches already route before old-page preparation, but the destination still rebuilds its player tables. Pandas propagates attrs into temporary rows and column selections, recursively copying raw provider evidence many times.

Read-only DataFrame views now exclude attrs during role-prior and learned-role iteration, projection application, saved game-metadata lookup, and market extraction. The source and returned result frames retain evidence; no global pandas behavior or simulation parameters change.

A local Streamlit AppTest using the supplied November 18 DK salary file (316 players) measured repeat preparation at 3.80 seconds before and 1.30 seconds after. Provider downloads were replaced with pending responses, lineup checks were stubbed, and diagnostic archive retention was suppressed. These numbers isolate page preparation, not browser transfer, cloud recovery or live-host performance. No build was launched by this benchmark.

Regression coverage compares original row traversal with the new views, checks nullable dtypes and evidence preservation, and exercises existing game-clock, role-learning, workspace-switch and full build/export tests.
