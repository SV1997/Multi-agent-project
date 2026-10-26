import { Type } from "class-transformer";
import { IsArray, IsIn, IsOptional, IsString, Matches, ValidateNested } from "class-validator";

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

export class DocumentsQueryDto {
    @IsString()
    namespace!: string;
}

export class DocumentParamDto {
    // doc ids are hex hashes; this also keeps "#", "/" and ".." out of the id forwarded to the ingestion service
    @Matches(/^[A-Za-z0-9_-]{1,64}$/, { message: "docId is not a valid document id" })
    docId!: string;
}
