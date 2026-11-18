import { describe, expect, it, vi } from 'vitest';
import { act, fireEvent, render, screen } from '@testing-library/react';
import LabImageForm, { countAdvancedFilled } from '../components/instructor/LabImageForm';
import UploadTray, { useWarnBeforeUnload } from '../components/UploadTray';
import { renderHook } from '@testing-library/react';

const tarFile = () => new File(['tar'], 'web.tar', { type: 'application/x-tar' });

function renderForm() {
  const onSubmit = vi.fn();
  const view = render(<LabImageForm courseId="course-1" submitting={false} onSubmit={onSubmit} onCancel={vi.fn()} />);
  const fileInput = view.container.querySelector('input[type="file"]') as HTMLInputElement;
  fireEvent.change(fileInput, { target: { files: [tarFile()] } });
  fireEvent.change(screen.getByLabelText(/Repository/), { target: { value: 'web' } });
  return { onSubmit, ...view };
}

const submit = async () => {
  await act(async () => {
    fireEvent.click(screen.getByRole('button', { name: 'Upload image' }));
  });
};

describe('LabImageForm: Advanced settings are optional', () => {
  it('Advanced is collapsed by default', () => {
    renderForm();
    expect(screen.getByRole('button', { name: /Advanced settings/ }).getAttribute('aria-expanded')).toBe('false');
    expect(document.getElementById('img-advanced')?.className).toContain('hidden');
  });

  it('submitting with Advanced untouched sends no ports / entrypoint / workdir / env (= use the image values)', async () => {
    const { onSubmit } = renderForm();
    await submit();

    expect(onSubmit).toHaveBeenCalledTimes(1);
    const [payload] = onSubmit.mock.calls[0];
    expect(payload).toMatchObject({
      repository: 'vlab/web',
      exposedPorts: [],
      entrypointScript: null,
      workdir: null,
      envVars: null,
    });
  });

  it('values typed in Advanced are sent trimmed', async () => {
    const { onSubmit } = renderForm();
    fireEvent.click(screen.getByRole('button', { name: /Advanced settings/ }));
    fireEvent.change(screen.getByLabelText('Entrypoint'), { target: { value: '  /bin/bash /run.sh ' } });
    fireEvent.change(screen.getByLabelText('Exposed ports'), { target: { value: '8080, 5173' } });
    fireEvent.change(screen.getByLabelText('Working directory'), { target: { value: '/workspace' } });
    await submit();

    expect(onSubmit.mock.calls[0][0]).toMatchObject({
      entrypointScript: '/bin/bash /run.sh',
      exposedPorts: [8080, 5173],
      workdir: '/workspace',
    });
  });

  it('an error inside the collapsed Advanced section opens it instead of failing silently', async () => {
    const { onSubmit } = renderForm();
    const toggle = screen.getByRole('button', { name: /Advanced settings/ });
    fireEvent.click(toggle);
    fireEvent.change(screen.getByLabelText('Working directory'), { target: { value: 'workspace' } });
    fireEvent.click(toggle); // พับกลับ
    await submit();

    expect(onSubmit).not.toHaveBeenCalled();
    expect(toggle.getAttribute('aria-expanded')).toBe('true');
    expect(screen.getByText('Use a full path that starts with /')).toBeDefined();
  });

  it('the collapsed header counts the fields that are set', () => {
    expect(countAdvancedFilled({ entrypointScript: '', exposedPorts: ' ', workdir: '', envVars: [] })).toBe(0);
    expect(
      countAdvancedFilled({ entrypointScript: 'x', exposedPorts: '8080', workdir: '', envVars: [{ key: 'A', value: '' }] }),
    ).toBe(3);
  });
});

describe('UploadTray', () => {
  it('renders nothing when there is no upload', () => {
    const { container } = render(<UploadTray />);
    expect(container.innerHTML).toBe('');
  });

  it('warns before the tab is closed only while an upload is running', () => {
    const { rerender, unmount } = renderHook(({ active }) => useWarnBeforeUnload(active), {
      initialProps: { active: true },
    });
    const event = new Event('beforeunload', { cancelable: true });
    window.dispatchEvent(event);
    expect(event.defaultPrevented).toBe(true);

    rerender({ active: false });
    const later = new Event('beforeunload', { cancelable: true });
    window.dispatchEvent(later);
    expect(later.defaultPrevented).toBe(false);
    unmount();
  });
});
