# PowerTools Assembly for Autodesk Fusion 360

PowerTools Assembly is a Fusion 360 add-in that provides productivity commands for teams working with multi-component assemblies and cloud-connected design data. It adds commands to the Design workspace toolbar and Quick Access Toolbar (QAT) that reduce the steps required for common assembly management tasks.

- **Compatibility:** Autodesk Fusion 360 (Windows and macOS)
- **Add-in type:** Fusion 360 Add-In (Python)
- **Author:** IMA LLC

---

## Commands

### Manage document references

**[Document References](./docs/Document%20References.md)**

Displays a dialog listing all documents related to the active design, organized by relationship type. Shows parent assemblies (where-used), child references (uses), associated drawings, standard component references, and related data documents. Each entry includes a thumbnail preview and buttons to open the document in Fusion 360 or in the Autodesk web browser.

**[Reference Manager](./docs/Reference%20Manager.md)**

Opens the Fusion 360 Reference Manager dialog directly from the Quick Access Toolbar. Provides a single location to review all references, update them individually or all at once, select specific versions, and open referenced documents in new tabs.

**[Externalize](./docs/Externalize.md)**

Converts one or more local (inline) components in the active assembly into independent cloud documents, then re-inserts them at their original positions and orientations.

- Externalize a single selected component occurrence.
- Externalize all local first-level components in one step using **Externalize All**.
- Save to the same folder as the active document or to a new named sub-folder.
- Automatically reuse an existing cloud file if one with the same name already exists.

**[Get and Update](./docs/Get%20and%20Update.md)**

Executes **Get All Latest** followed by **Update All Contexts From Parent** in a single Quick Access Toolbar command. Eliminates the multi-click process of retrieving the latest reference versions and then manually refreshing out-of-date assembly contexts.

**[Document Refresh](./docs/Document%20Refresh.md)**

Closes the active document, retrieves the latest version from the Autodesk Hub, and reopens it automatically. Useful in team workflows where other members have published new versions and you want to load them without navigating through the File menu manually.

**[Bottom-Up Update](./docs/Bottom-Up%20Update.md)**

Traverses the assembly hierarchy, opens each referenced component document in dependency order (leaves first), updates its references, optionally rebuilds and applies design intent, and saves it. Processes the entire assembly in a single command.

Key options:
- Rebuild all components to ensure they are current.
- Apply design intent (Part, Assembly, or Hybrid) automatically based on component content.
- Hide origins, joints, sketches, joint origins, and canvases for cleaner saves.
- Skip standard library components and already-saved documents.
- Write a timestamped log file for audit and troubleshooting.

---

### Information

**[Assembly Statistics](./docs/Assembly%20Statistics.md)**

Displays a summary dialog for the active design showing component instance counts, unique component counts, out-of-date reference counts, assembly nesting depth, document context count, assembly constraints, and joint totals broken down by type.

---

### Productivity

**[Insert STEP File](./docs/Insert%20Step.md)**

Opens a local file browser and inserts a selected STEP (`.stp`, `.step`) or Fusion archive (`.f3d`) file as an inline component in the active design. Bypasses the Hub upload and separate-tab workflow for faster local STEP insertion. Particularly useful in ECAD workflows for loading mechanical models into 3D package design tools.

---

## Architecture

PowerTools Assembly is a standard Fusion 360 add-in. Each command is implemented as a Python module in the `commands/` directory. Commands register themselves with the Fusion 360 API on add-in start and remove their UI registrations on stop.

```mermaid
C4Context
  title PowerTools Assembly – System Context

  Person(user, "Design Engineer", "Autodesk Fusion 360 user working with assemblies and team data")
  System(addin, "PowerTools Assembly Add-in", "Fusion 360 Python add-in providing assembly productivity commands")
  System_Ext(fusion, "Autodesk Fusion 360", "Desktop CAD application; hosts the add-in and exposes the adsk.core and adsk.fusion Python APIs")
  System_Ext(hub, "Autodesk Hub", "Cloud document storage, version management, and collaboration platform")
  System_Ext(fs, "Local File System", "Source for STEP and F3D files; destination for log files")

  Rel(user, addin, "Runs commands from toolbar, QAT, or File menu")
  Rel(addin, fusion, "Uses adsk.core and adsk.fusion APIs; executes built-in Fusion text commands")
  Rel(fusion, hub, "Reads and writes versioned documents; resolves references")
  Rel(addin, fs, "Reads STEP files for import; writes log files")
```

