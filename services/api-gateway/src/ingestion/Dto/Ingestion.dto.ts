import { Type } from "class-transformer";
import { IsArray, IsIn, IsOptional, IsString, ValidateNested } from "class-validator";

type SourceType = "pdf" | "url" | "markdown";
const DOCUMENT_TYPES = ["contract", "regulation", "policy"] as const;
type DocumentType = typeof DOCUMENT_TYPES[number];
type SourceType2 = "pdf" | "markdown";
class SourceItemDto {
    @IsString()
    path!: string;

    @IsIn(["pdf", "url", "markdown"], { message: "type must be either pdf, url, or markdown" })
    type!: SourceType;   // ✅ renamed to match Python's "type" field

    @IsOptional()
    @IsIn(DOCUMENT_TYPES, { message: "document_type must be contract, regulation or policy" })
    document_type?: DocumentType;
}

export class IngestionDto {
    @IsString()
    namespace!: string;

    @IsArray()
    @ValidateNested({ each: true })   // ✅ also add { each: true } — see note below
    @Type(() => SourceItemDto)
    source!: SourceItemDto[];
}

export class UploadIngestionDto {
    @IsString()
    namespace!: string
    @IsIn(["pdf", "markdown"], { message: "type must be either pdf or markdown" })
    type!: SourceType2
    // One document_type for the whole upload: when several files are sent together it applies to every file.
    @IsOptional()
    @IsIn(DOCUMENT_TYPES, { message: "document_type must be contract, regulation or policy" })
    document_type?: DocumentType
    // no `source` field — the file itself replaces it, comes via @UploadedFile()
}