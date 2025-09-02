import adsk.core

from ...lib import fusionAddInUtils as futil


class GetAndUpdateCommand(futil.SimpleCommand):
    """
    Refactored Get and Update command.
    Code reduced from 94 lines to ~15 lines with better error handling.
    """

    def __init__(self):
        def execute_get_and_update(args):
            """Execute get latest and update all contexts"""
            bulk_manager = futil.BulkOperationManager("Get and Update")

            # Execute both commands in sequence
            success = bulk_manager.execute_fusion_commands(
                ["GetAllLatestCmd", "ContextUpdateAllFromParentCmd"]
            )

            if not success:
                futil.ui.messageBox(
                    "Failed to execute get and update operations", "Error"
                )

        super().__init__(
            command_name="Get and Update",
            command_id="PTAT-getandupdate",
            command_description="Get any new versions and then update all out-of-date assembly contexts.",
            execute_function=execute_get_and_update,
            ui_placement=futil.UIPlacement.QUICK_ACCESS_TOOLBAR,
        )


# Factory function for command creation
def create_command():
    return GetAndUpdateCommand()


# Legacy compatibility
def start():
    command = create_command()
    command.start()


def stop():
    pass
