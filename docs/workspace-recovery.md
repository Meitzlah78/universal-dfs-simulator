# Reboot recovery

Open DK, FD, NFL, and NBA slates autosave full checkpoints after app interactions.
Wait for **Saved in this browser · Ready for reboot** before restarting. This
message appears only after the browser verifies the SHA-256 and commits its ZIP
and metadata in one IndexedDB transaction. The latest unconfirmed changes remain
marked **Saving changes…**. Errors stay visible rather than reporting success.

A new session restores the last active open slate. Other open slates restore on
selection, avoiding a large startup load. Closed tabs stay closed; their browser
backups are retained. This recovery belongs to the same browser and site origin.
It cannot recover work lost before autosaving was introduced.

`simmah_session_workspaces` captures widget-safe values, full simulation arrays,
DataFrames, original uploads, and queued diagnostic packages. A background worker
packs them into a safe typed ZIP (no pickle and no silent 16 MiB cache omissions).
Immutable host files live in the ignored `data/workspace_recovery` directory.
Temporary downloads use random owner and file capabilities under
`static/workspace_backups`; they are removed after browser confirmation so saved
history cannot trip Streamlit’s 1 GiB static-folder startup limit. HTTPS downloads bypass the WebSocket;
component messages normally contain only metadata and acknowledgements.
Superseded host revisions are removed only after the new browser commit is
acknowledged. Unchanged checkpoints reuse their file instead of growing storage.

After a host filesystem wipe, recovery uploads the verified browser copy in
acknowledged 1,000,000-character parts before restoring app widgets. These reruns
happen during recovery only. Normal autosaves use a polling fragment and never
stop or rerun the main model/page. Archives are limited to 180 MiB so the full
base64 recovery fits within the existing 256-part transport bound. Oversized or
unsupported saves produce an explicit error. The previous confirmed copy remains
intact. Save errors offer a download of the last host backup; an empty workspace
or save error also exposes a recovery ZIP importer.

Validation includes full-precision arrays larger than 16 MiB, mixed/nullable
DataFrames, typed keys, artifacts and uploads, real Streamlit widgets in a fresh
session, two-site lazy recovery, host disk deletion and browser reupload, actual
Streamlit static routes, bounded browser messages, iframe remounts, bad hashes,
closed tabs, private owner isolation, and acknowledgement-before-pruning.

Run:

```sh
python -m unittest discover -s tests -p 'test_workspace*.py'
node tests/test_workspace_backup_component.cjs
python -m unittest discover -s tests -p test_slate_workspaces.py
```
