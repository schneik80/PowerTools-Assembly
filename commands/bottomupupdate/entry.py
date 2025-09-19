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

# Holds references to event handlers to prevent garbage collection
local_handlers = []
# Set to track document IDs that have already been saved to avoid duplicate processing
saved = set()

# Command input IDs
REBUILD_INPUT_ID = "rebuild_all"  # Checkbox to enable full rebuild of all components
SKIP_STANDARD_ID = "skip_standard"  # Checkbox to skip standard library components
SKIP_SAVED_ID = "skip_saved"  # Checkbox to skip components that are already saved
HIDE_ORIGINS_ID = "hide_origins"  # Checkbox to hide coordinate system origins
HIDE_JOINTS_ID = "hide_joints"  # Checkbox to hide joint elements in the model
HIDE_CONSTRAINTS_ID = "hide_constraints"  # Checkbox to hide assembly constraints
HIDE_JOINTORIGINS_ID = "hide_jointorigins"  # Checkbox to hide joint origin markers
APPLY_INTENT_ID = "apply_intent"  # Checkbox to apply design intent before saving
LOG_ENABLE_ID = "enable_log"  # Checkbox to enable progress logging
LOG_PATH_ID = "log_path"  # Text input for custom log file path
LOG_BROWSE_ID = "browse_log"  # Button to browse for log file location


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

    # Get the active Fusion product and cast to Design for manipulation
    product = app.activeProduct
    design = adsk.fusion.Design.cast(product)
    doc = app.activeDocument
    # Title for dialogs and messages
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
    # Main tab
    main_tab = inputs.addTabCommandInput("mainTab", "Main")
    main_inputs = main_tab.children
    main_inputs.addBoolValueInput(REBUILD_INPUT_ID, "Rebuild all", True, "", True)
    main_inputs.addBoolValueInput(
        SKIP_STANDARD_ID, "Skip standard components", True, "", True
    )
    main_inputs.addBoolValueInput(
        SKIP_SAVED_ID, "Skip already saved components", True, "", True
    )
    main_inputs.addBoolValueInput(
        APPLY_INTENT_ID, "Apply design intent before save", True, "", False
    )

    # Visualization tab
    vis_tab = inputs.addTabCommandInput("visTab", "Visibility")
    vis_inputs = vis_tab.children
    vis_inputs.addBoolValueInput(HIDE_ORIGINS_ID, "Hide origins", True, "", False)
    vis_inputs.addBoolValueInput(HIDE_JOINTS_ID, "Hide joints", True, "", False)
    vis_inputs.addBoolValueInput(
        HIDE_CONSTRAINTS_ID, "Hide constraints", True, "", False
    )
    vis_inputs.addBoolValueInput(
        HIDE_JOINTORIGINS_ID, "Hide joint origins", True, "", False
    )

    # Logging tab
    log_tab = inputs.addTabCommandInput("logTab", "Logging")
    log_inputs = log_tab.children
    log_enable = log_inputs.addBoolValueInput(
        LOG_ENABLE_ID, "Log Progress", True, "", True
    )
    log_path = log_inputs.addStringValueInput(LOG_PATH_ID, "Log file path", "")
    log_path.isReadOnly = True
    browse_btn = log_inputs.addBoolValueInput(
        LOG_BROWSE_ID, "Browse…", False, "", False
    )
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
        """Helper function to write entries to the log file if logging is enabled"""
        if create_log and file_path:
            try:
                with open(file_path, "a", encoding="utf-8") as fh:
                    fh.write(entry + "\n")
            except Exception as log_e:
                futil.log(f"Failed to write log entry: {log_e}")

    app = adsk.core.Application.get()
    ui = app.userInterface
    start_total_time = time.time()  # Track total execution time
    try:
        design = app.activeProduct
        appVersionBuild = app.version  # Store Fusion version for save comments
        if not isinstance(design, adsk.fusion.Design):
            ui.messageBox("No active Fusion 360 design")
            return

        # Read dialog values from user inputs
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
        skip_saved = adsk.core.BoolValueCommandInput.cast(
            inputs.itemById(SKIP_SAVED_ID)
        ).value

        # Build the assembly structure and determine processing order
        root_component = design.rootComponent
        assembly_dict = {}
        traverse_assembly(root_component, assembly_dict)  # Build component hierarchy
        bottom_up_order = sort_dag_bottom_up(assembly_dict)  # Sort for dependency order
        dagString = assembly_dict_to_ascii(
            assembly_dict
        )  # Create visual representation
        futil.log("Assembly Structure:\n" + dagString)
        docCount = len(bottom_up_order)
        futil.log(f"Bottom-up order: {bottom_up_order}")
        if docCount == 0:
            ui.messageBox("No components found in the assembly.")
            return
        futil.log(f"----- Starting saving {docCount} components -----")
        saved_doc_count = 0  # Track how many documents were actually saved
        file_path = None

        # Set up logging if enabled
        if create_log:
            doc = app.activeDocument
            base_name = "assembly_log"
            if log_path_val:  # Use custom path if provided
                file_path = log_path_val
            else:
                # Generate default log filename based on document name
                if doc and doc.dataFile:
                    base_name = doc.dataFile.name
                elif doc and doc.name:
                    base_name = doc.name
                # Clean filename for filesystem compatibility
                base_name = re.sub(r"[\\/:*?\"<>|]+", "_", base_name)
                if not base_name.lower().endswith(".log"):
                    base_name += ".log"
                # Default location is user Documents folder
                file_path = os.path.join(os.path.expanduser("~/Documents"), base_name)
            # Write initial log info at start
            try:
                with open(file_path, "w", encoding="utf-8") as fh:
                    parent_project_name = None
                    doc_id = None
                    try:
                        # Get project and document information for logging
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
        # Process each component in bottom-up dependency order
        for component_name in bottom_up_order:
            if component_name == "RootComponent":  # Skip the root assembly itself
                continue
            component = design.allComponents.itemByName(component_name)
            if not component:  # Component not found, skip it
                continue
            # Get the design data file for this component
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
                # Get the project name to check if it's a standard component
                parent_project = (
                    component.parentDesign.parentDocument.dataFile.parentProject.name
                )
            except Exception:
                parent_project = None

            # Skip standard components if option is enabled
            if skip_standard and parent_project == "Standard Components":
                log_entry = f"Skipped standard component: {component_name}"
                write_log_entry(log_entry)

            # Skip already saved components if option is enabled
            if skip_saved and app.activeDocument.version == app.version:
                log_entry = f"Skipped already saved component: {component_name}"
                write_log_entry(log_entry)
                continue

            # Skip if we've already processed this document ID
            if docid in saved:
                continue
            saved.add(docid)  # Mark this document as processed

            # Open the component's document for editing
            document = app.data.findFileById(docid)
            app.documents.open(document, True)
            # Update all references in the newly opened document
            opened_doc = app.activeDocument
            opened_doc.updateAllReferences()

            # Ensure we're in the correct workspace for operations
            workspace = ui.workspaces.itemById("FusionSolidEnvironment")
            if workspace and not workspace.isActive:
                workspace.activate()
            des = adsk.fusion.Design.cast(app.activeProduct)

            # Rebuild the component if rebuild option is enabled
            if rebuild_all:
                futil.log(f"Rebuilding component: {component_name}")
                while not des.computeAll():  # Force compute until complete
                    adsk.doEvents()
                    time.sleep(0.1)  # Optional: Add a small delay to observe the update
                futil.log(f"Rebuild complete: {component_name}")

            # Add and remove a temporary attribute to trigger change detection
            des.attributes.add("FusionRA", "FusionRA", component_name)
            attr = des.attributes.itemByName("FusionRA", "FusionRA")
            attr.deleteMe()

            # Save the document with timestamp
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            app.activeDocument.save(
                f"Auto save in Fusion: {appVersionBuild}, by rebuild assembly."
            )
            app.activeDocument.close(True)  # Close after saving
            log_entry = f"{component_name} saved - [{timestamp}]"
            write_log_entry(log_entry)
            saved_doc_count += 1  # Increment counter for completed saves
            des = None  # Clear design reference

        print(f"----- Components saved -----")

        # Execute Fusion commands to get latest versions and update references
        cmdDefs = ui.commandDefinitions
        cmdGet = cmdDefs.itemById("GetAllLatestCmd")  # Get all latest command
        while not cmdGet.execute():
            adsk.doEvents()
            time.sleep(0.1)  # Optional: Add a small delay to observe the update
        cmdUpdate = cmdDefs.itemById(
            "ContextUpdateAllFromParentCmd"
        )  # Update all from parent
        while not cmdUpdate.execute():
            adsk.doEvents()
            time.sleep(0.1)  # Optional: Add a small delay to observe the update

        # Save the active document after updating references
        app.activeDocument.save(
            f"Auto save in Fusion: {appVersionBuild}, by rebuild assembly."
        )

        # Prepare completion message and finalize logging
        completion_msg = "Bottom-up Update complete."
        end_total_time = time.time()
        total_elapsed = (
            end_total_time - start_total_time
        )  # Calculate total execution time
        if create_log and file_path:
            try:
                # Write final statistics to log file
                with open(file_path, "a", encoding="utf-8") as fh:
                    fh.write(f"\nTotal documents saved: {saved_doc_count}\n")
                    fh.write(f"Total command run time: {total_elapsed:.2f} seconds\n")
                futil.log(f"Log written to: {file_path}")
                completion_msg += f"\nLog written to: {file_path}"
            except Exception as log_e:
                futil.log(f"Failed to write log: {log_e}")
                completion_msg += f"\nFailed to write log to: {file_path}\n{log_e}"
        ui.messageBox(completion_msg)  # Show completion message to user
    except Exception as e:
        if ui:
            ui.messageBox(f"Failed:\n{traceback.format_exc()}")


