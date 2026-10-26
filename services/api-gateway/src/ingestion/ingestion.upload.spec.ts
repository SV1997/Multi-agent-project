import { createHash } from 'crypto';
import { of } from 'rxjs';
import { IngestionService } from './ingestion.service';

// the upload path needs Prisma and storage only through the mocks below; stub the real modules so nothing heavy loads
jest.mock('src/prisma/prisma.service', () => ({ PrismaService: class {} }));
jest.mock('src/storage/storage.service', () => ({ StorageService: class {} }));

const CONFIG: Record<string, string> = {
  INGESTION_URL: 'http://ingestion-service:8002/api/v1/ingest',
  INTERNAL_SECRET: 's3cret',
};

function makeService() {
  const http = { post: jest.fn().mockReturnValue(of({ data: { warnings: [] } })) };
  const config = { get: jest.fn((key: string) => CONFIG[key]) };
  const prisma = { ingestionLog: { create: jest.fn().mockResolvedValue({}) } };
  const storage = {
    uploadFile: jest.fn(async (_buffer: Buffer, name: string) => `bucket-key/${name}`),
    getPresignedUrl: jest.fn(async (key: string) => `http://seaweed:8333/${key}?X-Amz-Signature=abc`),
  };
  const service = new IngestionService(http as any, config as any, prisma as any, storage as any);
  return { service, http, storage };
}

const upload = (originalname: string) => ({ originalname, buffer: Buffer.from('file bytes') }) as any;
const dto = (extra: object = {}) => ({ namespace: 'hr', type: 'pdf', ...extra }) as any;
const sentSources = (http: { post: jest.Mock }) => http.post.mock.calls[0][1].source;

describe('IngestionService.uploadFile sends the uploaded file name', () => {
  it('passes the original name of each file to the ingestion service', async () => {
    const { service, http } = makeService();

    await service.uploadFile(dto(), [upload('Handbook.pdf'), upload('Leave Policy 2025.pdf')], 'hr_team', 7);

    expect(sentSources(http).map((s: any) => s.file_name)).toEqual(['Handbook.pdf', 'Leave Policy 2025.pdf']);
  });

  it('still stores the file under a uuid-prefixed key, so the url alone cannot be used as the name', async () => {
    const { service, http, storage } = makeService();

    await service.uploadFile(dto(), [upload('Handbook.pdf')], 'hr_team', 7);

    expect(storage.uploadFile.mock.calls[0][1]).toMatch(/^[0-9a-f-]{36}-Handbook\.pdf$/);
    expect(sentSources(http)[0].path).toContain('Handbook.pdf?X-Amz-Signature=abc');
    expect(sentSources(http)[0].file_name).toBe('Handbook.pdf');
  });

  it('keeps the other source fields exactly as before', async () => {
    const { service, http } = makeService();

    await service.uploadFile(dto({ document_type: 'policy' }), [upload('  Handbook.PDF ')], 'hr_team', 7);

    const expectedDocId = createHash('sha1').update('hr/handbook.pdf').digest('hex').slice(0, 16);
    expect(sentSources(http)[0]).toMatchObject({ type: 'pdf', doc_id: expectedDocId, document_type: 'policy' });
    expect(http.post.mock.calls[0][1].namespace).toBe('hr');
  });
});
