# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2022-2026 IMA LLC

import adsk.core
import adsk.fusion
import os
import re
import time
import traceback
from datetime import datetime
from ...lib import fusionAddInUtils as futil
from ... import config

app = adsk.core.Application.get()
ui = app.userInterface

CMD_NAME = "Externalize"
CMD_ID = "PTAT-externalize"
CMD_Description = (
    "Save a component as an external cloud document and re-insert it at its "
    "original assembly position."
)
IS_PROMOTED = False

# Custom event used to defer the actual save/replace work out of
# command_execute. saveCopyAs's upload pipeline does not advance while
# command_execute holds the main thread (Autodesk forum 11164467); inside
# a customEvent handler it does. The spike command_test_customevent_save
# proved a stuck component (KLROLLE) went from ∞ stall to 5.9s.
EVENT_ID = "PTAT-externalize-runner"

# Global variables by referencing values from /config.py
WORKSPACE_ID = config.design_workspace
TAB_ID = config.tools_tab_id
TAB_NAME = config.my_tab_name

PANEL_ID = config.my_panel_id
PANEL_NAME = config.my_panel_name
PANEL_AFTER = config.my_panel_after

# Resource location for command icons
ICON_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resources", "")

# Command input IDs
SAVE_LOC_ID = "save_location"
SAME_AS_DOC = "Same as Document"
CREATE_SUBFOLDER = "Create Sub-folder"

LOG_ENABLE_ID = "enable_log"
LOG_PATH_ID = "log_path"
LOG_BROWSE_ID = "browse_log"
LOG_OPEN_VIEW_ID = "open_log_view"
RESUME_STATUS_ID = "resume_status"

# Holds references to event handlers
local_handlers = []

# Custom event handler kept alive across command invocations.
_event_handler = None

# State passed from command_execute → custom event handler. Replaced on each
# fire; cleared by the handler when it picks the run up.
_pending_run: dict | None = None

# Resume state computed in command_created and re-checked in command_execute.
resume_plan: dict = {}


# Executed when add-in is run.
def start():
    global _event_handler

    cmd_def = ui.commandDefinitions.addButtonDefinition(
        CMD_ID, CMD_NAME, CMD_Description, ICON_FOLDER
    )
    futil.add_handler(cmd_def.commandCreated, command_created)

    workspace = ui.workspaces.itemById(WORKSPACE_ID)
    toolbar_tab = workspace.toolbarTabs.itemById(TAB_ID)
    if toolbar_tab is None:
        toolbar_tab = workspace.toolbarTabs.add(TAB_ID, TAB_NAME)
    panel = toolbar_tab.toolbarPanels.itemById(PANEL_ID)
    if panel is None:
        panel = toolbar_tab.toolbarPanels.add(PANEL_ID, PANEL_NAME, PANEL_AFTER, False)

    control = panel.controls.addCommand(cmd_def)
    control.isPromoted = IS_PROMOTED

    # Register the runner customEvent. unregister-then-register ensures a
    # clean slate if the add-in was reloaded without restarting Fusion.
    try:
        app.unregisterCustomEvent(EVENT_ID)
    except Exception:
        pass
    custom_event = app.registerCustomEvent(EVENT_ID)
    _event_handler = _RunnerHandler()
    custom_event.add(_event_handler)


# Executed when add-in is stopped.
def stop():
    global _event_handler

    workspace = ui.workspaces.itemById(WORKSPACE_ID)
    panel = workspace.toolbarPanels.itemById(PANEL_ID)
    toolbar_tab = workspace.toolbarTabs.itemById(TAB_ID)
    command_control = panel.controls.itemById(CMD_ID)
    command_definition = ui.commandDefinitions.itemById(CMD_ID)

    if command_control:
        command_control.deleteMe()
    if command_definition:
        command_definition.deleteMe()
    if panel.controls.count == 0:
        panel.deleteMe()
    if toolbar_tab.toolbarPanels.count == 0:
        toolbar_tab.deleteMe()

    try:
        app.unregisterCustomEvent(EVENT_ID)
    except Exception:
        pass
    _event_handler = None


