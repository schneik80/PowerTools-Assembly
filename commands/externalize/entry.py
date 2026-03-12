import adsk.core
import adsk.fusion
import os
import traceback
from ...lib import fusionAddInUtils as futil
from ... import config

app = adsk.core.Application.get()
ui = app.userInterface

CMD_NAME = "Externalize"
CMD_ID = "PTAT-externalize"
CMD_Description = (
    "Save a component as an external cloud document and re-insert it at its "
    "original assembly position."
)
IS_PROMOTED = False

# Global variables by referencing values from /config.py
WORKSPACE_ID = config.design_workspace
TAB_ID = config.tools_tab_id
TAB_NAME = config.my_tab_name

PANEL_ID = config.my_panel_id
PANEL_NAME = config.my_panel_name
PANEL_AFTER = config.my_panel_after

# Resource location for command icons
ICON_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "resources", "")

# Holds references to event handlers
local_handlers = []


# Executed when add-in is run.
def start():
    # ******************************** Create Command Definition ********************************
    cmd_def = ui.commandDefinitions.addButtonDefinition(
        CMD_ID, CMD_NAME, CMD_Description, ICON_FOLDER
    )

    # Add command created handler.
    futil.add_handler(cmd_def.commandCreated, command_created)

    # ******************************** Create Command Control ********************************
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


# Called when the user clicks the button.
def command_created(args: adsk.core.CommandCreatedEventArgs):
    futil.log(f"{CMD_NAME} Command Created Event")

    cmd = args.command
    cmd.isExecutedWhenPreEmpted = False
    inputs = cmd.commandInputs

    # Selection input: pick the occurrence to externalize
    sel_input = inputs.addSelectionInput(
        "occurrence_sel",
        "Component",
        "Select the component occurrence to externalize",
    )
    sel_input.addSelectionFilter("Occurrences")
    sel_input.setSelectionLimits(1, 1)

    # Checkbox: externalize every local first-level component in the assembly
    ext_all = inputs.addBoolValueInput("externalize_all", "Externalize All", True)
    ext_all.tooltip = (
        "When checked, every local first-level component in the active assembly "
        "is externalized automatically. The component selector is disabled."
    )

    futil.add_handler(
        cmd.inputChanged, command_input_changed, local_handlers=local_handlers
    )
    futil.add_handler(cmd.execute, command_execute, local_handlers=local_handlers)
    futil.add_handler(cmd.destroy, command_destroy, local_handlers=local_handlers)


# Called whenever any input value changes in the dialog.
def command_input_changed(args: adsk.core.InputChangedEventArgs):
    futil.log(f"{CMD_NAME} Input Changed Event")

    changed_input = args.input
    if changed_input.id == "externalize_all":
        bool_input = adsk.core.BoolValueCommandInput.cast(changed_input)
        sel_input = adsk.core.SelectionCommandInput.cast(
            args.inputs.itemById("occurrence_sel")
        )
        if bool_input.value:
            # Hide the selector and make it optional (min=0) so the OK button
            # becomes active without requiring a selection.
            sel_input.isVisible = False
            sel_input.isEnabled = False
            sel_input.setSelectionLimits(0, 1)
        else:
            sel_input.isVisible = True
            sel_input.isEnabled = True
            sel_input.setSelectionLimits(1, 1)


# Called when the user clicks OK in the command dialog.
def command_execute(args: adsk.core.CommandEventArgs):
    futil.log(f"{CMD_NAME} Command Execute Event")

    try:
        design = adsk.fusion.Design.cast(app.activeProduct)
        if not design:
            ui.messageBox("A Fusion 3D Design must be active.", CMD_NAME)
            return

        inputs = args.command.commandInputs
        externalize_all: bool = adsk.core.BoolValueCommandInput.cast(
            inputs.itemById("externalize_all")
        ).value

        # --- Resolve the cloud folder from the active document ---
        active_data_file = app.activeDocument.dataFile
        if active_data_file is None:
            ui.messageBox(
                "The active document has not been saved to the cloud.\n"
                "Please save the document to a Fusion Team / Hub folder first.",
                CMD_NAME,
            )
            return

        cloud_folder: adsk.core.DataFolder = active_data_file.parentFolder

        if externalize_all:
            _externalize_all(design, cloud_folder)
        else:
            sel_input = adsk.core.SelectionCommandInput.cast(
                inputs.itemById("occurrence_sel")
            )

            if sel_input.selectionCount == 0:
                ui.messageBox("No component selected.", CMD_NAME)
                return

            _externalize_single(sel_input.selection(0).entity, design, cloud_folder)

    except:  # pylint:disable=bare-except
        app.log(f"{CMD_NAME} failed:\n{traceback.format_exc()}")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _find_existing_cloud_file(cloud_folder: adsk.core.DataFolder, comp_name: str):
    """Return the DataFile whose name matches comp_name, or None."""
    data_files = cloud_folder.dataFiles
    for i in range(data_files.count):
        item = data_files.item(i)
        if item.name == comp_name:
            return item
    return None


