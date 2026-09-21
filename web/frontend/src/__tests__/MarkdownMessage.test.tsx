import { render, screen } from '@testing-library/react';
import { describe, expect, test } from 'vitest';
import MarkdownMessage from '../components/MarkdownMessage';

describe('MarkdownMessage', () => {
  test('highlights a fenced block that names its language', () => {
    const { container } = render(
      <MarkdownMessage text={'```python\ndef greet():\n    return 1\n```'} />,
    );

    const code = container.querySelector('pre code');
    expect(code).not.toBeNull();
    expect(code).toHaveClass('hljs');
    expect(code).toHaveClass('language-python');
    // The token spans are what the imported theme colours.
    expect(container.querySelector('.hljs-keyword')).not.toBeNull();
  });

  test('keeps the code text and the copy affordance on a highlighted block', () => {
    render(<MarkdownMessage text={'```js\nconst answer = 42;\n```'} />);

    expect(screen.getByText(/const/)).toBeInTheDocument();
    expect(screen.getByRole('button')).toBeInTheDocument();
  });

  test('leaves a fence with no language unhighlighted', () => {
    const { container } = render(<MarkdownMessage text={'```\nplain text\n```'} />);

    expect(container.querySelector('pre code')).not.toHaveClass('hljs');
  });

  test('leaves inline code unhighlighted', () => {
    const { container } = render(<MarkdownMessage text={'run `bun run build`'} />);

    expect(container.querySelector('code')).not.toHaveClass('hljs');
  });

  test('survives a fence naming a language it does not know', () => {
    const { container } = render(
      <MarkdownMessage text={'```not-a-real-language\nsome text\n```'} />,
    );

    expect(container.querySelector('pre code')).toHaveTextContent('some text');
  });
});
