import React from 'react';
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import type { TooltipPayloadEntry } from 'recharts';
import { fmtCost, fmtTokens } from '../../api/analytics';
import { useT } from '../../i18n/context';
import SectionLabel from '../shared/SectionLabel';
import { ec, formatDate, formatMonth } from './present';
import type { TimeSeries } from './rangeStats';

// Daily and monthly aggregates are discrete measurements, so the areas are
// drawn with straight segments. A monotone curve invents the shape between
// two points -- on this data it drew $300 peaks on days that never had one.

// ── Stat card ────────────────────────────────────────────────────────────────
export function StatCard({
  label, value, sub, Icon, iconColor, iconBg, stagger = 'stagger-1',
}: {
  label: string; value: string; sub?: string;
  Icon: React.ElementType; iconColor: string; iconBg: string;
  stagger?: string;
}) {
  return (
    <div className={`animate-fade-rise ${stagger} glass-card group p-4`}>
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 space-y-0.5">
          <SectionLabel className="truncate">{label}</SectionLabel>
          <p className="text-xl font-bold text-slate-800 truncate">{value}</p>
          {sub && <p className="text-[10px] text-slate-500 truncate">{sub}</p>}
        </div>
        <div className={`p-2 rounded-lg shrink-0 ${iconBg} transition-transform duration-300 group-hover:scale-110`}>
          <Icon className={`w-4 h-4 ${iconColor}`} />
        </div>
      </div>
    </div>
  );
}

// ── Custom tooltip ────────────────────────────────────────────────────────────
// `TooltipPayloadEntry` is recharts' own entry shape (all fields optional / a
// union `ValueType = number | string | ReadonlyArray<number | string>`), so we
// normalize the bits we actually render instead of trusting them blindly.
export function ChartTooltip({ active, payload, label, isCost }: {
  active?: boolean; payload?: ReadonlyArray<TooltipPayloadEntry>;
  label?: string; isCost?: boolean;
}) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-3 shadow-lg text-xs">
      <p className="font-semibold mb-1.5 text-slate-700">{label}</p>
      {payload.map((entry, i) => {
        const color = entry.color ?? '#94a3b8';
        const value = typeof entry.value === 'number' ? entry.value : Number(entry.value ?? 0);
        return (
          <p key={i} className="flex gap-2 items-center" style={{ color }}>
            <span className="w-2 h-2 rounded-full shrink-0" style={{ background: color }} />
            <span className="text-slate-600">{String(entry.name ?? '')}:</span>
            <span className="font-semibold">
              {isCost ? fmtCost(value) : fmtTokens(value)}
            </span>
          </p>
        );
      })}
    </div>
  );
}

export function SectionTitle({ children, action }: { children: React.ReactNode; action?: React.ReactNode }) {
  return (
    <div className="mb-3 flex items-center justify-between gap-2">
      <SectionLabel>{children}</SectionLabel>
      {action}
    </div>
  );
}

interface TrendCardsProps {
  series: TimeSeries;
  granularity: 'day' | 'month';
  rangeLabel: string;
}

