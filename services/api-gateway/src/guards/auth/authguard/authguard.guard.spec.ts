import { JwtService } from '@nestjs/jwt';
import { AuthguardGuard } from './authguard.guard';

describe('AuthguardGuard', () => {
  it('should be defined', () => {
    expect(new AuthguardGuard(new JwtService())).toBeDefined();
  });
});
