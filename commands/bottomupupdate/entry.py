# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2022-2026 IMA LLC

import adsk.core, adsk.fusion
import os, re, traceback
import time
import sys
import subprocess
import tempfile
from ...lib import fusionAddInUtils as futil
from ... import config

app = adsk.core.Application.get()
ui = app.userInterface

CMD_NAME = "Bottom-up Update"
CMD_ID = "PTAT-bottomupupdate"
CMD_Description = "Save and update all references in the open assembly from the bottom up\n \nOptions to Rebuild all, log the results, hide objects and apply document intent.\nUpdating can skip standard components and already saved documents."
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
resume_plan = {}

# Command input IDs
REBUILD_INPUT_ID = "rebuild_all"  # Checkbox to enable full rebuild of all components
SKIP_STANDARD_ID = "skip_standard"  # Checkbox to skip standard library components
SKIP_SAVED_ID = "skip_saved"  # Checkbox to skip components that are already saved
HIDE_ORIGINS_ID = "hide_origins"  # Checkbox to hide coordinate system origins
HIDE_JOINTS_ID = "hide_joints"  # Checkbox to hide joint elements in the model
HIDE_SKETCHES_ID = "hide_sketches"  # Checkbox to hide component sketches
HIDE_JOINTORIGINS_ID = "hide_jointorigins"  # Checkbox to hide joint origin markers
HIDE_CANVASES_ID = "hide_canvases"  # Checkbox to hide canvases
APPLY_INTENT_ID = "apply_intent"  # Checkbox to apply design intent before saving
PAUSE_TIME_ID = "pause_time"  # Text input for upload completion poll interval in seconds
LOG_ENABLE_ID = "enable_log"  # Checkbox to enable progress logging
LOG_PATH_ID = "log_path"  # Text input for custom log file path
LOG_BROWSE_ID = "browse_log"  # Button to browse for log file location
LOG_OPEN_VIEW_ID = "open_log_view"  # Checkbox to auto-open a live log viewer
RESUME_STATUS_ID = "resume_status"  # Read-only status for resume behavior


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

    global product, design, title, resume_plan

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

    resume_plan = {
        "should_resume": False,
        "resume_start_index": 0,
        "last_saved_index": 0,
        "status_message": "A full run will start.",
    }
    try:
        root_component = design.rootComponent
        assembly_dict = {}
        traverse_assembly(root_component, assembly_dict)
        bottom_up_order = sort_dag_bottom_up(assembly_dict)
        resume_plan = _analyze_resume_state(
            _default_temp_log_path(), app.version, bottom_up_order
        )
    except Exception as resume_error:
        resume_plan = {
            "should_resume": False,
            "resume_start_index": 0,
            "last_saved_index": 0,
            "status_message": f"Resume check failed ({resume_error}). A full run will start.",
        }

    # Build command dialog inputs
    inputs: adsk.core.CommandInputs = args.command.commandInputs
    # Main tab
    main_tab = inputs.addTabCommandInput("mainTab", "Main")
    main_inputs = main_tab.children

    rebuild_input = main_inputs.addBoolValueInput(
        REBUILD_INPUT_ID, "Rebuild all", True, "", True
    )
    rebuild_input.tooltip = (
        "Forces a complete rebuild of all components to ensure they are up to date."
    )

    skip_standard_input = main_inputs.addBoolValueInput(
        SKIP_STANDARD_ID, "Skip standard components", True, "", True
    )
    skip_standard_input.tooltip = (
        "Skip processing of standard library component Documents."
    )

    skip_saved_input = main_inputs.addBoolValueInput(
        SKIP_SAVED_ID, "Skip already saved Documents", True, "", False
    )
    skip_saved_input.tooltip = (
        "Skip Documents that have already been saved in this Fusion client build."
    )

    apply_intent_input = main_inputs.addBoolValueInput(
        APPLY_INTENT_ID, "Apply Design Doc Intent", True, "", True
    )
    apply_intent_input.tooltip = "Applies design intent (Part, Assembly, or Hybrid) to the document's root component."

    resume_status_input = main_inputs.addTextBoxCommandInput(
        RESUME_STATUS_ID,
        "Run status",
        resume_plan.get("status_message", "A full run will start."),
        3,
        True,
    )
    resume_status_input.tooltip = (
        "Startup check based on temp log, Fusion client version, and current bottom-up list."
    )

    advanced_group = main_inputs.addGroupCommandInput("advancedGroup", "Advanced")
    advanced_group.isExpanded = False
    advanced_inputs = advanced_group.children

    # Add upload poll interval input
    pause_time_input = advanced_inputs.addStringValueInput(
        PAUSE_TIME_ID, "Upload check interval (seconds)", "0.5"
    )
    pause_time_input.tooltip = (
        "How often to check upload status after each save. Lower values react faster, higher values reduce CPU usage."
    )

    # Visualization tab
    vis_tab = inputs.addTabCommandInput("visTab", "Visibility")
    vis_inputs = vis_tab.children
    hide_origins_input = vis_inputs.addBoolValueInput(
        HIDE_ORIGINS_ID, "Hide origins", True, "", False
    )
    hide_origins_input.tooltip = "Hide the origin in the document's root component."

    hide_joints_input = vis_inputs.addBoolValueInput(
        HIDE_JOINTS_ID, "Hide joints", True, "", False
    )
    hide_joints_input.tooltip = "Hides all joints. \n \nSet the Joint Folder visibility off to hide any new Joints created."

    hide_sketches_input = vis_inputs.addBoolValueInput(
        HIDE_SKETCHES_ID, "Hide sketches", True, "", False
    )
    hide_sketches_input.tooltip = "Hides each sketch in the document's root component.\n \nSet the Sketch Folder visibility On to show any new Sketches created."

    hide_joint_origins_input = vis_inputs.addBoolValueInput(
        HIDE_JOINTORIGINS_ID, "Hide joint origins", True, "", False
    )
    hide_joint_origins_input.tooltip = "Hides each joint origin in the document's root component before saving.\n \nSet the Joint Origins Folder visibility On to show any new Joint Origins created."

    hide_canvases_input = vis_inputs.addBoolValueInput(
        HIDE_CANVASES_ID, "Hide canvases", True, "", False
    )
    hide_canvases_input.tooltip = "Hides each canvas in the document's root component before saving.\n \nSet the Canvases Folder visibility On to show any new Canvases created."

    # Logging tab
    log_tab = inputs.addTabCommandInput("logTab", "Logging")
    log_inputs = log_tab.children
    log_enable = log_inputs.addBoolValueInput(
        LOG_ENABLE_ID, "Log Progress", True, "", True
    )
    log_enable.tooltip = (
        "Enables detailed progress logging to a text file during the update process."
    )

    log_path = log_inputs.addStringValueInput(LOG_PATH_ID, "Log file path", "")
    log_path.isReadOnly = True

    browse_btn = log_inputs.addBoolValueInput(
        LOG_BROWSE_ID, "Browse…", False, "", False
    )
    browse_btn.tooltip = (
        "Click to browse and select a custom location for the log file."
    )

    open_view = log_inputs.addBoolValueInput(
        LOG_OPEN_VIEW_ID, "Open live log viewer", True, "", True
    )
    open_view.tooltip = (
        "Automatically opens a system console window to live-monitor log output while the command runs."
    )

    log_path.isEnabled = log_enable.value
    browse_btn.isEnabled = log_enable.value
    open_view.isEnabled = log_enable.value


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


