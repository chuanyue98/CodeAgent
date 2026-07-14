import { ArrowRight, Bot, Clock, History, Settings, Terminal } from 'lucide-react';
import { Link } from 'react-router-dom';

const QUICK_ACTIONS = [
  {
    to: '/agent/web',
    title: 'Web Agent',
    description: 'Start or continue a structured provider conversation.',
    icon: Bot,
  },
  {
    to: '/agent/terminal',
    title: 'Native Terminal',
    description: 'Launch the provider’s full interactive terminal experience.',
    icon: Terminal,
  },
  {
    to: '/automations/tasks',
    title: 'Automations',
    description: 'Run tasks and manage schedules from one workspace.',
    icon: Clock,
  },
  {
    to: '/activity/history',
    title: 'Activity',
    description: 'Review conversations, events, logs, and usage.',
    icon: History,
  },
  {
    to: '/settings/capabilities/skills',
    title: 'Capabilities',
    description: 'Configure skills, prompts, hooks, plugins, and MCP.',
    icon: Settings,
  },
] as const;

export default function HomePage() {
  return (
    <div className="mx-auto max-w-5xl space-y-6 p-2 sm:p-4 lg:p-8">
      <section className="glass-card overflow-hidden p-6 sm:p-8">
        <p className="mb-2 text-xs font-semibold uppercase tracking-widest text-primary">CodeAgent Workspace</p>
        <h2 className="max-w-2xl text-2xl font-bold text-slate-900 sm:text-3xl">
          Start with the work you want to do.
        </h2>
        <p className="mt-3 max-w-2xl text-sm leading-6 text-slate-500">
          Agent conversations, terminal sessions, automations, activity, and configuration are now grouped by workflow instead of exposed as separate top-level tools.
        </p>
      </section>

      <section aria-labelledby="quick-actions-heading">
        <h2 id="quick-actions-heading" className="mb-3 text-sm font-semibold text-slate-700">Quick actions</h2>
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {QUICK_ACTIONS.map(({ to, title, description, icon: Icon }) => (
            <Link key={to} to={to} className="group glass-card flex min-h-36 flex-col justify-between p-5 hover:border-primary/30 hover:bg-white">
              <div>
                <div className="mb-3 inline-flex rounded-xl bg-primary/10 p-2 text-primary">
                  <Icon className="h-5 w-5" />
                </div>
                <h3 className="text-base font-semibold text-slate-800">{title}</h3>
                <p className="mt-1.5 text-xs leading-5 text-slate-500">{description}</p>
              </div>
              <span className="mt-4 flex items-center gap-1 text-xs font-semibold text-primary">
                Open <ArrowRight className="h-3.5 w-3.5 transition-transform group-hover:translate-x-0.5" />
              </span>
            </Link>
          ))}
        </div>
      </section>
    </div>
  );
}
