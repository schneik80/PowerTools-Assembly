import adsk.core, adsk.fusion
import os, re, traceback
import time
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
saved = set()

# Command input IDs
REBUILD_INPUT_ID = "rebuild_all"
LOG_ENABLE_ID = "enable_log"
LOG_PATH_ID = "log_path"
LOG_BROWSE_ID = "browse_log"
SKIP_STANDARD_ID = "skip_standard"


# Executed when add-in is run.
def start():
    # Remove any existing command/control for clean setup
    workspace = ui.workspaces.itemById(WORKSPACE_ID)
    toolbar_tab = workspace.toolbarTabs.itemById(TAB_ID)
    if toolbar_tab is None:
        toolbar_tab = workspace.toolbarTabs.add(TAB_ID, TAB_NAME)
    panel = toolbar_tab.toolbarPanels.itemById(PANEL_ID)
    if panel is None:
        panel = toolbar_tab.toolbarPanels.add(PANEL_ID, PANEL_NAME, PANEL_AFTER, False)
    command_control = panel.controls.itemById(CMD_ID)
    if command_control:
        command_control.deleteMe()
    command_definition = ui.commandDefinitions.itemById(CMD_ID)
    if command_definition:
        command_definition.deleteMe()
    # Create new command definition and control
    cmd_def = ui.commandDefinitions.addButtonDefinition(
        CMD_ID, CMD_NAME, CMD_Description, ICON_FOLDER
    )
    futil.add_handler(cmd_def.commandCreated, command_created)
    control = panel.controls.addCommand(cmd_def)
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
        args.command.inputChanged, on_input_changed, local_handlers=local_handlers
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

    # Build command dialog inputs
    inputs: adsk.core.CommandInputs = args.command.commandInputs
    # Checkbox: Rebuild all (default on)
    inputs.addBoolValueInput(REBUILD_INPUT_ID, "Rebuild all", True, "", True)
    # Checkbox: create log file (default ON)
    log_enable = inputs.addBoolValueInput(LOG_ENABLE_ID, "Log Progress", True, "", True)
    # Checkbox: skip standard components (default ON)
    inputs.addBoolValueInput(
        SKIP_STANDARD_ID, "Skip standard components", True, "", True
    )
    # Read-only string to display chosen log path
    log_path = inputs.addStringValueInput(LOG_PATH_ID, "Log file path", "")
    log_path.isReadOnly = True
    # Browse button to choose save path
    browse_btn = inputs.addBoolValueInput(LOG_BROWSE_ID, "Browse…", False, "", False)
    # Enable/disable according to checkbox default
    log_path.isEnabled = log_enable.value
    browse_btn.isEnabled = log_enable.value


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