# Called when the user clicks the button.
def command_created(args: adsk.core.CommandCreatedEventArgs):
    futil.log(f"{CMD_NAME} Command Created Event")

    cmd = args.command
    cmd.isExecutedWhenPreEmpted = False
    inputs = cmd.commandInputs

    # Pre-compute resume plan so the Main tab can show status before any work runs.
    global resume_plan
    pending_names = _snapshot_local_component_names()
    try:
        resume_plan = _analyze_resume_state(
            _default_log_path(), app.version, pending_names
        )
    except Exception as resume_error:
        resume_plan = {
            "log_exists": False,
            "should_resume": False,
            "completed_successfully": False,
            "resume_skip_set": set(),
            "status_message": f"Resume check failed ({resume_error}). A full run will start.",
        }

    # ---- Main tab ----
    main_tab = inputs.addTabCommandInput("mainTab", "Main")
    main_inputs = main_tab.children

    sel_input = main_inputs.addSelectionInput(
        "occurrence_sel",
        "Component",
        "Select the component occurrence to externalize",
    )
    sel_input.addSelectionFilter("Occurrences")
    sel_input.setSelectionLimits(1, 1)

    ext_all = main_inputs.addBoolValueInput("externalize_all", "Externalize All", True)
    ext_all.tooltip = (
        "When checked, every local first-level component in the active assembly "
        "is externalized automatically. The component selector is disabled."
    )

    save_loc = main_inputs.addDropDownCommandInput(
        SAVE_LOC_ID,
        "Save Location",
        adsk.core.DropDownStyles.TextListDropDownStyle,  # type: ignore[arg-type]
    )
    save_loc.listItems.add(SAME_AS_DOC, True)
    save_loc.listItems.add(CREATE_SUBFOLDER, False)
    save_loc.tooltip = (
        "Same as Document — saves components into the same hub folder as the active document.\n"
        "Create Sub-folder — saves components into a new sub-folder named after the active document."
    )

    resume_status_input = main_inputs.addTextBoxCommandInput(
        RESUME_STATUS_ID,
        "Run status",
        resume_plan.get("status_message", "A full run will start."),
        3,
        True,
    )
    resume_status_input.tooltip = (
        "Startup check based on the temp log and Fusion client version."
    )

    # ---- Logging tab ----
    log_tab = inputs.addTabCommandInput("logTab", "Logging")
    log_inputs = log_tab.children

    log_enable = log_inputs.addBoolValueInput(
        LOG_ENABLE_ID, "Log Progress", True, "", True
    )
    log_enable.tooltip = (
        "Enables detailed progress logging to a text file during the externalize run."
    )

    log_path = log_inputs.addStringValueInput(
        LOG_PATH_ID, "Log file path", _default_log_path()
    )
    log_path.isReadOnly = True

    browse_btn = log_inputs.addBoolValueInput(
        LOG_BROWSE_ID, "Browse…", False, "", False
    )
    browse_btn.tooltip = "Click to choose a custom log file location."

    open_view = log_inputs.addBoolValueInput(
        LOG_OPEN_VIEW_ID, "Open live log viewer", True, "", True
    )
    open_view.tooltip = (
        "Automatically opens a system console window to live-monitor log output during the run."
    )

    log_path.isEnabled = log_enable.value
    browse_btn.isEnabled = log_enable.value
    open_view.isEnabled = log_enable.value

    futil.add_handler(
        cmd.inputChanged, command_input_changed, local_handlers=local_handlers
    )
    futil.add_handler(cmd.execute, command_execute, local_handlers=local_handlers)
    futil.add_handler(cmd.destroy, command_destroy, local_handlers=local_handlers)