def hide_origins_in_document(document):
    """
    Hide all coordinate system origins in the specified document.

    :param document: The Fusion document to process
    :return: A log string describing what was hidden
    """
    try:
        app = adsk.core.Application.get()

        # Get the active design
        design = adsk.fusion.Design.cast(app.activeProduct)
        if not design:
            return "No active design found"

        # Use Fusion API to directly control origin visibility
        try:
            # Check if the origin folder light bulb is on (visible) and turn it off
            if design.activeComponent.isOriginFolderLightBulbOn:
                design.activeComponent.isOriginFolderLightBulbOn = False
                return f"   Origin hidden "
            else:
                return "   Origin was already hidden"

        except Exception as api_e:
            return f"Error using Fusion API to hide origins: {str(api_e)}"

    except Exception as e:
        return f"Error hiding origins: {str(e)}"


def hide_joint_origins_in_document(document):
    """
    Hide all joint origins in the specified document.

    :param document: The Fusion document to process
    :return: A log string describing what was hidden
    """
    try:
        app = adsk.core.Application.get()

        # Get the active design
        design = adsk.fusion.Design.cast(app.activeProduct)
        if not design:
            return "No active design found"

        # Use Fusion API to directly control joint origin visibility
        try:
            # Set the joint origins folder light bulb to true (ensure folder is accessible)
            design.activeComponent.isJointOriginsFolderLightBulbOn = True

            # Check if there are joint origins to hide
            joint_origins = design.activeComponent.jointOrigins
            if joint_origins.count > 0:
                hidden_count = 0
                # Iterate over each joint origin and try to hide it
                for i in range(joint_origins.count):
                    joint_origin = joint_origins.item(i)
                    try:
                        # Try to use the light bulb property if available
                        if (
                            hasattr(joint_origin, "isLightBulbOn")
                            and joint_origin.isLightBulbOn
                        ):
                            joint_origin.isLightBulbOn = False
                            hidden_count += 1
                    except:
                        # If individual control fails, continue to next
                        continue

                if hidden_count > 0:
                    return f"   joint origins hidden ({hidden_count})"
                else:
                    return "   Attempted to hide joint origins - individual visibility control may be limited"
            else:
                return "   No joint origins found in document"

        except Exception as api_e:
            return f"Error using Fusion API to hide joint origins: {str(api_e)}"

    except Exception as e:
        return f"Error hiding joint origins: {str(e)}"


def hide_sketches_in_document(document):
    """
    Hide all sketches in the specified document.

    :param document: The Fusion document to process
    :return: A log string describing what was hidden
    """
    try:
        app = adsk.core.Application.get()

        # Get the active design
        design = adsk.fusion.Design.cast(app.activeProduct)
        if not design:
            return "No active design found"

        # Use Fusion API to directly control sketch visibility
        try:
            # Set the sketches folder light bulb to true (ensure folder is accessible)
            design.activeComponent.isSketchFolderLightBulbOn = True

            # Check if there are sketches to hide
            sketches = design.activeComponent.sketches
            if sketches.count > 0:
                hidden_count = 0
                # Iterate over each sketch and try to hide it
                for i in range(sketches.count):
                    sketch = sketches.item(i)
                    try:
                        # Try to use the light bulb property if available
                        if hasattr(sketch, "isLightBulbOn") and sketch.isLightBulbOn:
                            sketch.isLightBulbOn = False
                            hidden_count += 1
                    except:
                        # If individual control fails, continue to next
                        continue

                if hidden_count > 0:
                    return f"   sketches hidden ({hidden_count})"
                else:
                    return "   Attempted to hide sketches - individual visibility control may be limited"
            else:
                return "   No sketches found in document"

        except Exception as api_e:
            return f"Error using Fusion API to hide sketches: {str(api_e)}"

    except Exception as e:
        return f"Error hiding sketches: {str(e)}"