# This function will be called when the user completes the command.
def command_destroy(args: adsk.core.CommandEventArgs):
    global local_handlers
    local_handlers = []
    futil.log(f"{CMD_NAME} Command Destroy Event")


def _propose_default_log_filename() -> str:
    """Generate a default log filename based on the active document name"""
    app = adsk.core.Application.get()
    doc = app.activeDocument
    base_name = "assembly_log"
    if doc and doc.dataFile:
        base_name = doc.dataFile.name
    elif doc and doc.name:
        base_name = doc.name
    # Clean filename for filesystem compatibility
    base_name = re.sub(r"[\\/:*?\"<>|]+", "_", base_name)
    if not base_name.lower().endswith(".txt"):
        base_name += ".txt"
    return base_name


def on_input_changed(args: adsk.core.InputChangedEventArgs):
    """Handle changes to UI input controls in the command dialog"""
    try:
        changed = args.input
        inputs = args.inputs
        ui = adsk.core.Application.get().userInterface

        # Handle logging enable/disable toggle
        if changed.id == LOG_ENABLE_ID:
            enabled = adsk.core.BoolValueCommandInput.cast(changed).value
            path_input = adsk.core.StringValueCommandInput.cast(
                inputs.itemById(LOG_PATH_ID)
            )
            browse_btn = adsk.core.BoolValueCommandInput.cast(
                inputs.itemById(LOG_BROWSE_ID)
            )
            # Enable/disable log path controls based on logging checkbox
            path_input.isEnabled = enabled
            browse_btn.isEnabled = enabled

        # Handle browse button click for log file selection
        if changed.id == LOG_BROWSE_ID:
            # Treat as a momentary button
            btn = adsk.core.BoolValueCommandInput.cast(changed)
            # Reset state so it can be clicked again later
            btn.value = False

            # Create and configure file dialog for log file selection
            dlg: adsk.core.FileDialog = ui.createFileDialog()
            dlg.title = "Save log file"
            dlg.filter = "Text files (*.txt);;All Files (*.*)"
            dlg.isMultiSelectEnabled = False
            dlg.initialDirectory = os.path.expanduser(
                "~/Documents"
            )  # Default to Documents
            dlg.initialFilename = _propose_default_log_filename()

            # If user selected a file, update the path input
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