# Called whenever any input value changes in the dialog.
def command_input_changed(args: adsk.core.InputChangedEventArgs):
    futil.log(f"{CMD_NAME} Input Changed Event")

    try:
        changed_input = args.input
        inputs = args.inputs

        if changed_input.id == "externalize_all":
            bool_input = adsk.core.BoolValueCommandInput.cast(changed_input)
            sel_input = adsk.core.SelectionCommandInput.cast(
                inputs.itemById("occurrence_sel")
            )
            if bool_input.value:
                sel_input.isVisible = False
                sel_input.isEnabled = False
                sel_input.setSelectionLimits(0, 1)
            else:
                sel_input.isVisible = True
                sel_input.isEnabled = True
                sel_input.setSelectionLimits(1, 1)
            return

        if changed_input.id == LOG_ENABLE_ID:
            enabled = adsk.core.BoolValueCommandInput.cast(changed_input).value
            inputs.itemById(LOG_PATH_ID).isEnabled = enabled
            inputs.itemById(LOG_BROWSE_ID).isEnabled = enabled
            inputs.itemById(LOG_OPEN_VIEW_ID).isEnabled = enabled
            return

        if changed_input.id == LOG_BROWSE_ID:
            btn = adsk.core.BoolValueCommandInput.cast(changed_input)
            btn.value = False  # momentary

            dlg: adsk.core.FileDialog = ui.createFileDialog()
            dlg.title = "Save log file"
            dlg.filter = "Log files (*.log);;Text files (*.txt);;All Files (*.*)"
            dlg.isMultiSelectEnabled = False
            dlg.initialDirectory = futil.default_log_directory()
            dlg.initialFilename = _propose_default_log_filename()
            if dlg.showSave() == adsk.core.DialogResults.DialogOK:
                path_input = adsk.core.StringValueCommandInput.cast(
                    inputs.itemById(LOG_PATH_ID)
                )
                path_input.value = dlg.filename
            return

    except Exception:
        if ui:
            futil.handle_error(CMD_NAME, show_message_box=True)