def hide_joints_in_document(document):
    """
    Hide all joints in the specified document.

    :param document: The Fusion document to process
    :return: A log string describing what was hidden
    """
    try:
        app = adsk.core.Application.get()

        # Get the active design
        design = adsk.fusion.Design.cast(app.activeProduct)
        if not design:
            return "No active design found"

        # Use Fusion API to directly control joint visibility
        try:
            # Set the joints folder light bulb to false (hide folder)
            design.activeComponent.isJointsFolderLightBulbOn = False

            # Check if there are joints to hide
            joints = design.activeComponent.joints
            if joints.count > 0:
                hidden_count = 0
                # Iterate over each joint and try to hide it
                for i in range(joints.count):
                    joint = joints.item(i)
                    try:
                        # Try to use the light bulb property if available
                        if hasattr(joint, "isLightBulbOn") and joint.isLightBulbOn:
                            joint.isLightBulbOn = False
                            hidden_count += 1
                    except:
                        # If individual control fails, continue to next
                        continue

                if hidden_count > 0:
                    return f"   joints hidden ({hidden_count})"
                else:
                    return "   Attempted to hide joints - individual visibility control may be limited"
            else:
                return "   No joints found in document"

        except Exception as api_e:
            return f"Error using Fusion API to hide joints: {str(api_e)}"

    except Exception as e:
        return f"Error hiding joints: {str(e)}"


def hide_canvases_in_document(document):
    """
    Hide all canvases in the specified document.

    :param document: The Fusion document to process
    :return: A log string describing what was hidden
    """
    try:
        app = adsk.core.Application.get()

        # Get the active design
        design = adsk.fusion.Design.cast(app.activeProduct)
        if not design:
            return "No active design found"

        # Use Fusion API to directly control canvas visibility
        try:
            # Set the canvases folder light bulb to false (hide folder)
            design.activeComponent.isCanvasFolderLightBulbOn = False

            # Check if there are canvases to hide
            canvases = design.activeComponent.canvases
            if canvases.count > 0:
                hidden_count = 0
                # Iterate over each canvas and try to hide it
                for i in range(canvases.count):
                    canvas = canvases.item(i)
                    try:
                        # Try to use the light bulb property if available
                        if hasattr(canvas, "isLightBulbOn") and canvas.isLightBulbOn:
                            canvas.isLightBulbOn = False
                            hidden_count += 1
                    except:
                        # If individual control fails, continue to next
                        continue

                if hidden_count > 0:
                    return f"   canvases hidden ({hidden_count})"
                else:
                    return "   Attempted to hide canvases - individual visibility control may be limited"
            else:
                return "   No canvases found in document"

        except Exception as api_e:
            return f"Error using Fusion API to hide canvases: {str(api_e)}"

    except Exception as e:
        return f"Error hiding canvases: {str(e)}"


def wait_for_data_file_future(
    data_file_future,
    context_label,
    poll_interval_seconds=0.5,
    document=None,
    pre_save_version=None,
    timeout_seconds=300,
    settle_seconds=1.0,
):
    """
    Wait for a Fusion DataFileFuture to complete and report success/failure.

    :param data_file_future: Return value from Document.save (DataFileFuture or bool)
    :param context_label: Human readable label for logging
    :param poll_interval_seconds: Sleep interval between completion checks
    :param document: Document that was saved (optional, used for bool fallback)
    :param pre_save_version: Data file version before save (optional)
    :param timeout_seconds: Maximum time to wait before giving up
    :param settle_seconds: Stable-state settle window when version bump is unavailable
    :return: (is_success, message)
    """
    if data_file_future is None:
        return False, f"Save failed for {context_label}: save returned no result"

    poll_interval = max(0.05, poll_interval_seconds)

    # Some Fusion builds return bool from Document.save instead of DataFileFuture.
    if isinstance(data_file_future, bool):
        if not data_file_future:
            return False, f"Save failed for {context_label}: save returned False"

        if document is None:
            return True, f"Save+upload completed for {context_label}"

        start_time = time.time()
        stable_since = None
        stable_ready_checks = 0
        data_file_id = None
        try:
            if document.dataFile:
                data_file_id = document.dataFile.id
        except Exception:
            data_file_id = None

        while True:
            adsk.doEvents()

            current_version = None
            try:
                if data_file_id:
                    refreshed = adsk.core.Application.get().data.findFileById(data_file_id)
                    if refreshed and hasattr(refreshed, "versionNumber"):
                        current_version = refreshed.versionNumber
                if current_version is None and document.dataFile and hasattr(document.dataFile, "versionNumber"):
                    current_version = document.dataFile.versionNumber
            except Exception:
                current_version = None

            # Prefer a version bump when available.
            if (
                pre_save_version is not None
                and current_version is not None
                and current_version > pre_save_version
            ):
                return (
                    True,
                    f"Save+upload completed for {context_label} (version {pre_save_version} -> {current_version})",
                )

            # Fallback signal for builds without version visibility changes.
            doc_is_saved = getattr(document, "isSaved", None)
            doc_is_modified = getattr(document, "isModified", None)
            if doc_is_saved is True and doc_is_modified is False:
                stable_ready_checks += 1
                if stable_since is None:
                    stable_since = time.time()
                if stable_ready_checks >= 3 and (time.time() - stable_since) >= settle_seconds:
                    return True, f"Save+upload completed for {context_label}"
            else:
                stable_ready_checks = 0
                stable_since = None

            if timeout_seconds > 0 and (time.time() - start_time) >= timeout_seconds:
                return (
                    False,
                    f"Save wait timed out for {context_label} after {timeout_seconds} seconds",
                )

            time.sleep(poll_interval)

    if not hasattr(data_file_future, "isComplete"):
        return (
            False,
            f"Save failed for {context_label}: unsupported save result type {type(data_file_future).__name__}",
        )

    start_time = time.time()
    while not data_file_future.isComplete:
        adsk.doEvents()
        if timeout_seconds > 0 and (time.time() - start_time) >= timeout_seconds:
            return (
                False,
                f"Save wait timed out for {context_label} after {timeout_seconds} seconds",
            )
        time.sleep(poll_interval)

    if data_file_future.error:
        error_description = getattr(
            data_file_future, "errorDescription", "Unknown upload error"
        )
        return False, f"Save failed for {context_label}: {error_description}"

    return True, f"Save+upload completed for {context_label}"


