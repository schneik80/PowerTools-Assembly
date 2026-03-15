# PowerTools Assembly tools for Fusion

Make working as a team, cloud data, and with assemblies more productive.

## Data Workflow

## Manage Document References

**[Document References](./docs/Document%20References.md)**

Display a dialog with detailed information on the active document's references.
This includes parents, children, drawings, fasteners, and if using the related data powertool add-in, related documents created from templates. 

**[Reference Manager](./docs/Reference%20Manager.md)**

Show all references in the active document and their status. Provides utilities to work with references.

- Update all references or individually.
- Allow the selection of versions per reference.
- Open a reference in a new tab.

**[Externalize](./docs/Externalize.md)**

Save a local (inline) component as an external cloud document and re-insert it at its original assembly position.

- Externalize a single selected component occurrence.
- Externalize all local first-level components in the active assembly in one step.
- Reuses an existing cloud file if one with the same name already exists in the folder.

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

## Information tools

**[Assembly Statistics](./docs/Assembly%20Statistics.md)**

Provide assembly information on the active document. Reports on components, references and joints.

---

## Productivity tools

**[Insert STEP](./docs/Insert%20Step.md)**

Browse the local device and insert a STEP file into the active document.
