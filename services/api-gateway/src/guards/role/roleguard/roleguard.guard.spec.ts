import { Reflector } from '@nestjs/core';
import { RoleguardGuard } from './roleguard.guard';

describe('RoleguardGuard', () => {
  it('should be defined', () => {
    expect(new RoleguardGuard(new Reflector())).toBeDefined();
  });
});
