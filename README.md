# PowerTools Assembly tools for Fusion

PowerTools Assembly is a Fusion 360 add-in that provides productivity commands for teams working with multi-component assemblies and cloud-connected design data. It adds commands to the Design workspace toolbar and Quick Access Toolbar (QAT) that reduce the steps required for common assembly management tasks.

## Data Workflow

## Manage Document References

**[Document References](./docs/Document%20References.md)**

Display a dialog with detailed information on the active document's references.
This includes parents, children, drawings, fasteners, and if using the related data powertool add-in, related documents created from templates. 

**[Reference Manager](./docs/Reference%20Manager.md)**

Opens the Fusion 360 Reference Manager dialog directly from the Quick Access Toolbar. Provides a single location to review all references, update them individually or all at once, select specific versions, and open referenced documents in new tabs.

**[Externalize](./docs/Externalize.md)**

Converts one or more local (inline) components in the active assembly into independent cloud documents, then re-inserts them at their original positions and orientations.

- Externalize a single selected component occurrence.
- Externalize all local first-level components in one step using **Externalize All**.
- Save to the same folder as the active document or to a new named sub-folder.
- Automatically reuse an existing cloud file if one with the same name already exists.

**[Get and Update](./docs/Get%20and%20Update.md)**

Typical x-ref assemblies will use assembly contexts to create associativity across parts. When new versions of x-refs are available one must load the new versions and then update the out of date contexts. This power tool adds a QAT command to automatically get all latests and then update contexts.

**[Document Refresh](./docs/Document%20Refresh.md)**

When working in a team it can be necessary to reload the active assembly to load new versions created by other team members. Int he file menu the Refresh command will automatically close, get new versions and then reload the active document, saving you time and nuisance of doing this manually.

**[Bottom-Up Update](./docs/Bottom-Up%20Update.md)**

Save and update all references in the open assembly from the bottom up. Processes assembly components in dependency order to ensure proper reference updates.

- Update components from dependencies upward through the assembly hierarchy.
- Optional rebuild of all components to ensure they are current.
- Skip standard library components and already processed documents.
- Apply appropriate design intent (Part, Assembly, or Hybrid) automatically.
- Hide various UI elements (origins, joints, sketches, canvases) for cleaner saves.
- Detailed progress logging with timestamps and processing statistics.

---

### Information

**[Assembly Statistics](./docs/Assembly%20Statistics.md)**

Displays a summary dialog for the active design showing component instance counts, unique component counts, out-of-date reference counts, assembly nesting depth, document context count, assembly constraints, and joint totals broken down by type.

---

### Productivity

**[Insert STEP File](./docs/Insert%20Step.md)**

Opens a local file browser and inserts a selected STEP (`.stp`, `.step`) or Fusion archive (`.f3d`) file as an inline component in the active design. Bypasses the Hub upload and separate-tab workflow for faster local STEP insertion. Particularly useful in ECAD workflows for loading mechanical models into 3D package design tools.

---

## Productivity tools

**[Insert STEP](./docs/Insert%20Step.md)**

Browse the local device and insert a STEP file into the active document.
