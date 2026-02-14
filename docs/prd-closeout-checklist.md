# PRD Closeout Checklist (v1.1)

Last updated: 2026-02-14

| Item | Owner | Status | Decision / Next Action | Timestamp |
|---|---|---|---|---|
| Product name + trademark search | Product Ops | Pending external | Run trademark counsel search for `PathMind` and backup names before launch | 2026-02-14 |
| Pricing + packaging | PM + GTM | Pending external | Finalize free research beta + paid team tier proposal | 2026-02-14 |
| First 10 beta users + outreach | PM | In progress | Build target list and assign outreach owners | 2026-02-14 |
| Hosting budget approval | Engineering Manager + Finance | Pending external | Approve Postgres/Redis/API/Web monthly envelope | 2026-02-14 |
| OSS vs proprietary decision | Founders + Legal | Pending external | Keep code private during beta; revisit OSS after legal review | 2026-02-14 |
| ChEMBL CC BY-SA legal interpretation memo | Legal | Pending external (launch gate) | Formal opinion required before commercial launch | 2026-02-14 |

## Engineering Completion Status

- ETL/provenance implemented with nightly command and DB-backed metadata.
- Drug identity disambiguation flow implemented with explicit candidate selection.
- Uncertainty and partial-mapping flags implemented in API and frontend rendering.
- Export metadata implemented for CSV/JSON endpoints.
- Privacy controls implemented (`do_not_log`, IP masking, 90-day purge command, consent-gated analytics).
- Contracts/check pipeline and validation checklist documented in runbook.
