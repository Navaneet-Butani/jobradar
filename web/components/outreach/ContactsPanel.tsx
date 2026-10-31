"use client";

import { useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { AddressBook, Plus, Trash, UploadSimple } from "@phosphor-icons/react";
import type { OutreachContact } from "@/lib/types";
import { EmptyState } from "@/components/EmptyState";
import { Field } from "@/components/Field";
import { formatDate } from "@/lib/format";

const FIELD =
  "rounded-lg border border-border-strong bg-bg px-3 py-2 text-sm outline-none transition-colors focus:border-accent";

export function ContactsPanel({ contacts }: { contacts: OutreachContact[] }) {
  const router = useRouter();
  const fileRef = useRef<HTMLInputElement>(null);

  const [filter, setFilter] = useState("");
  const [busy, setBusy] = useState<null | "import" | "add">(null);
  const [error, setError] = useState<string | null>(null);
  const [report, setReport] = useState<string[] | null>(null);
  const [addOpen, setAddOpen] = useState(false);
  const [draft, setDraft] = useState({ email: "", contact_name: "", company_name: "", role_hint: "" });

  const visible = useMemo(() => {
    const q = filter.trim().toLowerCase();
    if (!q) return contacts;
    return contacts.filter((c) =>
      [c.email, c.company_name, c.contact_name, c.role_hint].some((v) => v?.toLowerCase().includes(q)),
    );
  }, [contacts, filter]);

  async function importCsv(file: File) {
    setBusy("import");
    setError(null);
    setReport(null);

    const form = new FormData();
    form.append("file", file);
    const res = await fetch("/api/outreach/contacts/import", { method: "POST", body: form });
    const payload = await res.json().catch(() => null);
    setBusy(null);
    if (fileRef.current) fileRef.current.value = "";

    if (!res.ok || !payload?.status) {
      setError(payload?.error_message ?? "Import failed");
      return;
    }
    const r = payload.data;
    setReport([
      `${r.imported} added, ${r.updated} updated${r.skipped ? `, ${r.skipped} skipped` : ""}.`,
      ...r.problems,
    ]);
    router.refresh();
  }

  async function addContact() {
    setBusy("add");
    setError(null);
    const res = await fetch("/api/outreach/contacts", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        email: draft.email,
        contact_name: draft.contact_name || null,
        company_name: draft.company_name || null,
        role_hint: draft.role_hint || null,
      }),
    });
    const payload = await res.json().catch(() => null);
    setBusy(null);

    if (!res.ok || !payload?.status) {
      setError(payload?.error_message ?? "Couldn't add that contact");
      return;
    }
    setDraft({ email: "", contact_name: "", company_name: "", role_hint: "" });
    setAddOpen(false);
    router.refresh();
  }

  async function remove(id: number) {
    setError(null);
    const res = await fetch(`/api/outreach/contacts/${id}`, { method: "DELETE" });
    if (!res.ok) {
      setError("Couldn't delete that contact");
      return;
    }
    router.refresh();
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-ink-soft">
          Only an <code className="rounded bg-bg-sunken px-1 py-0.5 font-mono text-xs">email</code> column is
          required. Company, name, designation and role are matched loosely if present.
        </p>
        <div className="flex items-center gap-2">
          <input
            ref={fileRef}
            type="file"
            accept=".csv,text/csv"
            className="hidden"
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) void importCsv(file);
            }}
          />
          <button
            type="button"
            disabled={busy !== null}
            onClick={() => fileRef.current?.click()}
            className="inline-flex items-center gap-1.5 rounded-lg bg-accent px-3.5 py-2 text-sm font-semibold text-accent-ink transition-opacity hover:opacity-90 disabled:opacity-50"
          >
            <UploadSimple size={15} />
            {busy === "import" ? "Importing…" : "Upload CSV"}
          </button>
          <button
            type="button"
            onClick={() => setAddOpen((v) => !v)}
            className="inline-flex items-center gap-1.5 rounded-lg border border-border-strong px-3.5 py-2 text-sm font-medium text-ink-soft transition-colors hover:border-accent hover:text-accent"
          >
            <Plus size={15} />
            Add one
          </button>
        </div>
      </div>

      {error && (
        <p role="alert" className="text-sm text-danger">
          {error}
        </p>
      )}

      {report && (
        <ul className="space-y-1 rounded-lg bg-bg-sunken p-3">
          {report.map((line) => (
            <li key={line} className="text-xs text-ink-soft">
              {line}
            </li>
          ))}
        </ul>
      )}

      {addOpen && (
        <div className="rounded-lg border border-border bg-bg-elevated p-4">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Field
              label="Email"
              required
              hint="The only required field"
              value={draft.email}
              onChange={(v) => setDraft({ ...draft, email: v })}
            />
            <Field
              label="Contact name"
              value={draft.contact_name}
              onChange={(v) => setDraft({ ...draft, contact_name: v })}
            />
            <Field
              label="Company"
              value={draft.company_name}
              onChange={(v) => setDraft({ ...draft, company_name: v })}
            />
            <Field
              label="Role they hire for"
              hint="Used by the {{role_hint}} merge field"
              value={draft.role_hint}
              onChange={(v) => setDraft({ ...draft, role_hint: v })}
            />
          </div>
          <div className="mt-3 flex items-center gap-3">
            <button
              type="button"
              onClick={addContact}
              disabled={busy !== null || !draft.email}
              className="rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-accent-ink transition-opacity hover:opacity-90 disabled:opacity-50"
            >
              {busy === "add" ? "Adding…" : "Add contact"}
            </button>
            <button
              type="button"
              onClick={() => setAddOpen(false)}
              className="text-sm text-ink-faint hover:text-ink"
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {contacts.length === 0 ? (
        <EmptyState
          icon={AddressBook}
          title="No contacts yet"
          description="Upload a CSV with columns like company, name, email, designation, or add one by hand."
        />
      ) : (
        <>
          <input
            className={`${FIELD} w-full`}
            type="search"
            aria-label="Filter contacts"
            placeholder="Filter by company, name or email…"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
          />

          <div className="overflow-hidden rounded-xl border border-border">
            <table className="w-full text-left text-sm">
              <thead className="bg-bg-sunken text-xs uppercase tracking-wide text-ink-faint">
                <tr>
                  <th className="px-3 py-2 font-medium">Company</th>
                  <th className="px-3 py-2 font-medium">Contact</th>
                  <th className="px-3 py-2 font-medium">Email</th>
                  <th className="px-3 py-2 font-medium">Hiring for</th>
                  <th className="px-3 py-2 font-medium">Last emailed</th>
                  <th className="w-10 px-3 py-2" />
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {visible.map((c) => (
                  <tr key={c.id} className="bg-bg-elevated transition-colors hover:bg-bg-sunken/60">
                    <td className="px-3 py-2.5 text-ink">{c.company_name ?? "-"}</td>
                    <td className="px-3 py-2.5 text-ink-soft">
                      {c.contact_name ?? "-"}
                      {c.title && <span className="ml-1 text-xs text-ink-faint">{c.title}</span>}
                    </td>
                    <td className="px-3 py-2.5 font-mono text-xs text-ink-soft">{c.email}</td>
                    <td className="px-3 py-2.5 text-ink-soft">{c.role_hint ?? "-"}</td>
                    <td className="px-3 py-2.5 text-xs text-ink-faint">
                      {c.last_emailed_at ? formatDate(c.last_emailed_at) : "never"}
                    </td>
                    <td className="px-3 py-2.5">
                      <button
                        type="button"
                        onClick={() => remove(c.id)}
                        aria-label={`Delete ${c.email}`}
                        className="rounded p-1 text-ink-faint transition-colors hover:text-danger"
                      >
                        <Trash size={15} />
                      </button>
                    </td>
                  </tr>
                ))}
                {visible.length === 0 && (
                  <tr>
                    <td colSpan={6} className="bg-bg-elevated px-3 py-8 text-center text-sm text-ink-faint">
                      Nothing matches “{filter}”.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}
