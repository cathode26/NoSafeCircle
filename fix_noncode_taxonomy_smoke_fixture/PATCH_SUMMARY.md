# Typed Non-Code Taxonomy Smoke-Test Fixture Fix

The production taxonomy logic had been patched, but the valid smoke-test
fixtures for `REQ-PIPELINE` and `REQ-DELIVERY` still had empty
`mapped_non_code_titles` values.

The deterministic checker correctly rejected those fixtures, causing:

`assert crew.deterministic_audit_checks(taxonomy_ok) == []`

This small continuation fixes only those fixture mappings:

- `REQ-PIPELINE` -> `No concurrent Unity asset edits`
- `REQ-DELIVERY` -> `Windows build`

It also changes the assertion to include the exact deterministic findings if a
future regression occurs.
