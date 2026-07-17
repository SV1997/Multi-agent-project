import { CanActivate, ExecutionContext, Injectable, UnauthorizedException } from '@nestjs/common';
import { Observable } from 'rxjs';
import { JwtService } from '@nestjs/jwt';
@Injectable()
export class AuthguardGuard implements CanActivate {
  constructor(private jwtService: JwtService) { }
  canActivate(
    context: ExecutionContext,
  ): boolean | Promise<boolean> | Observable<boolean> {
    const request = context.switchToHttp().getRequest();
    const header = request.headers["authorization"]
    if (!header) {
      throw new UnauthorizedException('No token available')
    }
    try {
      const token = header.split(" ")[1];
      console.log(token)
      const payload = this.jwtService.verify(token);
      request.user = payload;
      return true
    }
    catch {
      throw new UnauthorizedException("invalid token")
    }
  }
}
