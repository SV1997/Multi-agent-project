import { ArgumentsHost, Catch, ExceptionFilter,HttpException, HttpStatus } from '@nestjs/common';
import { Response, Request } from 'express';

@Catch()
export class HttpExceptionFilter implements ExceptionFilter {
  catch(exception: HttpException, host: ArgumentsHost) {
    const ctx = host.switchToHttp();
    const res = ctx.getResponse<Response>();
    const req = ctx.getRequest<Request>();


    const status = exception instanceof HttpException? exception.getStatus():HttpStatus.INTERNAL_SERVER_ERROR

    const message = exception instanceof HttpException? exception.message:"Internal Server Error"

    res.status(status).json({
      statusCode: status,
      timestamp: new Date().toISOString(),
      path: req.url,
      message: message
    })

  }
}