def _save_to_cloud(
    component: adsk.fusion.Component,
    comp_name: str,
    cloud_folder: adsk.core.DataFolder,
):
    """Upload component to the cloud folder and return the resulting DataFile.
    Returns None if the upload fails."""
    future = component.saveCopyAs(comp_name, cloud_folder, "", "")
    while True:
        if future.uploadState != adsk.core.UploadStates.UploadProcessing:
            break
        adsk.doEvents()

    if future.uploadState == adsk.core.UploadStates.UploadFailed:
        return None
    return future.dataFile


def _externalize_single(
    entity,
    design: adsk.fusion.Design,
    cloud_folder: adsk.core.DataFolder,
):
    """Externalize a single selected occurrence."""
    if isinstance(entity, adsk.fusion.Occurrence):
        occ = entity
    elif hasattr(entity, "assemblyContext") and entity.assemblyContext:
        occ = entity.assemblyContext
    else:
        ui.messageBox(
            "Selected entity is not a component occurrence. Please select a component.",
            CMD_NAME,
        )
        return

    comp_name = occ.component.name
    cached_transform: adsk.core.Matrix3D = occ.transform2
    root = design.rootComponent

    saved_data_file = _find_existing_cloud_file(cloud_folder, comp_name)
    if saved_data_file is not None:
        action = "reused existing cloud file"
    else:
        saved_data_file = _save_to_cloud(occ.component, comp_name, cloud_folder)
        if saved_data_file is None:
            ui.messageBox(f'Cloud upload of "{comp_name}" failed.', CMD_NAME)
            return
        action = f'saved to "{cloud_folder.name}"'

    occ.deleteMe()
    root.occurrences.addByInsert(saved_data_file, cached_transform, True)

    ui.messageBox(
        f'"{comp_name}" {action} and re-inserted at its original assembly position.',
        CMD_NAME,
    )


def _externalize_all(
    design: adsk.fusion.Design,
    cloud_folder: adsk.core.DataFolder,
):
    """Externalize every local first-level component in the active assembly."""
    root = design.rootComponent

    # Snapshot all local first-level occurrences before modifying anything.
    # A component is considered local when its parent design is the active design.
    pending = []
    for i in range(root.occurrences.count):
        occ = root.occurrences.item(i)
        if occ.component.parentDesign == design:
            pending.append(
                {
                    "occ": occ,
                    "component": occ.component,
                    "comp_name": occ.component.name,
                    "transform": occ.transform2,
                }
            )

    total = len(pending)
    if total == 0:
        ui.messageBox(
            "No local first-level components were found to externalize.", CMD_NAME
        )
        return

    progress_bar = ui.progressBar
    progress_bar.show("Externalizing component %v of %m…", 1, total)

    replaced = 0
    for idx, data in enumerate(pending):
        comp_name = data["comp_name"]
        progress_bar.progressValue = idx + 1
        adsk.doEvents()

        try:
            saved_data_file = _find_existing_cloud_file(cloud_folder, comp_name)
            if saved_data_file is None:
                saved_data_file = _save_to_cloud(
                    data["component"], comp_name, cloud_folder
                )
                if saved_data_file is None:
                    futil.log(
                        f'{CMD_NAME}: Cloud upload of "{comp_name}" failed — skipping.'
                    )
                    continue

            data["occ"].deleteMe()
            root.occurrences.addByInsert(saved_data_file, data["transform"], True)
            replaced += 1

        except:  # pylint:disable=bare-except
            app.log(
                f'{CMD_NAME}: Failed to externalize "{comp_name}":\n'
                f"{traceback.format_exc()}"
            )

    progress_bar.hide()

    ui.messageBox(
        f"{replaced} of {total} local components were externalized.", CMD_NAME
    )


# Called when the command is destroyed (dialog closed).
def command_destroy(args: adsk.core.CommandEventArgs):
    futil.log(f"{CMD_NAME} Command Destroy Event")

    global local_handlers
    local_handlers = []
