# P3 operator stop, uninstall, and rollback

Before use, verify the candidate ZIP's SHA-256 against the value delivered through the approved transfer channel. Extract each candidate into a new, version-specific directory; do not merge releases. Before replacing an existing installation, retain its approved ZIP and matching digest in the site-approved rollback location. The archive does not install a service, write manufacturing records, or migrate a site database.

P3 CLI commands exit after the requested operation. The standalone reference host is a foreground loopback-only HTTP process; it does not install a service or background worker. To stop an active investigation, use the host's Cancel control, then press Ctrl-C in the terminal running the host. The MCP adapter records cancellation as requested, not as remotely confirmed. The host returns no partial scientific evidence after cancellation.

To roll back an update, stop the host, remove only the new extraction directory, then extract the retained previously approved ZIP into a separate version-specific directory. Verify that ZIP's SHA-256 before extraction and reinstall its bundled SDK using the same offline steps in README.md. Reapply only the site-approved configuration stored outside the extraction directory. On first installation, the same procedure is an uninstall; there is no earlier P3 release to restore.

To uninstall an extracted candidate, stop the host and remove only the exact extraction directory. For the documented extraction name, run:

    python3 - <<'PY'
    from pathlib import Path
    import shutil

    candidate = Path("/absolute/path/to/p3-candidate-20261124-closure").resolve()
    assert candidate.is_dir() and candidate.name == "p3-candidate-20261124-closure"
    shutil.rmtree(candidate)
    PY

This removes the extracted application, its local virtual environment, and local development files, but not the ZIP archive or files stored elsewhere. Remove an exported evidence file only by its individually reviewed path. Retain authorized configuration, credentials, and audit records according to site policy. P3 does not write manufacturing records or change schemas.

This synthetic stop/uninstall procedure does not qualify production interruption, remote cancellation, audit retention, force-stop, or company rollback controls. The authorized site must verify those controls before internal use; do not use a broad process-kill command or delete site-owned files as a fallback.
