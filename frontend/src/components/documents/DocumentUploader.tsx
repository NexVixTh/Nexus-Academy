import { useState, useRef, type DragEvent, type ChangeEvent } from "react";
import { api, ApiError } from "../../api/client";
import { useApp } from "../../context/AppContext";
import {
  UploadCloudIcon,
  CheckCircleIcon,
  AlertTriangleIcon,
  RefreshIcon,
  CloseIcon,
} from "../common/Icons";

const MAX_SIZE_BYTES = 20 * 1024 * 1024; // 20 MB

interface DocumentUploaderProps {
  onUploadSuccess?: (documentId: string) => void;
  compact?: boolean;
}

export function DocumentUploader({
  onUploadSuccess,
  compact = false,
}: DocumentUploaderProps) {
  const { refreshDocuments, selectDocument, addToast } = useApp();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [isDragging, setIsDragging] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [uploadSuccessInfo, setUploadSuccessInfo] = useState<{
    documentId: string;
    pages: number;
    records: number;
    filename: string;
  } | null>(null);

  const validateFile = (file: File): string | null => {
    const ext = file.name.substring(file.name.lastIndexOf(".")).toLowerCase();
    if (ext !== ".pdf" && ext !== ".pptx") {
      return "Unsupported file format. Please upload a PDF (.pdf) or PowerPoint (.pptx) file.";
    }
    if (file.size > MAX_SIZE_BYTES) {
      return "File exceeds the 20 MB size limit.";
    }
    if (file.size === 0) {
      return "The uploaded file is empty (0 bytes).";
    }
    return null;
  };

  const handleFile = (file: File) => {
    const error = validateFile(file);
    if (error) {
      setErrorMessage(error);
      setSelectedFile(null);
      return;
    }
    setErrorMessage(null);
    setUploadSuccessInfo(null);
    setSelectedFile(file);
  };

  const onDragOver = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const onDragLeave = () => {
    setIsDragging(false);
  };

  const onDrop = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      handleFile(e.dataTransfer.files[0]);
    }
  };

  const onFileInputChange = (e: ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      handleFile(e.target.files[0]);
    }
  };

  const handleUpload = async () => {
    if (!selectedFile || isUploading) return;
    setIsUploading(true);
    setErrorMessage(null);

    try {
      const response = await api.uploadDocument(selectedFile);
      setUploadSuccessInfo({
        documentId: response.document_id,
        pages: response.pages_or_slides_processed,
        records: response.records_created,
        filename: selectedFile.name,
      });
      setSelectedFile(null);
      addToast(`Successfully ingested "${selectedFile.name}"`, "success");

      await refreshDocuments();
      selectDocument(response.document_id);
      if (onUploadSuccess) {
        onUploadSuccess(response.document_id);
      }
    } catch (err) {
      if (err instanceof ApiError) {
        setErrorMessage(err.detail || err.message);
      } else {
        setErrorMessage("An unexpected network or server error occurred during ingestion.");
      }
      addToast("Document ingestion failed.", "error");
    } finally {
      setIsUploading(false);
    }
  };

  const formatFileSize = (bytes: number): string => {
    if (bytes < 1024 * 1024) {
      return `${(bytes / 1024).toFixed(1)} KB`;
    }
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  return (
    <div className={`uploader-root ${compact ? "uploader-compact" : ""}`}>
      {/* Hidden File Input */}
      <input
        ref={fileInputRef}
        type="file"
        accept=".pdf,.pptx,application/pdf,application/vnd.openxmlformats-officedocument.presentationml.presentation"
        style={{ display: "none" }}
        onChange={onFileInputChange}
      />

      {/* Drag & Drop Surface */}
      <div
        className={`dropzone ${isDragging ? "dropzone-active" : ""} ${
          selectedFile ? "dropzone-has-file" : ""
        }`}
        onDragOver={onDragOver}
        onDragLeave={onDragLeave}
        onDrop={onDrop}
        onClick={() => {
          if (!selectedFile && !isUploading) {
            fileInputRef.current?.click();
          }
        }}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => {
          if ((e.key === "Enter" || e.key === " ") && !selectedFile && !isUploading) {
            fileInputRef.current?.click();
          }
        }}
        aria-label="Upload document area"
      >
        <div className="dropzone-glow" />
        <div className="dropzone-inner">
          <span className="dropzone-icon" aria-hidden="true">
            <UploadCloudIcon className="w-8 h-8" />
          </span>

          {!selectedFile ? (
            <>
              <p className="dropzone-heading">
                Drag and drop your syllabus, textbook, or slide deck
              </p>
              <p className="dropzone-sub">
                Supports <strong className="text-cyan">PDF</strong> (searchable pages) and{" "}
                <strong className="text-violet">PPTX</strong> (presentation slides) up to 20 MB.
              </p>
              <button
                type="button"
                className="btn btn-secondary btn-sm dropzone-browse-btn"
                onClick={(e) => {
                  e.stopPropagation();
                  fileInputRef.current?.click();
                }}
              >
                Browse local files
              </button>
            </>
          ) : (
            <div className="selected-file-panel" onClick={(e) => e.stopPropagation()}>
              <div className="file-preview-card">
                <div className="file-badge">
                  {selectedFile.name.endsWith(".pdf") ? "PDF" : "PPTX"}
                </div>
                <div className="file-details">
                  <span className="file-name" title={selectedFile.name}>
                    {selectedFile.name}
                  </span>
                  <span className="file-size">{formatFileSize(selectedFile.size)}</span>
                </div>
                {!isUploading && (
                  <button
                    type="button"
                    className="file-remove-btn"
                    onClick={() => setSelectedFile(null)}
                    aria-label="Remove selected file"
                  >
                    <CloseIcon />
                  </button>
                )}
              </div>

              <div className="file-actions">
                <button
                  type="button"
                  className="btn btn-primary btn-md"
                  onClick={handleUpload}
                  disabled={isUploading}
                >
                  {isUploading ? (
                    <>
                      <RefreshIcon className="w-4 h-4 spin" />
                      <span>Ingesting & Extracting Concepts...</span>
                    </>
                  ) : (
                    <>
                      <UploadCloudIcon className="w-4 h-4" />
                      <span>Ingest into Knowledge Studio</span>
                    </>
                  )}
                </button>
                {!isUploading && (
                  <button
                    type="button"
                    className="btn btn-ghost btn-sm"
                    onClick={() => setSelectedFile(null)}
                  >
                    Cancel
                  </button>
                )}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Error Message */}
      {errorMessage && (
        <div className="alert-box alert-error" role="alert">
          <AlertTriangleIcon className="w-5 h-5 flex-shrink-0" />
          <div className="alert-content">
            <span className="alert-title">Ingestion Error</span>
            <p className="alert-desc">{errorMessage}</p>
          </div>
        </div>
      )}

      {/* Success Notification */}
      {uploadSuccessInfo && (
        <div className="alert-box alert-success" role="status">
          <CheckCircleIcon className="w-5 h-5 flex-shrink-0" />
          <div className="alert-content">
            <span className="alert-title">Document Ready for Tutoring</span>
            <p className="alert-desc">
              Ingested <strong>{uploadSuccessInfo.filename}</strong> with{" "}
              {uploadSuccessInfo.pages} source units ({uploadSuccessInfo.records} indexed records). Concepts have been mapped.
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
