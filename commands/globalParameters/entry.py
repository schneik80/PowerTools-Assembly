# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2022-2026 IMA LLC

import adsk.core
import adsk.fusion
import os
import json
import re
from ...lib import fusionAddInUtils as futil
from ...lib.fusionAddInUtils import cache_utils as cache
from ... import config

app = adsk.core.Application.get()
ui = app.userInterface

# ── Command identity ──────────────────────────────────────────────────────────
CMD_ID = "PTAT-globalParameters"
CMD_NAME = "Global Parameters"
CMD_Description = "Create and Manage global parameters for the active Fusion Project"
IS_PROMOTED = False

# ── UI placement ──────────────────────────────────────────────────────────────
WORKSPACE_ID = config.design_workspace
TAB_ID = config.tools_tab_id
TAB_NAME = config.my_tab_name
PANEL_ID = config.my_panel_id
PANEL_NAME = config.my_panel_name
PANEL_AFTER = config.my_panel_after

# ── Paths ──────────────────────────────────────────────────────────────────────
ICON_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resources", "")

# ── Constants ─────────────────────────────────────────────────────────────────
UNIT_OPTIONS = ["in", "ft", "mm", "cm", "m"]

# ── Parameter name validation ─────────────────────────────────────────────────
# First char must be a letter; subsequent chars may be letter/digit or allowed symbols.
_PARAM_NAME_RE = re.compile(r'^[A-Za-z][A-Za-z0-9_"$°µ]*$')

# Fusion 360 unit designations that are reserved and cannot be parameter names.
# This list is case-sensitive — Fusion expressions are case-sensitive.
_RESERVED_UNITS: frozenset[str] = frozenset(
    {
        # Length
        "mm",
        "cm",
        "m",
        "km",
        "in",
        "ft",
        "yd",
        "mil",
        "thou",
        "um",
        "nm",
        "pm",
        # Angle
        "deg",
        "rad",
        "arcmin",
        "arcsec",
        "mas",
        "sr",
        # Volume / capacity
        "ml",
        "l",
        "dl",
        "cl",
        "gal",
        "qt",
        "pt",
        # Temperature
        "C",
        "F",
        "K",
        # Mass
        "g",
        "kg",
        "lb",
        "oz",
        "slug",
        "mg",
        "t",
        # Force
        "N",
        "kN",
        "lbf",
        "kip",
        "ozf",
        "dyn",
        # Pressure
        "Pa",
        "kPa",
        "MPa",
        "GPa",
        "psi",
        "ksi",
        "bar",
        "atm",
        # Power
        "W",
        "kW",
        "MW",
        "hp",
        # Energy
        "J",
        "kJ",
        "MJ",
        "cal",
        "kcal",
        "BTU",
        "Wh",
        "kWh",
        # Electrical
        "A",
        "mA",
        "V",
        "mV",
        "kV",
        "ohm",
        "Hz",
        "kHz",
        "MHz",
        # Time
        "s",
        "ms",
        "us",
        "min",
        "hr",
        # Built-in constant
        "pi",
    }
)
TABLE_ID = "gp_param_table"
ADD_BTN_ID = "gp_add_row_btn"
DEL_BTN_ID = "gp_del_row_btn"
HEADER_ROW = 0  # row 0 is always the frozen column-header row
CREATE_NEW_LABEL = "Create New"
MODE_INPUT_ID = "gp_mode"
STATUS_INPUT_ID = "gp_status"
PARAM_SET_NAME_ID = "gp_param_set_name"
# Sentinel prefix stored in parameter comments to identify PowerTools-managed parameters.
# UNIT_OPTIONS are the units offered in the UI; _RESERVED_UNITS is the broader set
# of Fusion unit strings that are forbidden as parameter names.
_PARAM_TAG = "PT-globparm"

local_handlers = []

# Module-level state populated when the dialog opens
_param_doc_map: dict = {}  # display name → adsk.core.DataFile
_active_doc_ref = None  # active document at dialog-open time
_active_project_ref = None  # active Fusion project at dialog-open time
_row_counter = 0  # monotonically-increasing row ID to avoid input-ID conflicts
_table_dirty = False  # True when the user has edited the table since last load
_command_executed = False  # True once command_execute has fired successfully
_param_doc_names: list[str] = []  # cached display names for dropdown


def _is_valid_param_name(name: str) -> tuple[bool, str]:
    """Return (is_valid: bool, reason: str) for a Fusion 360 parameter name."""
    if not name:
        return False, "Name is required"
    if not name[0].isalpha():
        return False, "Must start with a letter"
    if not _PARAM_NAME_RE.match(name):
        return False, 'Only letters, digits, _, ", $, °, µ are allowed'
    if name in _RESERVED_UNITS:
        return False, f'"{name}" is a reserved Fusion unit name'
    return True, ""


