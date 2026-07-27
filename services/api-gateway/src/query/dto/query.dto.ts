import {IsString, IsOptional} from 'class-validator'

// query.dto.ts
export class QueryDTO {
  @IsString() query!: string;
  @IsString() sessionId!: string;
}