def execute_command_with_timeout(
    command_definition,
    command_label,
    poll_interval_seconds=0.1,
    timeout_seconds=120,
):
    """
    Execute a Fusion command definition with polling and timeout protection.

    :return: (is_success, message)
    """
    if command_definition is None:
        return False, f"{command_label} not found"

    poll_interval = max(0.05, poll_interval_seconds)
    start_time = time.time()
    while True:
        if command_definition.execute():
            return True, f"{command_label} executed successfully"

        adsk.doEvents()
        if timeout_seconds > 0 and (time.time() - start_time) >= timeout_seconds:
            return (
                False,
                f"{command_label} timed out after {timeout_seconds} seconds",
            )
        time.sleep(poll_interval)


def open_live_log_viewer(log_file_path):
    """
    Open a platform-native live log viewer for the given file.

    macOS: Console.app via `open -a Console <path>` — natively follows live log files.
    Windows: PowerShell + Get-Content -Wait
    """
    try:
        if sys.platform == "darwin":
            subprocess.Popen(["open", "-a", "Console", log_file_path])
            return True, "Opened live log viewer in Console.app"

        if sys.platform == "win32":
            command = f'Get-Content -Path "{log_file_path}" -Wait'
            subprocess.Popen(
                [
                    "powershell",
                    "-NoExit",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-Command",
                    command,
                ]
            )
            return True, "Opened live log viewer in PowerShell"

        return False, "Live log viewer auto-open is currently supported on macOS and Windows only"
    except Exception as e:
        return False, f"Failed to open live log viewer: {e}"


