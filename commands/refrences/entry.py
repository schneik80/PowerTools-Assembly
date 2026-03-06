import adsk.core, adsk.fusion
import html, os, subprocess, traceback
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
ICON_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resources", "")

# Local list of event handlers used to maintain a reference so
# they are not released and garbage collected.
local_handlers = []

# Maps button input IDs → DataFile object or URL, populated on each invocation.
_fusion_btns: dict = {}
_browser_btns: dict = {}


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

        docParents, docChildren, docDrawings, docRelated, docFasteners = [], [], [], [], []

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
            return {"name": file.name, "id": file.id, "url": url, "file": file}

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

            table = grp.addTableCommandInput(f"{prefix}_table", title, 3, "6:1:1")
            table.minimumVisibleRows = 1
            table.maximumVisibleRows = 8
            table.columnSpacing = 2

            for i, item in enumerate(items):
                row = i

                name_in = grp.addTextBoxCommandInput(
                    f"{prefix}_name_{i}", "", html.escape(item["name"]), 1, True
                )

                if item.get("file"):
                    open_btn = grp.addBoolValueInput(
                        f"{prefix}_open_{i}", "⧉", False, "", False
                    )
                    open_btn.tooltip = "Open this document in Fusion"
                    _fusion_btns[f"{prefix}_open_{i}"] = item["file"]
                else:
                    open_btn = grp.addTextBoxCommandInput(
                        f"{prefix}_nopen_{i}", "", "–", 1, True
                    )

                if item.get("url"):
                    web_btn = grp.addBoolValueInput(
                        f"{prefix}_web_{i}", "↗", False, "", False
                    )
                    web_btn.tooltip = "Open in web browser"
                    _browser_btns[f"{prefix}_web_{i}"] = item["url"]
                else:
                    web_btn = grp.addTextBoxCommandInput(
                        f"{prefix}_nweb_{i}", "", "–", 1, True
                    )

                table.addCommandInput(name_in, row, 0)
                table.addCommandInput(open_btn, row, 1)
                table.addCommandInput(web_btn, row, 2)

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
    global local_handlers, _fusion_btns, _browser_btns
    local_handlers = []
    _fusion_btns = {}
    _browser_btns = {}
    futil.log(f"{CMD_NAME} Command Destroy Event")
