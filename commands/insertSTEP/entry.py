import os
import adsk.core
import adsk.fusion

from ...lib import fusionAddInUtils as futil


class InsertStepCommand(futil.FusionCommand):
    """
    Refactored Insert STEP File command.
    Code reduced from 133 lines to ~40 lines with better error handling.
    """

    def __init__(self):
        super().__init__(
            command_name="Insert STEP File",
            command_id="PTAT-insertSTEP",
            command_description="Insert a STEP file into the active Design Document",
            ui_placement=futil.UIPlacement.ASSEMBLY_TAB,  # Uses smart tab detection
            is_promoted=False,
        )

    def on_command_created(self, args: adsk.core.CommandCreatedEventArgs) -> None:
        """Handle STEP file selection and import immediately"""

        if not self.design:
            self.ui.messageBox("No active Fusion design", "No Design")
            return

        # Create and configure file dialog
        file_dialog = self.ui.createFileDialog()
        file_dialog.isMultiSelectEnabled = False
        file_dialog.title = "Select STEP File to Insert"
        file_dialog.filter = "STEP Files(*.stp;*.STP;*.step;*.STEP);;All files (*.*)"

        # Show file dialog
        if file_dialog.showOpen() != adsk.core.DialogResults.DialogOK:
            return

        # Import the selected STEP file
        self._import_step_file(file_dialog.filename)

    def _import_step_file(self, filename: str) -> None:
        """Import STEP file using Fusion text command"""
        try:
            # Format filename with quotes for text command
            quoted_filename = f'"{filename}"'
            command = f"Fusion.ImportComponent {quoted_filename}"

            # Execute import command
            self.app.executeTextCommand(command)

            # Log success
            base_filename = os.path.basename(filename)
            futil.log(f"Successfully imported STEP file: {base_filename}")

        except Exception as e:
            error_msg = f"Failed to import STEP file:\n{str(e)}"
            self.ui.messageBox(error_msg, "Import Error")
            futil.handle_error(f"STEP import failed: {str(e)}")

    def on_command_execute(self, args: adsk.core.CommandEventArgs) -> None:
        """Not used for this command - execution happens in on_command_created"""
        pass


# Factory function for command creation
def create_command():
    return InsertStepCommand()


# Legacy compatibility
def start():
    command = create_command()
    command.start()


def stop():
    pass
