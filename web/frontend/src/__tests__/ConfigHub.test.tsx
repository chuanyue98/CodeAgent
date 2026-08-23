import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router';
import ConfigHub from '../components/ConfigHub';
import { ProjectProvider } from '../context/ProjectContext';
import { expect, test, describe } from 'vitest';

function renderConfigHub() {
  return render(
    <MemoryRouter>
      <ProjectProvider>
        <ConfigHub />
      </ProjectProvider>
    </MemoryRouter>
  );
}

describe('ConfigHub Component', () => {
  test('renders config data from context', async () => {
    renderConfigHub();

    await screen.findByText(/CodeAgent 在本地运行/);
  });

  test('preserves editable row identity when an earlier project is removed', async () => {
    renderConfigHub();
    await screen.findByText(/CodeAgent 在本地运行/, {}, { timeout: 3000 });

    fireEvent.click(screen.getByRole('button', { name: '添加工作区' }));
    fireEvent.click(screen.getByRole('button', { name: '添加工作区' }));

    const firstProject = screen.getByLabelText('工作区路径 1');
    const secondProject = screen.getByLabelText('工作区路径 2');
    fireEvent.change(firstProject, { target: { value: '/workspace/first' } });
    fireEvent.change(secondProject, { target: { value: '/workspace/second' } });

    fireEvent.click(screen.getByRole('button', { name: '移除工作区 /workspace/first' }));

    const remainingProject = screen.getByLabelText('工作区路径 1');
    expect(remainingProject).toBe(secondProject);
    expect(remainingProject).toHaveValue('/workspace/second');
  });

  test('blocks saving an empty project row', async () => {
    renderConfigHub();
    await screen.findByText(/CodeAgent 在本地运行/, {}, { timeout: 3000 });

    fireEvent.click(screen.getByRole('button', { name: '添加工作区' }));
    fireEvent.click(screen.getByRole('button', { name: '保存全部修改' }));

    expect(await screen.findByText(/工作区路径和资源组为必填项/)).toBeVisible();
  });
});
