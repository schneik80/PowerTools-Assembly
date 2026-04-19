# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2022-2026 IMA LLC

import adsk.core
import adsk.fusion
import os
from ...lib import fusionAddInUtils as futil
from ...lib.fusionAddInUtils import cache_utils as cache
from ... import config

app = adsk.core.Application.get()
ui = app.userInterface

# ── Command identity ──────────────────────────────────────────────────────────
CMD_ID = "PTAT-linkGlobalParameters"
CMD_NAME = "Link Global Parameters"
CMD_Description = (
    "Derive global parameters from a parameter set into the active document"
)
IS_PROMOTED = False

# ── UI placement ──────────────────────────────────────────────────────────────
WORKSPACE_ID = config.design_workspace
TAB_ID = config.tools_tab_id
TAB_NAME = config.my_tab_name
PANEL_ID = config.my_panel_id
PANEL_NAME = config.my_panel_name
PANEL_AFTER = config.my_panel_after

# ── Paths ─────────────────────────────────────────────────────────────────────
ICON_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resources", "")

# ── Constants ─────────────────────────────────────────────────────────────────
TABLE_ID = "lgp_preview_table"
SOURCE_DD_ID = "lgp_source"
HEADER_ROW = 0
_PARAM_TAG = "PT-globparm"

local_handlers = []

# Module-level state populated when the dialog opens
_param_doc_map: dict = {}  # display name → adsk.core.DataFile
_param_doc_entries: list[dict] = []  # cached docs [{name, id}] for dropdown
_active_doc_ref = None  # active document at dialog-open time
_active_project_ref = None  # active Fusion project at dialog-open time
_row_counter = 0  # monotonically-increasing row ID to avoid input-ID conflicts


# ── Helpers ───────────────────────────────────────────────────────────────────


def _resolve_data_file_from_cache_id(project, doc_id: str):
    """Best-effort direct DataFile lookup by id. Returns DataFile or None."""
    if not doc_id:
        return None

    try:
        project_data = getattr(project, "data", None)
        find_file_by_id = getattr(project_data, "findFileById", None)
        if callable(find_file_by_id):
            data_file = find_file_by_id(doc_id)
            if data_file:
                return data_file
    except Exception:
        pass

    try:
        app_data = getattr(app, "data", None)
        find_file_by_id = getattr(app_data, "findFileById", None)
        if callable(find_file_by_id):
            data_file = find_file_by_id(doc_id)
            if data_file:
                return data_file
    except Exception:
        pass

    return None


def _ensure_param_doc_map_loaded(project) -> None:
    """Load Hub-backed DataFile map on demand if not already available."""
    global _param_doc_map, _param_doc_entries
    if _param_doc_map:
        return
    with futil.perf_timer("list_param_docs (lazy Hub scan)", "LGP.docs_resolve"):
        _param_doc_map = cache.list_param_docs(project, CMD_NAME)
    _param_doc_entries = [
        {"name": name, "id": getattr(data_file, "id", "")}
        for name, data_file in _param_doc_map.items()
    ]


def _refresh_param_doc_map(project) -> None:
    """Force-refresh the full parameter-doc map from Hub and rewrite docs cache."""
    global _param_doc_map, _param_doc_entries
    with futil.perf_timer("list_param_docs (forced Hub refresh)", "LGP.docs_resolve"):
        _param_doc_map = cache.list_param_docs(project, CMD_NAME)
    _param_doc_entries = [
        {"name": name, "id": getattr(data_file, "id", "")}
        for name, data_file in _param_doc_map.items()
    ]


def _cached_doc_id_for_name(doc_name: str) -> str:
    """Return cached document id for *doc_name*, or empty string if unknown."""
    for entry in _param_doc_entries:
        if entry.get("name") == doc_name:
            return entry.get("id", "")
    return ""