# ── Lifecycle ─────────────────────────────────────────────────────────────────


def start():
    # Clean up any stale definition left by a previous crash or incomplete stop
    existing_def = ui.commandDefinitions.itemById(CMD_ID)
    if existing_def:
        existing_def.deleteMe()

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


def stop():
    workspace = ui.workspaces.itemById(WORKSPACE_ID)
    panel = workspace.toolbarPanels.itemById(PANEL_ID)
    toolbar_tab = workspace.toolbarTabs.itemById(TAB_ID)
    command_control = panel.controls.itemById(CMD_ID) if panel else None
    command_def = ui.commandDefinitions.itemById(CMD_ID)
    if command_control:
        command_control.deleteMe()
    if command_def:
        command_def.deleteMe()
    if panel and panel.controls.count == 0:
        panel.deleteMe()
    if toolbar_tab and toolbar_tab.toolbarPanels.count == 0:
        toolbar_tab.deleteMe()


# ── Helpers ───────────────────────────────────────────────────────────────────


def _write_document_cache(doc: adsk.core.Document):
    """Write the active document's URN/id to the add-in cache folder.

    Returns (doc_id, project_name).
    Raises RuntimeError when the document has not yet been saved to a project.
    """
    data_file = doc.dataFile
    if data_file is None:
        raise RuntimeError(
            "This document has not been saved to a Fusion project.\n"
            "Please save it first, then try again."
        )

    doc_id = data_file.id
    project_name = data_file.parentFolder.parentProject.name

    os.makedirs(cache.CACHE_FOLDER, exist_ok=True)

    # Build a filesystem-safe filename from the document ID
    safe_id = re.sub(r"[^\w\-]", "_", doc_id)
    cache_path = os.path.join(cache.CACHE_FOLDER, f"{safe_id}.json")

    cache_data = {
        "documentId": doc_id,
        "documentName": doc.name,
        "projectName": project_name,
    }
    with open(cache_path, "w", encoding="utf-8") as fh:
        json.dump(cache_data, fh, indent=2)

    futil.log(f"{CMD_NAME}: cache written → {cache_path}")
    return doc_id, project_name


def _pending_cache_path(doc: adsk.core.Document) -> str | None:
    """Return the filesystem path for the pending-cache JSON for *doc*, or None
    if the document has not been saved to a project."""
    if doc is None or doc.dataFile is None:
        return None
    safe_id = re.sub(r"[^\w\-]", "_", doc.dataFile.id)
    return os.path.join(cache.CACHE_FOLDER, f"{safe_id}_pending.json")


def _write_pending_cache(
    doc: adsk.core.Document,
    mode: str,
    param_set_name: str,
    parameters: list,
) -> None:
    """Serialize the current dialog state to a pending-cache JSON file so it can
    be restored if the user chooses to reopen the dialog after cancelling."""
    path = _pending_cache_path(doc)
    if path is None:
        return
    os.makedirs(cache.CACHE_FOLDER, exist_ok=True)
    payload = {"mode": mode, "param_set_name": param_set_name, "parameters": parameters}
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)
    futil.log(f"{CMD_NAME}: pending cache written → {path}")


def _read_pending_cache(doc: adsk.core.Document) -> dict | None:
    """Return the pending-cache dict for *doc*, or None if no cache exists."""
    path = _pending_cache_path(doc)
    if path is None or not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        futil.log(f"{CMD_NAME}: failed to read pending cache — ignoring")
        return None


def _clear_pending_cache(doc: adsk.core.Document) -> None:
    """Delete the pending-cache file for *doc* if it exists."""
    path = _pending_cache_path(doc)
    if path and os.path.exists(path):
        try:
            os.remove(path)
            futil.log(f"{CMD_NAME}: pending cache deleted → {path}")
        except Exception:
            futil.log(f"{CMD_NAME}: failed to delete pending cache — ignoring")


def _add_header_row(
    inputs: adsk.core.CommandInputs, table: adsk.core.TableCommandInput
):
    """Add a read-only header row as the first row of the table."""
    labels = ["", "Name", "Value", "Unit", "Comment"]
    for col, label in enumerate(labels):
        hdr = inputs.addStringValueInput(f"gp_hdr_{col}", "", label)
        hdr.isReadOnly = True
        table.addCommandInput(hdr, HEADER_ROW, col)


