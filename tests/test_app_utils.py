import io
import os
import zipfile

from PIL import Image
from werkzeug.datastructures import FileMultiDict, FileStorage, ImmutableMultiDict

from src.utils.app_utils import extract_epub_cover, handle_request_files


def _build_epub_with_cover():
    epub_data = io.BytesIO()
    with zipfile.ZipFile(epub_data, 'w') as archive:
        archive.writestr(
            'META-INF/container.xml',
            '''<?xml version="1.0"?>
            <container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
                <rootfiles>
                    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml" />
                </rootfiles>
            </container>'''
        )
        archive.writestr(
            'OEBPS/content.opf',
            '''<?xml version="1.0"?>
            <package xmlns="http://www.idpf.org/2007/opf" version="2.0">
                <metadata>
                    <meta name="cover" content="cover-image" />
                </metadata>
                <manifest>
                    <item id="cover-image" href="images/cover.png" media-type="image/png" />
                </manifest>
            </package>'''
        )

        image_bytes = io.BytesIO()
        Image.new('RGB', (120, 200), 'black').save(image_bytes, format='PNG')
        archive.writestr('OEBPS/images/cover.png', image_bytes.getvalue())

    epub_data.seek(0)
    return epub_data


def test_extract_epub_cover_reads_cover_image():
    cover = extract_epub_cover(_build_epub_with_cover())
    assert cover is not None
    assert cover.size == (120, 200)


def test_handle_request_files_converts_epub_to_cover_png(tmp_path, monkeypatch):
    monkeypatch.setenv('SRC_DIR', str(tmp_path))
    save_dir = tmp_path / 'static' / 'images' / 'saved'
    save_dir.mkdir(parents=True)

    upload = FileStorage(
        stream=_build_epub_with_cover(),
        filename='book.epub',
        content_type='application/epub+zip',
    )
    request_files = FileMultiDict([('imageFiles[]', upload)])

    saved = handle_request_files(request_files, ImmutableMultiDict())

    saved_files = saved['imageFiles[]']
    assert len(saved_files) == 1
    saved_path = saved_files[0]
    assert saved_path.endswith('book_cover.png')
    assert os.path.exists(saved_path)
