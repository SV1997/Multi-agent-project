import {IsString, IsOptional} from 'class-validator'

export class QueryDTO {
  @IsString() query!: string;
  @IsString() sessionId!: string;
  @IsString() turnId!: string;
}