# Global Parameters

[Back to PowerTools Assembly](../README.md)

The Global Parameters command creates and manages a shared parameter set for the active Autodesk Fusion project. Parameters are stored in a dedicated Fusion document inside the `_Global Parameters` folder at the project root, making them available to any document in the project via the **Link Global Parameters** command.

## What you can do

- Create a new named parameter set for the active project.
- Edit an existing parameter set — add, modify, or remove parameters.
- Define parameters with a name, numeric value, unit (in, ft, mm, cm, m), and optional comment.
- Mark parameters as Fusion favorites so they appear in the Favorites panel of any consuming document.
- Restore unsaved changes from a previous session if the dialog was cancelled before saving.
- Use warm-start discovery caches to reduce project folder scanning and startup latency.

## Prerequisites

- An Autodesk Fusion 3D Design must be active.
- The active document must be saved to an Autodesk Hub project.

## How to use Global Parameters

### Create a new parameter set

1. Open the Autodesk Fusion Design workspace.
2. On the **Power Tools** panel, select **Global Parameters**.
3. The **Parameter Set** dropdown defaults to **Create New**. Leave it set to **Create New**.
4. In the **Name** field, enter a descriptive name for the parameter set (for example, `Enclosure Constants`).
5. Use the table to define your parameters:

   | Column | Description |
  | --- | --- |
   | (checkbox) | Select a row to enable the **Delete** toolbar button |
   | Name | Parameter name — must start with a letter; letters, digits, `_`, `"`, `$`, `°`, `µ` are allowed |
   | Value | Numeric value |
   | Unit | Unit from the dropdown (in, ft, mm, cm, m) |
   | Comment | Optional free-text description |

6. Use the **Add** toolbar button to insert additional parameter rows.
7. Use the **Delete** toolbar button to remove selected rows.
8. Select **OK** to save.

The command creates a new Fusion design document with the parameter set name in the `_Global Parameters` folder of the active project, and also writes the parameters directly into the active document.

### Edit an existing parameter set

1. Open the Autodesk Fusion Design workspace.
2. On the **Power Tools** panel, select **Global Parameters**.
3. In the **Parameter Set** dropdown, select the name of the parameter set you want to edit.
4. The table populates with the existing parameters.
5. Make your changes and select **OK** to save.

> **Note:** Once you select an existing parameter set, the dropdown locks for that session to prevent accidental mode switching after data has been loaded.

### Restore unsaved changes

If you cancelled the dialog in a previous session before saving, the command detects the saved state and offers to restore it. Select **Yes** in the prompt to reload the previous table contents.

## Access

The **Global Parameters** command is on the **Power Tools** panel in the **Tools** tab of the Autodesk Fusion Design workspace.

## Parameter name rules

| Rule | Detail |
| --- | --- |
| Must start with a letter | Digits and symbols are not allowed as the first character |
| Allowed characters | Letters, digits, `_`, `"`, `$`, `°`, `µ` |
| Case-sensitive | `Width` and `width` are treated as different parameters |
| Reserved names | Fusion unit names (`mm`, `in`, `ft`, `deg`, `rad`, `kg`, `s`, `pi`, etc.) are not allowed as parameter names |
| Duplicate names | Each parameter name must be unique within the set |

## Architecture

The following diagrams show how the Global Parameters command interacts with Autodesk Fusion and the project data model.

```mermaid
C4Context
  title Global Parameters – System Context

  Person(user, "Design Engineer", "Autodesk Fusion user defining shared project parameters")
  System(addin, "PowerTools Assembly", "Autodesk Fusion add-in")
  System_Ext(fusion, "Autodesk Fusion", "Host application and Python API (adsk.core / adsk.fusion)")
  System_Ext(hub, "Autodesk Hub", "Cloud project storage — hosts the _Global Parameters folder and parameter set documents")
  System_Ext(cache, "Local Cache", "add-in/cache/ folder — stores document URN, parameter snapshots, and pending (unsaved) session state")

  Rel(user, addin, "Opens Global Parameters dialog; defines or edits parameters")
  Rel(addin, fusion, "Reads active document and project; creates/updates parameter documents; writes user parameters")
  Rel(fusion, hub, "Saves parameter set document to _Global Parameters folder")
  Rel(addin, cache, "Writes document URN cache, parameter JSON snapshot, and pending-state JSON on cancel")
```

```mermaid
C4Component
  title Global Parameters – Component View

  Person(user, "Design Engineer")

  Component(cmd, "globalParameters/entry.py", "PowerTools Command", "Registers the toolbar button; builds and manages the command dialog lifecycle")
  Component(cache_mgr, "Cache helpers", "Internal Module", "_write_document_cache / _write_pending_cache / _read_pending_cache / _clear_pending_cache — persist dialog state to local JSON files")
  Component(param_doc, "Parameter document helpers", "Internal Module", "_create_parameters_document / _update_parameters_document — create or update a Fusion design doc holding the parameter set")
  Component(active_writer, "_write_params_to_active", "Internal Module", "Writes the parameter set directly into the active document's user parameters after creation")
  Component(table_ui, "Table UI helpers", "Internal Module", "_add_header_row / _add_data_row / _add_data_row_with_values / _collect_rows / _any_row_checked — manage the editable parameters table in the dialog")
  Component(validator, "_validate_and_reason", "Internal Module", "Validates parameter names (regex + reserved word list) and checks for duplicates; drives the OK button state")

  Component(api_design, "adsk.fusion.Design", "Fusion API", "userParameters collection — create, update, delete parameters; isFavorite flag")
  Component(api_data, "adsk.core.Data / DataFolder", "Fusion API", "Browses project root folder; creates _Global Parameters sub-folder; looks up existing parameter set documents")
  Component(api_docs, "adsk.core.Documents", "Fusion API", "open() and saveAs() for the parameter set document")

  Rel(user, cmd, "Interacts with dialog")
  Rel(cmd, cache_mgr, "Reads/writes pending and document-URN caches on open/cancel/execute")
  Rel(cmd, param_doc, "Calls on execute to persist parameter set to Hub")
  Rel(cmd, active_writer, "Calls on execute (Create New path) to mirror parameters into active doc")
  Rel(cmd, table_ui, "Builds table rows; collects edited values on execute")
  Rel(cmd, validator, "Called by validateInputs event and on each inputChanged event")
  Rel(param_doc, api_design, "Adds/replaces userParameters in the parameter set document")
  Rel(param_doc, api_data, "Navigates project folder tree to find or create _Global Parameters folder")
  Rel(param_doc, api_docs, "Opens and saves the parameter set Fusion document")
  Rel(active_writer, api_design, "Adds or updates userParameters in the already-open active document")
```