def _resolve_selected_data_file(project, doc_name: str):
    """Resolve selected DataFile by name with cache-id fast path and Hub fallback."""
    if not doc_name:
        return None

    data_file = _param_doc_map.get(doc_name)
    if data_file is not None:
        return data_file

    doc_id = _cached_doc_id_for_name(doc_name)
    if doc_id:
        with futil.perf_timer("resolve_selected_doc (cache id)", "LGP.docs_resolve"):
            data_file = _resolve_data_file_from_cache_id(project, doc_id)
        if data_file is not None:
            _param_doc_map[doc_name] = data_file
            return data_file

    # At this point the in-memory map may be partially populated (for example,
    # only the initially-previewed set). Force a full refresh so dropdown
    # changes can resolve any other cached names.
    _refresh_param_doc_map(project)
    return _param_doc_map.get(doc_name)


def _add_header_row(
    inputs: adsk.core.CommandInputs, table: adsk.core.TableCommandInput
):
    for col, label in enumerate(["Name", "Expression", "Unit", "Comment"]):
        hdr = inputs.addStringValueInput(f"lgp_hdr_{col}", "", label)
        hdr.isReadOnly = True
        table.addCommandInput(hdr, HEADER_ROW, col)



def _populate_preview_table(
    params: list[dict],
    inputs: adsk.core.CommandInputs,
    table: adsk.core.TableCommandInput,
    comment_key: str = "comment",
) -> None:
    """Add read-only rows to *table* from a list of parameter dicts.

    Accepts both sidecar format ({name, expression, unit, comment}) and
    Fusion API objects accessed via attribute names.
    *comment_key* lets the caller specify the dict key for the comment field.
    """
    global _row_counter
    for p in params:
        _row_counter += 1
        rid = _row_counter
        row = table.rowCount
        name_in = inputs.addStringValueInput(f"lgp_name_{rid}", "", p["name"])
        name_in.isReadOnly = True
        expr_in = inputs.addStringValueInput(f"lgp_expr_{rid}", "", p["expression"])
        expr_in.isReadOnly = True
        unit_in = inputs.addStringValueInput(f"lgp_unit_{rid}", "", p["unit"])
        unit_in.isReadOnly = True
        raw_comment = p.get(comment_key, "")
        # Strip the PT-globparm sentinel prefix if present
        if raw_comment.startswith(_PARAM_TAG):
            raw_comment = raw_comment[len(_PARAM_TAG):].strip()
        comment_in = inputs.addStringValueInput(f"lgp_comment_{rid}", "", raw_comment)
        comment_in.isReadOnly = True
        table.addCommandInput(name_in, row, 0)
        table.addCommandInput(expr_in, row, 1)
        table.addCommandInput(unit_in, row, 2)
        table.addCommandInput(comment_in, row, 3)


def _load_preview(
    data_file,
    inputs: adsk.core.CommandInputs,
    table: adsk.core.TableCommandInput,
) -> None:
    """Populate the read-only preview table for *data_file*.

    Fast path: reads from a JSON sidecar written by globalParameters on every
    save.  This avoids calling app.documents.open(), which switches the active
    document and is unreliable inside a running command dialog.

    Fallback: opens the document via the Fusion API when no sidecar exists
    (e.g. parameter sets created outside this add-in).
    """
    while table.rowCount > HEADER_ROW + 1:
        table.deleteRow(table.rowCount - 1)

    if not data_file:
        return

    # ── Fast path: sidecar written by globalParameters ────────────────────────
    cached_params = cache.read_param_set_sidecar(data_file)
    if cached_params is not None:
        with futil.perf_timer("load_preview (sidecar)", "LGP._load_preview"):
            _populate_preview_table(cached_params, inputs, table)
        return

    # ── Fallback: open the document via the Fusion API ────────────────────────
    try:
        with futil.perf_timer("documents.open", "LGP._load_preview"):
            params_doc = app.documents.open(data_file, False)
        try:
            params_design = adsk.fusion.Design.cast(
                params_doc.products.itemByProductType("DesignProductType")
            )
            if params_design is None:
                raise RuntimeError(
                    "Could not obtain Design product from the parameters document."
                )
            user_params = params_design.userParameters
            param_list = [
                {
                    "name": user_params.item(i).name,
                    "expression": user_params.item(i).expression,
                    "unit": user_params.item(i).unit,
                    "comment": user_params.item(i).comment or "",
                }
                for i in range(user_params.count)
            ]
        finally:
            params_doc.close(False)
        _populate_preview_table(param_list, inputs, table)
    except Exception as e:
        row = table.rowCount
        warn_in = inputs.addTextBoxCommandInput(
            f"lgp_warn_{row}",
            "",
            f'<b style="color:red">Failed to load parameters: {e}</b>',
            4,
            True,
        )
        table.addCommandInput(warn_in, row, 0)


