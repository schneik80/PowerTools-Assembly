import adsk.core, adsk.fusion
import html, os, traceback
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


# Executed when add-in is run.
def start():
    # ******************************** Create Command Definition ********************************
    cmd_def = ui.commandDefinitions.addButtonDefinition(
        CMD_ID, CMD_NAME, CMD_Description, ICON_FOLDER
    )

    # Define an event handler for the command created event. It will be called when the button is clicked.
    futil.add_handler(cmd_def.commandCreated, command_created)

    # ******************************** Create Command Control ********************************
    # Get target workspace for the command.
    workspace = ui.workspaces.itemById(WORKSPACE_ID)

    # Get target toolbar tab for the command and create the tab if necessary.
    toolbar_tab = workspace.toolbarTabs.itemById(TAB_ID)
    if toolbar_tab is None:
        toolbar_tab = workspace.toolbarTabs.add(TAB_ID, TAB_NAME)

    # Get target panel for the command and and create the panel if necessary.
    panel = toolbar_tab.toolbarPanels.itemById(PANEL_ID)
    if panel is None:
        panel = toolbar_tab.toolbarPanels.add(PANEL_ID, PANEL_NAME, PANEL_AFTER, False)

    # Create the command control, i.e. a button in the UI.
    control = panel.controls.addCommand(cmd_def)

    # Now you can set various options on the control such as promoting it to always be shown.
    control.isPromoted = IS_PROMOTED


# Executed when add-in is stopped.
def stop():
    # Get the various UI elements for this command
    workspace = ui.workspaces.itemById(WORKSPACE_ID)
    panel = workspace.toolbarPanels.itemById(PANEL_ID)
    toolbar_tab = workspace.toolbarTabs.itemById(TAB_ID)
    command_control = panel.controls.itemById(CMD_ID)
    command_definition = ui.commandDefinitions.itemById(CMD_ID)

    # Delete the button command control
    if command_control:
        command_control.deleteMe()

    # Delete the command definition
    if command_definition:
        command_definition.deleteMe()

    # Delete the panel if it is empty
    if panel.controls.count == 0:
        panel.deleteMe()

    # Delete the tab if it is empty
    if toolbar_tab.toolbarPanels.count == 0:
        toolbar_tab.deleteMe()


# Function that is called when a user clicks the corresponding button in the UI.
# This defines the contents of the command dialog and connects to the command related events.
def command_created(args: adsk.core.CommandCreatedEventArgs):
    futil.log(f"{CMD_NAME} Command Created Event")

    # Connect to the events that are needed by this command.
    futil.add_handler(
        args.command.execute, command_execute, local_handlers=local_handlers
    )
    futil.add_handler(
        args.command.destroy, command_destroy, local_handlers=local_handlers
    )


def command_execute(args: adsk.core.CommandCreatedEventArgs):
    # this handles the document close and reopen
    ui = None
    try:
        app = adsk.core.Application.get()
        ui = app.userInterface
        design = app.activeProduct
        doc = app.activeDocument

        if not design:
            ui.messageBox("No active Fusion design")
            return

        # Check that the active document has been saved.
        if futil.isSaved() == False:
            return

        parentDataFiles = doc.designDataFile.parentReferences
        childDataFiles = doc.designDataFile.childReferences
        totalRefs = parentDataFiles.count + childDataFiles.count
        docParents = []
        docChildren = []
        docDrawings = []
        docRelated = []
        docFasteners = []
        subString = " ‹+› "
        linkError = False

        progressBar = ui.progressBar
        progressBar.showBusy("Getting Document's References Link", True)
        adsk.doEvents

        # Create file_data dictionary template
        def make_file_data(file):
            url = None
            try:
                url = file.fusionWebURL
            except:
                url = None
            return {"name": file.name, "id": file.id, "url": url}

        # Process parent and related data files in one pass
        if parentDataFiles:
            for file in parentDataFiles:

                file_data = make_file_data(file)
                if subString in file.name:
                    docRelated.append(file_data)
                elif file.fileExtension == "f2d":
                    docDrawings.append(file_data)
                else:
                    docParents.append(file_data)

        # Process child data files in one pass
        if childDataFiles:
            for file in childDataFiles:

                file_data = make_file_data(file)
                try:
                    if file.parentProject.name == "Standard Components":
                        docFasteners.append(file_data)
                    else:
                        # Check if this is a configuration
                        if hasattr(file, "isConfiguration") and file.isConfiguration:
                            file_data["name"] += " (configuration)"
                        docChildren.append(file_data)
                except:
                    # If parentProject is not accessible, treat as regular child
                    # Still check for configuration status
                    try:
                        if hasattr(file, "isConfiguration") and file.isConfiguration:
                            file_data["name"] += " (configuration)"
                    except:
                        pass
                    docChildren.append(file_data)

        # Links String to report references
        links = f""

        if docParents:
            links += f"<h3>Parents ({len(docParents)}):</h3>"
            for item in docParents:
                if item["url"]:
                    links += f'<a href="{item["url"]}">{item["name"]}</a><br>'
                else:
                    links += f'{item["name"]}<br>'
                    linkError = True

        if docChildren:
            links += f"<h3>Children ({len(docChildren)}):</h3>"
            for item in docChildren:
                if item["url"]:
                    links += f'<a href="{item["url"]}">{item["name"]}</a><br>'
                else:
                    links += f'{item["name"]}<br>'
                    linkError = True

        if docDrawings:
            links += f"<h3>Drawings ({len(docDrawings)}):</h3>"
            for item in docDrawings:
                if item["url"]:
                    links += f'<a href="{item["url"]}">{item["name"]}</a><br>'
                else:
                    links += f'{item["name"]}<br>'
                    linkError = True

        if docRelated:
            links += f"<h3>Related Data ({len(docRelated)}):</h3>"
            for item in docRelated:
                if item["url"]:
                    links += f'<a href="{item["url"]}">{item["name"]}</a><br>'
                else:
                    links += f'{item["name"]}<br>'
                    linkError = True

        if docFasteners:
            links += f"<h3>Fasteners ({len(docFasteners)}):</h3>"
            for item in docFasteners:
                if item["url"]:
                    links += f'<a href="{item["url"]}">{item["name"]}</a><br>'
                else:
                    links += f'{item["name"]}<br>'
                    linkError = True

        # Hide the progress bar
        progressBar.hide()

        if linkError == True:
            links += f"<br><b>Note:</b> Some links may not be accessible due to permissions or other issues.<br>"
            # If no relationships found, show a message box
        if totalRefs == 0:
            ui.messageBox(
                "Document's current version has no references",
                f"{doc.name}",
                0,
                2,
            )

        # If relationships found, show a message box with the links
        else:
            relationsTitle = f"References {totalRefs} "

            ui.messageBox(links, f"{doc.name} - {relationsTitle}", 0, 2)

    except:
        if ui:
            ui.messageBox("Failed:\n{}".format(traceback.format_exc()))


# This function will be called when the user completes the command.
def command_destroy(args: adsk.core.CommandEventArgs):
    global local_handlers
    local_handlers = []
    futil.log(f"{CMD_NAME} Command Destroy Event")