# Called when the user clicks OK in the command dialog.
def command_execute(args: adsk.core.CommandEventArgs):
    """Set up the run, then defer all save/replace work to the customEvent
    handler. command_execute returns immediately so Fusion's upload pipeline
    can drain — saveCopyAs does NOT advance while command_execute holds the
    main thread (Autodesk forum 11164467)."""
    global _pending_run
    futil.log(f"{CMD_NAME} Command Execute Event")

    try:
        if _pending_run is not None:
            ui.messageBox(
                "An externalize run is already in progress. Wait for it to "
                "finish before starting another.",
                CMD_NAME,
            )
            return

        design = adsk.fusion.Design.cast(app.activeProduct)
        if not design:
            ui.messageBox("A Fusion 3D Design must be active.", CMD_NAME)
            return

        inputs = args.command.commandInputs

        active_data_file = app.activeDocument.dataFile
        if active_data_file is None:
            ui.messageBox(
                "The active document has not been saved to the cloud.\n"
                "Please save the document to a Fusion Team / Hub folder first.",
                CMD_NAME,
            )
            return

        externalize_all = adsk.core.BoolValueCommandInput.cast(
            inputs.itemById("externalize_all")
        ).value
        save_location = adsk.core.DropDownCommandInput.cast(
            inputs.itemById(SAVE_LOC_ID)
        ).selectedItem.name
        create_log = adsk.core.BoolValueCommandInput.cast(
            inputs.itemById(LOG_ENABLE_ID)
        ).value
        open_log_view = adsk.core.BoolValueCommandInput.cast(
            inputs.itemById(LOG_OPEN_VIEW_ID)
        ).value
        log_path_val = adsk.core.StringValueCommandInput.cast(
            inputs.itemById(LOG_PATH_ID)
        ).value or _default_log_path()

        cloud_folder: adsk.core.DataFolder = active_data_file.parentFolder
        if save_location == CREATE_SUBFOLDER:
            target_folder = _get_or_create_subfolder(cloud_folder, active_data_file.name)
        else:
            existing_sub = _find_existing_subfolder(cloud_folder, active_data_file.name)
            target_folder = existing_sub if existing_sub is not None else cloud_folder

        pending = _build_pending_list(design, externalize_all, inputs)
        if pending is None:
            return  # user-facing message already shown
        if not pending:
            ui.messageBox(
                "No local first-level components were found to externalize.", CMD_NAME
            )
            return

        # Re-check the log right before running so we have the most current state.
        pending_names = [d["comp_name"] for d in pending]
        resume_info = _analyze_resume_state(log_path_val, app.version, pending_names)
        skip_set = resume_info.get("resume_skip_set", set())

        # If the previous run completed cleanly, start fresh — overwrite the log.
        if resume_info.get("completed_successfully"):
            skip_set = set()
            log_mode = "w"
        else:
            log_mode = "a" if resume_info.get("should_resume") else "w"

        runnable = [d for d in pending if d["comp_name"] not in skip_set]
        total = len(runnable)
        skipped_resume = len(pending) - total

        if create_log:
            try:
                _write_log_header(
                    log_path_val,
                    log_mode,
                    fusion_version=app.version,
                    active_data_file=active_data_file,
                    target_folder=target_folder,
                    externalize_all=externalize_all,
                    resume_info=resume_info,
                    runnable_total=total,
                    skipped_resume=skipped_resume,
                    pending_names=pending_names,
                    skip_set=skip_set,
                )
            except Exception as log_e:
                futil.log(f"Failed to initialize log file: {log_e}")
                create_log = False

        log_writer = _LogWriter(log_path_val if create_log else None)

        if create_log and open_log_view:
            _, msg = futil.open_live_log_viewer(log_path_val)
            log_writer(msg)

        # Stash run state for the customEvent handler. The handler runs after
        # this command_execute returns, in a context where saveCopyAs's
        # upload pipeline actually drains.
        _pending_run = {
            "log_writer": log_writer,
            "runnable": runnable,
            "target_folder": target_folder,
            "parent_doc": app.activeDocument,
            "total": total,
            "skipped_resume": skipped_resume,
        }

        log_writer(
            f"Run scheduled: {total} components ({skipped_resume} skipped from prior run). "
            f"Firing customEvent…"
        )
        ok = app.fireCustomEvent(EVENT_ID)
        log_writer(f"fireCustomEvent returned {ok}; dialog will close now.")

    except:  # pylint:disable=bare-except
        _pending_run = None
        app.log(f"{CMD_NAME} failed:\n{traceback.format_exc()}")


# ---------------------------------------------------------------------------
# Custom event handler — runs the actual save/replace work outside command_execute
# ---------------------------------------------------------------------------


