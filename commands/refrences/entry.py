import adsk.core, adsk.fusion
import html, os, subprocess, tempfile, time, traceback, uuid
from ...lib import fusionAddInUtils as futil
from ... import config

app = adsk.core.Application.get()
ui = app.userInterface

CMD_NAME = "Document References"
CMD_ID = "PTAT-docrefs"
CMD_Description = "List Active Document References"
IS_PROMOTED = False

# Global variables by referencing values from /config.py
WORKSPACE_ID = config.design_workspace
TAB_ID = config.tools_tab_id
TAB_NAME = config.my_tab_name

PANEL_ID = config.my_panel_id
PANEL_NAME = config.my_panel_name
PANEL_AFTER = config.my_panel_after

# Resource location for command icons, here we assume a sub folder in this directory named "resources".
_res = os.path.dirname(os.path.abspath(__file__))
ICON_FOLDER = os.path.join(_res, "resources", "")
OPEN_ICON_FOLDER = os.path.join(_res, "resources", "open", "")
WEB_ICON_FOLDER = os.path.join(_res, "resources", "web", "")
THUMB_PLACEHOLDER = os.path.join(_res, "resources", "doc_thumb.png")

# Temp directory for downloaded thumbnails — one subdir per session.
THUMB_DIR = os.path.join(tempfile.gettempdir(), "PTAT_thumbs")
os.makedirs(THUMB_DIR, exist_ok=True)

# Local list of event handlers used to maintain a reference so
# they are not released and garbage collected.
local_handlers = []

# Maps button input IDs → DataFile object or URL, populated on each invocation.
_fusion_btns: dict = {}
_browser_btns: dict = {}
# Cache: file_id → local thumbnail path
_thumb_cache: dict = {}
# Track temp files created this session for cleanup
_thumb_paths: list = []


# Executed when add-in is run.
def start():
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


# Executed when add-in is stopped.
def stop():
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


