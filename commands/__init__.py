# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2022-2026 IMA LLC

from .assemblybuilder import entry as assemblybuilder
from .assemblystats import entry as assemblystats
from .getandupdate import entry as getandupdate
from .bottomupupdate import entry as bottomupupdate
from .externalize import entry as externalize
from .globalParameters import entry as globalParameters
from .insertSTEP import entry as insertSTEP
from .linkGlobalParameters import entry as linkGlobalParameters
from .refmanager import entry as refmanager
from .refreshGlobalParametersCache import entry as refreshGlobalParametersCache
from .refrences import entry as refrences
from .refresh import entry as refresh

# Fusion will automatically call the start() and stop() functions.
commands = [
    assemblybuilder,
    assemblystats,
    getandupdate,
    bottomupupdate,
    externalize,
    globalParameters,
    insertSTEP,
    linkGlobalParameters,
    refmanager,
    refreshGlobalParametersCache,
    refrences,
    refresh,
]


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