class _RunnerHandler(adsk.core.CustomEventHandler):
    """Runs the per-iteration externalize loop in a context where Fusion's
    upload pipeline actually advances.

    Per iteration:
      1. Find existing cloud file by name, or `saveCopyAs` to upload.
      2. `deleteMe` the original local occurrence.
      3. `addByInsert` the cloud reference at the original transform.
      4. `AutoSaveFilesCommand` — local recovery checkpoint (no cloud version).
      5. CHECKPOINT marker → resume can pick up here on next run.

    At end of run: one `Document.save` to commit a single new parent version
    that contains every replacement (instead of one cloud version per
    iteration).
    """

    def notify(self, args):
        global _pending_run
        run = _pending_run
        _pending_run = None

        if run is None:
            futil.log(f"{CMD_NAME}: handler fired with no pending run — ignoring")
            return

        log_writer = run["log_writer"]
        runnable = run["runnable"]
        target_folder = run["target_folder"]
        parent_doc = run["parent_doc"]
        total = run["total"]
        skipped_resume = run["skipped_resume"]

        # Use the lightweight status-bar progress bar (NOT the modal
        # ProgressDialog — that one was tested and didn't help; we want
        # non-modal feedback that doesn't intercept events).
        progress_bar = ui.progressBar
        try:
            try:
                progress_bar.show(
                    f"{CMD_NAME}: externalizing %v of %m…", 0, max(total, 1)
                )
            except Exception:
                # Status-bar progress is best-effort; never fail the run
                # because of it.
                pass

            replaced = self._run_loop(
                runnable, target_folder, total, log_writer, progress_bar
            )
            self._finalize(
                parent_doc, replaced, total, skipped_resume, log_writer
            )
        except Exception:
            log_writer(
                f"Externalize handler crashed:\n{traceback.format_exc()}"
            )
            try:
                ui.messageBox(
                    f"{CMD_NAME} failed:\n{traceback.format_exc()}", CMD_NAME
                )
            except Exception:
                pass
        finally:
            try:
                progress_bar.hide()
            except Exception:
                pass

    def _run_loop(self, runnable, target_folder, total, log_writer, progress_bar):
        design = adsk.fusion.Design.cast(app.activeProduct)
        if design is None:
            log_writer("ERROR: no active design when handler started")
            return 0
        root = design.rootComponent

        replaced = 0
        no_cancel = lambda: False

        for idx, data in enumerate(runnable, 1):
            comp_name = data["comp_name"]

            try:
                progress_bar.message = f"Externalizing {comp_name} (%v of %m)"
                progress_bar.progressValue = idx - 1
            except Exception:
                pass

            try:
                df = _find_existing_cloud_file(target_folder, comp_name)
                if df is not None:
                    log_writer(f"[{idx}/{total}] reused {comp_name}")
                else:
                    log_writer(f"[{idx}/{total}] uploading {comp_name}…")
                    upload_t0 = time.monotonic()
                    df = _save_to_cloud(
                        data["component"],
                        comp_name,
                        target_folder,
                        log_writer,
                        no_cancel,
                    )
                    if df is None:
                        log_writer(
                            f"[{idx}/{total}] upload failed for {comp_name} — skipping"
                        )
                        continue
                    log_writer(
                        f"[{idx}/{total}] uploaded {comp_name} "
                        f"({time.monotonic() - upload_t0:.1f}s)"
                    )

                log_writer(f"[{idx}/{total}] replacing {comp_name}…")
                data["occ"].deleteMe()
                root.occurrences.addByInsert(df, data["transform"], True)
                replaced += 1
                log_writer(f"[{idx}/{total}] replaced {comp_name}")

                # Local recovery checkpoint — keeps work safe across crashes
                # without creating a new parent cloud version every iteration.
                _temp_save(log_writer)

                log_writer(
                    f"CHECKPOINT|REPLACE_COMPLETE|component={comp_name}|index={idx}"
                )

                try:
                    progress_bar.progressValue = idx
                except Exception:
                    pass

            except Exception:
                log_writer(
                    f'[{idx}/{total}] error on "{comp_name}":\n{traceback.format_exc()}'
                )

        return replaced

    def _finalize(self, parent_doc, replaced, total, skipped_resume, log_writer):
        # Single cloud-committing save for the parent. One new parent version
        # for the whole run, no matter how many components were replaced.
        if replaced > 0:
            try:
                _save_parent_doc(parent_doc, replaced, log_writer, lambda: False)
            except Exception:
                log_writer(f"Parent save raised:\n{traceback.format_exc()}")

        if replaced == total:
            footer = (
                f"Externalize completed successfully. {replaced} of {total} replaced "
                f"this run; {skipped_resume} from prior run."
            )
        else:
            footer = (
                f"Externalize finished with skips. {replaced} of {total} replaced "
                f"this run; {skipped_resume} from prior run."
            )
        log_writer(footer)

        try:
            ui.messageBox(
                f"{replaced} of {total} components were externalized this run."
                + (
                    f"\nResumed from prior run: {skipped_resume} already done."
                    if skipped_resume
                    else ""
                ),
                CMD_NAME,
            )
        except Exception:
            pass


