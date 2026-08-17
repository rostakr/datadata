# A6 real-data browser QA v3

`tools.a6_real_data_ui_qa_v3` is a local-only physical browser acceptance runner for private canonical SQLite data.

The runner starts a dedicated Streamlit child process and passes both the canonical database path and the selected canonical conversation through process-local environment variables. The browser therefore does not need to manipulate the sidebar source/contact selectors before acceptance checks begin.

Default Playwright behavior remains bundled Chromium. Environments where bundled Chromium is unavailable may explicitly select an installed Chromium channel, for example `--browser-channel chrome`.

The runner preserves the existing privacy contract:

- absolute database paths are not written to the report;
- canonical conversation identifiers are not written to the report;
- private contact/message/source identifiers are rejected by the report privacy guard;
- screenshots remain opt-in because they may contain private content;
- the browser matrix covers desktop, iPhone portrait and iPhone landscape;
- data/provenance checks and real A6 interaction checks remain fail-closed.

The launcher-targeted Streamlit entrypoint is `tools/a6_real_data_target_app.py`. It scopes only the local QA UI target; it does not modify the canonical database and does not persist the target selector.