def _add_data_row(
    inputs: adsk.core.CommandInputs, table: adsk.core.TableCommandInput
) -> None:
    """Append one blank editable parameter row to the table."""
    _add_data_row_with_values(inputs, table, "", "0.0", "mm", "", True)


def _collect_rows(table: adsk.core.TableCommandInput) -> list[dict]:
    """Return a list of dicts for every data row (skips header row 0)."""
    rows = []
    for r in range(HEADER_ROW + 1, table.rowCount):
        chk = adsk.core.BoolValueCommandInput.cast(table.getInputAtPosition(r, 0))
        name = adsk.core.StringValueCommandInput.cast(table.getInputAtPosition(r, 1))
        val = adsk.core.StringValueCommandInput.cast(table.getInputAtPosition(r, 2))
        unit = adsk.core.DropDownCommandInput.cast(table.getInputAtPosition(r, 3))
        cmnt = adsk.core.StringValueCommandInput.cast(table.getInputAtPosition(r, 4))

        if name is None:
            continue

        rows.append(
            {
                "enabled": chk.value if chk else False,
                "name": name.value.strip(),
                "value": float(val.value) if val and val.value.strip() else 0.0,
                "unit": unit.selectedItem.name if unit else "mm",
                "comment": cmnt.value if cmnt else "",
            }
        )
    return rows


def _any_row_checked(table: adsk.core.TableCommandInput) -> bool:
    """Return True if at least one data row checkbox is checked."""
    for r in range(HEADER_ROW + 1, table.rowCount):
        chk = adsk.core.BoolValueCommandInput.cast(table.getInputAtPosition(r, 0))
        if chk and chk.value:
            return True
    return False


def _ensure_param_doc_map_loaded(project) -> None:
    """Load Hub-backed DataFile map on demand if not already available."""
    global _param_doc_map, _param_doc_names
    if _param_doc_map:
        return
    with futil.perf_timer("list_param_docs (lazy Hub scan)", "GP.docs_resolve"):
        _param_doc_map = cache.list_param_docs(project, CMD_NAME)
    _param_doc_names = list(_param_doc_map.keys())


def _add_data_row_with_values(
    inputs: adsk.core.CommandInputs,
    table: adsk.core.TableCommandInput,
    name: str,
    value_str: str,
    unit: str,
    comment: str,
    enabled: bool = True,
) -> None:
    """Add a data row pre-filled with the given values."""
    global _row_counter
    _row_counter += 1
    rid = _row_counter
    row = table.rowCount

    chk = inputs.addBoolValueInput(f"gp_chk_{rid}", " ", True, "", enabled)
    name_in = inputs.addStringValueInput(f"gp_name_{rid}", "Name", name)
    val_in = inputs.addStringValueInput(f"gp_val_{rid}", "Value", value_str)
    unit_in = inputs.addDropDownCommandInput(
        f"gp_unit_{rid}", "Unit", adsk.core.DropDownStyles.TextListDropDownStyle  # type: ignore[arg-type]
    )
    for u in UNIT_OPTIONS:
        unit_in.listItems.add(u, u == unit, "")
    cmnt_in = inputs.addStringValueInput(f"gp_cmnt_{rid}", "Comment", comment)

    table.addCommandInput(chk, row, 0)
    table.addCommandInput(name_in, row, 1)
    table.addCommandInput(val_in, row, 2)
    table.addCommandInput(unit_in, row, 3)
    table.addCommandInput(cmnt_in, row, 4)


def _load_parameters_from_doc(
    data_file,
    inputs: adsk.core.CommandInputs,
    table: adsk.core.TableCommandInput,
) -> None:
    """Open an existing parameters document and load its user parameters into the table."""
    while table.rowCount > HEADER_ROW + 1:
        table.deleteRow(table.rowCount - 1)

    original_doc = app.activeDocument
    with futil.perf_timer("documents.open", "GP._load_params_from_doc"):
        params_doc = app.documents.open(data_file, False)
    try:
        design = adsk.fusion.Design.cast(
            params_doc.products.itemByProductType("DesignProductType")
        )
        if design is None:
            return
        n = design.userParameters.count
        with futil.perf_timer(f"build table rows (n={n})", "GP._load_params_from_doc"):
            for i in range(n):
                p = design.userParameters.item(i)
                # Parse the numeric part from the stored expression (e.g. "25.4 mm" → "25.4")
                expr = p.expression or "0.0"
                parts = expr.split()
                value_str = parts[0] if parts else "0.0"
                unit = p.unit if p.unit in UNIT_OPTIONS else "mm"
                raw_comment = p.comment or ""
                if raw_comment.startswith(_PARAM_TAG):
                    raw_comment = raw_comment[len(_PARAM_TAG) :].strip()
                _add_data_row_with_values(
                    inputs, table, p.name, value_str, unit, raw_comment
                )
    finally:
        with futil.perf_timer("documents.close", "GP._load_params_from_doc"):
            params_doc.close(False)
        cache.safe_activate(original_doc, CMD_NAME)


