import { useEffect, useState } from 'react';
import {
  ArrowRight,
  Bot,
  CheckCircle2,
  Circle,
  Clock,
  FolderGit2,
  History,
  Loader2,
  Settings,
  Terminal,
} from 'lucide-react';
import { Link } from 'react-router';
import { useProject } from '../context/ProjectContext';
import { fetchAgentProviders } from '../api/agent';
import request from '../utils/request';
import type { ProviderCapabilities } from '../types/agent';
import { workspaceLabel } from '../utils/agentWorkspaceHelpers';

const QUICK_ACTIONS = [
  {
    to: '/agent/web',
    title: 'Web Agent',
    description: 'Start or continue a structured provider conversation.',
    icon: Bot,
  },
  {
    to: '/agent/terminal',
    title: 'Local Terminal',
    description: 'Open a provider CLI in an in-browser terminal, running on this machine.',
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

interface SetupStep {
  id: string;
  done: boolean;
  title: string;
  doneDetail: string;
  todoDetail: string;
  ctaLabel: string;
  ctaTo: string;
}

/**
 * A single setup step. Rendered as a row rather than a card so the whole
 * checklist reads top-to-bottom in one glance, and so an incomplete step is
 * the only thing carrying colour on the page.
 */
function SetupRow({ step }: { step: SetupStep }) {
  return (
    <li className="flex items-start gap-3 px-4 py-3">
      {step.done
        ? <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-500" aria-hidden />
        : <Circle className="mt-0.5 h-4 w-4 shrink-0 text-amber-500" aria-hidden />}
      <div className="min-w-0 flex-1">
        <p className={`text-sm font-semibold ${step.done ? 'text-slate-500' : 'text-slate-900'}`}>
          {step.title}
        </p>
        <p className="mt-0.5 text-xs leading-5 text-slate-500">
          {step.done ? step.doneDetail : step.todoDetail}
        </p>
      </div>
      {!step.done && (
        <Link
          to={step.ctaTo}
          className="shrink-0 rounded-lg bg-primary px-3 py-1.5 text-xs font-semibold text-white transition-opacity hover:opacity-90"
        >
          {step.ctaLabel}
        </Link>
      )}
    </li>
  );
}

export default function HomePage() {
  const { validProjects, projects, selectedWorkspace } = useProject();
  const [providers, setProviders] = useState<ProviderCapabilities[] | null>(null);
  const [taskCount, setTaskCount] = useState<number | null>(null);

  useEffect(() => {
    // Best-effort: Home must still render its guidance if either probe fails,
    // so a failure resolves to "none found" rather than an error screen.
    void fetchAgentProviders().then(setProviders).catch(() => setProviders([]));
    void request<unknown[]>('/api/tasks')
      .then(list => setTaskCount(Array.isArray(list) ? list.length : 0))
      .catch(() => setTaskCount(0));
  }, []);

  const availableProviders = providers?.filter(provider => provider.available) ?? [];
  const probing = providers === null || taskCount === null;

  const steps: SetupStep[] = [
    {
      id: 'workspace',
      done: validProjects.length > 0,
      title: 'Register a workspace',
      doneDetail: `${validProjects.length} workspace${validProjects.length === 1 ? '' : 's'} registered${
        selectedWorkspace ? ` · working in ${workspaceLabel(selectedWorkspace)}` : ''
      }.`,
      todoDetail: projects.length > 0
        ? 'Registered paths could not be found on disk. Fix or remove them in Workspace settings.'
        : 'CodeAgent only operates inside directories you register. Add the absolute path of a project you want it to work on.',
      ctaLabel: 'Add workspace',
      ctaTo: '/settings/workspace',
    },
    {
      id: 'provider',
      done: availableProviders.length > 0,
      title: 'Connect a provider CLI',
      doneDetail: `Available: ${availableProviders.map(provider => provider.displayName).join(', ')}.`,
      todoDetail: 'No provider CLI was detected. Install and sign in to one (claude, gemini, codex, or opencode), then re-check under Settings › System.',
      ctaLabel: 'Check system',
      ctaTo: '/settings/system',
    },
    {
      id: 'task',
      done: (taskCount ?? 0) > 0,
      title: 'Create your first task (optional)',
      doneDetail: `${taskCount} reusable task${taskCount === 1 ? '' : 's'} available to run or schedule.`,
      todoDetail: 'Tasks are reusable prompts you can run on any engine or put on a schedule. Describe one and let the AI write it.',
      ctaLabel: 'Create task',
      ctaTo: '/automations/tasks',
    },
  ];

  const remaining = steps.filter(step => !step.done && step.id !== 'task').length;
  const ready = !probing && remaining === 0;

  return (
    <div className="mx-auto max-w-5xl space-y-6 p-2 sm:p-4 lg:p-8">
      <section className="glass-card overflow-hidden p-6 sm:p-8">
        <p className="mb-2 text-xs font-semibold uppercase tracking-widest text-primary">CodeAgent Workspace</p>
        <h2 className="max-w-2xl text-2xl font-bold text-slate-900 sm:text-3xl">
          {ready ? 'Ready when you are.' : 'Two steps to your first agent run.'}
        </h2>
        <p className="mt-3 max-w-2xl text-sm leading-6 text-slate-500">
          CodeAgent runs the AI CLI you already use — Claude, Gemini, Codex, or OpenCode —
          against a directory you choose, with your own prompts and skills injected. Nothing
          leaves this machine except the provider&apos;s own traffic.
        </p>
        {ready && (
          <Link
            to="/agent/web"
            className="mt-5 inline-flex items-center gap-2 rounded-xl bg-primary px-4 py-2.5 text-sm font-semibold text-white shadow-lg shadow-primary/20 transition-opacity hover:opacity-90"
          >
            <Bot className="h-4 w-4" /> Start an agent session
          </Link>
        )}
      </section>

      <section aria-labelledby="setup-heading" className="glass-card overflow-hidden">
        <div className="flex items-center justify-between gap-3 border-b border-slate-100 px-4 py-3">
          <h2 id="setup-heading" className="flex items-center gap-2 text-sm font-semibold text-slate-700">
            <FolderGit2 className="h-4 w-4 text-primary" />
            Setup
          </h2>
          <span className="flex items-center gap-1.5 text-xs text-slate-400">
            {probing
              ? <><Loader2 className="h-3 w-3 animate-spin" /> Checking…</>
              : `${steps.filter(step => step.done).length} of ${steps.length} complete`}
          </span>
        </div>
        <ul className="divide-y divide-slate-100">
          {steps.map(step => <SetupRow key={step.id} step={step} />)}
        </ul>
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