def _temp_save(log_fn=None):
    """Recovery checkpoint via Fusion's `AutoSaveFilesCommand` text command.

    Saves the active document's working state to local recovery cache without
    creating a new cloud version. Combined with a single `Document.save` at
    end-of-run, this gives crash safety mid-run without burning one cloud
    version per replacement.
    """
    log = log_fn or (lambda _msg: None)
    try:
        cmd_defs = ui.commandDefinitions
        autosave = cmd_defs.itemById("AutoSaveFilesCommand")
        if autosave is None:
            log("AutoSaveFilesCommand not found in commandDefinitions")
            return False
        return bool(autosave.execute())
    except Exception as e:
        log(f"AutoSaveFilesCommand raised: {e}")
        return False


# ---------------------------------------------------------------------------
# Pending-list construction
# ---------------------------------------------------------------------------


def _snapshot_local_component_names():
    """Return component names for local first-level occurrences in the active design.

    Used by command_created to drive the resume status, before any inputs are read.
    Robust to no-active-design — returns an empty list.
    """
    design = adsk.fusion.Design.cast(app.activeProduct)
    if not design:
        return []
    names = []
    root = design.rootComponent
    for i in range(root.occurrences.count):
        occ = root.occurrences.item(i)
        if occ.component.parentDesign == design:
            names.append(occ.component.name)
    return names


def _build_pending_list(design, externalize_all, inputs):
    """Build the [{occ, component, comp_name, transform}, …] list for the run.

    Returns an empty list if there are no local components, or None on a user-facing
    error (in which case a messageBox has already been shown)."""
    root = design.rootComponent

    if externalize_all:
        pending = []
        for i in range(root.occurrences.count):
            occ = root.occurrences.item(i)
            if occ.component.parentDesign == design:
                pending.append(
                    {
                        "occ": occ,
                        "component": occ.component,
                        "comp_name": occ.component.name,
                        "transform": occ.transform2,
                    }
                )
        return pending

    sel_input = adsk.core.SelectionCommandInput.cast(inputs.itemById("occurrence_sel"))
    if sel_input.selectionCount == 0:
        ui.messageBox("No component selected.", CMD_NAME)
        return None

    entity = sel_input.selection(0).entity
    if isinstance(entity, adsk.fusion.Occurrence):
        occ = entity
    elif hasattr(entity, "assemblyContext") and entity.assemblyContext:
        occ = entity.assemblyContext
    else:
        ui.messageBox(
            "Selected entity is not a component occurrence. Please select a component.",
            CMD_NAME,
        )
        return None

    if occ.component.parentDesign != design:
        ui.messageBox(
            f'"{occ.component.name}" is already an external reference.',
            CMD_NAME,
        )
        return []

    return [
        {
            "occ": occ,
            "component": occ.component,
            "comp_name": occ.component.name,
            "transform": occ.transform2,
        }
    ]


# ---------------------------------------------------------------------------
# Parent-doc helpers
# ---------------------------------------------------------------------------