def _update_parameters_document(
    parameters: list,
    params_data_file,
    active_doc: adsk.core.Document,
) -> None:
    """Open an existing parameters document, replace its user parameters, and save."""
    with futil.perf_timer("documents.open", "GP._update_params_doc"):
        params_doc = app.documents.open(params_data_file, False)
    try:
        design = adsk.fusion.Design.cast(
            params_doc.products.itemByProductType("DesignProductType")
        )
        if design is None:
            raise RuntimeError(
                "Could not obtain Design product from parameters document."
            )
        n_existing = design.userParameters.count
        with futil.perf_timer(
            f"deleteMe loop (n={n_existing})", "GP._update_params_doc"
        ):
            while design.userParameters.count > 0:
                design.userParameters.item(0).deleteMe()
        n_new = len(parameters)
        with futil.perf_timer(
            f"userParameters.add loop (n={n_new})", "GP._update_params_doc"
        ):
            for p in parameters:
                raw_comment = p["comment"].strip()
                comment = f"{_PARAM_TAG} {raw_comment}".strip()
                value_input = adsk.core.ValueInput.createByString(
                    f"{p['value']} {p['unit']}"
                )
                user_param = design.userParameters.add(
                    p["name"], value_input, p["unit"], comment
                )
                user_param.isFavorite = True
        with futil.perf_timer("document.save", "GP._update_params_doc"):
            params_doc.save("Global Parameters — PowerTools")
        cache.write_param_set_sidecar(params_data_file, parameters, CMD_NAME)
        futil.log(
            f"{CMD_NAME}: existing parameters document updated → {params_data_file.name}"
        )
    except Exception:
        params_doc.close(False)
        cache.safe_activate(active_doc, CMD_NAME)
        raise
    with futil.perf_timer("documents.close", "GP._update_params_doc"):
        params_doc.close(False)
    cache.safe_activate(active_doc, CMD_NAME)


def _create_parameters_document(
    parameters: list,
    active_doc: adsk.core.Document,
    param_set_name: str,
) -> tuple:
    """Create a new Fusion doc with enabled user parameters, save it to a
    '_Global Parameters' folder at the root of the active Fusion project,
    switch back to active_doc, and return (params_doc, params_data_file).
    The caller is responsible for closing params_doc.
    """
    project = _active_project_ref
    if project is None:
        raise RuntimeError("No active Fusion project found.")
    root_folder = project.rootFolder

    # Find or create the "_Global Parameters" folder at the project root
    with futil.perf_timer("find_global_params_folder", "GP._create_params_doc"):
        target_folder = cache.find_global_params_folder(project, CMD_NAME)
    if target_folder is None:
        with futil.perf_timer(
            "dataFolders.add (create folder)", "GP._create_params_doc"
        ):
            target_folder = root_folder.dataFolders.add(cache.GLOBAL_PARAMS_FOLDER_NAME)
        cache.write_global_params_folder_cache(project, target_folder, CMD_NAME)
    else:
        cache.write_global_params_folder_cache(project, target_folder, CMD_NAME)

    doc_name = param_set_name

    # Creating a new doc switches app.activeDocument — active_doc was captured before this call
    with futil.perf_timer("documents.add (new design doc)", "GP._create_params_doc"):
        params_doc = app.documents.add(adsk.core.DocumentTypes.FusionDesignDocumentType)

    try:
        design = adsk.fusion.Design.cast(
            params_doc.products.itemByProductType("DesignProductType")
        )
        if design is None:
            raise RuntimeError("Could not obtain Design product from new document.")

        design.designType = adsk.fusion.DesignTypes.ParametricDesignType

        n = len(parameters)
        with futil.perf_timer(
            f"userParameters.add loop (n={n})", "GP._create_params_doc"
        ):
            for p in parameters:
                raw_comment = p["comment"].strip()
                comment = f"{_PARAM_TAG} {raw_comment}".strip()
                # p["value"] is a Python float from _collect_rows; produces e.g. "25.4 mm"
                value_input = adsk.core.ValueInput.createByString(
                    f"{p['value']} {p['unit']}"
                )
                user_param = design.userParameters.add(
                    p["name"], value_input, p["unit"], comment
                )
                user_param.isFavorite = True

        with futil.perf_timer("document.saveAs (Hub upload)", "GP._create_params_doc"):
            params_doc.saveAs(
                doc_name, target_folder, "Global Parameters — PowerTools", ""
            )
        params_data_file = params_doc.dataFile
        cache.write_param_set_sidecar(params_data_file, parameters, CMD_NAME)

    except Exception:
        # If creation failed, close the partial document before re-raising
        params_doc.close(False)
        cache.safe_activate(active_doc, CMD_NAME)
        raise

    # Switch back to the original document
    cache.safe_activate(active_doc, CMD_NAME)
    futil.log(f"{CMD_NAME}: parameters document saved → {doc_name}")
    return params_doc, params_data_file


