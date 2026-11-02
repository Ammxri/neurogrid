"""NeuroVault (§15, NV-F01 to NV-F03 in v0.2, NV-F04 to NV-F07 in v1.0; A-30, A-90, A-93 to A-95): the vault
folder with the consent records, the hash-chained access log, the registers and the impact assessment.

- ``store``: where the vault lies (VaultLocation, locate, locate_default), its states, ``init_vault`` with the
  templates, ``replace_file`` (one-step rewrite of a vault file such as consents.yaml) and the reading of
  the registers (read_vault_file, located, LoadedRegister).
- ``lock``: the one vault lock of every reader and writer (exclusive, HeldLock, VaultLocked).
- ``ledger``: access.jsonl (append, append_locked, snapshot, iter_entries, verify).
- ``roles``: role names (validate_role, role_looks_identifying) and the role register roles.yaml (LoadedRoles,
  read_roles, load_for_check).
- ``retention``, ``risks``: retention.yaml and risks.yaml (LoadedRetention, read_retention; LoadedRisks,
  read_risks; load_for_check).
- ``consents``: consents.yaml for M14 and ``vault consent add``.
- ``_os``: all platform code (msvcrt/fcntl locks, modes, folder fsync).

Import boundary (ARC-01, tests/unit/test_architecture.py): the vault imports only neurogrid.kernel,
neurogrid.model, neurogrid.io and neurogrid.config, never the CLI, the pipeline, the checks or the report;
the checks read it as a supplier.
"""
