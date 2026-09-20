import Taro from '@tarojs/taro';
import { API_BASE, STORAGE_KEYS } from '@/config';

// ==================== 多模态输入上传封装 ====================
// 语音识别 / 图片识别后端走 multipart 文件上传(Taro.uploadFile),
// 返回统一的 { text } 结构,前端再把 text 作为用户输入接入现有 SSE 问诊。

export interface RecognizeResult {
  text: string;
}

interface UploadFileOptions {
  url: string; // 已含 API_BASE 的路径(可带 query)
  filePath: string; // 本地临时文件路径
  name: string; // 表单字段名(audio / image)
}

/**
 * 通用文件上传 + 结果解析。
 * 兼容后端错误协议:4xx/5xx 时从 { detail } 提取可读错误信息。
 */
function uploadFile<T extends RecognizeResult>(opts: UploadFileOptions): Promise<T> {
  const token = Taro.getStorageSync(STORAGE_KEYS.TOKEN);
  return new Promise<T>((resolve, reject) => {
    Taro.uploadFile({
      url: `${API_BASE}${opts.url}`,
      filePath: opts.filePath,
      name: opts.name,
      header: token ? { Authorization: `Bearer ${token}` } : {},
      timeout: 120000,
      success: (res) => {
        if (res.statusCode >= 400) {
          let detail = `识别失败(${res.statusCode})`;
          try {
            const parsed = JSON.parse(res.data) as { detail?: string };
            if (parsed.detail) detail = parsed.detail;
          } catch {
            /* 非 JSON 错误体,用默认文案 */
          }
          reject(new Error(detail));
          return;
        }
        try {
          resolve(JSON.parse(res.data) as T);
        } catch {
          reject(new Error('识别结果解析失败,请重试'));
        }
      },
      fail: (err) => {
        const errMsg = (err as { errMsg?: string })?.errMsg || '';
        if (errMsg.includes('ERR_CONNECTION_REFUSED') || errMsg.includes('request:fail')) {
          reject(new Error(`无法连接后端服务 ${API_BASE}:请先启动后端再重试`));
        } else if (errMsg.includes('timeout')) {
          reject(new Error('识别超时,请重试'));
        } else {
          reject(new Error(errMsg || '上传失败'));
        }
      },
    });
  });
}

/**
 * 语音识别:录音文件 -> 文本
 */
export function recognizeSpeech(filePath: string): Promise<RecognizeResult> {
  return uploadFile<RecognizeResult>({ url: '/api/asr', filePath, name: 'audio' });
}

/**
 * 图片识别:图片文件 -> 文本(可选识别指令 prompt)
 */
export function recognizeImage(filePath: string, prompt?: string): Promise<RecognizeResult> {
  const qs = prompt ? `?prompt=${encodeURIComponent(prompt)}` : '';
  return uploadFile<RecognizeResult>({ url: `/api/vision${qs}`, filePath, name: 'image' });
}
