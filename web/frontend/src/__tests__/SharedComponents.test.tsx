import { fireEvent, render, screen } from '@testing-library/react';
import { Plus, Search } from 'lucide-react';
import { describe, expect, test, vi } from 'vitest';
import Badge from '../components/shared/Badge';
import Button from '../components/shared/Button';
import EmptyState from '../components/shared/EmptyState';
import ErrorBar from '../components/shared/ErrorBar';
import { Field, Input, SearchInput, Select, Textarea } from '../components/shared/Field';
import GlassCard from '../components/shared/GlassCard';
import SectionLabel from '../components/shared/SectionLabel';
import StatusDot from '../components/shared/StatusDot';

describe('Badge', () => {
  test('neutral is the default look', () => {
    render(<Badge>claude</Badge>);
    const badge = screen.getByText('claude');
    expect(badge.className).toContain('bg-muted');
    expect(badge.className).toContain('uppercase');
  });

  test('sm shrinks the padding and text size', () => {
    render(<Badge size="sm">opencode</Badge>);
    expect(screen.getByText('opencode').className).toContain('text-[9px]');
  });
});

describe('Button', () => {
  test('fires onClick', () => {
    const onClick = vi.fn();
    render(<Button onClick={onClick}>Go</Button>);
    fireEvent.click(screen.getByRole('button', { name: 'Go' }));
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  test('loading disables the button and hides the icon', () => {
    const onClick = vi.fn();
    const { container } = render(
      <Button loading icon={Plus} onClick={onClick}>
        Save
      </Button>,
    );
    const button = screen.getByRole('button', { name: 'Save' });
    expect(button).toBeDisabled();
    // The spinner is a Lucide icon <svg>; the Plus icon must not be rendered.
    expect(container.querySelectorAll('svg')).toHaveLength(1);
    fireEvent.click(button);
    expect(onClick).not.toHaveBeenCalled();
  });

  test('renders the icon when not loading', () => {
    const { container } = render(<Button icon={Plus}>Add</Button>);
    expect(container.querySelector('svg')).not.toBeNull();
  });

  test('destructive variant applies its own classes', () => {
    render(<Button variant="destructive">Remove</Button>);
    expect(screen.getByRole('button', { name: 'Remove' }).className).toContain(
      'text-destructive',
    );
  });
});

describe('EmptyState', () => {
  test('full card renders title, body, and action', () => {
    render(
      <EmptyState
        icon={Search}
        title="Nothing here"
        body="Try a different filter."
        action={<button type="button">Reset</button>}
      />,
    );
    expect(screen.getByText('Nothing here')).toBeVisible();
    expect(screen.getByText('Try a different filter.')).toBeVisible();
    expect(screen.getByRole('button', { name: 'Reset' })).toBeVisible();
  });

  test('compact renders without the glass-card treatment', () => {
    const { container } = render(<EmptyState compact title="No matches" />);
    expect(screen.getByText('No matches')).toBeVisible();
    expect(container.querySelector('.glass-card')).toBeNull();
  });
});

describe('ErrorBar', () => {
  test('renders as an alert with the message', () => {
    render(<ErrorBar message="Something broke" />);
    expect(screen.getByRole('alert')).toHaveTextContent('Something broke');
  });

  test('retry and dismiss callbacks fire', () => {
    const onRetry = vi.fn();
    const onDismiss = vi.fn();
    render(<ErrorBar message="boom" onRetry={onRetry} onDismiss={onDismiss} />);
    fireEvent.click(screen.getByRole('button', { name: 'Retry' }));
    expect(onRetry).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByLabelText('Dismiss notification'));
    expect(onDismiss).toHaveBeenCalledTimes(1);
  });

  test('omits retry/dismiss when not provided', () => {
    render(<ErrorBar message="boom" />);
    expect(screen.getByRole('alert')).toBeInTheDocument();
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });
});

describe('Field family', () => {
  test('label is wired to the control via htmlFor', () => {
    render(
      <Field label="Name" htmlFor="field-name">
        <Input id="field-name" />
      </Field>,
    );
    expect(screen.getByLabelText('Name').tagName).toBe('INPUT');
  });

  test('error wins over hint', () => {
    render(
      <Field label="Name" htmlFor="f" hint="a hint" error="an error">
        <Input id="f" />
      </Field>,
    );
    expect(screen.getByText('an error')).toBeVisible();
    expect(screen.queryByText('a hint')).not.toBeInTheDocument();
  });

  test('hint shows when there is no error', () => {
    render(
      <Field label="Name" htmlFor="f" hint="a hint">
        <Input id="f" />
      </Field>,
    );
    expect(screen.getByText('a hint')).toBeVisible();
  });

  test('Textarea and Select render as the right elements', () => {
    render(
      <>
        <Textarea aria-label="body" />
        <Select aria-label="pick">
          <option value="a">a</option>
        </Select>
      </>,
    );
    expect(screen.getByLabelText('body').tagName).toBe('TEXTAREA');
    expect(screen.getByLabelText('pick').tagName).toBe('SELECT');
  });

  test('SearchInput keeps the plain input semantics', () => {
    render(<SearchInput aria-label="Search tasks" placeholder="type" />);
    expect(screen.getByLabelText('Search tasks')).toHaveAttribute('placeholder', 'type');
  });
});

describe('GlassCard', () => {
  test('default wraps content in the glass-card class', () => {
    const { container } = render(<GlassCard>content</GlassCard>);
    const card = container.firstElementChild as HTMLElement;
    expect(card.className).toContain('glass-card');
    expect(card).toHaveTextContent('content');
  });

  test('interactive adds the hover idiom', () => {
    const { container } = render(<GlassCard interactive>x</GlassCard>);
    expect((container.firstElementChild as HTMLElement).className).toContain(
      'glass-card-interactive',
    );
  });

  test('feature variant swaps the card class', () => {
    const { container } = render(<GlassCard variant="feature">x</GlassCard>);
    expect((container.firstElementChild as HTMLElement).className).toContain(
      'glass-card-feature',
    );
  });
});

describe('SectionLabel', () => {
  test('renders as a <p> by default', () => {
    render(<SectionLabel>Overview</SectionLabel>);
    const label = screen.getByText('Overview');
    expect(label.tagName).toBe('P');
    expect(label.className).toContain('uppercase');
  });

  test('honors the as prop for heading levels', () => {
    render(<SectionLabel as="h3">Details</SectionLabel>);
    expect(screen.getByText('Details').tagName).toBe('H3');
  });
});

describe('StatusDot', () => {
  test('tone picks the dot color', () => {
    const { container } = render(<StatusDot tone="failed" />);
    expect(container.querySelector('.bg-red-500')).not.toBeNull();
  });

  test('pulse adds the halo ring', () => {
    const { container } = render(<StatusDot tone="running" pulse />);
    expect(container.querySelector('.animate-pulse-ring')).not.toBeNull();
  });

  test('no pulse means a single dot', () => {
    const { container } = render(<StatusDot tone="neutral" />);
    expect(container.querySelector('.animate-pulse-ring')).toBeNull();
    expect(container.querySelectorAll('span.rounded-full')).toHaveLength(1);
  });
});
