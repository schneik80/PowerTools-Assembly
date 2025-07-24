import adsk.core, adsk.fusion
import os, re, traceback
from ...lib import fusionAddInUtils as futil
from ... import config

app = adsk.core.Application.get()
ui = app.userInterface

CMD_NAME = "Assembly Statistics"
CMD_ID = "PTAT-assemblystats"
CMD_Description = "Assembly statistics on component counts, assembly levels and Joints"
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

# Holds references to event handlers
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


# Function to be called when a user clicks the corresponding button in the UI.
def command_created(args: adsk.core.CommandCreatedEventArgs):
    futil.log(f"{CMD_NAME} Command Created Event")

    # Connect to the events that are needed by this command.
    futil.add_handler(
        args.command.execute, command_execute, local_handlers=local_handlers
    )
    futil.add_handler(
        args.command.destroy, command_destroy, local_handlers=local_handlers
    )

    global product, design, title

    product = app.activeProduct
    design = adsk.fusion.Design.cast(product)
    doc = app.activeDocument
    title = CMD_NAME

    # Check a Design document is active.
    if not design:
        ui.messageBox("A Fusion 3D Design must be active", "title")
        return

    # Check that the active document has been saved.
    if futil.isSaved() == False:
        return


def command_execute(args: adsk.core.CommandCreatedEventArgs):
    ui = None

    futil.log(f"{CMD_NAME} Command Execute Event")

    try:

        # Get the application and user interface objects.
        app = adsk.core.Application.get()
        ui = app.userInterface

        # Get the root component of the active design.
        rootComp = design.rootComponent

        # Get the document details
        root_name = design.rootComponent.name
        # get out of date references
        try:
            # Count out of date references
            out_of_date_refs = sum(
                1 for ref in app.activeDocument.documentReferences if ref.isOutOfDate
            )
            adsk.core.Application.log(f"Out of date references: {out_of_date_refs}")
        except Exception as e:
            adsk.core.Application.log(f"Error counting out of date references: {e}")

        # Get the total number of unique components and total components.
        total_unique = (
            design.allComponents.count - 1
        )  # Get unique components, subtract 1 to remove for root component.
        total_count = rootComp.allOccurrences.count  # Get total components.
        mTitle = f"{root_name} Component Statistics"

        # Display the result.
        # Write the results to the TEXT COMMANDS window.
        adsk.core.Application.log(f"{root_name}:")
        adsk.core.Application.log(f"Unique components: {total_unique}")
        adsk.core.Application.log(f"Total components: {total_count}")

        # Get the assembly statistics
        # Use a regex pattern to match the text commands number/text list output
        pattern = (
            r".[a-zA-Z]\.+\D|\d\.+\D"  # match the text commands number/text list output
        )
        stats = app.executeTextCommand("Component.AnalyseHierarchy")
        statsListSplit = stats.splitlines()  # split output into a list
        statsList = [
            re.sub(pattern, "", e) for e in statsListSplit
        ]  # strip list numbering from list

        # Get the compute time for the document
        try:
            # force get compute time
            docComputeTimes = app.executeTextCommand("fusion.computetime /f")
            # Extract the serial compute time from the second line
            docComputelong = (
                docComputeTimes.strip().split("\n")[1].split(":", 1)[1].strip()
            )
            docComputeshort = "{:.2g}".format(float(docComputelong))
            # construct the compute time string
            docCompute = f"{docComputeshort} seconds"

        except:
            docCompute = f"<i>Error. Unable to retrieve compute time.</i>"

        # Get the number of contexts in the timeline
        try:
            docTimeline = app.executeTextCommand("timeline.print")
            docContexts = sum(
                1 for line in docTimeline.strip().split("\n") if "Context" in line
            )
        except:
            docContexts = f"<i>Error. Unable to retrieve timeline contexts.</i>"
            adsk.core.Application.log("Error retrieving timeline contexts.")

        docConstraints = rootComp.assemblyConstraints.count
        docTangents = rootComp.tangentRelationships.count
        docRigidGroups = rootComp.rigidGroups.count

        resultString = (
            f"<b>Document Compute:</b><br>"
            f"Compute time: {docCompute} <br>"
            f"<br>"
            f"<b>Assembly Components:</b><br>"
            f"{statsList[1]} <br>"
            f"{statsList[2]} <br>"
            f"Total number of unique components: {total_unique} <br>"
            f"Total number of out-of-date components: {out_of_date_refs} <br>"
            f"{statsList[3]} <br>"
            f"Number of document contexts: {docContexts} <br>"
            f"<br>"
            f"<b>Relationship Information:</b><br>"
            f"Number of document constraints: {docConstraints} <br>"
            f"<br>"
            f"Number of document tangent Relationships: {docTangents} <br>"
            f"<br>"
            f"Joints:<br>"
            f" - {statsList[4]} <br>"
            f" - {statsList[5]} <br>"
            f" - {statsList[6]} <br>"
            f" - {statsList[7]} <br>"
            f" - {statsList[8]} <br>"
            f" - {statsList[9]} <br>"
            f" - {statsList[10]} <br>"
            f" - {statsList[11]} <br>"
            f" - {statsList[12]} <br>"
            f" - {statsList[13]} <br>"
            f" - {statsList[14]} <br>"
            f" - {statsList[15]} <br>"
            f" - {statsList[16]} <br>"
            f"<br>"
            f"Total number of Rigid Groups: {docRigidGroups}"
        )

        # Display results in a MESSAGE BOX.
        ui.messageBox(resultString, mTitle, 0, 2)

    except:
        if ui:
            ui.messageBox("Failed:\n{}".format(traceback.format_exc()))


# This function will be called when the user completes the command.
def command_destroy(args: adsk.core.CommandEventArgs):
    global local_handlers
    local_handlers = []
    futil.log(f"{CMD_NAME} Command Destroy Event")
