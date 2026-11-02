"""NeuroVault (§15, NV-F01 to NV-F03 in v0.2; A-30, A-90): the vault folder with the consent records and the
hash-chained access log.

- ``store``: where the vault lies (VaultLocation, locate, locate_default), its states, ``init_vault`` and
  ``replace_file`` (one-step rewrite of a vault file such as consents.yaml).
- ``lock``: the one vault lock of every reader and writer (exclusive, HeldLock, VaultLocked).
- ``ledger``: access.jsonl (append, append_locked, snapshot, iter_entries, verify).
- ``roles``: role names (validate_role, role_looks_identifying).
- ``_os``: all platform code (msvcrt/fcntl locks, modes, folder fsync).

Import boundary (ARC-01, tests/unit/test_architecture.py): the vault imports only neurogrid.kernel,
neurogrid.model, neurogrid.io and neurogrid.config, never the CLI, the pipeline, the checks or the report;
the checks read it as a supplier.
"""