def _derive_into_active(data_file, active_doc: adsk.core.Document) -> None:
    """Derive favorite parameters from *data_file* into *active_doc*.

    DeriveFeatures API rules (learned through debugging):
    - createInput() requires a Design object, NOT a DataFile
    - deriveFeatures lives on rootComponent.features, not on design.features
    - Setting isIncludeFavoriteParameters = True is sufficient to derive only
      parameters — no sourceEntities or excludedEntities manipulation needed
    - The source document must remain OPEN until all post-creation edits are done
    - The timeline marker is moved to position 0 before adding the derive feature
      so it is always inserted first; the marker is restored to the end afterward
    """
    active_design = adsk.fusion.Design.cast(
        active_doc.products.itemByProductType("DesignProductType")
    )
    if active_design is None:
        raise RuntimeError("Could not obtain Design product from the active document.")

    with futil.perf_timer("documents.open", "LGP._derive_into_active"):
        params_doc = app.documents.open(data_file, False)
    try:
        params_design = adsk.fusion.Design.cast(
            params_doc.products.itemByProductType("DesignProductType")
        )
        if params_design is None:
            raise RuntimeError(
                "Could not obtain Design product from the parameters document."
            )

        derive_features = active_design.rootComponent.features.deriveFeatures

        derive_input = derive_features.createInput(params_design)
        derive_input.isIncludeFavoriteParameters = True
        timeline = active_design.timeline
        timeline.markerPosition = 0
        with futil.perf_timer("derive_features.add", "LGP._derive_into_active"):
            derive_features.add(derive_input)
        timeline.markerPosition = timeline.count

        futil.log(f"{CMD_NAME}: parameters derived from '{data_file.name}'")
    finally:
        with futil.perf_timer("close + reactivate", "LGP._derive_into_active"):
            params_doc.close(False)
            cache.safe_activate(active_doc, CMD_NAME)


# ── Lifecycle ─────────────────────────────────────────────────────────────────


def start():
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

    # Position Link Global Parameters immediately after Global Parameters
    control = panel.controls.addCommand(cmd_def, "PTAT-globalParameters", False)
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


# ── Event handlers ─────────────────────────────────────────────────────────────


