"""PDF 选页预览：内存中渲染，不执行文档脚本、不把整份文件发给模型。"""
import base64
import binascii
import io
import re
import threading

import pypdfium2 as pdfium

MAX_FILE = 20 * 1024 * 1024
MAX_PAGES = 100
_pdf_lock = threading.Lock()  # PDFium 不允许跨线程并发调用。


def preview_pdf(data_url, page_number=1):
    if type(page_number) is not int or page_number < 1:
        raise ValueError('请选择有效的 PDF 页码。')
    if not isinstance(data_url, str) or len(data_url) > 28_000_000:
        raise ValueError('PDF 请小于 20 MB。')
    match = re.fullmatch(r'data:application/pdf;base64,([A-Za-z0-9+/=]+)', data_url)
    if not match:
        raise ValueError('请选择 PDF 文件。')
    try:
        raw = base64.b64decode(match.group(1), validate=True)
    except binascii.Error:
        raise ValueError('PDF 没有读完整，请重新选择。') from None
    if len(raw) > MAX_FILE:
        raise ValueError('PDF 请小于 20 MB。')
    if not raw.lstrip().startswith(b'%PDF-'):
        raise ValueError('文件内容不是有效的 PDF，请重新选择。')
    try:
        with _pdf_lock, pdfium.PdfDocument(raw) as document:
            count = len(document)
            if not 1 <= count <= MAX_PAGES:
                raise ValueError('当前支持 1–100 页的 PDF，请拆分后再上传。')
            if page_number > count:
                raise ValueError(f'这份 PDF 共 {count} 页，请重新选择页码。')
            page = document[page_number - 1]
            try:
                width, height = page.get_size()
                if min(width,height) < 16 or max(width,height) > 14400:
                    raise ValueError('这一页的尺寸不适合识别，请换一页或上传截图。')
                bitmap = page.render(scale=min(2000/max(width,height), 3), draw_annots=False)
                try:
                    image = bitmap.to_pil().convert('RGB')
                    output = io.BytesIO()
                    image.save(output, format='JPEG', quality=90)
                finally:
                    bitmap.close()
            finally:
                page.close()
    except pdfium.PdfiumError:
        raise ValueError('PDF 无法打开，可能已加密或损坏。请上传可正常打开的 PDF。') from None
    return {'ok':True, 'page':page_number, 'page_count':count, 'width':image.width, 'height':image.height,
            'preview':'data:image/jpeg;base64,' + base64.b64encode(output.getvalue()).decode()}
