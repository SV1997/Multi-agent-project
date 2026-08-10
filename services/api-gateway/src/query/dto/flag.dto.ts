import { Type } from "class-transformer";
import { IsIn, IsOptional, IsString, ValidateNested } from "class-validator";

type SourceType = "pdf" | "url" | "markdown";

class SourceItemDto {
    @IsString()
    path!: string;

    @IsIn(["pdf", "url", "markdown"], { message: "type must be either pdf, url, or markdown" })
    type!: SourceType;  
}

export class FlagDto {
    @IsString()
    answer!: string;

    @IsOptional()
    @IsString()
    reason?: string;

    @IsString()
    domain!:string;

    @ValidateNested({ each: true }) 
    @Type(() => SourceItemDto)
    source!: SourceItemDto[];
}