# Function that is called when a user clicks the corresponding button in the UI.
# Collects references, then builds the command dialog with five tables.
def command_created(args: adsk.core.CommandCreatedEventArgs):
    futil.log(f"{CMD_NAME} Command Created Event")

    futil.add_handler(
        args.command.execute, command_execute, local_handlers=local_handlers
    )
    futil.add_handler(
        args.command.inputChanged, on_input_changed, local_handlers=local_handlers
    )
    futil.add_handler(
        args.command.destroy, command_destroy, local_handlers=local_handlers
    )

    global _fusion_btns, _browser_btns
    _fusion_btns = {}
    _browser_btns = {}

    try:
        app = adsk.core.Application.get()
        ui = app.userInterface
        doc = app.activeDocument
        design = app.activeProduct

        if app.isOffLine:
            ui.messageBox(
                "You are currently offline. Please connect to the internet and try again."
            )
            return

        if not design:
            ui.messageBox("No active Fusion design")
            return

        if not futil.isSaved():
            return

        parentDataFiles = doc.designDataFile.parentReferences
        childDataFiles = doc.designDataFile.childReferences
        subString = " ‹+› "

        docParents, docChildren, docDrawings, docRelated, docFasteners = (
            [],
            [],
            [],
            [],
            [],
        )

        # Build a name→component map for all components in the active design
        _comp_by_name = {c.name: c for c in design.allComponents}

        def _save_data_object(data_obj, dest) -> bool:
            """Try all known methods to persist a DataObject to a PNG file."""

            # Method 1: saveToFile
            try:
                if data_obj.saveToFile(dest):
                    return True
            except Exception:
                pass
            # Method 2: iterate known byte-property names
            for attr in ("imageData", "data", "bytes", "content"):
                try:
                    raw = getattr(data_obj, attr)
                    if raw is not None:
                        with open(dest, "wb") as f:
                            f.write(raw)
                        return True
                except Exception:
                    pass
            # Method 3: log all attrs so we can fix it next time
            futil.log(
                f"[Thumbnail] Unknown DataObject attrs: "
                f"{[a for a in dir(data_obj) if not a.startswith('_')]}"
            )
            return False

        def fetch_thumbnail(data_file) -> str:
            """Get a thumbnail for data_file, writing it to THUMB_DIR.
            Prefers Component.createThumbnail() for components present in the
            assembly; falls back to DataFile.thumbnail future for everything else.
            Returns the local file path or THUMB_PLACEHOLDER on failure."""
            file_id = data_file.id
            if file_id in _thumb_cache:
                return _thumb_cache[file_id]

            safe_urn = "".join(c if c.isalnum() else "_" for c in file_id)[:80]
            fname = f"{uuid.uuid4().hex}_{safe_urn}.png"
            dest = os.path.join(THUMB_DIR, fname)

            # --- Strategy 1: component in the assembly ---
            component = _comp_by_name.get(data_file.name)
            if component:
                try:
                    data_obj = component.createThumbnail(32, 32, "PNG")
                    if data_obj and _save_data_object(data_obj, dest):
                        _thumb_cache[file_id] = dest
                        _thumb_paths.append(dest)
                        futil.log(f"[Thumbnail] OK (component): {data_file.name}")
                        return dest
                    futil.log(
                        f"[Thumbnail] createThumbnail failed to save for: {data_file.name}"
                    )
                except Exception:
                    futil.log(
                        f"[Thumbnail] createThumbnail exception for {data_file.name}:\n"
                        f"{traceback.format_exc()}"
                    )

            # --- Strategy 2: DataFile.thumbnail future ---
            try:
                future = data_file.thumbnail
                if future is None:
                    futil.log(f"[Thumbnail] No future for: {data_file.name}")
                    return THUMB_PLACEHOLDER

                deadline = time.time() + 5.0
                while future.state == 0:
                    adsk.doEvents()
                    if time.time() > deadline:
                        futil.log(f"[Thumbnail] Timeout: {data_file.name}")
                        return THUMB_PLACEHOLDER
                    time.sleep(0.05)

                if future.state != 1:
                    futil.log(
                        f"[Thumbnail] Future failed state={future.state}: {data_file.name}"
                    )
                    return THUMB_PLACEHOLDER

                data_obj = future.dataObject
                if data_obj and _save_data_object(data_obj, dest):
                    _thumb_cache[file_id] = dest
                    _thumb_paths.append(dest)
                    futil.log(f"[Thumbnail] OK (future): {data_file.name}")
                    return dest

            except Exception:
                futil.log(
                    f"[Thumbnail] Future exception for {data_file.name}:\n"
                    f"{traceback.format_exc()}"
                )

            return THUMB_PLACEHOLDER

        progressBar = ui.progressBar
        progressBar.showBusy("Getting Document References…", True)
        adsk.doEvents

        def make_file_data(file):
            url = None
            try:
                candidate = file.fusionWebURL
                if candidate:
                    url = candidate
            except Exception:
                pass
            return {
                "name": file.name,
                "id": file.id,
                "url": url,
                "file": file,
                "thumb": None,
            }

        for file in parentDataFiles or []:
            fd = make_file_data(file)
            if subString in file.name:
                docRelated.append(fd)
            elif file.fileExtension == "f2d":
                docDrawings.append(fd)
            else:
                docParents.append(fd)

        for file in childDataFiles or []:
            fd = make_file_data(file)
            try:
                if file.parentProject.name == "Standard Components":
                    docFasteners.append(fd)
                else:
                    if hasattr(file, "isConfiguration") and file.isConfiguration:
                        fd["name"] += " (configuration)"
                    docChildren.append(fd)
            except Exception:
                docChildren.append(fd)

        # Fetch thumbnails for all collected references.
        all_items = docParents + docChildren + docDrawings + docFasteners + docRelated
        for fd in all_items:
            progressBar.showBusy(f"Fetching thumbnail: {fd['name'][:40]}…", True)
            adsk.doEvents
            fd["thumb"] = fetch_thumbnail(fd["file"])

        progressBar.hide()

        cmd = args.command
        cmd.okButtonText = "Close"
        inputs = cmd.commandInputs

        def _add_table(title, items, prefix):
            group = inputs.addGroupCommandInput(
                f"{prefix}_group", f"{title}  ({len(items)})"
            )
            group.isExpanded = bool(items)
            group.isEnabledCheckBoxDisplayed = False

            if not items:
                return

            grp = group.children

            def _set_row_tooltip(input_obj, item_name, thumb_path):
                try:
                    input_obj.tooltip = item_name
                except Exception:
                    pass
                try:
                    input_obj.tooltipDescription = item_name
                except Exception:
                    pass
                try:
                    input_obj.toolClipFilename = thumb_path
                except Exception:
                    pass

            # 3 columns: name | open | web
            table = grp.addTableCommandInput(f"{prefix}_table", title, 3, "10:1:1")
            table.minimumVisibleRows = 1
            table.maximumVisibleRows = 8
            table.columnSpacing = 2

            for i, item in enumerate(items):
                thumb_path = item.get("thumb") or THUMB_PLACEHOLDER

                name_in = grp.addTextBoxCommandInput(
                    f"{prefix}_name_{i}", "", html.escape(item["name"]), 1, True
                )
                _set_row_tooltip(name_in, item["name"], thumb_path)

                if item.get("file"):
                    open_btn = grp.addBoolValueInput(
                        f"{prefix}_open_{i}", "", False, OPEN_ICON_FOLDER, False
                    )
                    open_btn.tooltip = "Open this document in Fusion"
                    _set_row_tooltip(open_btn, item["name"], thumb_path)
                    _fusion_btns[f"{prefix}_open_{i}"] = item["file"]
                else:
                    open_btn = grp.addTextBoxCommandInput(
                        f"{prefix}_nopen_{i}", "", "–", 1, True
                    )
                    _set_row_tooltip(open_btn, item["name"], thumb_path)

                if item.get("url"):
                    web_btn = grp.addBoolValueInput(
                        f"{prefix}_web_{i}", "", False, WEB_ICON_FOLDER, False
                    )
                    web_btn.tooltip = "Open in web browser"
                    _set_row_tooltip(web_btn, item["name"], thumb_path)
                    _browser_btns[f"{prefix}_web_{i}"] = item["url"]
                else:
                    web_btn = grp.addTextBoxCommandInput(
                        f"{prefix}_nweb_{i}", "", "–", 1, True
                    )
                    _set_row_tooltip(web_btn, item["name"], thumb_path)

                table.addCommandInput(name_in, i, 0)
                table.addCommandInput(open_btn, i, 1)
                table.addCommandInput(web_btn, i, 2)

        _add_table("Used In (Parents)", docParents, "parents")
        _add_table("Uses (Children)", docChildren, "children")
        _add_table("Drawings", docDrawings, "drawings")
        _add_table("Fasteners", docFasteners, "fasteners")
        _add_table("Related Data", docRelated, "related")

    except Exception:
        if ui:
            ui.messageBox("Failed:\n{}".format(traceback.format_exc()))


