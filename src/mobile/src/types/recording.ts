export type Recording = {
  createdAt: string;
  durationMs: number;
  filePath: string;
  id: string;
  name: string;
  uploadingStatus: "to_upload" | "uploading" | "failed";
};