def _save_to_cloud(
    component: adsk.fusion.Component,
    comp_name: str,
    cloud_folder: adsk.core.DataFolder,
    log_fn=None,
    cancel_check=None,
):
    """Upload `component` to `cloud_folder`; return DataFile or None.

    Tight `adsk.doEvents()` spin on `future.uploadState`, no `time.sleep`.
    The continuous event pumping is what advances Fusion's upload pipeline
    while command_execute is held open. A `time.sleep` parks the main
    thread and the pipeline stalls indefinitely (forum 11164467); batching
    many futures without a tight per-iteration pump has the same effect.
    Pattern restored from commit 9609042 where it was first proven to work.
    """
    log = log_fn or (lambda _msg: None)
    is_cancelled = cancel_check or (lambda: False)

    save_t0 = time.monotonic()
    try:
        future = component.saveCopyAs(comp_name, cloud_folder, "", "")
    except Exception as e:
        log(f"  saveCopyAs raised: {e}")
        return None
    if future is None:
        log("  saveCopyAs returned None")
        return None

    last_heartbeat = save_t0
    while True:
        adsk.doEvents()
        try:
            state = future.uploadState
        except Exception as e:
            log(f"  reading uploadState raised: {e}")
            return None

        if state != adsk.core.UploadStates.UploadProcessing:
            break
        if is_cancelled():
            return None

        now = time.monotonic()
        if now - last_heartbeat >= 5.0:
            log(f"  still waiting on {comp_name} ({now - save_t0:.0f}s)")
            last_heartbeat = now

    if state == adsk.core.UploadStates.UploadFailed:
        return None

    try:
        df = future.dataFile
    except Exception as e:
        log(f"  reading future.dataFile raised: {e}")
        return None
    return df


def _save_parent_doc(parent_doc, replaced_count, log_fn, cancel_check):
    """Commit the parent design once after the run.

    Returns True on success, False on failure.
    """
    pre_version = None
    try:
        if parent_doc.dataFile and hasattr(parent_doc.dataFile, "versionNumber"):
            pre_version = parent_doc.dataFile.versionNumber
    except Exception:
        pre_version = None

    log_fn(f"Saving parent design (pre_version={pre_version})…")
    try:
        save_result = parent_doc.save(
            f"Externalize: {replaced_count} components replaced"
        )
    except Exception as e:
        log_fn(f"Parent save raised: {e}")
        return False

    ok, msg = futil.wait_for_upload(
        save_result,
        "parent assembly",
        document=parent_doc,
        pre_save_version=pre_version,
    )
    if not ok:
        log_fn(f"Parent save failed: {msg}")
        return False
    if cancel_check and cancel_check():
        return False
    log_fn(msg)
    return True


# ---------------------------------------------------------------------------
# Cloud folder helpers
# ---------------------------------------------------------------------------


def _get_or_create_subfolder(parent_folder: adsk.core.DataFolder, name: str):
    """Return (or create) the subfolder of `parent_folder` with the given name."""
    sub_folders = parent_folder.dataFolders
    for i in range(sub_folders.count):
        folder = sub_folders.item(i)
        if folder.name == name:
            return folder
    return sub_folders.add(name)


def _find_existing_subfolder(parent_folder: adsk.core.DataFolder, name: str):
    """Return the subfolder with the given name inside parent_folder, or None."""
    sub_folders = parent_folder.dataFolders
    for i in range(sub_folders.count):
        folder = sub_folders.item(i)
        if folder.name == name:
            return folder
    return None


def _find_existing_cloud_file(cloud_folder: adsk.core.DataFolder, comp_name: str):
    """Return the DataFile whose name matches comp_name, or None."""
    data_files = cloud_folder.dataFiles
    for i in range(data_files.count):
        item = data_files.item(i)
        if item.name == comp_name:
            return item
    return None


# ---------------------------------------------------------------------------
# Logging / resume
# ---------------------------------------------------------------------------


def _propose_default_log_filename() -> str:
    """Generate a default log filename based on the active document name."""
    doc = app.activeDocument
    base_name = "externalize_log"
    if doc and doc.dataFile:
        base_name = doc.dataFile.name
    elif doc and doc.name:
        base_name = doc.name
    base_name = re.sub(r"[\\/:*?\"<>|]+", "_", base_name)
    if not base_name.lower().endswith(".log"):
        base_name += "_externalize.log"
    return base_name


def _default_log_path() -> str:
    """Return the default log path used for auto logging in this command."""
    return os.path.join(futil.default_log_directory(), _propose_default_log_filename())


