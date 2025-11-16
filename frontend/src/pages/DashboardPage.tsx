import { useCallback, useEffect, useRef, useState } from 'react';
import UploadZone from '../components/UploadZone';
import DocumentList from '../components/DocumentList';
import { API_BASE_URL } from '../config';
import type { DocumentListItem } from '../types';

const POLLING_INTERVAL_MS = 5000;

function DashboardPage() {
  const [documents, setDocuments] = useState<DocumentListItem[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const isLoadingRef = useRef(false);

  const loadDocuments = useCallback(async () => {
    if (isLoadingRef.current) {
      return;
    }
    isLoadingRef.current = true;
    setIsLoading(true);
    try {
      const response = await fetch(`${API_BASE_URL}/documents/`, {
        credentials: 'include'
      });
      if (!response.ok) {
        throw new Error('Nie udało się pobrać dokumentów.');
      }
      const data: DocumentListItem[] = await response.json();
      setDocuments(data);
    } catch (error) {
      console.error(error);
    } finally {
      setIsLoading(false);
      isLoadingRef.current = false;
    }
  }, []);

  useEffect(() => {
    void loadDocuments();
  }, [loadDocuments]);

  useEffect(() => {
    const shouldPoll = documents.some(
      (document) => document.status === 'processing' || document.status === 'received'
    );

    if (!shouldPoll) {
      return undefined;
    }

    const intervalId = window.setInterval(() => {
      if (!isLoadingRef.current) {
        void loadDocuments();
      }
    }, POLLING_INTERVAL_MS);

    return () => {
      window.clearInterval(intervalId);
    };
  }, [documents, loadDocuments]);

  return (
    <div className="dashboard">
      <section className="panel">
        <h1>Panel dokumentów</h1>
        <p>
          Prześlij dokument aby uruchomić przetwarzanie. Analiza odbywa się lokalnie w środowisku PoC, dlatego odświeżaj
          listę, aby obserwować status.
        </p>
        <UploadZone onUploadComplete={loadDocuments} />
      </section>
      <DocumentList documents={documents} isLoading={isLoading} onRefresh={loadDocuments} />
    </div>
  );
}

export default DashboardPage;
