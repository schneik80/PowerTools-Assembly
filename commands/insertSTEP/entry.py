# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2022-2026 IMA LLC

import adsk.core, adsk.fusion
import os, traceback
from ...lib import fusionAddInUtils as futil
from ... import config

app = adsk.core.Application.get()
ui = app.userInterface

CMD_NAME = "Insert STEP File"
CMD_ID = "PTAT-insertSTEP"
CMD_Description = "Insert a STEP file into the active Design Document"
IS_PROMOTED = False

# Place insert STEP in the Assembly, Insert tab of the Fusion UI.
WORKSPACE_ID = "FusionSolidEnvironment"

# Define both tabs where the command will appear
TABS = [
    {
        "TAB_ID": "AssemblyTab",
        "TAB_NAME": "ASSEMBLY",
        "PANEL_ID": "InsertAssemblePanel",
        "PANEL_NAME": "INSERT",
    },
    {
        "TAB_ID": "SolidTab",
        "TAB_NAME": "SOLID",
        "PANEL_ID": "InsertPanel",
        "PANEL_NAME": "Insert",
    },
]

# Resource location for command icons, here we assume a sub folder in this directory named "resources".
ICON_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resources", "")

# Local list of event handlers used to maintain a reference so
# they are not released and garbage collected.
local_handlers = []


# Executed when add-in is run.
def start():
    # ******************************** Create Command Definition ********************************
    cmd_def = ui.commandDefinitions.addButtonDefinition(
        CMD_ID, CMD_NAME, CMD_Description, ICON_FOLDER
    )

    # Add command created handler. The function passed here will be executed when the command is executed.
    futil.add_handler(cmd_def.commandCreated, command_created)

    # ******************************** Create Command Control ********************************
    # Get target workspace for the command.
    workspace = ui.workspaces.itemById(WORKSPACE_ID)

    # Add the command to each tab/panel.
    for tab_info in TABS:
        toolbar_tab = workspace.toolbarTabs.itemById(tab_info["TAB_ID"])
        if toolbar_tab is None:
            toolbar_tab = workspace.toolbarTabs.add(
                tab_info["TAB_ID"], tab_info["TAB_NAME"]
            )

        panel = toolbar_tab.toolbarPanels.itemById(tab_info["PANEL_ID"])
        if panel is None:
            panel = toolbar_tab.toolbarPanels.add(
                tab_info["PANEL_ID"], tab_info["PANEL_NAME"]
            )

        control = panel.controls.addCommand(cmd_def, "PT-assemblystats", True)
        control.isPromoted = IS_PROMOTED


# Executed when add-in is stopped.
def stop():
    workspace = ui.workspaces.itemById(WORKSPACE_ID)

    for tab_info in TABS:
        panel = workspace.toolbarPanels.itemById(tab_info["PANEL_ID"])
        toolbar_tab = workspace.toolbarTabs.itemById(tab_info["TAB_ID"])

        if panel:
            command_control = panel.controls.itemById(CMD_ID)
            if command_control:
                command_control.deleteMe()

            if panel.controls.count == 0:
                panel.deleteMe()

        if toolbar_tab and toolbar_tab.toolbarPanels.count == 0:
            toolbar_tab.deleteMe()

    command_definition = ui.commandDefinitions.itemById(CMD_ID)
    if command_definition:
        command_definition.deleteMe()


# Function to be called when a user clicks the corresponding button in the UI.
def command_created(args: adsk.core.CommandCreatedEventArgs):
    futil.log(f"{CMD_NAME} Command Started Event")
    ui = None
    try:
        app = adsk.core.Application.get()
        ui = app.userInterface
        product = app.activeProduct
        design = adsk.fusion.Design.cast(product)

        # Check a Design document is active.
        if not design:
            ui.messageBox("No active Fusion design", "No Design")
            return

        # Set styles of file dialog.
        fileDlg = ui.createFileDialog()
        fileDlg.isMultiSelectEnabled = False
        fileDlg.title = "Fusion Insert STEP"
        fileDlg.filter = "STEP Files(*.stp;*.STP;*.step;*.STEP);;All files (*.*)"

        # Show file open dialog
        dlgResult = fileDlg.showOpen()
        if dlgResult == adsk.core.DialogResults.DialogOK:
            filename = fileDlg.filename
        else:
            return

        filename = '"' + filename + '"'
        command = f"Fusion.ImportComponent {filename}"
        app.executeTextCommand(command)

    except:
        if ui:
            ui.messageBox("Failed:\n{}".format(traceback.format_exc()))

    futil.log(f"{CMD_NAME} Command Completed Event")
