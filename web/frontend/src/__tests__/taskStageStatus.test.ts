import { describe, expect, test } from 'vitest';
import { classifyStageStatus } from '../components/TaskDashboard/types';

describe('classifyStageStatus', () => {
  test.each([
    ['', 'todo'],
    ['未开始', 'todo'],
    ['not started', 'todo'],
    ['已完成', 'done'],
    ['已完成 ✅', 'done'],
    ['DONE', 'done'],
    ['Done', 'done'],
    ['无需修改', 'done'],
    ['Complete', 'done'],
    ['Closed', 'done'],
    ['进行中', 'wip'],
    ['IN_PROGRESS', 'wip'],
    ['IN PROGRESS', 'wip'],
    ['等待 CI 中', 'wip'],
    ['PR 审核中', 'wip'],
    ['Blocked — waiting on review', 'wip'],
    // An unrecognized-but-non-empty status still counts as "started" rather
    // than silently invisible.
    ['Something the model made up', 'wip'],
  ])('classifies %j as %s', (status, expected) => {
    expect(classifyStageStatus(status)).toBe(expected);
  });
});
