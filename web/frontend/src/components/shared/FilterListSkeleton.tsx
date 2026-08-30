/**
 * Loading placeholder for the filter-sidebar + row-list layout shared by
 * Activity's History and Events tabs. Both tabs render the same skeleton so
 * switching between them doesn't look like arriving in a different app.
 */
export default function FilterListSkeleton({ label }: { label: string }) {
  return (
    <div
      className="flex flex-col xl:flex-row gap-4 min-h-full xl:h-full animate-fade-in"
      aria-busy="true"
      aria-label={label}
    >
      <div className="w-full xl:w-56 shrink-0 glass-card p-4 space-y-4">
        <div className="h-4 w-16 rounded bg-muted animate-pulse" />
        <div className="h-8 w-full rounded-lg bg-muted animate-pulse" />
        <div className="space-y-2">
          <div className="h-3 w-24 rounded bg-muted animate-pulse" />
          <div className="h-8 w-full rounded-lg bg-muted animate-pulse" />
          <div className="h-8 w-full rounded-lg bg-muted animate-pulse" />
        </div>
        <div className="space-y-2">
          <div className="h-3 w-16 rounded bg-muted animate-pulse" />
          {[0, 1, 2].map(i => (
            <div key={i} className="h-6 w-full rounded-md bg-muted animate-pulse" />
          ))}
        </div>
      </div>
      <div className="flex-1 min-w-0 glass-card p-5 space-y-2">
        <div className="h-4 w-24 rounded bg-muted animate-pulse mb-4" />
        {[0, 1, 2, 3, 4, 5].map(i => (
          <div key={i} className="border border-border rounded-xl p-4 flex items-center justify-between gap-3">
            <div className="space-y-2 min-w-0 flex-1">
              <div className="h-3.5 w-40 rounded bg-muted animate-pulse" />
              <div className="h-3 w-64 max-w-full rounded bg-muted animate-pulse" />
            </div>
            <div className="flex items-center gap-4 shrink-0">
              <div className="h-3 w-12 rounded bg-muted animate-pulse" />
              <div className="h-3 w-12 rounded bg-muted animate-pulse" />
              <div className="h-3 w-16 rounded bg-muted animate-pulse" />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
