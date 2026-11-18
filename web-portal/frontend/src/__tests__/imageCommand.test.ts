import { describe, expect, it } from 'vitest';
import { imageCommand } from '../components/instructor/LabImageTab';

describe('imageCommand: command the container runs when Entrypoint is left empty', () => {
  it('joins ENTRYPOINT then CMD like Docker does', () => {
    expect(imageCommand({ entrypoint: ['/usr/bin/entrypoint.sh', '--bind-addr', '0.0.0.0:8080'], cmd: ['.'] }))
      .toBe('/usr/bin/entrypoint.sh --bind-addr 0.0.0.0:8080 .');
  });

  it('quotes arguments that contain spaces (shell-form CMD)', () => {
    expect(imageCommand({ entrypoint: [], cmd: ['/bin/sh', '-c', 'npm run dev'] })).toBe('/bin/sh -c "npm run dev"');
  });

  it('says (none) when the image sets neither', () => {
    expect(imageCommand({ entrypoint: [], cmd: [] })).toBe('(none)');
  });

  it('is unknown (undefined) for an old runner result or no scan yet', () => {
    expect(imageCommand(undefined)).toBeUndefined();
    expect(imageCommand({ exposedPorts: [8080] })).toBeUndefined();
  });
});