def command_execute(args: adsk.core.CommandEventArgs):
    # ...existing code...
    global product, design, title, saved, resume_plan
    from datetime import datetime

    app = adsk.core.Application.get()
    ui = app.userInterface
    start_total_time = time.time()  # Track total execution time

    # Initialize logging variables early
    create_log = False
    file_path = None
    progress_bar = None  # Initialize progress bar variable

    def write_log_entry(entry):
        """Helper function to write entries to the log file if logging is enabled"""
        if create_log and file_path:
            try:
                with open(file_path, "a", encoding="utf-8") as fh:
                    fh.write(entry + "\n")
            except Exception as log_e:
                futil.log(f"Failed to write log entry: {log_e}")

    try:
        design = app.activeProduct
        appVersionBuild = app.version  # Store Fusion version for save comments
        if not isinstance(design, adsk.fusion.Design):
            ui.messageBox("No active Fusion design")
            return

        # Keep the starting/top document open throughout command execution.
        top_document = app.activeDocument
        top_document_id = None
        try:
            if top_document and top_document.dataFile:
                top_document_id = top_document.dataFile.id
        except Exception:
            top_document_id = None

        def is_top_document(doc):
            if not doc:
                return False
            if doc == top_document:
                return True
            try:
                return bool(top_document_id and doc.dataFile and doc.dataFile.id == top_document_id)
            except Exception:
                return False

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
        open_log_view = adsk.core.BoolValueCommandInput.cast(
            inputs.itemById(LOG_OPEN_VIEW_ID)
        ).value
        log_path_val = adsk.core.StringValueCommandInput.cast(
            inputs.itemById(LOG_PATH_ID)
        ).value
        skip_saved = adsk.core.BoolValueCommandInput.cast(
            inputs.itemById(SKIP_SAVED_ID)
        ).value
        hide_origins = adsk.core.BoolValueCommandInput.cast(
            inputs.itemById(HIDE_ORIGINS_ID)
        ).value
        hide_joints = adsk.core.BoolValueCommandInput.cast(
            inputs.itemById(HIDE_JOINTS_ID)
        ).value
        hide_sketches = adsk.core.BoolValueCommandInput.cast(
            inputs.itemById(HIDE_SKETCHES_ID)
        ).value
        hide_joint_origins = adsk.core.BoolValueCommandInput.cast(
            inputs.itemById(HIDE_JOINTORIGINS_ID)
        ).value
        hide_canvases = adsk.core.BoolValueCommandInput.cast(
            inputs.itemById(HIDE_CANVASES_ID)
        ).value

        # Read and validate upload poll interval
        pause_time_input = inputs.itemById(PAUSE_TIME_ID)
        if pause_time_input:
            pause_time_str = adsk.core.StringValueCommandInput.cast(
                pause_time_input
            ).value
            try:
                pause_time = float(pause_time_str)
                if pause_time < 0:
                    pause_time = 0.5
            except (ValueError, TypeError):
                pause_time = 0.5
                futil.log(
                    f"Invalid upload check interval '{pause_time_str}', using default 0.5 seconds"
                )
                write_log_entry(
                    f"Invalid upload check interval '{pause_time_str}', using default 0.5 seconds"
                )
        else:
            pause_time = 0.5
            futil.log(
                "Upload check interval input not found, using default 0.5 seconds"
            )
            write_log_entry(
                "Upload check interval input not found, using default 0.5 seconds"
            )

        # Build the assembly structure and determine processing order
        root_component = design.rootComponent
        assembly_dict = {}
        traverse_assembly(root_component, assembly_dict)  # Build component hierarchy
        bottom_up_order = sort_dag_bottom_up(assembly_dict)  # Sort for dependency order

        docCount = len(bottom_up_order)
        default_temp_log_path = _default_temp_log_path()
        resume_info = _analyze_resume_state(
            default_temp_log_path, appVersionBuild, bottom_up_order
        )
        if resume_info.get("completed_successfully") and resume_info.get("log_exists"):
            try:
                with open(default_temp_log_path, "w", encoding="utf-8"):
                    pass
            except Exception as clear_error:
                futil.log(f"Failed to clear previous completed log: {clear_error}")
        resume_plan = resume_info
        resume_start_index = max(
            0, min(resume_info.get("resume_start_index", 0), docCount)
        )
        saved_doc_count = (
            max(resume_info.get("last_saved_index", 0), 0)
            if resume_info.get("should_resume")
            else 0
        )

        futil.log(f"Bottom-up order: {bottom_up_order}")
        write_log_entry(f"Bottom-up order: {bottom_up_order}")
        futil.log(resume_info.get("status_message", "A full run will start."))
        write_log_entry(resume_info.get("status_message", "A full run will start."))
        if docCount == 0:
            ui.messageBox("No components found in the assembly.")
            return
        futil.log(f"----- Starting saving {docCount} components -----")
        write_log_entry(f"----- Starting saving {docCount} components -----")

        # Set up logging if enabled
        if create_log:
            doc = app.activeDocument
            if log_path_val:  # Use custom path if provided
                file_path = log_path_val
            else:
                file_path = default_temp_log_path
            # Write initial log info at start
            try:
                log_mode = "a" if resume_info.get("should_resume") else "w"
                with open(file_path, log_mode, encoding="utf-8") as fh:
                    if log_mode == "a":
                        fh.write("\n----- Resume attempt -----\n")
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
                    fh.write(f"Fusion client version: {appVersionBuild}\n")
                    fh.write(f"Active Document Parent Project: {parent_project_name}\n")
                    fh.write(f"Active Document ID: {doc_id}\n")
                    fh.write("Command Options:\n")
                    fh.write(f"  Rebuild all: {rebuild_all}\n")
                    fh.write(f"  Create log file: {create_log}\n")
                    fh.write(f"  Open live log viewer: {open_log_view}\n")
                    fh.write(f"  Skip standard components: {skip_standard}\n")
                    fh.write(f"  Upload check interval: {pause_time} seconds\n")
                    fh.write(f"  Log file path: {file_path}\n")
                    fh.write(
                        f"  Resume requested: {resume_info.get('should_resume', False)}\n"
                    )
                    fh.write(
                        f"  Resume start index: {resume_start_index}\n"
                    )
                    fh.write("\nBottom-up order:\n")
                    fh.write("\n".join(bottom_up_order))
                    fh.write("\n\nDocument save log:\n")
            except Exception as log_e:
                futil.log(f"Failed to write initial log: {log_e}")

            if open_log_view and file_path:
                _, open_msg = open_live_log_viewer(file_path)
                futil.log(open_msg)
                write_log_entry(open_msg)

        # Initialize progress bar for document processing
        progress_bar = ui.createProgressDialog()
        progress_bar.cancelButtonText = "Cancel"
        progress_bar.isBackgroundTranslucent = False
        progress_bar.isCancelButtonShown = True
        progress_bar.maximumValue = docCount
        progress_bar.minimumValue = 0
        progress_bar.progressValue = resume_start_index
        progress_bar.show(
            "Bottom-up Update Progress",
            "Resuming from checkpoint..."
            if resume_info.get("should_resume")
            else "Preparing to update components...",
            resume_start_index,
            docCount,
            1,
        )

        # Counter for progress tracking
        processed_count = resume_start_index

        # Process each component in bottom-up dependency order
        for component_name in bottom_up_order[resume_start_index:]:
            if component_name == "RootComponent":  # Skip the root assembly itself
                processed_count += 1
                progress_bar.progressValue = processed_count
                progress_bar.message = (
                    f"Skipping root component ({processed_count} of {docCount})"
                )
                continue
            component = design.allComponents.itemByName(component_name)
            if not component:  # Component not found, skip it
                processed_count += 1
                progress_bar.progressValue = processed_count
                progress_bar.message = f"Component not found: {component_name} ({processed_count} of {docCount})"
                continue
            # Get the design data file for this component
            design_data_file = getattr(
                component.parentDesign.parentDocument, "designDataFile", None
            )
            if design_data_file is None:
                log_entry = f"Skipping Component (no designDataFile): {component_name}"
                futil.log(log_entry)
                write_log_entry(log_entry)
                processed_count += 1
                progress_bar.progressValue = processed_count
                progress_bar.message = f"Skipping {component_name} (no design file) ({processed_count} of {docCount})"
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
                log_entry = f"Skipping standard component: {component_name}"
                futil.log(log_entry)
                write_log_entry(log_entry)
                processed_count += 1
                progress_bar.progressValue = processed_count
                progress_bar.message = f"Skipping standard component: {component_name} ({processed_count} of {docCount})"
                continue

            # Skip already saved components if option is enabled
            target_doc_version = None
            try:
                target_doc_version = component.parentDesign.parentDocument.version
            except Exception:
                target_doc_version = None

            if skip_saved and target_doc_version == appVersionBuild:
                log_entry = f"Skipping already saved component: {component_name}"
                futil.log(log_entry)
                write_log_entry(log_entry)
                processed_count += 1
                progress_bar.progressValue = processed_count
                progress_bar.message = f"Skipping already saved: {component_name} ({processed_count} of {docCount})"
                continue

            # Skip if we've already processed this document ID
            if docid in saved:
                processed_count += 1
                progress_bar.progressValue = processed_count
                progress_bar.message = f"Skipping already processed: {component_name} ({processed_count} of {docCount})"
                continue
            saved.add(docid)  # Mark this document as processed

            # Update progress bar before opening document
            processed_count += 1
            progress_bar.progressValue = processed_count
            progress_bar.message = (
                f"Updating component {processed_count} of {docCount}: {component_name}"
            )

            # Open the component's document for editing
            try:
                document = app.data.findFileById(docid)
                if not document:
                    error_msg = (
                        f"Could not find document for component: {component_name}"
                    )
                    futil.log(error_msg)
                    write_log_entry(error_msg)
                    progress_bar.message = f"Failed to find document: {component_name} ({processed_count} of {docCount})"
                    continue

                app.documents.open(document, True)
                # Log the document open event
                futil.log(f"Opened component: {component_name}")
                write_log_entry(f"Opened component: {component_name}")
            except Exception as open_error:
                error_msg = (
                    f"Failed to open document for {component_name}: {str(open_error)}"
                )
                futil.log(error_msg)
                write_log_entry(error_msg)
                progress_bar.message = f"Failed to open document: {component_name} ({processed_count} of {docCount})"
                continue  # Skip this component and move to the next one
            # Update all references in the newly opened document
            opened_doc = app.activeDocument
            try:
                opened_doc.updateAllReferences()
                futil.log(f"Updated references for component: {component_name}")
                write_log_entry(f"Updated references for component: {component_name}")
            except RuntimeError as ref_error:
                error_msg = f"Failed to update references for {component_name}: {str(ref_error)}"
                futil.log(error_msg)
                write_log_entry(error_msg)
                # Continue processing despite reference update failure

            # Ensure we're in the correct workspace for operations
            workspace = ui.workspaces.itemById("FusionSolidEnvironment")
            if workspace and not workspace.isActive:
                workspace.activate()
            des = adsk.fusion.Design.cast(app.activeProduct)

            # Hide origins if option is enabled
            if hide_origins:
                hide_log = hide_origins_in_document(opened_doc)
                futil.log(f"   Hide origins for {component_name}: {hide_log}")
                write_log_entry(f"   Hide origins for {component_name}: {hide_log}")

            # Hide joints if option is enabled
            if hide_joints:
                hide_joint_log = hide_joints_in_document(opened_doc)
                futil.log(f"   Hide joints for {component_name}: {hide_joint_log}")
                write_log_entry(
                    f"   Hide joints for {component_name}: {hide_joint_log}"
                )

            # Hide joint origins if option is enabled
            if hide_joint_origins:
                hide_joint_log = hide_joint_origins_in_document(opened_doc)
                futil.log(
                    f"   Hide joint origins for {component_name}: {hide_joint_log}"
                )
                write_log_entry(
                    f"   Hide joint origins for {component_name}: {hide_joint_log}"
                )

            # Hide sketches if option is enabled
            if hide_sketches:
                hide_sketch_log = hide_sketches_in_document(opened_doc)
                futil.log(f"   Hide sketches for {component_name}: {hide_sketch_log}")
                write_log_entry(
                    f"   Hide sketches for {component_name}: {hide_sketch_log}"
                )

            # Hide canvases if option is enabled
            if hide_canvases:
                hide_canvas_log = hide_canvases_in_document(opened_doc)
                futil.log(f"   Hide canvases for {component_name}: {hide_canvas_log}")
                write_log_entry(
                    f"   Hide canvases for {component_name}: {hide_canvas_log}"
                )

            # Apply design intent if option is enabled
            apply_intent = adsk.core.BoolValueCommandInput.cast(
                inputs.itemById(APPLY_INTENT_ID)
            ).value

            if apply_intent and des:
                # Determine the appropriate design intent type
                # PartDesignIntentType = 0, AssemblyDesignIntentType = 1, HybridDesignIntentType = 2
                if des.rootComponent.occurrences.count == 0:
                    # No children = part
                    intent_type = adsk.fusion.DesignIntentTypes.PartDesignIntentType
                    intent_label = "part"
                    futil.log(
                        f"   Applying part intent to {component_name} (no children)"
                    )
                    write_log_entry(
                        f"   Applying part intent to {component_name} (no children)"
                    )
                else:
                    child_count = des.rootComponent.occurrences.count
                    sketch_count = des.rootComponent.sketches.count
                    body_count = des.rootComponent.bRepBodies.count

                    if sketch_count > 0 or body_count > 0:
                        # Has children AND has sketches or bodies = hybrid assembly
                        intent_type = adsk.fusion.DesignIntentTypes.HybridDesignIntentType
                        intent_label = "hybrid assembly"
                        futil.log(
                            f"   Applying hybrid assembly intent to {component_name} ({child_count} children, {sketch_count} sketches, {body_count} bodies)"
                        )
                        write_log_entry(
                            f"   Applying hybrid assembly intent to {component_name} ({child_count} children, {sketch_count} sketches, {body_count} bodies)"
                        )
                    else:
                        # Has children but no sketches or bodies = regular assembly
                        intent_type = adsk.fusion.DesignIntentTypes.AssemblyDesignIntentType
                        intent_label = "assembly"
                        futil.log(
                            f"   Applying assembly intent to {component_name} ({child_count} children, no sketches/bodies)"
                        )
                        write_log_entry(
                            f"   Applying assembly intent to {component_name} ({child_count} children, no sketches/bodies)"
                        )

                try:
                    des.designIntent = intent_type
                    futil.log(f"   {intent_label.capitalize()} intent applied to {component_name}")
                    write_log_entry(f"   {intent_label.capitalize()} intent applied to {component_name}")
                except Exception as intent_error:
                    futil.log(
                        f"   Failed to apply {intent_label} intent to {component_name}: {intent_error}"
                    )
                    write_log_entry(
                        f"   Failed to apply {intent_label} intent to {component_name}: {intent_error}"
                    )

            # Rebuild the component if rebuild option is enabled
            if rebuild_all:
                futil.log(f"   Rebuilding component: {component_name}")
                write_log_entry(f"   Rebuilding component: {component_name}")
                while not des.computeAll():  # Force compute until complete
                    adsk.doEvents()
                    time.sleep(0.1)  # Optional: Add a small delay to observe the update
                futil.log(f"   Rebuild complete: {component_name}")
                write_log_entry(f"   Rebuilt {component_name}")

            # Add and remove a temporary attribute to trigger change detection
            des.attributes.add("FusionRA", "FusionRA", component_name)
            attr = des.attributes.itemByName("FusionRA", "FusionRA")
            attr.deleteMe()

            # Save the document with timestamp
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            active_doc = app.activeDocument
            pre_save_version = None
            try:
                if active_doc.dataFile and hasattr(active_doc.dataFile, "versionNumber"):
                    pre_save_version = active_doc.dataFile.versionNumber
            except Exception:
                pre_save_version = None

            data_file_future = active_doc.save(
                f"Auto save in Fusion: {appVersionBuild}, by rebuild assembly."
            )

            save_ok, save_msg = wait_for_data_file_future(
                data_file_future,
                component_name,
                pause_time,
                document=active_doc,
                pre_save_version=pre_save_version,
            )
            futil.log(f"   {save_msg}")
            write_log_entry(f"   {save_msg}")
            if not save_ok:
                try:
                    if not is_top_document(active_doc):
                        active_doc.close(False)
                except Exception:
                    pass
                continue

            if not is_top_document(active_doc):
                active_doc.close(False)  # Already saved, avoid triggering another save cycle
            log_entry = f"   {component_name} saved - [{timestamp}]"
            futil.log(log_entry)
            write_log_entry(log_entry)
            saved_doc_count += 1  # Increment counter for completed saves

            checkpoint_entry = (
                f"CHECKPOINT|SAVE_UPLOAD_COMPLETE|component={component_name}|"
                f"saved_index={saved_doc_count}|total={docCount}|timestamp={timestamp}"
            )
            futil.log(checkpoint_entry)
            write_log_entry(checkpoint_entry)

            # Add progress separator
            progress_msg = (
                f"----- Completed {saved_doc_count} of {docCount} components -----"
            )
            futil.log(progress_msg)
            write_log_entry(progress_msg)

            des = None  # Clear design reference

        futil.log(f"----- Components saved -----")
        write_log_entry(f"----- Components saved -----")

        # Update progress bar for final steps
        progress_bar.message = "Getting latest versions of all components..."

        # Execute Fusion commands to get latest versions and update references
        futil.log("Executing GetAllLatestCmd...")
        write_log_entry("Executing GetAllLatestCmd...")
        cmdDefs = ui.commandDefinitions
        cmdGet = cmdDefs.itemById("GetAllLatestCmd")  # Get all latest command
        get_all_ok, get_all_msg = execute_command_with_timeout(
            cmdGet, "GetAllLatestCmd", poll_interval_seconds=0.1, timeout_seconds=120
        )
        futil.log(get_all_msg)
        write_log_entry(get_all_msg)
        if not get_all_ok:
            raise RuntimeError(get_all_msg)

        futil.log("Executing ContextUpdateAllFromParentCmd...")
        write_log_entry("Executing ContextUpdateAllFromParentCmd...")
        progress_bar.message = "Updating all references from parent..."
        cmdUpdate = cmdDefs.itemById(
            "ContextUpdateAllFromParentCmd"
        )  # Update all from parent
        update_ok, update_msg = execute_command_with_timeout(
            cmdUpdate,
            "ContextUpdateAllFromParentCmd",
            poll_interval_seconds=0.1,
            timeout_seconds=120,
        )
        futil.log(update_msg)
        write_log_entry(update_msg)
        if not update_ok:
            raise RuntimeError(update_msg)

        # Save the active document after updating references
        progress_bar.message = "Saving main assembly document..."
        futil.log("Saving active document after updating references...")
        write_log_entry("Saving active document after updating references...")
        main_doc = app.activeDocument
        main_pre_save_version = None
        try:
            if main_doc.dataFile and hasattr(main_doc.dataFile, "versionNumber"):
                main_pre_save_version = main_doc.dataFile.versionNumber
        except Exception:
            main_pre_save_version = None

        final_save_future = main_doc.save(
            f"Auto save in Fusion: {appVersionBuild}, by rebuild assembly."
        )
        final_save_ok, final_save_msg = wait_for_data_file_future(
            final_save_future,
            "main assembly",
            pause_time,
            document=main_doc,
            pre_save_version=main_pre_save_version,
        )
        futil.log(final_save_msg)
        write_log_entry(final_save_msg)
        if not final_save_ok:
            raise RuntimeError(final_save_msg)

        final_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        final_checkpoint_entry = (
            "CHECKPOINT|SAVE_UPLOAD_COMPLETE|component=main assembly|"
            f"saved_index={saved_doc_count}|total={docCount}|timestamp={final_timestamp}"
        )
        futil.log(final_checkpoint_entry)
        write_log_entry(final_checkpoint_entry)

        # Hide the progress bar
        progress_bar.hide()

        # Prepare completion message and finalize logging
        completion_msg = "Bottom-up Update complete."
        end_total_time = time.time()
        total_elapsed = (
            end_total_time - start_total_time
        )  # Calculate total execution time

        # Log final statistics to both logging systems
        futil.log(f"Total documents saved: {saved_doc_count}")
        futil.log(f"Total command run time: {total_elapsed:.2f} seconds")
        write_log_entry(f"Total documents saved: {saved_doc_count}")
        write_log_entry(f"Total command run time: {total_elapsed:.2f} seconds")

        if create_log and file_path:
            try:
                futil.log(f"Log written to: {file_path}")
                completion_msg += f"\nLog written to: {file_path}"
            except Exception as log_e:
                futil.log(f"Failed to write log: {log_e}")
                completion_msg += f"\nFailed to write log to: {file_path}\n{log_e}"

        # Clear global variables for next run
        saved.clear()  # Clear the set of processed document IDs
        resume_plan = {}
        product = None
        design = None
        title = None
        futil.log("Cleared global variables for next execution")
        write_log_entry("Cleared global variables for next execution")

        futil.log("Bottom-up Update completed successfully")
        write_log_entry("Bottom-up Update completed successfully")
        ui.messageBox(completion_msg)  # Show completion message to user
    except Exception as e:
        # Hide progress bar if it exists
        try:
            if progress_bar:
                progress_bar.hide()
        except:
            pass  # Ignore any errors hiding the progress bar

        # Clear global variables even on failure to ensure clean state for next run
        saved.clear()
        resume_plan = {}
        product = None
        design = None
        title = None
        futil.log("Cleared global variables after error")
        write_log_entry("Cleared global variables after error")
        if ui:
            ui.messageBox(f"Failed:\n{traceback.format_exc()}")