def command_created(args: adsk.core.CommandCreatedEventArgs):
    futil.log(f"{CMD_NAME} Command Created Event")

    doc = app.activeDocument
    inputs = args.command.commandInputs

    # Check if the active document is saved (not untitled)
    if not getattr(doc, 'isSaved', True):
        ui.messageBox(
            "Please save your document before using Link Global Parameters.\n\n"
            "The command cannot be used on an unsaved (untitled) document."
        )
        args.isCancelled = True
        return

    project = cache.get_active_project(CMD_NAME)
    if project is None:
        inputs.addTextBoxCommandInput(
            "lgp_error",
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

    global _param_doc_map, _param_doc_entries, _active_doc_ref, _active_project_ref, _row_counter
    _active_doc_ref = doc
    _active_project_ref = project
    _row_counter = 0
    # Always scan the Hub to keep the list fresh (no stale/deleted entries).
    with futil.perf_timer("list_param_docs (Hub scan)", "LGP.command_created"):
        _param_doc_map = cache.list_param_docs(project, CMD_NAME)
    _param_doc_entries = [
        {"name": name, "id": getattr(data_file, "id", "")}
        for name, data_file in _param_doc_map.items()
    ]

    if not _param_doc_entries:
        inputs.addTextBoxCommandInput(
            "lgp_error",
            "",
            '<b style="color:red">No parameter sets found in this project.</b>'
            "<br>Use <b>Global Parameters</b> to create a parameter set first.",
            4,
            True,
        )
        futil.add_handler(
            args.command.destroy, command_destroy, local_handlers=local_handlers
        )
        return

    # ── Build the dialog ──────────────────────────────────────────────────────

    # Project name — read-only
    proj_input = adsk.core.StringValueCommandInput.cast(
        inputs.addStringValueInput(
            "lgp_project_name",
            "Project",
            project.name,
        )
    )
    proj_input.isReadOnly = True

    # Parameter set selector
    source_dd = inputs.addDropDownCommandInput(
        SOURCE_DD_ID,
        "Parameter Set",
        adsk.core.DropDownStyles.TextListDropDownStyle,  # type: ignore[arg-type]
    )
    first = True
    for entry in _param_doc_entries:
        source_dd.listItems.add(entry["name"], first, "")
        first = False


    # Read-only preview table: Name | Expression | Unit | Comment
    table = adsk.core.TableCommandInput.cast(
        inputs.addTableCommandInput(TABLE_ID, "Parameters", 4, "3:4:2:4")
    )
    table.minimumVisibleRows = 4
    table.maximumVisibleRows = 12
    table.columnSpacing = 1
    table.hasGrid = True

    _add_header_row(inputs, table)


    # Pre-load preview for the initially-selected document
    first_name = _param_doc_entries[0]["name"]
    first_data_file = _param_doc_map.get(first_name)
    if first_data_file is None:
        with futil.perf_timer("resolve_initial_doc (cache id)", "LGP.command_created"):
            first_data_file = _resolve_data_file_from_cache_id(
                project,
                _param_doc_entries[0].get("id", ""),
            )
        if first_data_file is not None:
            _param_doc_map[first_name] = first_data_file

    if first_data_file is not None:
        with futil.perf_timer("initial load_preview", "LGP.command_created"):
            _load_preview(first_data_file, inputs, table)

    # ── Connect events ────────────────────────────────────────────────────────
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
    futil.log(f"{CMD_NAME} Command Execute Event")
    source_dd = adsk.core.DropDownCommandInput.cast(
        args.command.commandInputs.itemById(SOURCE_DD_ID)
    )
    if source_dd is None or source_dd.selectedItem is None:
        return
    if _active_project_ref is None:
        return
    project = _active_project_ref
    data_file = _resolve_selected_data_file(project, source_dd.selectedItem.name)
    if data_file is None:
        return
    try:
        _derive_into_active(data_file, _active_doc_ref or app.activeDocument)
    except Exception:
        futil.handle_error(CMD_NAME, show_message_box=True)


def command_input_changed(args: adsk.core.InputChangedEventArgs):
    if args.input.id == SOURCE_DD_ID:
        source_dd = adsk.core.DropDownCommandInput.cast(args.inputs.itemById(SOURCE_DD_ID))
        table = adsk.core.TableCommandInput.cast(args.inputs.itemById(TABLE_ID))
        if source_dd is None or table is None or source_dd.selectedItem is None:
            return
        if _active_project_ref is None:
            return
        project = _active_project_ref
        data_file = _resolve_selected_data_file(project, source_dd.selectedItem.name)
        if data_file is not None:
            with futil.perf_timer("load_preview (dropdown change)", "LGP.input_changed"):
                _load_preview(data_file, args.inputs, table)


def command_validate_input(args: adsk.core.ValidateInputsEventArgs):
    source_dd = adsk.core.DropDownCommandInput.cast(args.inputs.itemById(SOURCE_DD_ID))
    args.areInputsValid = source_dd is not None and source_dd.selectedItem is not None


def command_destroy(args: adsk.core.CommandEventArgs):
    futil.log(f"{CMD_NAME} Command Destroy Event")
    global local_handlers, _active_doc_ref, _active_project_ref, _param_doc_map, _param_doc_entries, _row_counter
    local_handlers = []
    _active_doc_ref = None
    _active_project_ref = None
    _param_doc_map = {}
    _param_doc_entries = []
    _row_counter = 0
