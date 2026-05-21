import { type ChangeEvent, type FormEvent, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import { resolveActiveSession } from "@/lib/workspace";
import {
  importCddCaseJsonPackage,
  loadWorkspaceStore,
  parseCddCaseJsonPackage,
  saveWorkspaceStore,
} from "@/lib/workspace-store";

export function SearchPage() {
  const [identifier, setIdentifier] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [importMessage, setImportMessage] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const navigate = useNavigate();

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const trimmed = identifier.trim();
    if (trimmed === "") {
      setError("Enter a Singapore company name or UEN.");
      return;
    }

    setError(null);
    navigate(`/c/${encodeURIComponent(trimmed)}`);
  };

  const handleImport = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (file === undefined) return;

    try {
      const cddCasePackage = parseCddCaseJsonPackage(await file.text());
      const session = resolveActiveSession();
      const nextStore = importCddCaseJsonPackage(loadWorkspaceStore(), session, {
        package: cddCasePackage,
      });
      saveWorkspaceStore(nextStore);
      setImportMessage(`Imported case for ${cddCasePackage.case.counterpartyIdentifier}.`);
      navigate(`/case/${encodeURIComponent(cddCasePackage.case.id)}`);
    } catch (error) {
      setImportMessage(error instanceof Error ? error.message : "Case import failed.");
    } finally {
      if (fileInputRef.current !== null) {
        fileInputRef.current.value = "";
      }
    }
  };

  return (
    <main>
      <h1>Dude CDD</h1>
      <p>Start a browser-local CDD case from a Singapore company name or UEN and run the retained CDD orchestrator.</p>
      <p className="notice">
        Dude is for analyst review. It does not provide legal, tax, AML, sanctions, credit,
        investment, or licensed-advisor advice. Absence of public evidence is not a positive
        clearance finding.
      </p>

      <form aria-label="CDD search" onSubmit={handleSubmit}>
        <label htmlFor="counterparty-identifier">Company name or UEN</label>
        <input
          autoComplete="off"
          id="counterparty-identifier"
          name="identifier"
          onChange={(event) => {
            setIdentifier(event.target.value);
            if (error !== null) setError(null);
          }}
          placeholder="Example Pte Ltd or 201912345A"
          type="search"
          value={identifier}
        />
        {error === null ? null : (
          <p className="error" role="alert">
            {error}
          </p>
        )}
        <button type="submit">Start CDD case</button>
      </form>

      <section>
        <h2>Import case JSON</h2>
        <p className="muted">
          Case files are browser-local workflow state. Notes and tasks stay separate from source facts after import.
        </p>
        <label htmlFor="case-json">Dude CDD case JSON</label>
        <input
          accept="application/json,.json"
          id="case-json"
          onChange={(event) => void handleImport(event)}
          ref={fileInputRef}
          type="file"
        />
        {importMessage === null ? null : <p className="notice">{importMessage}</p>}
      </section>
    </main>
  );
}
