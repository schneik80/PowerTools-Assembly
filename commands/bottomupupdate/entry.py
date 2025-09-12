import adsk.core, adsk.fusion
import os, re, traceback
from ...lib import fusionAddInUtils as futil
from ... import config

app = adsk.core.Application.get()
ui = app.userInterface

CMD_NAME = "Bottom-up Update"
CMD_ID = "PTAT-bottomupupdate"
CMD_Description = (
    "Save and update all references in the open assembly from the bottom up"
)
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
saved = []


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

    # Check if there are any references to update
    if app.activeDocument.documentReferences.count == 0:
        ui.messageBox("No document references found", title)
        return

    # Check that the active document has been saved.
    if futil.isSaved() == False:
        return


def traverse_assembly(component, parent_dict):
    """
    Recursively traverses the assembly and creates a dictionary for each component.
    :param component: The root component to traverse.
    :param parent_dict: The dictionary to store child components.
    """
    for occurrence in component.occurrences:
        child_component = occurrence.component
        if child_component.name not in parent_dict:
            # Add the child component to the dictionary
            parent_dict[child_component.name] = {
                "component": child_component,
                "children": {},
            }
        # Recursively traverse the child component
        traverse_assembly(
            child_component, parent_dict[child_component.name]["children"]
        )


def sort_dag_bottom_up(assembly_dict):
    """
    Sorts the dictionary as a DAG in bottom-up order.
    :param assembly_dict: The dictionary representing the assembly structure.
    :return: A list of components in bottom-up order.
    """
    sorted_components = []

    def traverse_dag(node):
        for child_name, child_data in node["children"].items():
            traverse_dag(child_data)
        sorted_components.append(node["component"].name)

    for key, value in assembly_dict.items():
        traverse_dag(value)

    return sorted_components


def UpdateAll(ui):
    """
    Update all references in the assembly to newly saved versions.
    ui: The user interface object.
    """
    # this handles the update and get latest
    try:
        cmdDefs = ui.commandDefinitions
        cmdGet = cmdDefs.itemById("GetAllLatestCmd")
        cmdGet.execute()
        cmdUpdate = cmdDefs.itemById("ContextUpdateAllFromParentCmd")
        cmdUpdate.execute()

    except:
        if ui:
            ui.messageBox("Failed:\n{}".format(traceback.format_exc()))


def is_external_component(comp: adsk.fusion.Component):
    """
    Check if the component is external by checking its occurrences
    comp: A fusion component object.
    """
    app = adsk.core.Application.get()
    product = app.activeProduct
    design = adsk.fusion.Design.cast(product)
    if not design:
        return False

    root = design.rootComponent
    occs = root.occurrencesByComponent(comp)
    return any(occ.isReferencedComponent for occ in occs)


def assembly_dict_to_ascii(assembly_dict):
    """
    Generate an ASCII diagram as a string from the assembly_dict structure.
    :param assembly_dict: The dictionary representing the assembly structure.
    :return: A string containing the ASCII diagram.
    """

    def build_ascii(node, prefix="", is_last=True):
        lines = []
        comp_name = node["component"].name
        connector = "└── " if is_last else "├── "
        lines.append(prefix + connector + comp_name)
        children = list(node["children"].values())
        for idx, child in enumerate(children):
            is_child_last = idx == len(children) - 1
            child_prefix = prefix + ("    " if is_last else "│   ")
            lines.extend(build_ascii(child, child_prefix, is_child_last))
        return lines

    ascii_lines = []
    items = list(assembly_dict.values())
    for idx, node in enumerate(items):
        is_last = idx == len(items) - 1
        ascii_lines.extend(build_ascii(node, "", is_last))
    return "\n".join(ascii_lines)


def command_execute(args: adsk.core.CommandCreatedEventArgs):
    futil.log(f"{CMD_NAME} Command Execute Event")
    ui = None

    try:
        app = adsk.core.Application.get()
        ui = app.userInterface
        design = app.activeProduct
        appVersionBuild = app.version

        if not isinstance(design, adsk.fusion.Design):
            ui.messageBox("No active Fusion 360 design")
            return

        root_component = design.rootComponent
        assembly_dict = {}

        # Start traversing from the root component
        traverse_assembly(root_component, assembly_dict)

        # Sort the dictionary as a DAG in bottom-up order
        bottom_up_order = sort_dag_bottom_up(assembly_dict)
        # dagString = assembly_dict_to_ascii(assembly_dict)
        # futil.log("Assembly Structure:\n" + dagString)

        # Print the bottom-up order to the console
        docCount = len(bottom_up_order)
        futil.log(f"Bottom-up order: {bottom_up_order}")

        if docCount == 0:
            ui.messageBox("No components found in the assembly.")
            return
        futil.log(f"----- Starting saving {docCount} components -----")

        for component_name in bottom_up_order:
            # Get the component by name from the design

            if component_name == "RootComponent":
                # Get the component by name from the design
                continue

            component = design.allComponents.itemByName(component_name)
            # if not is_external_component(component):
            #     # Skip if the component is not external
            #     print(f"Component {component_name} is not external. Skipping.")
            #     continue

            if component:
                # Open the component document
                docid = component.parentDesign.parentDocument.designDataFile.id  # type: ignore
                if docid not in saved:

                    saved.append(docid)  # to avoid duplicate saves

                    # Get the component document
                    document = app.data.findFileById(docid)
                    app.documents.open(document, True)

                    # Check if the component is already saved in the current version
                    # docVersionBuild = app.activeDocument.version
                    # if docVersionBuild == appVersionBuild:
                    #     print(f"Component {component_name} already saved in version {appVersionBuild}")
                    #     # Close the component document
                    #     app.activeDocument.close(True)
                    #     continue

                    # Make sure design workspace is active
                    workspace = ui.workspaces.itemById("FusionSolidEnvironment")
                    if workspace and not workspace.isActive:
                        workspace.activate()
                    des = adsk.fusion.Design.cast(app.activeProduct)
                    des.attributes.add("FusionRA", "FusionRA", component_name)
                    attr = des.attributes.itemByName("FusionRA", "FusionRA")
                    attr.deleteMe()

                    # Save the component document
                    app.activeDocument.save(
                        f"Auto save in Fusion: {appVersionBuild}, by rebuild assembly."
                    )
                    # Close the component document
                    app.activeDocument.close(True)
                    print(f"Component {component_name} saved and closed successfully.")

                else:
                    continue

        # Update all references in the assembly to newly saved versions
        UpdateAll(ui)
        print(f"----- Components saved -----")

        adsk.doEvents()

        # Show a message box indicating that all external assembly references have been saved
        ui.messageBox("All external Assembly References Saved.")

    except Exception as e:
        if ui:
            ui.messageBox(f"Failed:\n{traceback.format_exc()}")


# This function will be called when the user completes the command.
def command_destroy(args: adsk.core.CommandEventArgs):
    global local_handlers
    local_handlers = []
    futil.log(f"{CMD_NAME} Command Destroy Event")
