import { useState, useRef } from "react";
import { Button } from "@/components/ui/button";
import { Upload, X, Image as ImageIcon } from "lucide-react";

interface FileUploadProps {
  label: string;
  onFileSelect: (file: File | null) => void;
  accept?: string;
  id: string;
}

export function FileUpload({ label, onFileSelect, accept = "image/*", id }: FileUploadProps) {
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selected = e.target.files?.[0];
    if (selected) {
      setFile(selected);
      const objectUrl = URL.createObjectURL(selected);
      setPreview(objectUrl);
      onFileSelect(selected);
    }
  };

  const handleClear = () => {
    setFile(null);
    setPreview(null);
    if (inputRef.current) inputRef.current.value = "";
    onFileSelect(null);
  };

  return (
    <div className="w-full">
      <p className="text-sm font-medium mb-2 text-primary">{label}</p>
      
      {!file ? (
        <div 
          className="border-2 border-dashed border-border rounded-xl p-6 flex flex-col items-center justify-center bg-muted/30 hover:bg-muted/50 transition-colors cursor-pointer"
          onClick={() => inputRef.current?.click()}
        >
          <div className="w-12 h-12 rounded-full bg-primary/10 flex items-center justify-center text-primary mb-3">
            <Upload className="w-6 h-6" />
          </div>
          <p className="text-sm font-medium text-primary">انقر لاختيار ملف</p>
          <p className="text-xs text-muted-foreground mt-1">JPG, PNG (الحد الأقصى 5MB)</p>
          <input
            id={id}
            type="file"
            ref={inputRef}
            onChange={handleFileChange}
            accept={accept}
            className="hidden"
          />
        </div>
      ) : (
        <div className="border border-border rounded-xl p-3 flex items-center justify-between bg-card">
          <div className="flex items-center gap-3 overflow-hidden">
            {preview ? (
              <div className="w-12 h-12 rounded bg-muted overflow-hidden flex-shrink-0">
                <img src={preview} alt="Preview" className="w-full h-full object-cover" />
              </div>
            ) : (
              <div className="w-12 h-12 rounded bg-muted flex items-center justify-center text-muted-foreground flex-shrink-0">
                <ImageIcon className="w-6 h-6" />
              </div>
            )}
            <div className="overflow-hidden">
              <p className="text-sm font-medium truncate">{file.name}</p>
              <p className="text-xs text-muted-foreground">{(file.size / 1024 / 1024).toFixed(2)} MB</p>
            </div>
          </div>
          <Button variant="ghost" size="icon" onClick={handleClear} className="text-muted-foreground hover:text-destructive flex-shrink-0">
            <X className="w-4 h-4" />
          </Button>
        </div>
      )}
    </div>
  );
}
