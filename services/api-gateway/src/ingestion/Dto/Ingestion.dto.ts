import { Type } from "class-transformer";
import { IsArray, IsIn, IsString, ValidateNested } from "class-validator";

type SourceType = "pdf" | "url" | "markdown";

class SourceItemDto {
    @IsString()
    path!: string;

    @IsIn(["pdf", "url", "markdown"], { message: "type must be either pdf, url, or markdown" })
    type!: SourceType;   // ✅ renamed to match Python's "type" field
}

export class IngestionDto {
    @IsString()
    namespace!: string;

    @IsArray()
    @ValidateNested({ each: true })   // ✅ also add { each: true } — see note below
    @Type(() => SourceItemDto)
    source!: SourceItemDto[];
}