# This function will be called when the user completes the command.
def command_destroy(args: adsk.core.CommandEventArgs):
    global local_handlers, saved, product, design, title, resume_plan
    local_handlers = []
    saved.clear()  # Clear the set of processed document IDs
    resume_plan = {}
    product = None
    design = None
    title = None
    futil.log(f"{CMD_NAME} Command Destroy Event - cleared global variables")


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


def _default_log_directory() -> str:
    """Return the default directory for log files based on the current OS."""
    if sys.platform in ("darwin", "win32"):
        return tempfile.gettempdir()
    return os.path.expanduser("~/Documents")


def _default_temp_log_path() -> str:
    """Return the default log path used for auto logging in this command."""
    app = adsk.core.Application.get()
    doc = app.activeDocument
    base_name = "assembly_log"
    if doc and doc.dataFile:
        base_name = doc.dataFile.name
    elif doc and doc.name:
        base_name = doc.name
    base_name = re.sub(r"[\\/:*?\"<>|]+", "_", base_name)
    if not base_name.lower().endswith(".log"):
        base_name += ".log"
    return os.path.join(_default_log_directory(), base_name)


def _extract_latest_bottom_up_order(log_lines):
    """Extract the most recent Bottom-up order section from a log file."""
    marker_indexes = [
        i for i, line in enumerate(log_lines) if line.strip() == "Bottom-up order:"
    ]
    if not marker_indexes:
        return []

    start_idx = marker_indexes[-1] + 1
    order = []
    for line in log_lines[start_idx:]:
        value = line.strip()
        if not value or value == "Document save log:":
            break
        order.append(value)
    return order