def command_execute(args: adsk.core.CommandEventArgs):
    # ...existing code...
    from datetime import datetime

    def write_log_entry(entry):
        if create_log and file_path:
            try:
                with open(file_path, "a", encoding="utf-8") as fh:
                    fh.write(entry + "\n")
            except Exception as log_e:
                futil.log(f"Failed to write log entry: {log_e}")

    app = adsk.core.Application.get()
    ui = app.userInterface
    start_total_time = time.time()
    try:
        design = app.activeProduct
        appVersionBuild = app.version
        if not isinstance(design, adsk.fusion.Design):
            ui.messageBox("No active Fusion 360 design")
            return
        # Read dialog values
        inputs: adsk.core.CommandInputs = args.command.commandInputs
        skip_standard = adsk.core.BoolValueCommandInput.cast(
            inputs.itemById(SKIP_STANDARD_ID)
        ).value
        rebuild_all = adsk.core.BoolValueCommandInput.cast(
            inputs.itemById(REBUILD_INPUT_ID)
        ).value
        create_log = adsk.core.BoolValueCommandInput.cast(
            inputs.itemById(LOG_ENABLE_ID)
        ).value
        log_path_val = adsk.core.StringValueCommandInput.cast(
            inputs.itemById(LOG_PATH_ID)
        ).value
        root_component = design.rootComponent
        assembly_dict = {}
        traverse_assembly(root_component, assembly_dict)
        bottom_up_order = sort_dag_bottom_up(assembly_dict)
        dagString = assembly_dict_to_ascii(assembly_dict)
        futil.log("Assembly Structure:\n" + dagString)
        docCount = len(bottom_up_order)
        futil.log(f"Bottom-up order: {bottom_up_order}")
        if docCount == 0:
            ui.messageBox("No components found in the assembly.")
            return
        futil.log(f"----- Starting saving {docCount} components -----")
        saved_doc_count = 0
        file_path = None
        if create_log:
            doc = app.activeDocument
            base_name = "assembly_log"
            if log_path_val:
                file_path = log_path_val
            else:
                if doc and doc.dataFile:
                    base_name = doc.dataFile.name
                elif doc and doc.name:
                    base_name = doc.name
                base_name = re.sub(r"[\\/:*?\"<>|]+", "_", base_name)
                if not base_name.lower().endswith(".log"):
                    base_name += ".log"
                file_path = os.path.join(os.path.expanduser("~/Documents"), base_name)
            # Write initial log info at start
            try:
                with open(file_path, "w", encoding="utf-8") as fh:
                    parent_project_name = None
                    doc_id = None
                    try:
                        parent_project_name = (
                            doc.dataFile.parentProject.name
                            if doc and doc.dataFile and doc.dataFile.parentProject
                            else None
                        )
                        doc_id = doc.dataFile.id if doc and doc.dataFile else None
                    except Exception:
                        parent_project_name = None
                        doc_id = None
                    fh.write(f"Active Document Parent Project: {parent_project_name}\n")
                    fh.write(f"Active Document ID: {doc_id}\n")
                    fh.write("Command Options:\n")
                    fh.write(f"  Rebuild all: {rebuild_all}\n")
                    fh.write(f"  Create log file: {create_log}\n")
                    fh.write(f"  Skip standard components: {skip_standard}\n")
                    fh.write(f"  Log file path: {file_path}\n")
                    fh.write("\nAssembly Diagram:\n")
                    fh.write(dagString)
                    fh.write("\n\nBottom-up order:\n")
                    fh.write("\n".join(bottom_up_order))
                    fh.write("\n\nDocument save log:\n")
            except Exception as log_e:
                futil.log(f"Failed to write initial log: {log_e}")
        for component_name in bottom_up_order:
            if component_name == "RootComponent":
                continue
            component = design.allComponents.itemByName(component_name)
            if not component:
                continue
            design_data_file = getattr(
                component.parentDesign.parentDocument, "designDataFile", None
            )
            if design_data_file is None:
                log_entry = f"Skipped component (no designDataFile): {component_name}"
                write_log_entry(log_entry)
                continue
            docid = design_data_file.id
            parent_project = None
            try:
                parent_project = (
                    component.parentDesign.parentDocument.dataFile.parentProject.name
                )
            except Exception:
                parent_project = None
            if skip_standard and parent_project == "Standard Components":
                log_entry = f"Skipped standard component: {component_name}"
                write_log_entry(log_entry)
                continue
            if docid in saved:
                continue
            saved.add(docid)
            document = app.data.findFileById(docid)
            app.documents.open(document, True)
            # Update all references in the newly opened document
            opened_doc = app.activeDocument
            opened_doc.updateAllReferences()

            workspace = ui.workspaces.itemById("FusionSolidEnvironment")
            if workspace and not workspace.isActive:
                workspace.activate()
            des = adsk.fusion.Design.cast(app.activeProduct)
            if rebuild_all:
                futil.log(f"Rebuilding component: {component_name}")
                while not des.computeAll():
                    adsk.doEvents()
                    time.sleep(0.1)  # Optional: Add a small delay to observe the update
                futil.log(f"Rebuild complete: {component_name}")
            des.attributes.add("FusionRA", "FusionRA", component_name)
            attr = des.attributes.itemByName("FusionRA", "FusionRA")
            attr.deleteMe()
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            app.activeDocument.save(
                f"Auto save in Fusion: {appVersionBuild}, by rebuild assembly."
            )
            app.activeDocument.close(True)
            log_entry = f"{component_name} saved - [{timestamp}]"
            write_log_entry(log_entry)
            saved_doc_count += 1
            des = None
        print(f"----- Components saved -----")
        cmdDefs = ui.commandDefinitions
        cmdGet = cmdDefs.itemById("GetAllLatestCmd")
        while not cmdGet.execute():
            adsk.doEvents()
            time.sleep(0.1)  # Optional: Add a small delay to observe the update
        cmdUpdate = cmdDefs.itemById("ContextUpdateAllFromParentCmd")
        while not cmdUpdate.execute():
            adsk.doEvents()
            time.sleep(0.1)  # Optional: Add a small delay to observe the update

        # Save the active document after updating references
        app.activeDocument.save(
            f"Auto save in Fusion: {appVersionBuild}, by rebuild assembly."
        )

        completion_msg = "Bottom-up Update complete."
        end_total_time = time.time()
        total_elapsed = end_total_time - start_total_time
        if create_log and file_path:
            try:
                with open(file_path, "a", encoding="utf-8") as fh:
                    fh.write(f"\nTotal documents saved: {saved_doc_count}\n")
                    fh.write(f"Total command run time: {total_elapsed:.2f} seconds\n")
                futil.log(f"Log written to: {file_path}")
                completion_msg += f"\nLog written to: {file_path}"
            except Exception as log_e:
                futil.log(f"Failed to write log: {log_e}")
                completion_msg += f"\nFailed to write log to: {file_path}\n{log_e}"
        ui.messageBox(completion_msg)
    except Exception as e:
        if ui:
            ui.messageBox(f"Failed:\n{traceback.format_exc()}")


