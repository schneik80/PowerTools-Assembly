#  Refactored command initialization using the new registry system
#  Code reduced from 33 lines to ~20 lines with better maintainability

from ..lib import fusionAddInUtils as futil

# Import refactored command classes
from .assemblystats.entry import create_command as create_assembly_stats
from .getandupdate.entry import create_command as create_get_and_update
from .bottomupupdate.entry import create_command as create_bottom_up_update
from .insertSTEP.entry import create_command as create_insert_step
from .refrences.entry import create_command as create_document_references

# Import remaining commands (legacy until refactored)
from .refmanager.entry import start as refmanager_start, stop as refmanager_stop
from .refresh.entry import start as refresh_start, stop as refresh_stop


def start():
    """Start all commands using the new registry system"""
    try:
        # Register refactored commands
        futil.command_registry.register_command_instance(create_assembly_stats())
        futil.command_registry.register_command_instance(create_get_and_update())
        futil.command_registry.register_command_instance(create_bottom_up_update())
        futil.command_registry.register_command_instance(create_insert_step())
        futil.command_registry.register_command_instance(create_document_references())

        # Start all registered commands
        futil.command_registry.start_all()

        # Start legacy commands (temporary until refactored)
        refmanager_start()
        refresh_start()

        futil.log(
            f"Started {futil.command_registry.get_command_count()} commands successfully"
        )

    except Exception as e:
        futil.handle_error(f"Failed to start commands: {str(e)}")


def stop():
    """Stop all commands using the new registry system"""
    try:
        # Stop all registered commands
        futil.command_registry.stop_all()

        # Stop legacy commands (temporary until refactored)
        refmanager_stop()
        refresh_stop()

        futil.log("Stopped all commands successfully")

    except Exception as e:
        futil.handle_error(f"Failed to stop commands: {str(e)}")


# Utility functions for development and debugging
def list_commands():
    """List all registered commands"""
    return futil.command_registry.list_commands()


def get_command_stats():
    """Get command registration statistics"""
    return {
        "total_commands": futil.command_registry.get_command_count(),
        "registered_commands": futil.command_registry.list_commands(),
    }
