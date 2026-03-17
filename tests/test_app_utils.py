from io import BytesIO
import os

from src.utils.app_utils import handle_request_files


class FakeFile:
    def __init__(self, filename: str, content: bytes):
        self.filename = filename
        self._content = content

    def save(self, file_path: str):
        with open(file_path, "wb") as file_obj:
            file_obj.write(self._content)


class FakeFiles:
    def __init__(self, mapping):
        self.mapping = mapping

    def keys(self):
        return self.mapping.keys()

    def items(self, multi=False):
        for key, files in self.mapping.items():
            if multi:
                for file_obj in files:
                    yield key, file_obj
            else:
                yield key, files[0]


class FakeForm:
    def getlist(self, key):
        return []

    def get(self, key):
        return None


def test_handle_request_files_accepts_epub_upload():
    files = FakeFiles({"imageFiles[]": [FakeFile("book.epub", b"dummy epub data")]})

    result = handle_request_files(files, FakeForm())

    assert "imageFiles[]" in result
    assert len(result["imageFiles[]"]) == 1

    saved_file = result["imageFiles[]"][0]
    assert saved_file.endswith("book.epub")
    assert os.path.exists(saved_file)

    os.remove(saved_file)


def test_handle_request_files_rejects_unknown_extension():
    files = FakeFiles({"imageFiles[]": [FakeFile("notes.txt", b"plain text")]})

    result = handle_request_files(files, FakeForm())

    assert result == {}
