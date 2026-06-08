const statCards = [
  { label: "Repositories", value: "—" },
  { label: "Open Issues", value: "—" },
  { label: "Active Agents", value: "—" },
  { label: "Pull Requests", value: "—" },
];

export function DashboardPage() {
  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-lg font-semibold text-gray-900">Overview</h2>
        <p className="mt-1 text-sm text-gray-500">
          Connect a repository to get started.
        </p>
      </div>

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {statCards.map((card) => (
          <div
            key={card.label}
            className="rounded-lg border border-gray-200 bg-white p-4"
          >
            <p className="text-xs font-medium uppercase tracking-wide text-gray-500">
              {card.label}
            </p>
            <p className="mt-2 text-2xl font-semibold text-gray-900">
              {card.value}
            </p>
          </div>
        ))}
      </div>

      <div className="rounded-lg border border-gray-200 bg-white p-6">
        <p className="text-sm text-gray-500">
          No activity yet. Connect a repository to begin.
        </p>
      </div>
    </div>
  );
}