def _extract_last_component_checkpoint(log_lines):
    """Return the last component checkpoint tuple (component_name, saved_index)."""
    last_component = None
    last_saved_index = 0

    for line in log_lines:
        line = line.strip()
        if not line.startswith("CHECKPOINT|SAVE_UPLOAD_COMPLETE|"):
            continue
        parts = line.split("|")
        fields = {}
        for part in parts[2:]:
            if "=" not in part:
                continue
            k, v = part.split("=", 1)
            fields[k] = v

        component = fields.get("component")
        if not component or component == "main assembly":
            continue

        try:
            saved_index = int(fields.get("saved_index", "0"))
        except ValueError:
            saved_index = 0

        last_component = component
        last_saved_index = saved_index

    return last_component, last_saved_index


def _analyze_resume_state(log_path, fusion_client_version, current_bottom_up_order):
    """Inspect an existing log and return whether this run should resume."""
    result = {
        "log_exists": False,
        "matches_version": False,
        "completed_successfully": False,
        "dag_matches": False,
        "should_resume": False,
        "resume_component": None,
        "resume_start_index": 0,
        "last_saved_index": 0,
        "clear_log": False,
        "status_message": "No previous log found. A full run will start.",
    }

    if not log_path or not os.path.exists(log_path):
        return result

    result["log_exists"] = True
    try:
        with open(log_path, "r", encoding="utf-8") as fh:
            log_lines = fh.read().splitlines()
    except Exception as read_error:
        result["status_message"] = (
            f"Found previous log but could not read it ({read_error}). A full run will start."
        )
        return result

    version_line = next(
        (line for line in log_lines if line.startswith("Fusion client version:")), None
    )
    logged_version = ""
    if version_line:
        logged_version = version_line.split(":", 1)[1].strip()

    if logged_version == fusion_client_version:
        result["matches_version"] = True
    else:
        result["status_message"] = (
            "Previous temp log is from a different Fusion client version. "
            "A full run will start."
        )
        return result

    logged_order = _extract_latest_bottom_up_order(log_lines)
    result["dag_matches"] = logged_order == current_bottom_up_order
    result["completed_successfully"] = any(
        "Bottom-up Update completed successfully" in line for line in log_lines
    )

    if result["completed_successfully"]:
        result["clear_log"] = True
        result["status_message"] = (
            "Previous run completed successfully. Log will be reset for a new run."
        )
        return result

    if not result["dag_matches"]:
        result["status_message"] = (
            "Previous run did not complete, but the component save list has changed. "
            "A full run will start."
        )
        return result

    last_component, last_saved_index = _extract_last_component_checkpoint(log_lines)
    if last_component and last_component in current_bottom_up_order:
        next_index = current_bottom_up_order.index(last_component) + 1
        result["resume_component"] = last_component
        result["resume_start_index"] = min(next_index, len(current_bottom_up_order))
        result["last_saved_index"] = max(last_saved_index, 0)
        result["should_resume"] = True
        result["status_message"] = (
            f"Resume available. Next component after '{last_component}' will be processed."
        )
        return result

    result["status_message"] = (
        "Previous run did not complete and save list matches. "
        "No completed checkpoint was found, so processing will restart from the beginning."
    )
    return result


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
            open_view = adsk.core.BoolValueCommandInput.cast(
                inputs.itemById(LOG_OPEN_VIEW_ID)
            )
            # Enable/disable log path controls based on logging checkbox
            path_input.isEnabled = enabled
            browse_btn.isEnabled = enabled
            open_view.isEnabled = enabled

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
            dlg.initialDirectory = _default_log_directory()
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
