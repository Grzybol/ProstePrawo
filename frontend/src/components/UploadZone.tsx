import { useCallback, useRef, useState } from 'react';
import { API_BASE_URL } from '../config';

interface UploadZoneProps {
  onUploadComplete: () => void;
}

const ACCEPTED_TYPES = ['.pdf', '.txt', '.md', '.docx'];

function UploadZone({ onUploadComplete }: UploadZoneProps) {
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isUploading, setIsUploading] = useState(false);

  const uploadFiles = useCallback(
    async (files: FileList | null) => {
      if (!files || files.length === 0) {
        return;
      }
      const file = files[0];
      const formData = new FormData();
      formData.append('file', file);
      setIsUploading(true);
      setError(null);
      try {
        const response = await fetch(`${API_BASE_URL}/documents/`, {
          method: 'POST',
          body: formData
        });
        if (!response.ok) {
          const message = await response.text();
          throw new Error(message || 'Nie udało się przesłać pliku.');
        }
        onUploadComplete();
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Nieznany błąd przesyłania.');
      } finally {
        setIsUploading(false);
        if (fileInputRef.current) {
          fileInputRef.current.value = '';
        }
      }
    },
    [onUploadComplete]
  );

  const handleDrop = useCallback(
    async (event: React.DragEvent<HTMLDivElement>) => {
      event.preventDefault();
      setIsDragging(false);
      await uploadFiles(event.dataTransfer.files);
    },
    [uploadFiles]
  );

  const handleSelectFile = useCallback(async () => {
    await uploadFiles(fileInputRef.current?.files ?? null);
  }, [uploadFiles]);

  return (
    <div className="upload-zone">
      <div
        className={`drop-area ${isDragging ? 'dragging' : ''}`}
        onDragOver={(event) => {
          event.preventDefault();
          setIsDragging(true);
        }}
        onDragLeave={() => setIsDragging(false)}
        onDrop={handleDrop}
      >
        <p>Przeciągnij dokument tutaj lub wybierz z dysku.</p>
        <button type="button" onClick={() => fileInputRef.current?.click()} disabled={isUploading}>
          {isUploading ? 'Przesyłanie...' : 'Wybierz plik'}
        </button>
        <p className="hint">Obsługiwane formaty: {ACCEPTED_TYPES.join(', ')}</p>
        <input
          ref={fileInputRef}
          type="file"
          accept={ACCEPTED_TYPES.join(',')}
          hidden
          onChange={handleSelectFile}
        />
      </div>
      {error && <p className="error-message">{error}</p>}
    </div>
  );
}

export default UploadZone;
