# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2022-2026 IMA LLC

"""Shared helper for waiting on Fusion save/upload operations.

`wait_for_upload(save_result, ...)` accepts the three shapes Fusion's save
APIs return depending on the call and client build:

  - `DataFileFuture` with `uploadState` — Component.saveCopyAs
  - `DataFileFuture` with `isComplete` / `error` — Document.save (newer builds)
  - `bool` — Document.save (some builds; uses a version-bump fallback)

Pass `log_fn` to surface heartbeat lines in the caller's log.

Note: `Component.saveCopyAs` from inside a command with CommandInputs needs
a tight `adsk.doEvents()` spin (no `time.sleep`) to advance Fusion's upload
pipeline — see `commands/externalize/entry.py::_save_to_cloud`. This helper
is for `Document.save` flows where the standard polling cadence works.
"""

import time
import adsk.core


DEFAULT_UPLOAD_TIMEOUT_SECONDS = 300
DEFAULT_POLL_INTERVAL_SECONDS = 0.5
DEFAULT_SETTLE_SECONDS = 1.0
DEFAULT_HEARTBEAT_SECONDS = 5.0


def _noop_log(_msg):
    pass


def wait_for_upload(
    save_result,
    context_label,
    *,
    poll_interval_seconds=DEFAULT_POLL_INTERVAL_SECONDS,
    document=None,
    pre_save_version=None,
    timeout_seconds=DEFAULT_UPLOAD_TIMEOUT_SECONDS,
    settle_seconds=DEFAULT_SETTLE_SECONDS,
    log_fn=None,
    heartbeat_seconds=DEFAULT_HEARTBEAT_SECONDS,
):
    """Wait for a Fusion save/upload to finish and report success/failure.

    For the bool path, pass `document` (and optionally `pre_save_version`)
    so the helper has something to poll. Without `document`, a True bool
    is taken at face value.

    `log_fn`, if provided, is called with status strings (entry, heartbeats).
    Use it to surface progress in the caller's log file.

    Returns (ok: bool, message: str). On success, when `save_result` is a
    DataFileFuture, the caller can read `save_result.dataFile`.
    """
    log = log_fn or _noop_log

    if save_result is None:
        msg = f"Save failed for {context_label}: save returned no result"
        log(f"[wait_for_upload] {msg}")
        return False, msg

    poll_interval = max(0.05, poll_interval_seconds)
    log(
        f"[wait_for_upload] start: {context_label} "
        f"result_type={type(save_result).__name__} "
        f"timeout={timeout_seconds}s poll={poll_interval}s"
    )

    if isinstance(save_result, bool):
        if not save_result:
            msg = f"Save failed for {context_label}: save returned False"
            log(f"[wait_for_upload] {msg}")
            return False, msg
        if document is None:
            msg = f"Save+upload completed for {context_label} (bool, no doc to poll)"
            log(f"[wait_for_upload] {msg}")
            return True, msg
        return _wait_via_document_state(
            document,
            context_label,
            poll_interval,
            pre_save_version,
            timeout_seconds,
            settle_seconds,
            log,
            heartbeat_seconds,
        )

    if hasattr(save_result, "uploadState"):
        try:
            initial_state = save_result.uploadState
        except Exception as e:
            initial_state = f"<error reading uploadState: {e}>"
        log(
            f"[wait_for_upload] {context_label}: polling via uploadState "
            f"(initial={initial_state})"
        )
        return _wait_via_upload_state(
            save_result,
            context_label,
            poll_interval,
            timeout_seconds,
            log,
            heartbeat_seconds,
        )

    if hasattr(save_result, "isComplete"):
        log(f"[wait_for_upload] {context_label}: polling via isComplete")
        return _wait_via_is_complete(
            save_result,
            context_label,
            poll_interval,
            timeout_seconds,
            log,
            heartbeat_seconds,
        )

    msg = (
        f"Save failed for {context_label}: unsupported save result type "
        f"{type(save_result).__name__}"
    )
    log(f"[wait_for_upload] {msg}")
    return False, msg


