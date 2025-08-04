"""Tests for FileManager class."""

from collections.abc import AsyncGenerator
from io import BytesIO
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import UploadFile
from fastapi_mongo_base.core.exceptions import BaseHTTPException

from apps.files.file_manager import FileManager
from apps.files.models import FileMetaData, ObjectMetaData
from apps.files.schemas import PermissionEnum


class TestFileManager:
    """Test cases for FileManager class."""

    @pytest.fixture
    def file_manager(self) -> FileManager:
        """Create a FileManager instance for testing."""
        return FileManager(storage_backend_name="local")

    @pytest.fixture
    def sample_file(self) -> BytesIO:
        """Create a sample file for testing."""
        content = b"Hello, World! This is a test file content."
        file = BytesIO(content)
        file.name = "test.txt"
        return file

    @pytest.fixture
    def upload_file(self, sample_file: BytesIO) -> UploadFile:
        """Create an UploadFile instance for testing."""
        return UploadFile(
            file=sample_file, filename="test.txt", content_type="text/plain"
        )

    @pytest.fixture
    def mock_storage_backend(self) -> AsyncMock:
        """Create a mock storage backend."""
        mock = AsyncMock()
        mock.upload_file.return_value = {"url": "http://example.com/test.txt"}
        mock.file_exists.return_value = True
        mock.download_file.return_value = BytesIO(b"Hello, World!")
        mock.stream_file.return_value = self._mock_stream()
        mock.delete_file.return_value = True
        mock.generate_presigned_url.return_value = "http://example.com/presigned"
        return mock

    def _mock_stream(self) -> AsyncGenerator[bytes]:
        """Create a mock async generator for streaming."""

        async def stream() -> AsyncGenerator[bytes]:  # noqa: RUF029
            yield b"Hello, "
            yield b"World!"

        return stream()

    @pytest.mark.asyncio
    async def test_file_manager_initialization(self, file_manager: FileManager) -> None:
        """Test FileManager initialization."""
        assert file_manager.storage_backend_name == "local"
        assert file_manager._storage_backend is None

    @pytest.mark.asyncio
    async def test_storage_backend_property(self, file_manager: FileManager) -> None:
        """Test storage_backend property."""
        backend = file_manager.storage_backend
        assert backend is not None
        assert file_manager._storage_backend is not None

    @pytest.mark.asyncio
    async def test_get_filepath_with_filename(self, file_manager: FileManager) -> None:
        """Test _get_filepath with filename parameter."""
        filepath, filename = await file_manager._get_filepath(
            user_id="test_user", filename="test/path/file.txt"
        )
        assert filepath == "test/path/file.txt"
        assert filename == "file.txt"

    @pytest.mark.asyncio
    async def test_get_filepath_with_file_filename(
        self, file_manager: FileManager
    ) -> None:
        """Test _get_filepath with file_filename parameter."""
        filepath, filename = await file_manager._get_filepath(
            user_id="test_user", file_filename="uploaded_file.txt"
        )
        assert filepath == "uploaded_file.txt"
        assert filename == "uploaded_file.txt"

    @pytest.mark.asyncio
    async def test_get_filepath_invalid_ending_slash(
        self, file_manager: FileManager
    ) -> None:
        """Test _get_filepath with invalid filename ending with slash."""
        with pytest.raises(BaseHTTPException) as exc_info:
            await file_manager._get_filepath(user_id="test_user", filename="test/path/")
        assert exc_info.value.status_code == 400
        assert exc_info.value.error == "invalid_filename"

    @pytest.mark.asyncio
    async def test_process_file_success(
        self, file_manager: FileManager, upload_file: UploadFile
    ) -> None:
        """Test successful file processing."""
        with patch.object(file_manager, "storage_backend") as mock_backend:
            mock_backend.upload_file.return_value = {
                "url": "http://example.com/test.txt"
            }
            mock_backend.file_exists.return_value = True

            result = await file_manager.process_file(
                file=upload_file, user_id="test_user", blocking=True
            )

            assert isinstance(result, FileMetaData)
            assert result.user_id == "test_user"
            assert result.filename == "test.txt"
            assert result.content_type == "text/plain"
            assert result.size > 0
            assert result.filehash is not None

    @pytest.mark.asyncio
    async def test_process_file_existing_file(
        self, file_manager: FileManager, upload_file: UploadFile
    ) -> None:
        """Test processing file that already exists."""
        # Create an existing file with same hash
        existing_file = FileMetaData(
            user_id="test_user",
            filename="existing.txt",
            filehash="test_hash",
            key="test_key",
            content_type="text/plain",
            size=100,
            parent_id=None,
        )
        await existing_file.save()

        with patch.object(file_manager, "storage_backend") as mock_backend:
            mock_backend.upload_file.return_value = {
                "url": "http://example.com/test.txt"
            }
            mock_backend.file_exists.return_value = True

            result = await file_manager.process_file(
                file=upload_file,
                user_id="test_user",
                parent_id=existing_file.parent_id,
                blocking=True,
            )

            # Should return existing file
            assert result.uid == existing_file.uid

    @pytest.mark.asyncio
    async def test_change_file_success(
        self, file_manager: FileManager, upload_file: UploadFile
    ) -> None:
        """Test successful file change."""
        # Create existing file metadata
        existing_file = FileMetaData(
            user_id="test_user",
            filename="old.txt",
            filehash="old_hash",
            key="old_key",
            content_type="text/plain",
            size=100,
            parent_id=None,
        )
        await existing_file.save()

        with patch.object(file_manager, "storage_backend") as mock_backend:
            mock_backend.upload_file.return_value = {
                "url": "http://example.com/new.txt"
            }
            mock_backend.file_exists.return_value = True

            result = await file_manager.change_file(
                file_metadata=existing_file, file=upload_file, blocking=True
            )

            assert result.filename == "test.txt"
            assert result.filehash != "old_hash"
            assert result.key != "old_key"

    @pytest.mark.asyncio
    async def test_change_file_with_history(
        self, file_manager: FileManager, upload_file: UploadFile
    ) -> None:
        """Test file change with history preservation."""
        existing_file = FileMetaData(
            user_id="test_user",
            filename="old.txt",
            filehash="old_hash",
            key="old_key",
            content_type="text/plain",
            size=100,
            parent_id=None,
        )
        await existing_file.save()

        with patch.object(file_manager, "storage_backend") as mock_backend:
            mock_backend.upload_file.return_value = {
                "url": "http://example.com/new.txt"
            }
            mock_backend.file_exists.return_value = True

            result = await file_manager.change_file(
                file_metadata=existing_file,
                file=upload_file,
                blocking=True,
                overwrite=False,
            )

            assert len(result.history) > 0
            assert result.history[0]["filehash"] == "old_hash"

    @pytest.mark.asyncio
    async def test_manage_upload_to_storage_success(
        self, file_manager: FileManager
    ) -> None:
        """Test successful upload to storage."""
        file_bytes = BytesIO(b"test content")
        s3_key = "test/key"
        filehash = "test_hash"
        content_type = "text/plain"
        size = 12

        with patch.object(file_manager, "storage_backend") as mock_backend:
            mock_backend.upload_file.return_value = {
                "url": "http://example.com/test.txt"
            }
            mock_backend.file_exists.return_value = True

            result = await file_manager._manage_upload_to_storage(
                file_bytes=file_bytes,
                s3_key=s3_key,
                filehash=filehash,
                content_type=content_type,
                size=size,
            )

            assert isinstance(result, ObjectMetaData)
            assert result.key == s3_key
            assert result.object_hash == filehash
            assert result.content_type == content_type
            assert result.size == size

    @pytest.mark.asyncio
    async def test_manage_upload_to_storage_existing_object(
        self, file_manager: FileManager
    ) -> None:
        """Test upload when object already exists."""
        # Create existing object
        existing_obj = ObjectMetaData(
            key="test/key", size=100, object_hash="test_hash", content_type="text/plain"
        )
        await existing_obj.save()

        file_bytes = BytesIO(b"test content")
        s3_key = "test/key"
        filehash = "test_hash"
        content_type = "text/plain"
        size = 12

        result = await file_manager._manage_upload_to_storage(
            file_bytes=file_bytes,
            s3_key=s3_key,
            filehash=filehash,
            content_type=content_type,
            size=size,
        )

        assert result.uid == existing_obj.uid

    @pytest.mark.asyncio
    async def test_manage_upload_to_storage_upload_failed(
        self, file_manager: FileManager
    ) -> None:
        """Test upload failure handling."""
        file_bytes = BytesIO(b"test content")
        s3_key = "test/key"
        filehash = "test_hash"
        content_type = "text/plain"
        size = 12

        with patch.object(file_manager, "storage_backend") as mock_backend:
            mock_backend.upload_file.return_value = {
                "url": "http://example.com/test.txt"
            }
            mock_backend.file_exists.return_value = False  # Upload failed

            with pytest.raises(BaseHTTPException) as exc_info:
                await file_manager._manage_upload_to_storage(
                    file_bytes=file_bytes,
                    s3_key=s3_key,
                    filehash=filehash,
                    content_type=content_type,
                    size=size,
                )

            assert exc_info.value.status_code == 500
            assert exc_info.value.error == "upload_failed"

    @pytest.mark.asyncio
    async def test_download_file(self, file_manager: FileManager) -> None:
        """Test file download."""
        file_metadata = FileMetaData(
            user_id="test_user",
            filename="test.txt",
            filehash="test_hash",
            key="test/key",
            content_type="text/plain",
            size=100,
        )

        with patch.object(file_manager, "storage_backend") as mock_backend:
            mock_backend.download_file.return_value = BytesIO(b"Hello, World!")

            result = await file_manager.download_file(file_metadata)

            assert isinstance(result, BytesIO)
            assert result.read() == b"Hello, World!"

    @pytest.mark.asyncio
    async def test_stream_file(self, file_manager: FileManager) -> None:
        """Test file streaming."""
        file_metadata = FileMetaData(
            user_id="test_user",
            filename="test.txt",
            filehash="test_hash",
            key="test/key",
            content_type="text/plain",
            size=100,
        )

        with patch.object(file_manager, "storage_backend") as mock_backend:
            mock_backend.stream_file.return_value = self._mock_stream()

            chunks = [chunk async for chunk in file_manager.stream_file(file_metadata)]

            assert chunks == [b"Hello, ", b"World!"]

    @pytest.mark.asyncio
    async def test_delete_file(self, file_manager: FileManager) -> None:
        """Test file deletion."""
        file_metadata = FileMetaData(
            user_id="test_user",
            filename="test.txt",
            filehash="test_hash",
            key="test/key",
            content_type="text/plain",
            size=100,
        )

        with patch.object(file_manager, "storage_backend") as mock_backend:
            mock_backend.delete_file.return_value = True

            result = await file_manager.delete_file(file_metadata)

            assert result is True
            mock_backend.delete_file.assert_called_once_with(file_metadata.key)

    @pytest.mark.asyncio
    async def test_generate_presigned_url(self, file_manager: FileManager) -> None:
        """Test presigned URL generation."""
        file_metadata = FileMetaData(
            user_id="test_user",
            filename="test.txt",
            filehash="test_hash",
            key="test/key",
            content_type="text/plain",
            size=100,
        )

        with patch.object(file_manager, "storage_backend") as mock_backend:
            mock_backend.generate_presigned_url.return_value = (
                "http://example.com/presigned"
            )

            result = await file_manager.generate_presigned_url(
                file_metadata, expires_in=3600
            )

            assert result == "http://example.com/presigned"
            mock_backend.generate_presigned_url.assert_called_once_with(
                file_metadata.key, expires_in=3600
            )

    @pytest.mark.asyncio
    async def test_process_file_with_public_permission(
        self, file_manager: FileManager, upload_file: UploadFile
    ) -> None:
        """Test file processing with public permission."""
        with patch.object(file_manager, "storage_backend") as mock_backend:
            mock_backend.upload_file.return_value = {
                "url": "http://example.com/test.txt"
            }
            mock_backend.file_exists.return_value = True

            result = await file_manager.process_file(
                file=upload_file,
                user_id="test_user",
                blocking=True,
                public_permission='{"permission": "READ"}',
            )

            assert result.public_permission.permission == PermissionEnum.READ

    @pytest.mark.asyncio
    async def test_process_file_invalid_public_permission(
        self, file_manager: FileManager, upload_file: UploadFile
    ) -> None:
        """Test file processing with invalid public permission."""
        with patch.object(file_manager, "storage_backend") as mock_backend:
            mock_backend.upload_file.return_value = {
                "url": "http://example.com/test.txt"
            }
            mock_backend.file_exists.return_value = True

            # Should not raise exception, just log warning
            result = await file_manager.process_file(
                file=upload_file,
                user_id="test_user",
                blocking=True,
                public_permission='{"invalid": "json"}',
            )

            assert result is not None
            assert result.public_permission.permission == PermissionEnum.NONE