def _write_params_to_active(
    parameters: list,
    active_doc: adsk.core.Document,
) -> None:
    """Write *parameters* directly into active_doc's user parameters.

    Existing user parameters that match a name in *parameters* are updated
    in-place; new names are added. This avoids creating any derived component
    reference in the active document's browser.
    """
    active_design = adsk.fusion.Design.cast(
        active_doc.products.itemByProductType("DesignProductType")
    )
    if active_design is None:
        raise RuntimeError("Could not obtain Design product from active document.")

    n = len(parameters)
    user_params = active_design.userParameters
    with futil.perf_timer(
        f"write userParameters loop (n={n})", "GP._write_params_to_active"
    ):
        for p in parameters:
            raw_comment = p["comment"].strip()
            comment = f"{_PARAM_TAG} {raw_comment}".strip()
            value_input = adsk.core.ValueInput.createByString(
                f"{p['value']} {p['unit']}"
            )
            existing = user_params.itemByName(p["name"])
            if existing:
                existing.expression = f"{p['value']} {p['unit']}"
                existing.comment = comment
                existing.isFavorite = True
            else:
                new_param = user_params.add(p["name"], value_input, p["unit"], comment)
                new_param.isFavorite = True

    futil.log(
        f"{CMD_NAME}: {len(parameters)} parameter(s) written directly into active document."
    )


# ── UI helpers ────────────────────────────────────────────────────────────────


def _update_status(inputs: adsk.core.CommandInputs, dirty: bool) -> None:
    """Update the status text below the parameters table."""
    status = adsk.core.TextBoxCommandInput.cast(inputs.itemById(STATUS_INPUT_ID))
    if status:
        status.text = "Unsaved changes" if dirty else "Up to date"


def _apply_parameters(inputs: adsk.core.CommandInputs) -> str | None:
    """Collect rows and save them to the parameters document.
    Returns the saved parameter set name on success, or None on failure."""
    table = adsk.core.TableCommandInput.cast(inputs.itemById(TABLE_ID))
    if table is None:
        return None

    active_doc = _active_doc_ref or app.activeDocument

    parameters = _collect_rows(table)
    futil.log(f"{CMD_NAME}: {len(parameters)} parameter(s) collected → {parameters}")


    mode_dd = adsk.core.DropDownCommandInput.cast(inputs.itemById(MODE_INPUT_ID))
    selected_mode = (
        mode_dd.selectedItem.name
        if mode_dd and mode_dd.selectedItem
        else CREATE_NEW_LABEL
    )

    if not parameters:
        futil.log(f"{CMD_NAME}: no parameters collected — skipping document creation.")
        return selected_mode

    params_doc = None
    saved_name = selected_mode
    try:
        if selected_mode == CREATE_NEW_LABEL:
            param_set_name_input = adsk.core.StringValueCommandInput.cast(
                inputs.itemById(PARAM_SET_NAME_ID)
            )
            saved_name = (
                param_set_name_input.value.strip()
                if param_set_name_input
                else active_doc.name
            )
            params_doc, _params_data_file = _create_parameters_document(
                parameters, active_doc, saved_name
            )
            project = _active_project_ref
            cache.upsert_param_docs_cache_entry(
                project,
                saved_name,
                getattr(_params_data_file, "id", ""),
                CMD_NAME,
            )
            _param_doc_map[saved_name] = _params_data_file
            if saved_name not in _param_doc_names:
                _param_doc_names.append(saved_name)
            params_doc.close(False)
            params_doc = None  # already closed; prevent double-close in finally
        else:
            if not _param_doc_map and _active_project_ref is not None:
                _ensure_param_doc_map_loaded(_active_project_ref)
            existing_data_file = _param_doc_map.get(selected_mode)
            if existing_data_file is not None:
                _update_parameters_document(parameters, existing_data_file, active_doc)
        return saved_name
    except Exception:
        futil.handle_error(CMD_NAME, show_message_box=True)
        return None
    finally:
        if params_doc is not None:
            params_doc.close(False)