def _wait_via_upload_state(
    future, context_label, poll_interval, timeout_seconds, log, heartbeat_seconds
):
    start = time.monotonic()
    last_heartbeat = start
    last_state = None

    while True:
        try:
            current_state = future.uploadState
        except Exception as e:
            msg = (
                f"Reading uploadState failed for {context_label}: {e}"
            )
            log(f"[wait_for_upload] {msg}")
            return False, msg

        if current_state != adsk.core.UploadStates.UploadProcessing:
            break

        if current_state != last_state:
            log(
                f"[wait_for_upload] {context_label}: uploadState={current_state}"
            )
            last_state = current_state

        adsk.doEvents()
        now = time.monotonic()
        elapsed = now - start

        if heartbeat_seconds > 0 and (now - last_heartbeat) >= heartbeat_seconds:
            log(
                f"[wait_for_upload] {context_label}: still waiting "
                f"(uploadState={current_state}, elapsed={elapsed:.1f}s)"
            )
            last_heartbeat = now

        if timeout_seconds > 0 and elapsed >= timeout_seconds:
            msg = f"Upload timed out for {context_label} after {timeout_seconds}s"
            log(f"[wait_for_upload] {msg}")
            return False, msg
        time.sleep(poll_interval)

    log(
        f"[wait_for_upload] {context_label}: poll loop exited "
        f"uploadState={current_state} elapsed={time.monotonic() - start:.1f}s"
    )

    if current_state == adsk.core.UploadStates.UploadFailed:
        return False, f"Upload failed for {context_label} (UploadFailed)"
    if current_state != adsk.core.UploadStates.UploadFinished:
        return (
            False,
            f"Upload ended in unexpected state for {context_label} "
            f"(uploadState={current_state})",
        )
    try:
        df = future.dataFile
    except Exception as e:
        return (
            False,
            f"Upload finished but reading dataFile raised for {context_label}: {e}",
        )
    if df is None:
        return (
            False,
            f"Upload reported finished but dataFile is None for {context_label}",
        )
    return True, f"Upload completed for {context_label}"


def _wait_via_is_complete(
    future, context_label, poll_interval, timeout_seconds, log, heartbeat_seconds
):
    start = time.monotonic()
    last_heartbeat = start
    while not future.isComplete:
        adsk.doEvents()
        now = time.monotonic()
        elapsed = now - start
        if heartbeat_seconds > 0 and (now - last_heartbeat) >= heartbeat_seconds:
            log(
                f"[wait_for_upload] {context_label}: still waiting "
                f"(isComplete=False, elapsed={elapsed:.1f}s)"
            )
            last_heartbeat = now
        if timeout_seconds > 0 and elapsed >= timeout_seconds:
            msg = (
                f"Save wait timed out for {context_label} after {timeout_seconds}s"
            )
            log(f"[wait_for_upload] {msg}")
            return False, msg
        time.sleep(poll_interval)

    if getattr(future, "error", False):
        error_description = getattr(
            future, "errorDescription", "Unknown upload error"
        )
        return False, f"Save failed for {context_label}: {error_description}"
    return True, f"Save+upload completed for {context_label}"


def _wait_via_document_state(
    document,
    context_label,
    poll_interval,
    pre_save_version,
    timeout_seconds,
    settle_seconds,
    log,
    heartbeat_seconds,
):
    app = adsk.core.Application.get()
    start = time.monotonic()
    last_heartbeat = start
    stable_since = None
    stable_ready_checks = 0

    data_file_id = None
    try:
        if document.dataFile:
            data_file_id = document.dataFile.id
    except Exception:
        data_file_id = None

    while True:
        adsk.doEvents()

        current_version = None
        try:
            if data_file_id:
                refreshed = app.data.findFileById(data_file_id)
                if refreshed and hasattr(refreshed, "versionNumber"):
                    current_version = refreshed.versionNumber
            if (
                current_version is None
                and document.dataFile
                and hasattr(document.dataFile, "versionNumber")
            ):
                current_version = document.dataFile.versionNumber
        except Exception:
            current_version = None

        if (
            pre_save_version is not None
            and current_version is not None
            and current_version > pre_save_version
        ):
            return (
                True,
                f"Save+upload completed for {context_label} "
                f"(version {pre_save_version} -> {current_version})",
            )

        doc_is_saved = getattr(document, "isSaved", None)
        doc_is_modified = getattr(document, "isModified", None)
        if doc_is_saved is True and doc_is_modified is False:
            stable_ready_checks += 1
            if stable_since is None:
                stable_since = time.monotonic()
            if (
                stable_ready_checks >= 3
                and (time.monotonic() - stable_since) >= settle_seconds
            ):
                return True, f"Save+upload completed for {context_label}"
        else:
            stable_ready_checks = 0
            stable_since = None

        now = time.monotonic()
        elapsed = now - start
        if heartbeat_seconds > 0 and (now - last_heartbeat) >= heartbeat_seconds:
            log(
                f"[wait_for_upload] {context_label}: still waiting "
                f"(version={current_version} pre={pre_save_version} "
                f"isSaved={doc_is_saved} isModified={doc_is_modified} "
                f"elapsed={elapsed:.1f}s)"
            )
            last_heartbeat = now

        if timeout_seconds > 0 and elapsed >= timeout_seconds:
            msg = (
                f"Save wait timed out for {context_label} after {timeout_seconds}s"
            )
            log(f"[wait_for_upload] {msg}")
            return False, msg

        time.sleep(poll_interval)
