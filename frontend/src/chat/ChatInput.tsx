import {
  ClipboardEvent,
  ChangeEvent,
  DragEvent,
  FormEvent,
  KeyboardEvent,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

interface ChatInputProps {
  onSend: (message: string, files: File[]) => Promise<void> | void;
  disabled: boolean;
}

interface PendingAttachment {
  id: string;
  file: File;
  previewUrl: string | null;
}

const MAX_IMAGES = 3;
const MAX_DOCUMENTS = 2;
const MAX_TOTAL_FILES = MAX_IMAGES + MAX_DOCUMENTS;
const IMAGE_EXTENSIONS = [".png", ".jpg", ".jpeg", ".gif", ".webp"];
const DOCUMENT_EXTENSIONS = [".pdf", ".txt", ".py", ".js", ".ts", ".csv", ".ipynb"];
const MAX_IMAGE_BYTES = 5 * 1024 * 1024;
const MAX_DOCUMENT_BYTES = 2 * 1024 * 1024;

function getFileKind(file: File): "image" | "document" | "unsupported" {
  const ext = extensionOf(file.name);
  if (IMAGE_EXTENSIONS.includes(ext)) return "image";
  if (DOCUMENT_EXTENSIONS.includes(ext)) return "document";
  return "unsupported";
}

function extensionOf(filename: string): string {
  const idx = filename.lastIndexOf(".");
  if (idx < 0) return "";
  return filename.slice(idx).toLowerCase();
}

function validateFile(file: File): string | null {
  const fileKind = getFileKind(file);
  if (fileKind === "image") {
    if (file.size > MAX_IMAGE_BYTES) {
      return `File "${file.name}" is too large.`;
    }
    return null;
  }

  if (fileKind === "document") {
    if (file.size > MAX_DOCUMENT_BYTES) {
      return `File "${file.name}" is too large.`;
    }
    return null;
  }

  return `Unsupported file type: ${file.name}.`;
}

function createAttachment(file: File): PendingAttachment {
  const ext = extensionOf(file.name);
  const isImage = IMAGE_EXTENSIONS.includes(ext);
  return {
    id: `${file.name}-${file.size}-${Math.random().toString(36).slice(2, 10)}`,
    file,
    previewUrl: isImage ? URL.createObjectURL(file) : null,
  };
}

export function ChatInput({ onSend, disabled }: ChatInputProps) {
  const [text, setText] = useState("");
  const [attachments, setAttachments] = useState<PendingAttachment[]>([]);
  const [error, setError] = useState("");
  const [isSending, setIsSending] = useState(false);
  const [isDragging, setIsDragging] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const attachmentsRef = useRef<PendingAttachment[]>([]);

  const effectiveDisabled = disabled || isSending;
  const canSend = useMemo(
    () => text.trim().length > 0 || attachments.length > 0,
    [text, attachments]
  );

  useEffect(() => {
    attachmentsRef.current = attachments;
  }, [attachments]);

  useEffect(() => {
    return () => {
      for (const attachment of attachmentsRef.current) {
        if (attachment.previewUrl) {
          URL.revokeObjectURL(attachment.previewUrl);
        }
      }
    };
  }, []);

  const addFiles = (incomingFiles: File[]) => {
    if (incomingFiles.length === 0) return;
    setError("");

    let imageCount = attachments.filter(
      (item) => getFileKind(item.file) === "image"
    ).length;
    let documentCount = attachments.filter(
      (item) => getFileKind(item.file) === "document"
    ).length;

    const newAttachments: PendingAttachment[] = [];
    for (const file of incomingFiles) {
      const validationError = validateFile(file);
      if (validationError) {
        setError(validationError);
        for (const item of newAttachments) {
          if (item.previewUrl) URL.revokeObjectURL(item.previewUrl);
        }
        return;
      }

      const kind = getFileKind(file);
      if (kind === "image") {
        imageCount += 1;
      } else if (kind === "document") {
        documentCount += 1;
      }
      if (imageCount > MAX_IMAGES || documentCount > MAX_DOCUMENTS) {
        setError(
          `Too many files. You can upload up to ${MAX_IMAGES} photos and ${MAX_DOCUMENTS} files per message.`
        );
        for (const item of newAttachments) {
          if (item.previewUrl) URL.revokeObjectURL(item.previewUrl);
        }
        return;
      }
      newAttachments.push(createAttachment(file));
    }

    if (attachments.length + newAttachments.length > MAX_TOTAL_FILES) {
      setError(
        `Too many files. You can upload up to ${MAX_IMAGES} photos and ${MAX_DOCUMENTS} files per message.`
      );
      for (const item of newAttachments) {
        if (item.previewUrl) URL.revokeObjectURL(item.previewUrl);
      }
      return;
    }

    setAttachments((prev) => [...prev, ...newAttachments]);
  };

  const removeAttachment = (id: string) => {
    setAttachments((prev) => {
      const found = prev.find((item) => item.id === id);
      if (found?.previewUrl) {
        URL.revokeObjectURL(found.previewUrl);
      }
      return prev.filter((item) => item.id !== id);
    });
  };

  const resetAfterSend = () => {
    setText("");
    setError("");
    setAttachments((prev) => {
      for (const item of prev) {
        if (item.previewUrl) URL.revokeObjectURL(item.previewUrl);
      }
      return [];
    });
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
    }
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  };

  const handleSubmit = async (e?: FormEvent) => {
    e?.preventDefault();
    if (!canSend || effectiveDisabled) return;

    try {
      setIsSending(true);
      await onSend(
        text.trim(),
        attachments.map((item) => item.file)
      );
      resetAfterSend();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to send message.");
    } finally {
      setIsSending(false);
    }
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      void handleSubmit();
    }
  };

  const handleInput = () => {
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
      textareaRef.current.style.height = `${Math.min(
        textareaRef.current.scrollHeight,
        200
      )}px`;
    }
  };

  const handleFileInputChange = (e: ChangeEvent<HTMLInputElement>) => {
    const selectedFiles = Array.from(e.target.files ?? []);
    addFiles(selectedFiles);
  };

  const handleDragOver = (e: DragEvent<HTMLFormElement>) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = (e: DragEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (e.currentTarget === e.target) {
      setIsDragging(false);
    }
  };

  const handleDrop = (e: DragEvent<HTMLFormElement>) => {
    e.preventDefault();
    setIsDragging(false);
    if (effectiveDisabled) return;
    const droppedFiles = Array.from(e.dataTransfer.files ?? []);
    addFiles(droppedFiles);
  };

  const handlePaste = (e: ClipboardEvent<HTMLTextAreaElement>) => {
    if (effectiveDisabled) return;

    // Support quick screenshot paste from clipboard.
    const clipboardFiles: File[] = [];
    for (const item of Array.from(e.clipboardData.items)) {
      if (item.kind === "file" && item.type.startsWith("image/")) {
        const file = item.getAsFile();
        if (file) clipboardFiles.push(file);
      }
    }
    if (clipboardFiles.length > 0) {
      addFiles(clipboardFiles);
    }
  };

  return (
    <form
      onSubmit={handleSubmit}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
      className={`border-t border-gray-200 p-4 bg-white ${
        isDragging ? "ring-2 ring-accent ring-inset" : ""
      }`}
    >
      {attachments.length > 0 && (
        <div className="mb-3 flex flex-wrap gap-2">
          {attachments.map((attachment) => {
            const isImage = attachment.previewUrl !== null;
            return (
              <div
                key={attachment.id}
                className="relative rounded-md border border-gray-200 bg-gray-50 p-2 pr-7"
              >
                {isImage ? (
                  <img
                    src={attachment.previewUrl ?? ""}
                    alt={attachment.file.name}
                    className="h-16 w-20 rounded object-cover"
                  />
                ) : (
                  <p className="text-xs text-gray-700 max-w-[180px] truncate">
                    {attachment.file.name}
                  </p>
                )}
                <button
                  type="button"
                  onClick={() => removeAttachment(attachment.id)}
                  className="absolute right-1 top-1 text-gray-400 hover:text-gray-700"
                  aria-label="Remove attachment"
                >
                  ×
                </button>
              </div>
            );
          })}
        </div>
      )}

      <div className="flex items-end gap-3">
        <input
          ref={fileInputRef}
          type="file"
          multiple
          onChange={handleFileInputChange}
          className="hidden"
          accept=".png,.jpg,.jpeg,.gif,.webp,.pdf,.txt,.py,.js,.ts,.csv,.ipynb"
        />
        <button
          type="button"
          onClick={() => fileInputRef.current?.click()}
          disabled={effectiveDisabled || attachments.length >= MAX_TOTAL_FILES}
          className="h-10 w-10 rounded-lg border border-gray-300 text-gray-600 hover:bg-gray-100 disabled:opacity-50"
          title="Attach files"
        >
          <svg
            className="mx-auto h-5 w-5"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M15.172 7l-6.586 6.586a2 2 0 102.828 2.828L18 9.828a4 4 0 10-5.656-5.656L5.757 10.76a6 6 0 108.486 8.486L20.5 13"
            />
          </svg>
        </button>

        <textarea
          ref={textareaRef}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={handleKeyDown}
          onInput={handleInput}
          onPaste={handlePaste}
          placeholder="Ask a question... (Shift+Enter for new line)"
          rows={1}
          disabled={effectiveDisabled}
          className="flex-1 resize-none border border-gray-300 rounded-lg px-4 py-2.5 focus:outline-none focus:ring-2 focus:ring-accent disabled:opacity-50"
        />

        <button
          type="submit"
          disabled={effectiveDisabled || !canSend}
          className="bg-accent text-brand font-medium px-5 py-2.5 rounded-lg hover:bg-accent-dark focus:outline-none focus:ring-2 focus:ring-accent disabled:opacity-50 whitespace-nowrap"
        >
          {isSending ? "Sending..." : "Send"}
        </button>
      </div>

      {error && <p className="mt-2 text-sm text-red-600">{error}</p>}
      <p className="mt-1 text-xs text-gray-400">
        Drag and drop files, or paste screenshots with Ctrl+V (up to 3 photos and 2 files).
      </p>
    </form>
  );
}