# ── Event handlers ────────────────────────────────────────────────────────────


def command_created(args: adsk.core.CommandCreatedEventArgs):
    futil.log(f"{CMD_NAME} Command Created Event")

    # ── 1. Resolve active project ─────────────────────────────────────────────
    doc = app.activeDocument
    inputs = args.command.commandInputs

    project = cache.get_active_project(CMD_NAME)
    if project is None:
        inputs.addTextBoxCommandInput(
            "gp_error",
            "",
            '<b style="color:red">No active Fusion project found.</b>'
            "<br>Open a project in the Data Panel, then try again.",
            3,
            True,
        )
        futil.add_handler(
            args.command.destroy, command_destroy, local_handlers=local_handlers
        )
        return

    project_name = project.name

    # ── 2. Reset per-dialog state ─────────────────────────────────────────────

    global _param_doc_map, _param_doc_names, _active_doc_ref, _active_project_ref, _row_counter, _table_dirty, _command_executed
    _active_doc_ref = doc
    _active_project_ref = project
    _row_counter = 0
    _table_dirty = False
    _command_executed = False
    # Always scan the Hub — the JSON cache is written here and used only as a
    # fast-path by lazy loaders later. Skipping the scan caused stale/deleted
    # documents to persist in the dropdown indefinitely.
    with futil.perf_timer("list_param_docs (Hub scan)", "GP.command_created"):
        _param_doc_map = cache.list_param_docs(project, CMD_NAME)
    _param_doc_names = list(_param_doc_map.keys())

    # ── 3. Build the dialog ───────────────────────────────────────────────────

    # Project name — read-only, at the very top
    proj_input = adsk.core.StringValueCommandInput.cast(
        inputs.addStringValueInput("gp_project_name", "Project", project_name)
    )
    proj_input.isReadOnly = True

    # Mode selector: "Create New" or pick an existing parameter document
    mode_dd = inputs.addDropDownCommandInput(
        MODE_INPUT_ID,
        "Parameter Set",
        adsk.core.DropDownStyles.TextListDropDownStyle,  # type: ignore[arg-type]
    )
    mode_dd.listItems.add(CREATE_NEW_LABEL, True, "")
    for existing_name in _param_doc_names:
        mode_dd.listItems.add(existing_name, False, "")

    # Name field — editable when creating new; shows doc name when editing existing
    inputs.addStringValueInput(PARAM_SET_NAME_ID, "Name", doc.name if doc else "")

    # Parameters table – 5 columns, proportional widths: ckb | name | value | unit | comment
    table = adsk.core.TableCommandInput.cast(
        inputs.addTableCommandInput(TABLE_ID, "Parameters", 5, "1:3:2:2:4")
    )
    table.minimumVisibleRows = 4
    table.maximumVisibleRows = 12
    table.columnSpacing = 1
    table.hasGrid = True

    # Table toolbar buttons (Add / Delete row)
    add_btn = inputs.addBoolValueInput(ADD_BTN_ID, "Add", False, "", True)
    del_btn = inputs.addBoolValueInput(DEL_BTN_ID, "Delete", False, "", False)
    table.addToolbarCommandInput(add_btn)
    table.addToolbarCommandInput(del_btn)

    # Populate header row then one blank data row
    _add_header_row(inputs, table)
    _add_data_row(inputs, table)

    # ── 3b. Restore pending cache if one exists from a cancelled session ───────
    with futil.perf_timer("read_pending_cache", "GP.command_created"):
        pending = _read_pending_cache(doc)
    if pending is not None:
        restore_result = ui.messageBox(
            "Unsaved changes from a previous session were found.\n"
            "Would you like to restore them?",
            "Restore Unsaved Changes",
            adsk.core.MessageBoxButtonTypes.YesNoButtonType,
            adsk.core.MessageBoxIconTypes.QuestionIconType,
        )
        if restore_result == adsk.core.DialogResults.DialogYes:
            cached_mode = pending.get("mode", CREATE_NEW_LABEL)
            for i in range(mode_dd.listItems.count):
                item = mode_dd.listItems.item(i)
                item.isSelected = item.name == cached_mode
            mode_dd.isEnabled = False
            param_set_name_input = adsk.core.StringValueCommandInput.cast(
                inputs.itemById(PARAM_SET_NAME_ID)
            )
            if param_set_name_input:
                param_set_name_input.value = pending.get("param_set_name", "")
                param_set_name_input.isReadOnly = cached_mode != CREATE_NEW_LABEL
            # Replace the default blank row with the cached rows
            while table.rowCount > HEADER_ROW + 1:
                table.deleteRow(table.rowCount - 1)
            for row_data in pending.get("parameters", []):
                _add_data_row_with_values(
                    inputs,
                    table,
                    row_data.get("name", ""),
                    str(row_data.get("value", "0.0")),
                    row_data.get("unit", "mm"),
                    row_data.get("comment", ""),
                    row_data.get("enabled", True),
                )
            if table.rowCount <= HEADER_ROW:
                _add_data_row(inputs, table)
            _table_dirty = True
        _clear_pending_cache(doc)

    # Status indicator below the table
    status_box = inputs.addTextBoxCommandInput(
        STATUS_INPUT_ID, "", "Up to date", 1, True
    )
    status_box.isFullWidth = True

    # ── 4. Connect command events ─────────────────────────────────────────────
    futil.add_handler(
        args.command.execute, command_execute, local_handlers=local_handlers
    )
    futil.add_handler(
        args.command.inputChanged, command_input_changed, local_handlers=local_handlers
    )
    futil.add_handler(
        args.command.validateInputs,
        command_validate_input,
        local_handlers=local_handlers,
    )
    futil.add_handler(
        args.command.destroy, command_destroy, local_handlers=local_handlers
    )