def on_input_changed(args: adsk.core.InputChangedEventArgs):
    btn = args.input
    btn_id = btn.id

    # BoolValueInput fires on both press (True) and release (False) — only act on press.
    if hasattr(btn, "value") and not btn.value:
        return

    if btn_id in _fusion_btns:
        data_file = _fusion_btns[btn_id]
        try:
            app.documents.open(data_file)
            args.input.parentCommand.doExecute(False)
        except Exception:
            ui.messageBox(
                "Failed to open document in Fusion:\n{}".format(traceback.format_exc())
            )

    elif btn_id in _browser_btns:
        url = _browser_btns[btn_id]
        try:
            if os.name == "nt":
                subprocess.Popen(["start", url], shell=True)
            else:
                subprocess.Popen(["open", url])
        except Exception:
            ui.messageBox("Failed to open URL:\n{}".format(traceback.format_exc()))


# Called when the user clicks OK / Close — no action needed for a read-only dialog.
def command_execute(args: adsk.core.CommandEventArgs):
    futil.log(f"{CMD_NAME} Command Execute Event")


# This function will be called when the user completes the command.
def command_destroy(args: adsk.core.CommandEventArgs):
    global local_handlers, _fusion_btns, _browser_btns, _thumb_cache, _thumb_paths
    local_handlers = []
    _fusion_btns = {}
    _browser_btns = {}
    _thumb_cache = {}
    for path in _thumb_paths:
        try:
            os.remove(path)
        except Exception:
            pass
    _thumb_paths.clear()
    futil.log(f"{CMD_NAME} Command Destroy Event")
