from .assemblystats import entry as assemblystats
from .getandupdate import entry as getandupdate
from .insertSTEP import entry as insertSTEP
from .refmanager import entry as refmanager
from .refrences import entry as refrences
from .refresh import entry as refresh

# Fusion will automatically call the start() and stop() functions.
commands = [assemblystats, getandupdate, insertSTEP, refmanager, refrences, refresh]


# Assumes you defined a "start" function in each of your modules.
# The start function will be run when the add-in is started.
def start():
    for command in commands:
        command.start()


# Assumes you defined a "stop" function in each of your modules.
# The stop function will be run when the add-in is stopped.
def stop():
    for command in commands:
        command.stop()