def command_execute(args: adsk.core.CommandEventArgs):
    global _command_executed
    futil.log(f"{CMD_NAME} Command Execute Event")
    saved_name = _apply_parameters(args.command.commandInputs)
    if saved_name is not None:
        _command_executed = True
        _clear_pending_cache(_active_doc_ref)


def command_input_changed(args: adsk.core.InputChangedEventArgs):
    global _table_dirty
    changed = args.input
    inputs = args.inputs
    if config.DEBUG:
        futil.log(f"{CMD_NAME} Input Changed: {changed.id}")

    table = adsk.core.TableCommandInput.cast(inputs.itemById(TABLE_ID))
    if table is None:
        return

    if changed.id == MODE_INPUT_ID:
        mode_dd = adsk.core.DropDownCommandInput.cast(inputs.itemById(MODE_INPUT_ID))
        if mode_dd is None:
            return

        new_selection = (
            mode_dd.selectedItem.name if mode_dd.selectedItem else CREATE_NEW_LABEL
        )

        param_set_name_input = adsk.core.StringValueCommandInput.cast(
            inputs.itemById(PARAM_SET_NAME_ID)
        )

        # Clear all data rows before switching mode
        while table.rowCount > HEADER_ROW + 1:
            table.deleteRow(table.rowCount - 1)

        if new_selection == CREATE_NEW_LABEL:
            if param_set_name_input:
                param_set_name_input.isReadOnly = False
                param_set_name_input.value = (
                    _active_doc_ref.name if _active_doc_ref else ""
                )
            _add_data_row(inputs, table)
        else:
            if not _param_doc_map and _active_project_ref is not None:
                _ensure_param_doc_map_loaded(_active_project_ref)
            data_file = _param_doc_map.get(new_selection)
            if param_set_name_input:
                param_set_name_input.isReadOnly = True
                param_set_name_input.value = new_selection
            if data_file is not None:
                with futil.perf_timer("load_parameters_from_doc", "GP.input_changed"):
                    _load_parameters_from_doc(data_file, inputs, table)

        # Lock the dropdown — the user has committed to this source for this session
        mode_dd.isEnabled = False
        _table_dirty = False
        _update_status(inputs, False)

    elif changed.id == ADD_BTN_ID:
        _add_data_row(inputs, table)
        _table_dirty = True
        _update_status(inputs, True)

    elif changed.id == DEL_BTN_ID:
        # Delete all checked rows; if all rows are deleted, add a fresh empty row
        rows_to_delete = []
        for r in range(HEADER_ROW + 1, table.rowCount):
            chk = adsk.core.BoolValueCommandInput.cast(table.getInputAtPosition(r, 0))
            if chk and chk.value:
                rows_to_delete.append(r)
        for r in reversed(rows_to_delete):
            table.deleteRow(r)
        # If no data rows remain, add a blank one
        if table.rowCount <= HEADER_ROW:
            _add_data_row(inputs, table)
        # Update delete button enabled state
        del_btn = adsk.core.BoolValueCommandInput.cast(inputs.itemById(DEL_BTN_ID))
        if del_btn:
            del_btn.isEnabled = _any_row_checked(table)
        _table_dirty = True
        _update_status(inputs, True)

    elif changed.id.startswith("gp_chk_"):
        # Update delete button enabled state when a checkbox changes
        del_btn = adsk.core.BoolValueCommandInput.cast(inputs.itemById(DEL_BTN_ID))
        if del_btn:
            del_btn.isEnabled = _any_row_checked(table)
        _table_dirty = True
        _update_status(inputs, True)

    elif (
        changed.id.startswith("gp_name_")
        or changed.id.startswith("gp_val_")
        or changed.id.startswith("gp_cmnt_")
        or changed.id.startswith("gp_unit_")
    ):
        _table_dirty = True
        _update_status(inputs, True)


