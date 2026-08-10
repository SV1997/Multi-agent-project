import { Controller, Get } from '@nestjs/common';
import { HealthCheckService, HealthCheck, PrismaHealthIndicator, HttpHealthIndicator } from '@nestjs/terminus';
import { SkipThrottle } from '@nestjs/throttler';
import { PrismaService } from 'src/prisma/prisma.service';
@Controller('health')
export class HealthController {
    constructor(
        private health: HealthCheckService,
        private http: HttpHealthIndicator,
        private prisma: PrismaHealthIndicator,
        private prismaService: PrismaService
    ){}
    @SkipThrottle()
    @Get()
    @HealthCheck()
    async healthCheck(){
        return this.health.check([
            () => this.prisma.pingCheck('database', this.prismaService, { timeout: 5000 })  // 5 seconds instead of default 1)
        ])
    }

}
