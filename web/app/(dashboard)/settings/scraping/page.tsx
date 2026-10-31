import { getRoleCategories } from "@/lib/session";
import { RoleCategoryForm } from "./RoleCategoryForm";

export default async function ScrapingSettingsPage() {
  const roles = await getRoleCategories();

  return (
    <section className="rounded-xl border border-border bg-bg-raised p-5">
      <div className="mb-4 max-w-[70ch]">
        <h2 className="font-display text-sm font-semibold text-ink">Role categories</h2>
        <p className="mt-1 text-xs text-ink-faint">
          Which kinds of role the scrapers collect. This is upstream of matching: unchecked
          categories are never stored, so they cost nothing and can never appear in anyone&rsquo;s
          feed. Company job boards list every opening (sales, recruiting, finance), not just
          engineering. One real run brought back 1,948 postings of which 526 were not technical
          roles at all. A posting is kept only if its title matches a category below.
        </p>
        <p className="mt-2 text-xs text-ink-faint">
          Changes apply to the <strong className="font-semibold text-ink-soft">next ingest run</strong>.
          Jobs already collected stay in the database. This controls what arrives, not what
          you can see.
        </p>
      </div>

      <RoleCategoryForm initial={roles} />
    </section>
  );
}