def _validate_and_reason(inputs: adsk.core.CommandInputs) -> str:
    """Return an empty string when all inputs are valid, or a short human-readable
    reason string when they are not. Used by both the validate handler and the
    status box."""
    table = adsk.core.TableCommandInput.cast(inputs.itemById(TABLE_ID))
    if table is None:
        return "No parameter table found"

    param_set_name_input = adsk.core.StringValueCommandInput.cast(
        inputs.itemById(PARAM_SET_NAME_ID)
    )
    if param_set_name_input is not None and not param_set_name_input.value.strip():
        return "Parameter set name is required"

    if table.rowCount <= HEADER_ROW + 1:
        return ""  # empty table — allowed

    seen_names: set = set()
    for r in range(HEADER_ROW + 1, table.rowCount):
        name = adsk.core.StringValueCommandInput.cast(table.getInputAtPosition(r, 1))
        val = adsk.core.StringValueCommandInput.cast(table.getInputAtPosition(r, 2))

        if name is None:
            continue

        name_val = name.value.strip()
        if not name_val:
            continue  # blank rows are skipped

        ok, reason = _is_valid_param_name(name_val)
        if not ok:
            return f'Row {r}: "{name_val}" — {reason}'

        if name_val in seen_names:
            return f'Duplicate parameter name: "{name_val}"'
        seen_names.add(name_val)

        if val is not None:
            try:
                float(val.value.strip())
            except ValueError:
                return f'Row {r}: value "{val.value.strip()}" is not a valid number'

    return ""


def command_validate_input(args: adsk.core.ValidateInputsEventArgs):
    inputs = args.inputs
    reason = _validate_and_reason(inputs)

    status = adsk.core.TextBoxCommandInput.cast(inputs.itemById(STATUS_INPUT_ID))
    if status:
        if reason:
            status.text = f"Cannot save: {reason}"
        else:
            status.text = "Unsaved changes" if _table_dirty else "Up to date"

    args.areInputsValid = reason == ""


def command_destroy(args: adsk.core.CommandEventArgs):
    futil.log(f"{CMD_NAME} Command Destroy Event")
    global local_handlers, _active_doc_ref, _active_project_ref, _param_doc_map, _param_doc_names, _row_counter, _table_dirty, _command_executed

    should_reopen = False

    if _table_dirty and not _command_executed and _active_doc_ref is not None:
        # Snapshot the current table state into the pending cache before the
        # dialog is torn down so it can be restored if the user chooses to reopen.
        try:
            cmd_inputs = args.command.commandInputs
            table = adsk.core.TableCommandInput.cast(cmd_inputs.itemById(TABLE_ID))
            mode_dd = adsk.core.DropDownCommandInput.cast(
                cmd_inputs.itemById(MODE_INPUT_ID)
            )
            param_set_name_input = adsk.core.StringValueCommandInput.cast(
                cmd_inputs.itemById(PARAM_SET_NAME_ID)
            )
            current_mode = (
                mode_dd.selectedItem.name
                if mode_dd and mode_dd.selectedItem
                else CREATE_NEW_LABEL
            )
            param_set_name = (
                param_set_name_input.value.strip() if param_set_name_input else ""
            )
            parameters = _collect_rows(table) if table else []
            _write_pending_cache(
                _active_doc_ref, current_mode, param_set_name, parameters
            )
        except Exception:
            futil.log(
                f"{CMD_NAME}: could not write pending cache in destroy — ignoring"
            )

        result = ui.messageBox(
            "You have unsaved changes. Reopen the dialog to continue editing?",
            "Unsaved Changes — Global Parameters",
            adsk.core.MessageBoxButtonTypes.YesNoButtonType,
            adsk.core.MessageBoxIconTypes.QuestionIconType,
        )
        if result == adsk.core.DialogResults.DialogYes:
            should_reopen = True
        else:
            _clear_pending_cache(_active_doc_ref)

    local_handlers = []
    _active_doc_ref = None
    _active_project_ref = None
    _param_doc_map = {}
    _param_doc_names = []
    _row_counter = 0
    _table_dirty = False
    _command_executed = False

    if should_reopen:
        cmd_def = ui.commandDefinitions.itemById(CMD_ID)
        if cmd_def:
            cmd_def.execute()