## Caching and Discovery Logic

Global Parameters uses layered cache reads before any Hub scan:

1. `gp_folder_<project-key>.json`: project-scoped folder id cache for `_Global Parameters`.
2. `gp_docs_<project-key>.json`: project-scoped parameter set list used to pre-populate the Parameter Set dropdown.
3. `<active-doc-id>_pending.json`: cancel-time unsaved session restore payload.
4. `<active-doc-id>_parameters.json`: last collected table rows snapshot.

When cache-based resolution fails, the command falls back to Hub scans and then refreshes cache files. On **Create New**, the command also upserts the new parameter-set `{name,id}` into `gp_docs_<project-key>.json` immediately so Link Global Parameters can discover it without waiting for a full rescan.

```mermaid
C4Component
  title Global Parameters – Cache Components

  Component(cmd, "Global Parameters command", "commands/globalParameters/entry.py", "Dialog lifecycle + parameter persistence")
  Component(folder_cache, "Folder cache", "gp_folder_<project-key>.json", "Caches _Global Parameters folder id")
  Component(docs_cache, "Docs cache", "gp_docs_<project-key>.json", "Caches parameter-set names and ids")
  Component(doc_cache, "Document cache", "<doc-id>.json", "Caches active document identity metadata")
  Component(param_cache, "Parameter snapshot cache", "<doc-id>_parameters.json", "Caches collected parameter rows")
  Component(pending_cache, "Pending session cache", "<doc-id>_pending.json", "Caches unsaved dialog state for restore")
  Component(hub_scan, "Hub discovery fallback", "adsk.core.DataFolder / DataFiles", "Scans root folders and parameter-set files when cache misses")
  Component(docs_upsert, "Docs cache upsert", "_upsert_param_docs_cache_entry", "Inserts/updates a single newly-created parameter set in gp_docs cache")

  Rel(cmd, folder_cache, "Read on open, write on successful resolve")
  Rel(cmd, docs_cache, "Read on open, write after list scan")
  Rel(cmd, docs_upsert, "Called after Create New saveAs")
  Rel(docs_upsert, docs_cache, "Write single-entry update")
  Rel(cmd, doc_cache, "Write on command_created")
  Rel(cmd, param_cache, "Write on execute")
  Rel(cmd, pending_cache, "Read on open, write on cancel, clear on execute")
  Rel(cmd, hub_scan, "Fallback when cache miss/stale")
```

```mermaid
sequenceDiagram
  autonumber
  actor User
  participant Cmd as Global Parameters
  participant Cache as Local Cache
  participant Hub as Fusion Hub API

  User->>Cmd: Open command
  Cmd->>Cache: Read gp_docs and pending cache
  alt Docs cache hit
    Cache-->>Cmd: Parameter set names
    Cmd->>Cmd: Build dropdown without Hub scan
  else Docs cache miss
    Cmd->>Hub: List docs in _Global Parameters
    Hub-->>Cmd: DataFile map
    Cmd->>Cache: Write gp_docs
  end

  User->>Cmd: Save (Create New or Edit Existing)
  alt Create New
    Cmd->>Cache: Read/resolve gp_folder
    alt Folder cache miss
      Cmd->>Hub: Scan root folders for _Global Parameters
      Hub-->>Cmd: Folder
      Cmd->>Cache: Write gp_folder
    end
    Cmd->>Hub: SaveAs new parameter-set document
    Cmd->>Cache: Upsert {name,id} into gp_docs
  else Edit Existing
    Cmd->>Hub: Open existing parameter-set document
    Cmd->>Hub: Overwrite userParameters + save
  end
  Cmd->>Cache: Clear pending cache
```

```mermaid
sequenceDiagram
  actor User
  participant Dialog as Global Parameters Dialog
  participant Cache as Local Cache
  participant Hub as Autodesk Hub

  User->>Dialog: Open Global Parameters
  Dialog->>Cache: Check for pending (unsaved) session state
  alt Pending cache found
    Dialog->>User: Offer to restore unsaved changes
    User->>Dialog: Confirm restore
    Dialog->>Dialog: Reload table from pending cache
  end
  User->>Dialog: Fill / edit parameter table
  User->>Dialog: Click OK
  alt Create New
    Dialog->>Hub: Create new Fusion doc in _Global Parameters folder
    Dialog->>Dialog: Write parameters into active document
    Dialog->>Cache: Clear pending cache
  else Edit Existing
    Dialog->>Hub: Open and overwrite existing parameter set doc
    Dialog->>Cache: Clear pending cache
  end
  alt User cancels instead
    Dialog->>Cache: Write pending cache with current table state
  end
```