class _LogWriter:
    """Append-on-call writer. When path is None, lines go only to futil.log
    (which writes to the Text Command window when DEBUG is on). When path is
    set, each call also appends one line to the file — open/write/close per
    call, so a crash still leaves a complete trail."""

    def __init__(self, path: str | None):
        self._path = path

    def __call__(self, line: str):
        futil.log(line)
        if self._path is None:
            return
        try:
            with open(self._path, "a", encoding="utf-8") as fh:
                fh.write(line + "\n")
        except Exception as e:
            futil.log(f"Failed to write log entry: {e}")


def _write_log_header(
    path: str,
    mode: str,
    *,
    fusion_version,
    active_data_file,
    target_folder,
    externalize_all,
    resume_info,
    runnable_total,
    skipped_resume,
    pending_names,
    skip_set,
):
    """Open the log file in `mode` (w or a) and write the run preamble."""
    with open(path, mode, encoding="utf-8") as fh:
        if mode == "a":
            fh.write("\n----- Resume attempt -----\n")
        fh.write(
            f"===== Externalize run started {datetime.now().isoformat()} =====\n"
        )
        fh.write(f"Fusion client version: {fusion_version}\n")
        fh.write(
            f"Active Document: {active_data_file.name} (id={active_data_file.id})\n"
        )
        fh.write(f"Target folder: {target_folder.name}\n")
        fh.write(f"Externalize All: {externalize_all}\n")
        fh.write(f"Resume requested: {resume_info.get('should_resume', False)}\n")
        fh.write(
            f"Components to process: {runnable_total}  "
            f"(skipped from prior run: {skipped_resume})\n"
        )
        fh.write("Pending order:\n")
        for name in pending_names:
            marker = "  [done]" if name in skip_set else ""
            fh.write(f"  - {name}{marker}\n")
        fh.write("Externalize log:\n")


def _analyze_resume_state(log_path, fusion_client_version, current_pending_names):
    """Inspect an existing log and return whether this run should resume."""
    result = {
        "log_exists": False,
        "matches_version": False,
        "completed_successfully": False,
        "should_resume": False,
        "resume_skip_set": set(),
        "status_message": "No previous log found. A full run will start.",
    }

    if not log_path or not os.path.exists(log_path):
        return result
    result["log_exists"] = True

    try:
        with open(log_path, "r", encoding="utf-8") as fh:
            log_lines = fh.read().splitlines()
    except Exception as read_error:
        result["status_message"] = (
            f"Found previous log but could not read it ({read_error}). A full run will start."
        )
        return result

    version_line = next(
        (line for line in log_lines if line.startswith("Fusion client version:")), None
    )
    logged_version = ""
    if version_line:
        logged_version = version_line.split(":", 1)[1].strip()

    if logged_version != fusion_client_version:
        result["status_message"] = (
            "Previous temp log is from a different Fusion client version. "
            "A full run will start."
        )
        return result
    result["matches_version"] = True

    if any("Externalize completed successfully" in line for line in log_lines):
        result["completed_successfully"] = True
        result["status_message"] = (
            "Previous run completed successfully. Log will be reset for a new run."
        )
        return result

    completed = set()
    for line in log_lines:
        line = line.strip()
        if not line.startswith("CHECKPOINT|REPLACE_COMPLETE|"):
            continue
        parts = line.split("|")
        for part in parts[2:]:
            if part.startswith("component="):
                completed.add(part.split("=", 1)[1])
                break

    relevant = completed & set(current_pending_names)
    if relevant:
        result["should_resume"] = True
        result["resume_skip_set"] = relevant
        result["status_message"] = (
            f"Resume available — {len(relevant)} of {len(current_pending_names)} already done."
        )
    else:
        result["status_message"] = (
            "Previous run did not complete; no matching checkpoints. A full run will start."
        )
    return result


# Called when the command is destroyed (dialog closed).
def command_destroy(args: adsk.core.CommandEventArgs):
    futil.log(f"{CMD_NAME} Command Destroy Event")
    global local_handlers, resume_plan
    local_handlers = []
    resume_plan = {}