# This function will be called when the user completes the command.
def command_destroy(args: adsk.core.CommandEventArgs):
    global local_handlers
    local_handlers = []
    futil.log(f"{CMD_NAME} Command Destroy Event")


def _propose_default_log_filename() -> str:
    app = adsk.core.Application.get()
    doc = app.activeDocument
    base_name = "assembly_log"
    if doc and doc.dataFile:
        base_name = doc.dataFile.name
    elif doc and doc.name:
        base_name = doc.name
    base_name = re.sub(r"[\\/:*?\"<>|]+", "_", base_name)
    if not base_name.lower().endswith(".txt"):
        base_name += ".txt"
    return base_name


def on_input_changed(args: adsk.core.InputChangedEventArgs):
    try:
        changed = args.input
        inputs = args.inputs
        ui = adsk.core.Application.get().userInterface

        if changed.id == LOG_ENABLE_ID:
            enabled = adsk.core.BoolValueCommandInput.cast(changed).value
            path_input = adsk.core.StringValueCommandInput.cast(
                inputs.itemById(LOG_PATH_ID)
            )
            browse_btn = adsk.core.BoolValueCommandInput.cast(
                inputs.itemById(LOG_BROWSE_ID)
            )
            path_input.isEnabled = enabled
            browse_btn.isEnabled = enabled

        if changed.id == LOG_BROWSE_ID:
            # Treat as a momentary button
            btn = adsk.core.BoolValueCommandInput.cast(changed)
            # Reset state so it can be clicked again later
            btn.value = False

            dlg: adsk.core.FileDialog = ui.createFileDialog()
            dlg.title = "Save log file"
            dlg.filter = "Text files (*.txt);;All Files (*.*)"
            dlg.isMultiSelectEnabled = False
            dlg.initialDirectory = os.path.expanduser("~/Documents")
            dlg.initialFilename = _propose_default_log_filename()
            if dlg.showSave() == adsk.core.DialogResults.DialogOK:
                sel_path = dlg.filename
                path_input = adsk.core.StringValueCommandInput.cast(
                    inputs.itemById(LOG_PATH_ID)
                )
                path_input.value = sel_path
    except Exception:
        ui = adsk.core.Application.get().userInterface
        if ui:
            ui.messageBox("Input handling failed:\n{}".format(traceback.format_exc()))
