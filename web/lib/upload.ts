// 올릴 파일 준비. Vercel 함수는 요청 본문이 4.5MB까지라, 사진은 브라우저에서 줄여 JPEG로 보낸다.
// (서버의 image_prep이 다시 회전·크기·EXIF 정리를 한다.)

export const MAX_PDF_BYTES = 3 * 1024 * 1024;
const LONG_SIDE = 2000;
const JPEG_QUALITY = 0.88;

export interface Prepared {
  b64: string;
  filename: string;
  kind: "image" | "pdf";
  previewUrl: string | null;
}

export class UploadError extends Error {}

function toBase64(buf: ArrayBuffer): string {
  const bytes = new Uint8Array(buf);
  let s = "";
  for (let i = 0; i < bytes.length; i += 0x8000) s += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  return btoa(s);
}

async function shrinkImage(file: File): Promise<Blob> {
  let bitmap: ImageBitmap;
  try {
    bitmap = await createImageBitmap(file, { imageOrientation: "from-image" });
  } catch {
    throw new UploadError("이 사진은 열 수 없어요. 스크린샷을 찍거나 JPG로 바꿔 올려 주세요.");
  }
  const scale = Math.min(1, LONG_SIDE / Math.max(bitmap.width, bitmap.height));
  const canvas = document.createElement("canvas");
  canvas.width = Math.round(bitmap.width * scale);
  canvas.height = Math.round(bitmap.height * scale);
  canvas.getContext("2d")!.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
  bitmap.close();
  return new Promise((resolve, reject) =>
    canvas.toBlob((b) => (b ? resolve(b) : reject(new UploadError("사진을 준비하지 못했어요. 다른 사진으로 해 주세요."))), "image/jpeg", JPEG_QUALITY),
  );
}

export async function prepareFile(file: File): Promise<Prepared> {
  const isPdf = file.type === "application/pdf" || file.name.toLowerCase().endsWith(".pdf");
  if (isPdf) {
    if (file.size > MAX_PDF_BYTES) throw new UploadError("PDF가 3MB를 넘어요. 계약서 쪽만 사진으로 찍어 올려 주세요.");
    return { b64: toBase64(await file.arrayBuffer()), filename: file.name, kind: "pdf", previewUrl: null };
  }
  if (!file.type.startsWith("image/") && !/\.(jpe?g|png|heic|heif|webp)$/i.test(file.name)) {
    throw new UploadError("사진(JPG·PNG)이나 PDF만 올릴 수 있어요.");
  }
  const blob = await shrinkImage(file);
  return {
    b64: toBase64(await blob.arrayBuffer()),
    filename: file.name.replace(/\.[^.]+$/, "") + ".jpg",
    kind: "image",
    previewUrl: URL.createObjectURL(blob),
  };
}
