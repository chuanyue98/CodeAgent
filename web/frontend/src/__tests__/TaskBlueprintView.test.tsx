import { render, screen } from '@testing-library/react';
import { describe, expect, test } from 'vitest';
import TaskBlueprintView from '../components/TaskDashboard/TaskBlueprintView';

describe('TaskBlueprintView', () => {
  test('parses and renders four-section blueprint with cards (bilingual headers)', () => {
    const content = `
# Sample Task
## Objective (目标)
Do some cleanup.
## Context (背景)
Technical debt accumulated over time.
## Instructions (指令)
1. Step one.
2. Step two.
## Verification (验证)
Run tests.
`;
    render(<TaskBlueprintView content={content} title="Sample Task" />);

    // Check that card headers are present
    expect(screen.getByText('Objective')).toBeVisible();
    expect(screen.getByText('Context')).toBeVisible();
    expect(screen.getByText('Instructions')).toBeVisible();
    expect(screen.getByText('Verification')).toBeVisible();

    // Check that section contents are rendered
    expect(screen.getByText(/Do some cleanup/)).toBeVisible();
    expect(screen.getByText(/Technical debt accumulated over time/)).toBeVisible();
    expect(screen.getByText(/Step one/)).toBeVisible();
    expect(screen.getByText(/Step two/)).toBeVisible();
    expect(screen.getByText(/Run tests/)).toBeVisible();
  });

  test('parses and renders four-section blueprint with pure English headers', () => {
    const content = `
## Objective
Refactor database schema.

## Context
High latency on queries.

## Instructions
- Add missing indexes
- Optimize join conditions

## Verification
Explain query plan.
`;
    render(<TaskBlueprintView content={content} title="DB Refactor" />);

    expect(screen.getByText(/Refactor database schema/)).toBeVisible();
    expect(screen.getByText(/High latency on queries/)).toBeVisible();
    expect(screen.getByText(/Add missing indexes/)).toBeVisible();
    expect(screen.getByText(/Explain query plan/)).toBeVisible();
  });

  test('parses and renders four-section blueprint with pure Chinese headers', () => {
    const content = `
## 目标
优化前端打包产物体积

## 背景
首屏加载较慢，包含冗余依赖

## 执行指令
1. 移除未使用的库
2. 开启代码分割

## 验收标准
打包产物减小 30% 以上
`;
    render(<TaskBlueprintView content={content} title="前端优化" />);

    expect(screen.getByText(/优化前端打包产物体积/)).toBeVisible();
    expect(screen.getByText(/首屏加载较慢/)).toBeVisible();
    expect(screen.getByText(/移除未使用的库/)).toBeVisible();
    expect(screen.getByText(/打包产物减小 30% 以上/)).toBeVisible();
  });

  test('does not misidentify ## lines inside code blocks as sections', () => {
    const content = `
## Objective
Fix shell script execution.

## Context
Comments in scripts were confusing the parser.

## Instructions
Run the following script:
\`\`\`bash
## This is a bash comment
echo "hello world"
\`\`\`

## Verification
Script runs without error.
`;
    render(<TaskBlueprintView content={content} title="Fix Script" />);

    expect(screen.getByText(/Fix shell script execution/)).toBeVisible();
    expect(screen.getByText(/Comments in scripts were confusing the parser/)).toBeVisible();
    expect(screen.getByText(/This is a bash comment/)).toBeVisible();
    expect(screen.getByText(/Script runs without error/)).toBeVisible();
  });

  test('renders freeform markdown when content does not follow the four-section structure', () => {
    const content = `
# Freeform Task
This task has non-standard sections:

### Stage 1: Exploration
Find all broken links.

### Stage 2: Report
Write findings into report.md.
`;
    render(<TaskBlueprintView content={content} title="Freeform Task" />);

    expect(screen.getByText(/This task has non-standard sections/)).toBeVisible();
    expect(screen.getByText(/Stage 1: Exploration/)).toBeVisible();
    expect(screen.getByText(/Find all broken links/)).toBeVisible();
    expect(screen.getByText(/Stage 2: Report/)).toBeVisible();
  });

  test('renders friendly empty state when content is empty or only whitespace', () => {
    const { rerender } = render(<TaskBlueprintView content="" title="Empty Task" />);
    expect(screen.getByText(/No blueprint content available/i)).toBeVisible();

    rerender(<TaskBlueprintView content={'   \t  '} title="Empty Task" />);
    expect(screen.getByText(/No blueprint content available/i)).toBeVisible();

    rerender(<TaskBlueprintView content={'   \n   \n   '} title="Empty Task" />);
    expect(screen.getByText(/No blueprint content available/i)).toBeVisible();

    rerender(<TaskBlueprintView content={undefined} title="Empty Task" />);
    expect(screen.getByText(/No blueprint content available/i)).toBeVisible();
  });
});
