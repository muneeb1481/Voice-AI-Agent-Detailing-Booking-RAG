import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { CalendarClock, CalendarDays, FileText, Layers, XCircle } from 'lucide-react'
import { Card, CardBody, CardHeader } from '@/components/ui/Card'
import { Skeleton, EmptyState } from '@/components/ui/Skeleton'
import { StateBadge, StatusBadge } from '@/components/ui/Badge'
import { api } from '@/lib/api'
import type { Booking, Stats } from '@/lib/types'
import { stateColor } from '@/lib/usStates'
import { formatDate, formatTime } from '@/lib/utils'

function StatTile({
  label,
  value,
  icon,
  hint,
}: {
  label: string
  value: number | string
  icon: React.ReactNode
  hint?: string
}) {
  return (
    <Card className="p-5">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-xs font-medium text-muted">{label}</p>
          <p className="mt-2 text-2xl font-semibold tabular-nums tracking-tight">{value}</p>
          {hint && <p className="mt-1 text-[11px] text-muted">{hint}</p>}
        </div>
        <div className="grid h-9 w-9 place-items-center rounded-lg bg-[rgb(var(--bg-subtle))] text-muted">
          {icon}
        </div>
      </div>
    </Card>
  )
}

export function Dashboard() {
  const [stats, setStats] = useState<Stats | null>(null)
  const [upcoming, setUpcoming] = useState<Booking[] | null>(null)

  useEffect(() => {
    const now = new Date().toISOString()
    api.stats().then(setStats).catch(() => setStats(null))
    api
      .bookings({ date_from: now })
      .then((b) => setUpcoming(b.slice(0, 6)))
      .catch(() => setUpcoming([]))
  }, [])

  const stateData = stats
    ? Object.entries(stats.by_state)
        .map(([state, count]) => ({ state, count }))
        .sort((a, b) => b.count - a.count)
        .slice(0, 8)
    : []

  return (
    <div className="space-y-6">
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-5">
        {stats ? (
          <>
            <StatTile
              label="Today"
              value={stats.bookings_today}
              icon={<CalendarDays className="h-4 w-4" />}
              hint="appointments scheduled"
            />
            <StatTile
              label="Upcoming"
              value={stats.upcoming}
              icon={<CalendarClock className="h-4 w-4" />}
              hint="active, not yet done"
            />
            <StatTile
              label="This week"
              value={stats.bookings_this_week}
              icon={<CalendarDays className="h-4 w-4" />}
            />
            <StatTile
              label="Cancelled"
              value={stats.cancelled_this_week}
              icon={<XCircle className="h-4 w-4" />}
              hint="this week"
            />
            <StatTile
              label="Knowledge"
              value={stats.documents}
              icon={<FileText className="h-4 w-4" />}
              hint={`${stats.chunks} embedded chunks`}
            />
          </>
        ) : (
          Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} className="h-[104px]" />)
        )}
      </div>

      <div className="grid gap-4 lg:grid-cols-5">
        <Card className="lg:col-span-2">
          <CardHeader title="Bookings by state" subtitle="Current week, top 8" />
          <CardBody className="h-64 pt-2">
            {stats ? (
              stateData.length === 0 ? (
                <EmptyState title="No bookings this week yet" />
              ) : (
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={stateData} margin={{ left: -20, right: 8, top: 8 }}>
                    <CartesianGrid vertical={false} stroke="rgb(var(--border))" />
                    <XAxis
                      dataKey="state"
                      tickLine={false}
                      axisLine={false}
                      tick={{ fill: 'rgb(var(--fg-muted))', fontSize: 11 }}
                    />
                    <YAxis
                      allowDecimals={false}
                      tickLine={false}
                      axisLine={false}
                      tick={{ fill: 'rgb(var(--fg-muted))', fontSize: 11 }}
                    />
                    <Tooltip
                      cursor={{ fill: 'rgb(var(--bg-subtle))' }}
                      contentStyle={{
                        background: 'rgb(var(--panel))',
                        border: '1px solid rgb(var(--border))',
                        borderRadius: 10,
                        fontSize: 12,
                        color: 'rgb(var(--fg))',
                      }}
                    />
                    <Bar dataKey="count" radius={[6, 6, 0, 0]} maxBarSize={48}>
                      {stateData.map((d) => (
                        <Cell key={d.state} fill={stateColor(d.state)} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              )
            ) : (
              <Skeleton className="h-full w-full" />
            )}
          </CardBody>
        </Card>

        <Card className="lg:col-span-3">
          <CardHeader
            title="Next appointments"
            subtitle="Soonest first"
            action={
              <Link
                to="/bookings"
                className="text-xs font-medium text-[rgb(var(--accent))] hover:underline"
              >
                View all
              </Link>
            }
          />
          {upcoming === null ? (
            <CardBody className="space-y-3">
              {Array.from({ length: 4 }).map((_, i) => (
                <Skeleton key={i} className="h-12" />
              ))}
            </CardBody>
          ) : upcoming.length === 0 ? (
            <EmptyState
              icon={<Layers className="h-6 w-6" />}
              title="No upcoming appointments"
              description="Bookings taken by the voice agent will land here automatically."
            />
          ) : (
            <ul className="divide-y divide-[rgb(var(--border))]">
              {upcoming.map((b) => (
                <li key={b.id} className="flex items-center gap-4 px-5 py-3">
                  <div className="w-20 shrink-0">
                    <p className="text-xs font-medium">{formatDate(b.starts_at, b.state)}</p>
                    <p className="text-[11px] text-muted tabular-nums">
                      {formatTime(b.starts_at, b.state)}
                    </p>
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium">{b.customer.name}</p>
                    <p className="truncate text-xs text-muted">
                      {b.vehicle ?? 'Vehicle not noted'} · {b.customer.phone}
                    </p>
                  </div>
                  <div className="flex shrink-0 gap-1.5">
                    <StateBadge state={b.state} />
                    <StatusBadge status={b.status} />
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
    </div>
  )
}
