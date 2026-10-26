import { ForbiddenException, HttpException, InternalServerErrorException } from '@nestjs/common';
import { of, throwError } from 'rxjs';
import { IngestionService } from './ingestion.service';

// the service only needs Prisma and storage for ingestion; stub them so these tests load nothing heavy
jest.mock('src/prisma/prisma.service', () => ({ PrismaService: class {} }));
jest.mock('src/storage/storage.service', () => ({ StorageService: class {} }));

const CONFIG: Record<string, string> = {
  INGESTION_URL: 'http://ingestion-service:8002/api/v1/ingest',
  INTERNAL_SECRET: 's3cret',
};

function makeService() {
  const http = { get: jest.fn(), delete: jest.fn() };
  const config = { get: jest.fn((key: string) => CONFIG[key]) };
  const service = new IngestionService(http as any, config as any, {} as any, {} as any);
  return { service, http };
}

const axiosError = (status?: number, data?: unknown) =>
  Object.assign(new Error('request failed'), {
    code: status ? undefined : 'ECONNREFUSED',
    response: status ? { status, data } : undefined,
  });

describe('IngestionService documents', () => {
  describe('listDocuments', () => {
    it('calls the sibling /documents URL with the namespace and the internal secret', async () => {
      const { service, http } = makeService();
      http.get.mockReturnValue(of({ data: { namespace: 'hr', documents: [{ doc_id: 'a1' }] } }));

      const result = await service.listDocuments('hr', 'hr_team');

      expect(http.get).toHaveBeenCalledWith('http://ingestion-service:8002/api/v1/documents', {
        params: { namespace: 'hr' },
        headers: { 'x-internal-secret': 's3cret' },
      });
      expect(result).toEqual({ namespace: 'hr', documents: [{ doc_id: 'a1' }] });
    });

    it('refuses a namespace the role cannot access, without calling the ingestion service', async () => {
      const { service, http } = makeService();
      await expect(service.listDocuments('legal', 'hr_team')).rejects.toBeInstanceOf(ForbiddenException);
      await expect(service.listDocuments('hr', 'guest')).rejects.toBeInstanceOf(ForbiddenException);
      expect(http.get).not.toHaveBeenCalled();
    });

    it('lets an admin list every namespace', async () => {
      const { service, http } = makeService();
      http.get.mockReturnValue(of({ data: { documents: [] } }));
      for (const ns of ['legal', 'hr', 'engineering', 'finance', 'support']) {
        await service.listDocuments(ns, 'admin');
      }
      expect(http.get).toHaveBeenCalledTimes(5);
    });
  });

  describe('deleteDocument', () => {
    it('deletes by id within the namespace and reports success', async () => {
      const { service, http } = makeService();
      http.delete.mockReturnValue(of({ data: { chunks_deleted: 4 } }));

      const result = await service.deleteDocument('abc123', 'legal', 'legal_team', 7);

      expect(http.delete).toHaveBeenCalledWith('http://ingestion-service:8002/api/v1/documents/abc123', {
        params: { namespace: 'legal' },
        headers: { 'x-internal-secret': 's3cret' },
      });
      expect(result).toEqual({ success: true, data: { chunks_deleted: 4 } });
    });

    it('url-encodes the document id so it cannot change the path', async () => {
      const { service, http } = makeService();
      http.delete.mockReturnValue(of({ data: {} }));
      await service.deleteDocument('a/../b', 'hr', 'hr_team', 1);
      expect(http.delete.mock.calls[0][0]).toBe('http://ingestion-service:8002/api/v1/documents/a%2F..%2Fb');
    });

    it('refuses a namespace the role cannot access, without calling the ingestion service', async () => {
      const { service, http } = makeService();
      await expect(service.deleteDocument('abc123', 'finance', 'hr_team', 1)).rejects.toBeInstanceOf(ForbiddenException);
      expect(http.delete).not.toHaveBeenCalled();
    });

    it('passes a 404 from the ingestion service through with its message', async () => {
      const { service, http } = makeService();
      http.delete.mockReturnValue(throwError(() => axiosError(404, { detail: 'No document abc123 found in the hr namespace' })));

      const err = await service.deleteDocument('abc123', 'hr', 'hr_team', 1).catch((e) => e);

      expect(err).toBeInstanceOf(HttpException);
      expect(err.getStatus()).toBe(404);
      expect(err.message).toBe('No document abc123 found in the hr namespace');
    });

    it('hides internal details when the ingestion service is unreachable', async () => {
      const { service, http } = makeService();
      http.delete.mockReturnValue(throwError(() => axiosError()));

      await expect(service.deleteDocument('abc123', 'hr', 'hr_team', 1)).rejects.toBeInstanceOf(InternalServerErrorException);
    });
  });
});