```mermaid
C4Container
  title PowerTools Assembly – Container View

  Person(user, "Design Engineer")

  Container(main, "PowerTools-Assembly.py", "Python", "Add-in entry point; calls commands.start() and commands.stop()")
  Container(config, "config.py", "Python", "Shared configuration constants: workspace ID, tab ID, panel ID, company name")
  Container(cmd_init, "commands/__init__.py", "Python", "Aggregates all command modules; iterates start() and stop() across all commands")
  Container(futil, "lib/fusionAddInUtils", "Python", "Shared utilities: event handler registration, logging, isSaved() helper")

  Container(assemblystats, "commands/assemblystats", "Python", "Assembly Statistics command")
  Container(bottomup, "commands/bottomupupdate", "Python", "Bottom-Up Update command")
  Container(externalize, "commands/externalize", "Python", "Externalize command")
  Container(getupdate, "commands/getandupdate", "Python", "Get and Update command")
  Container(insertstep, "commands/insertSTEP", "Python", "Insert STEP File command")
  Container(refmanager, "commands/refmanager", "Python", "Reference Manager command")
  Container(docrefs, "commands/refrences", "Python", "Document References command")
  Container(refresh, "commands/refresh", "Python", "Document Refresh command")

  System_Ext(fusion, "Fusion 360 API", "adsk.core / adsk.fusion")

  Rel(user, main, "Installs and enables add-in")
  Rel(main, cmd_init, "Calls start() / stop()")
  Rel(cmd_init, assemblystats, "Starts/stops")
  Rel(cmd_init, bottomup, "Starts/stops")
  Rel(cmd_init, externalize, "Starts/stops")
  Rel(cmd_init, getupdate, "Starts/stops")
  Rel(cmd_init, insertstep, "Starts/stops")
  Rel(cmd_init, refmanager, "Starts/stops")
  Rel(cmd_init, docrefs, "Starts/stops")
  Rel(cmd_init, refresh, "Starts/stops")
  Rel(assemblystats, futil, "Uses event registration and logging")
  Rel(bottomup, futil, "Uses event registration and logging")
  Rel(docrefs, futil, "Uses event registration and logging")
  Rel(externalize, futil, "Uses event registration and logging")
  Rel(config, assemblystats, "Provides workspace and panel IDs")
  Rel(config, bottomup, "Provides workspace and panel IDs")
  Rel(config, externalize, "Provides workspace and panel IDs")
  Rel(config, docrefs, "Provides workspace and panel IDs")
  Rel(assemblystats, fusion, "Uses adsk API")
  Rel(bottomup, fusion, "Uses adsk API")
  Rel(externalize, fusion, "Uses adsk API")
  Rel(docrefs, fusion, "Uses adsk API")
  Rel(getupdate, fusion, "Delegates to GetAllLatestCmd and ContextUpdateAllFromParentCmd")
  Rel(refmanager, fusion, "Delegates to ReferenceManagerCmd")
  Rel(refresh, fusion, "Calls close() and documents.open()")
  Rel(insertstep, fusion, "Executes Fusion.ImportComponent text command")
```

## Installation

1. Download or clone this repository to your local machine.
2. In Fusion 360, open the **Scripts and Add-ins** dialog (**Tools** > **Add-Ins** > **Scripts and Add-Ins**, or press **Shift+S**).
3. On the **Add-Ins** tab, select the **+** button and browse to the folder containing `PowerTools-Assembly.py`.
4. Select the add-in in the list and select **Run**. To load automatically on startup, select **Run on Startup**.

## Uninstalling

1. Open the **Scripts and Add-ins** dialog.
2. On the **Add-Ins** tab, select **PowerTools Assembly** and select **Stop**.
3. To remove it permanently, deselect **Run on Startup** and remove the folder from the add-ins directory.

## License

See [LICENSE](./LICENSE) for details.