export function CostTrendCard({ series, granularity, rangeLabel }: TrendCardsProps) {
  const t = useT();
  const formatAxis = granularity === 'month' ? formatMonth : formatDate;
  return (
    <div className="animate-fade-rise stagger-2 glass-card p-5">
      <SectionTitle>
        {t('charts.costByEngine', {
          period: granularity === 'month' ? t('charts.perMonth') : t('charts.lastRange', { range: rangeLabel }),
        })}
      </SectionTitle>
      <ResponsiveContainer width="100%" height={240}>
        <AreaChart data={series.cost} margin={{ top: 5, right: 10, left: 0, bottom: 5 }}>
          <defs>
            {series.engines.map(eng => (
              <linearGradient key={eng} id={`grad-${eng}`} x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor={ec(eng)} stopOpacity={0.5} />
                <stop offset="95%" stopColor={ec(eng)} stopOpacity={0.05} />
              </linearGradient>
            ))}
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
          <XAxis
            dataKey="_key" tick={{ fontSize: 11 }} tickLine={false}
            tickFormatter={v => formatAxis(String(v))}
          />
          <YAxis
            tick={{ fontSize: 11 }} tickLine={false}
            tickFormatter={v => `$${(v as number).toFixed(0)}`}
            width={45}
          />
          <Tooltip
            content={props => (
              <ChartTooltip
                active={props.active}
                payload={props.payload}
                label={props.label != null ? formatAxis(String(props.label)) : undefined}
                isCost
              />
            )}
          />
          {series.engines.map(eng => (
            <Area
              key={eng} type="linear" dataKey={eng} name={eng}
              stroke={ec(eng)} strokeWidth={2} fill={`url(#grad-${eng})`}
            />
          ))}
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

export function TokensTrendCard({ series, granularity, rangeLabel }: TrendCardsProps) {
  const t = useT();
  return (
    <div className="animate-fade-rise stagger-3 glass-card p-5">
      <SectionTitle>
        {t('charts.tokensByEngine', {
          period: granularity === 'month' ? t('charts.perMonth') : t('charts.lastRange', { range: rangeLabel }),
        })}
      </SectionTitle>
      <ResponsiveContainer width="100%" height={200}>
        {granularity === 'month' ? (
          <BarChart data={series.tokens} margin={{ top: 5, right: 10, left: 0, bottom: 5 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
            <XAxis dataKey="_key" tick={{ fontSize: 11 }} tickLine={false}
              tickFormatter={v => formatMonth(String(v))} />
            <YAxis tick={{ fontSize: 11 }} tickLine={false}
              tickFormatter={v => fmtTokens(v as number)} width={45} />
            <Tooltip
              content={props => (
                <ChartTooltip
                  active={props.active}
                  payload={props.payload}
                  label={props.label != null ? formatMonth(String(props.label)) : undefined}
                />
              )}
            />
            {series.engines.map((eng, i) => (
              <Bar key={eng} dataKey={eng} name={eng} stackId="a" fill={ec(eng)}
                radius={i === series.engines.length - 1 ? [3, 3, 0, 0] : [0, 0, 0, 0]} />
            ))}
          </BarChart>
        ) : (
          <AreaChart data={series.tokens} margin={{ top: 5, right: 10, left: 0, bottom: 5 }}>
            <defs>
              {series.engines.map(eng => (
                <linearGradient key={eng} id={`tgrad-${eng}`} x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor={ec(eng)} stopOpacity={0.4} />
                  <stop offset="95%" stopColor={ec(eng)} stopOpacity={0.02} />
                </linearGradient>
              ))}
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
            <XAxis dataKey="_key" tick={{ fontSize: 11 }} tickLine={false}
              tickFormatter={v => formatDate(String(v))} />
            <YAxis tick={{ fontSize: 11 }} tickLine={false}
              tickFormatter={v => fmtTokens(v as number)} width={45} />
            <Tooltip
              content={props => (
                <ChartTooltip
                  active={props.active}
                  payload={props.payload}
                  label={props.label != null ? formatDate(String(props.label)) : undefined}
                />
              )}
            />
            {series.engines.map(eng => (
              <Area key={eng} type="linear" dataKey={eng} name={eng}
                stroke={ec(eng)} strokeWidth={2} fill={`url(#tgrad-${eng})`} />
            ))}
          </AreaChart>
        )}
      </ResponsiveContainer>
    </div>
  );
}

export interface PieDatum {
  name: string;
  value: number;
}

export function CostDistributionCard({ pieData }: { pieData: PieDatum[] }) {
  const t = useT();
  if (pieData.length === 0) return null;
  return (
    <div className="glass-card p-4">
      <SectionTitle>{t('charts.costDistribution')}</SectionTitle>
      <ResponsiveContainer width="100%" height={180}>
        <PieChart>
          <Pie
            data={pieData} dataKey="value" nameKey="name"
            cx="50%" cy="45%" innerRadius={42} outerRadius={64}
            paddingAngle={2}
            label={({ percent }: { percent?: number }) =>
              (percent ?? 0) > 0.05 ? `${((percent ?? 0) * 100).toFixed(0)}%` : ''
            }
            labelLine={false}
          >
            {pieData.map(entry => (
              <Cell key={entry.name} fill={ec(entry.name)} strokeWidth={1} />
            ))}
          </Pie>
          <Tooltip
            content={({ active, payload }) => {
              if (!active || !payload?.length) return null;
              const p = payload[0].payload as { name: string; value: number };
              return (
                <div className="rounded-lg border border-slate-200 bg-white p-2 shadow-lg text-xs">
                  <p className="font-semibold" style={{ color: ec(p.name) }}>{p.name}</p>
                  <p className="text-slate-600">{fmtCost(p.value)}</p>
                </div>
              );
            }}
          />
        </PieChart>
      </ResponsiveContainer>
      <div className="flex flex-wrap gap-x-3 gap-y-1 justify-center mt-1">
        {pieData.map(e => (
          <span key={e.name} className="flex items-center gap-1 text-[10px] text-slate-500">
            <span className="w-2 h-2 rounded-full" style={{ background: ec(e.name) }} />
            {e.name}
          </span>
        ))}
      </div>
    </div>
  );
}
