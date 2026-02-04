import imageCompression from "browser-image-compression";

export async function resizeImage(blob, maxWidth = 1024) {
  const img = document.createElement("img");
  const url = URL.createObjectURL(blob);
  img.src = url;
  await img.decode();

  // 2. Canvas로 리사이징
  const scale = Math.min(1, maxWidth / img.width);
  const canvas = document.createElement("canvas");
  canvas.width = img.width * scale;
  canvas.height = img.height * scale;
  const ctx = canvas.getContext("2d");
  ctx.drawImage(img, 0, 0, canvas.width, canvas.height);

  // 3. Canvas를 Blob으로 변환
  const resizedBlob = await new Promise((resolve) =>
    canvas.toBlob((b) => resolve(b), "image/jpeg", 0.9) // 품질 0.9
  );

  URL.revokeObjectURL(url);

  // 4. 브라우저 압축 라이브러리 적용 (1MB 이하 목표)
  const options = {
    maxSizeMB: 1,
    useWebWorker: true,
    fileType: "image/jpeg",
  };

  try {
    const compressedFile = await imageCompression(resizedBlob, options);
    return compressedFile;
  } catch (error) {
    console.error(error);
    return resizedBlob; // 압축 실패 시 리사이즈한 Blob 반환
  }
}
