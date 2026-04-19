# Refresh Global Parameters Cache

[Back to PowerTools Assembly](../README.md)

The Refresh Global Parameters Cache command forces a full scan of the active Autodesk Hub project's `_Global Parameters` folder and rewrites the local cache files that **Global Parameters** and **Link Global Parameters** use for fast dialog startup. Use it when parameter sets appear missing, stale, or out of order in those dialogs — typically after adding, removing, or renaming parameter set documents outside the add-in.

## What you can do

- Force a complete rescan of the active project's `_Global Parameters` folder, bypassing any cached folder or document metadata.
- Rewrite `gp_folder_<project-key>.json` and `gp_docs_<project-key>.json` so the other two commands pick up the refreshed list on next open.
- Receive a summary message box reporting how many parameter sets were found in the project.

## Prerequisites

- An Autodesk Fusion document must be active and the Data Panel must resolve an active project.
- The active project must contain a `_Global Parameters` folder (created by **Global Parameters**).

## How to use Refresh Global Parameters Cache

1. Open the Autodesk Fusion Design workspace with any document from the target project active.
2. Open the **File** dropdown on the Quick Access Toolbar (QAT).
3. Expand the **PowerTools Settings** submenu.
4. Select **Refresh Global Parameters Cache**.

The command scans the project root for the `_Global Parameters` folder, enumerates every parameter set document inside it, and overwrites both cache files. A message box reports how many parameter sets were found.

> **Note:** If the project has no `_Global Parameters` folder, the command reports that no folder was found and exits without writing anything.

## Access

The **Refresh Global Parameters Cache** command is located under **File › PowerTools Settings** on the Quick Access Toolbar. The PowerTools Settings submenu is shared with other PowerTools add-ins — if it does not yet exist, the command creates it on first run.

## Architecture

```mermaid
C4Context
  title Refresh Global Parameters Cache – System Context

  Person(user, "Design Engineer", "Autodesk Fusion user resolving stale parameter set listings")
  System(addin, "PowerTools Assembly", "Autodesk Fusion add-in")
  System_Ext(fusion, "Autodesk Fusion", "Host application and Python API (adsk.core / adsk.fusion)")
  System_Ext(hub, "Autodesk Hub", "Cloud project storage — _Global Parameters folder and parameter set documents")
  System_Ext(cache, "Local Cache", "add-in/cache/ folder — stores folder id and docs caches for fast dialog startup")

  Rel(user, addin, "Runs Refresh Global Parameters Cache from File > PowerTools Settings")
  Rel(addin, fusion, "Resolves active project; scans root folders and data files")
  Rel(fusion, hub, "Reads _Global Parameters folder and every DataFile inside it")
  Rel(addin, cache, "Overwrites gp_folder and gp_docs cache files for the active project")
```

```mermaid
C4Component
  title Refresh Global Parameters Cache – Component View

  Person(user, "Design Engineer")
  Component(cmd, "refreshGlobalParametersCache/entry.py", "PowerTools Command", "Adds the button to the PowerTools Settings submenu; runs a fresh scan on click")
  Component(cache_utils, "cache_utils.py", "Internal Module", "write_global_params_folder_cache / write_param_docs_cache — canonical cache writers shared with the other two commands")
  Component(api_data, "adsk.core.Data / DataFolder", "Fusion API", "rootFolder.dataFolders and folder.dataFiles enumeration")
  Component(folder_cache, "gp_folder cache", "gp_folder_<project-key>.json", "Project-scoped folder id")
  Component(docs_cache, "gp_docs cache", "gp_docs_<project-key>.json", "Project-scoped parameter set names and ids")

  Rel(user, cmd, "Selects File > PowerTools Settings > Refresh Global Parameters Cache")
  Rel(cmd, api_data, "Locates _Global Parameters folder; enumerates parameter set documents")
  Rel(cmd, cache_utils, "Delegates cache writes so formats stay in sync")
  Rel(cache_utils, folder_cache, "Overwrite")
  Rel(cache_utils, docs_cache, "Overwrite")
```

```mermaid
sequenceDiagram
  autonumber
  actor User
  participant QAT as File › PowerTools Settings
  participant Cmd as Refresh Global Parameters Cache
  participant Hub as Fusion Hub API
  participant Cache as Local Cache

  User->>QAT: Click Refresh Global Parameters Cache
  QAT->>Cmd: command_created fires
  Cmd->>Hub: Resolve active project
  alt No active project
    Cmd->>User: Message box — no active project
  else Project resolved
    Cmd->>Hub: Scan rootFolder.dataFolders for _Global Parameters
    alt Folder missing
      Cmd->>User: Message box — folder not found
    else Folder found
      Cmd->>Hub: Enumerate DataFiles in folder
      Cmd->>Cache: Overwrite gp_folder cache
      Cmd->>Cache: Overwrite gp_docs cache
      Cmd->>User: Message box — N parameter set(s) found
    end
  end
```

---

[Back to PowerTools Assembly](../README.md)

---

*Copyright © 2026 IMA LLC. All rights reserved.*
