# Legal Attribution Verification Artifact

Date: 2026-02-14

## Verification Checklist

- [x] Attribution text is rendered on analysis dashboard actions panel.
- [x] Attribution text is included in JSON export metadata envelope.
- [x] Attribution text is included in CSV export metadata header lines.
- [x] Source version snapshot is present in API analysis payload.
- [x] Source version snapshot is present in CSV/JSON exports.

## Manual Evidence Capture Steps

1. Run `erlotinib` analysis in local web app.
2. Confirm attribution line appears in the right actions panel.
3. Download `export.csv` and verify `# attribution:` metadata line exists.
4. Download `export.json` and verify `metadata.attribution` and `metadata.version_snapshot`.
5. Store screenshots in this folder when legal requests evidence packaging.
