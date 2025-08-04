"""Integration tests for the complete file management workflow."""

import base64
from io import BytesIO
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import UploadFile
from fastapi_mongo_base.core.exceptions import BaseHTTPException
from usso.exceptions import PermissionDenied

from apps.files.file_manager import FileManager
from apps.files.models import FileMetaData, ObjectMetaData
from apps.files.routes import FilesRouter
from apps.files.schemas import FileMetaDataSchema, PermissionEnum


class TestFileManagementIntegration:
    """Integration tests for complete file management workflow."""

    @pytest.fixture
    def file_manager(self) -> FileManager:
        """Create a FileManager instance for testing."""
        return FileManager(storage_backend_name="local")

    @pytest.fixture
    def files_router(self) -> FilesRouter:
        """Create a FilesRouter instance for testing."""
        return FilesRouter()

    @pytest.fixture
    def sample_file_content(self) -> bytes:
        """Create sample file content."""
        return b"Hello, World! This is a test file for integration testing."

    @pytest.fixture
    def upload_file(self, sample_file_content: bytes) -> UploadFile:
        """Create an UploadFile for testing."""
        file = BytesIO(sample_file_content)
        return UploadFile(
            file=file, filename="integration_test.txt", content_type="text/plain"
        )

    @pytest.mark.asyncio
    async def test_complete_file_upload_workflow(
        self, file_manager: FileManager, upload_file: UploadFile
    ) -> None:
        """Test complete file upload workflow."""
        # Step 1: Process file
        file_metadata = await file_manager.process_file(
            file=upload_file, user_id="integration_user", blocking=True
        )

        # Verify file metadata
        assert file_metadata.user_id == "integration_user"
        assert file_metadata.filename == "integration_test.txt"
        assert file_metadata.content_type == "text/plain"
        assert file_metadata.size > 0
        assert file_metadata.filehash is not None
        assert file_metadata.key is not None

        # Save to database
        await file_metadata.save()

        # Step 2: Verify file exists in database
        retrieved_file = await FileMetaData.get_item(
            uid=file_metadata.uid, user_id="integration_user"
        )
        assert retrieved_file is not None
        assert retrieved_file.uid == file_metadata.uid

        # Step 3: Verify object metadata exists
        object_metadata = await ObjectMetaData.get_key(file_metadata.key)
        assert object_metadata is not None
        assert object_metadata.key == file_metadata.key
        assert object_metadata.object_hash == file_metadata.filehash

        # Step 4: Test file download
        downloaded_content = await file_manager.download_file(file_metadata)
        assert downloaded_content is not None
        assert (
            downloaded_content.read()
            == b"Hello, World! This is a test file for integration testing."
        )

        # Step 5: Test file streaming
        stream_chunks = [
            chunk async for chunk in file_manager.stream_file(file_metadata)
        ]

        assert len(stream_chunks) > 0
        assert (
            b"".join(stream_chunks)
            == b"Hello, World! This is a test file for integration testing."
        )

        # Step 6: Test presigned URL generation
        presigned_url = await file_manager.generate_presigned_url(file_metadata)
        assert presigned_url is not None
        assert "presigned" in presigned_url

    @pytest.mark.asyncio
    async def test_file_update_workflow(
        self, file_manager: FileManager, upload_file: UploadFile
    ) -> None:
        """Test file update workflow."""
        # Step 1: Create initial file
        initial_file = await file_manager.process_file(
            file=upload_file, user_id="update_user", blocking=True
        )
        await initial_file.save()

        # Step 2: Create new file content
        new_content = b"Updated file content for testing."
        new_file = BytesIO(new_content)
        new_upload_file = UploadFile(
            file=new_file, filename="updated_test.txt", content_type="text/plain"
        )

        # Step 3: Update file
        updated_file = await file_manager.change_file(
            file_metadata=initial_file,
            file=new_upload_file,
            blocking=True,
            overwrite=False,  # Keep history
        )

        # Verify update
        assert updated_file.filename == "updated_test.txt"
        assert updated_file.filehash != initial_file.filehash
        assert updated_file.key != initial_file.key
        assert len(updated_file.history) > 0
        assert updated_file.history[0]["filehash"] == initial_file.filehash

        # Step 4: Verify new content
        downloaded_content = await file_manager.download_file(updated_file)
        assert downloaded_content.read() == new_content

    @pytest.mark.asyncio
    async def test_directory_operations(self) -> None:
        """Test directory operations."""
        # Step 1: Create root directory
        root_dir = await FileMetaData.create_directory(
            user_id="dir_user", dirname="root", parent_id=None
        )

        # Step 2: Create subdirectory
        sub_dir = await FileMetaData.create_directory(
            user_id="dir_user", dirname="sub", parent_id=root_dir.uid
        )

        # Step 3: Create file in subdirectory
        file_in_sub = FileMetaData(
            user_id="dir_user",
            filename="file_in_sub.txt",
            filehash="sub_file_hash",
            key="sub/file_key",
            content_type="text/plain",
            size=50,
            parent_id=sub_dir.uid,
        )
        await file_in_sub.save()

        # Step 4: List files in root directory
        root_files = await FileMetaData.list_items(
            user_id="dir_user", parent_id=root_dir.uid
        )
        assert len(root_files) == 1
        assert root_files[0].uid == sub_dir.uid

        # Step 5: List files in subdirectory
        sub_files = await FileMetaData.list_items(
            user_id="dir_user", parent_id=sub_dir.uid
        )
        assert len(sub_files) == 1
        assert sub_files[0].uid == file_in_sub.uid

        # Step 6: Test path resolution
        parent_id, filename = await FileMetaData.get_path(
            filepath="root/sub/file.txt", user_id="dir_user", create=True
        )
        assert parent_id == sub_dir.uid
        assert filename == "file.txt"

    @pytest.mark.asyncio
    async def test_permission_workflow(self) -> None:
        """Test permission workflow."""
        # Step 1: Create file
        file = FileMetaData(
            user_id="owner_user",
            filename="permission_test.txt",
            filehash="perm_hash",
            key="perm/key",
            content_type="text/plain",
            size=100,
        )
        await file.save()

        # Step 2: Test owner permissions
        owner_permission = file.user_permission("owner_user")
        assert owner_permission.permission == PermissionEnum.OWNER
        assert owner_permission.read is True
        assert owner_permission.write is True
        assert owner_permission.delete is True

        # Step 3: Test other user permissions (should be NONE by default)
        other_permission = file.user_permission("other_user")
        assert other_permission.permission == PermissionEnum.NONE
        assert other_permission.read is False
        assert other_permission.write is False
        assert other_permission.delete is False

        # Step 4: Set permission for other user
        from apps.files.schemas import Permission

        new_permission = Permission(
            user_id="other_user", permission=PermissionEnum.READ
        )
        await file.set_permission("other_user", new_permission)

        # Step 5: Verify permission was set
        updated_permission = file.user_permission("other_user")
        assert updated_permission.permission == PermissionEnum.READ
        assert updated_permission.read is True
        assert updated_permission.write is False

        # Step 6: Test public permission
        file.public_permission.permission = PermissionEnum.READ
        await file.save()

        public_permission = file.user_permission(None)
        assert public_permission.permission == PermissionEnum.READ

    @pytest.mark.asyncio
    async def test_deletion_workflow(self) -> None:
        """Test file deletion workflow."""
        # Step 1: Create file
        file = FileMetaData(
            user_id="delete_user",
            filename="delete_test.txt",
            filehash="delete_hash",
            key="delete/key",
            content_type="text/plain",
            size=100,
        )
        await file.save()

        # Step 2: Soft delete
        await file.soft_delete("delete_user")
        assert file.is_deleted is True
        assert file.deleted_at is not None

        # Step 3: Verify file is not accessible normally
        files = await FileMetaData.list_items(user_id="delete_user", is_deleted=False)
        assert len([f for f in files if f.uid == file.uid]) == 0

        # Step 4: Verify file is accessible when including deleted
        files = await FileMetaData.list_items(user_id="delete_user", is_deleted=True)
        assert len([f for f in files if f.uid == file.uid]) == 1

        # Step 5: Restore file
        await file.restore("delete_user")
        assert file.is_deleted is False
        assert file.deleted_at is None

        # Step 6: Hard delete
        await file.soft_delete("delete_user")
        await file.hard_delete("delete_user")

        # Step 7: Verify file is completely deleted
        retrieved = await FileMetaData.get_item(file.uid, user_id="delete_user")
        assert retrieved is None

    @pytest.mark.asyncio
    async def test_volume_calculation(self) -> None:
        """Test volume calculation."""
        # Step 1: Create files for different users
        user1_file1 = FileMetaData(
            user_id="volume_user1",
            filename="file1.txt",
            key="vol/file1",
            content_type="text/plain",
            size=100,
        )
        await user1_file1.save()

        user1_file2 = FileMetaData(
            user_id="volume_user1",
            filename="file2.txt",
            key="vol/file2",
            content_type="text/plain",
            size=200,
        )
        await user1_file2.save()

        user2_file = FileMetaData(
            user_id="volume_user2",
            filename="file3.txt",
            key="vol/file3",
            content_type="text/plain",
            size=300,
        )
        await user2_file.save()

        # Step 2: Calculate volumes
        user1_volume = await FileMetaData.get_volume("volume_user1")
        user2_volume = await FileMetaData.get_volume("volume_user2")

        assert user1_volume == 300  # 100 + 200
        assert user2_volume == 300  # 300

    @pytest.mark.asyncio
    async def test_duplicate_file_handling(
        self, file_manager: FileManager, upload_file: UploadFile
    ) -> None:
        """Test handling of duplicate files."""
        # Step 1: Upload first file
        file1 = await file_manager.process_file(
            file=upload_file, user_id="dup_user", parent_id=None, blocking=True
        )
        await file1.save()

        # Step 2: Upload same file again
        upload_file.file.seek(0)  # Reset file pointer
        file2 = await file_manager.process_file(
            file=upload_file, user_id="dup_user", parent_id=None, blocking=True
        )

        # Step 3: Verify same file is returned (deduplication)
        assert file2.uid == file1.uid
        assert file2.filehash == file1.filehash

        # Step 4: Upload same file to different parent
        upload_file.file.seek(0)
        file3 = await file_manager.process_file(
            file=upload_file,
            user_id="dup_user",
            parent_id="different_parent",
            blocking=True,
        )

        # Should still return the same file due to same hash
        assert file3.uid == file1.uid

    @pytest.mark.asyncio
    async def test_base64_upload_workflow(self, files_router: FilesRouter) -> None:
        """Test base64 upload workflow."""
        # Step 1: Prepare base64 content
        content = b"Base64 test content"
        base64_content = base64.b64encode(content).decode()
        mime_type = "text/plain"

        # Step 2: Mock the upload process
        with patch.object(files_router, "get_user") as mock_get_user:
            mock_get_user.return_value = type(
                "User",
                (),
                {
                    "uid": "base64_user",
                    "email": "test@example.com",
                    "username": "base64_user",
                    "is_active": True,
                    "is_verified": True,
                    "tenant_id": "test_tenant",
                },
            )()

            with patch.object(files_router, "upload_file") as mock_upload:
                mock_upload.return_value = FileMetaDataSchema(
                    user_id="base64_user",
                    filename="base64_test.txt",
                    filehash="base64_hash",
                    key="base64/key",
                    content_type="text/plain",
                    size=len(content),
                )

                result = await files_router.upload_file_base64(
                    request=AsyncMock(),
                    user_id="base64_user",
                    file=base64_content,
                    mime_type=mime_type,
                )

                assert result.filename == "base64_test.txt"
                assert result.content_type == "text/plain"
                assert result.size == len(content)

    @pytest.mark.asyncio
    async def test_error_handling(self, file_manager: FileManager) -> None:
        """Test error handling scenarios."""
        # Test 1: Invalid filename ending with slash
        with pytest.raises(BaseHTTPException) as exc_info:
            await file_manager._get_filepath(
                user_id="error_user", filename="invalid/path/"
            )
        assert exc_info.value.status_code == 400
        assert exc_info.value.error == "invalid_filename"

        # Test 2: Upload failure
        file_bytes = BytesIO(b"test content")
        with patch.object(file_manager, "storage_backend") as mock_backend:
            mock_backend.upload_file.return_value = {
                "url": "http://example.com/test.txt"
            }
            mock_backend.file_exists.return_value = False  # Upload failed

            with pytest.raises(BaseHTTPException) as exc_info:
                await file_manager._manage_upload_to_storage(
                    file_bytes=file_bytes,
                    s3_key="test/key",
                    filehash="test_hash",
                    content_type="text/plain",
                    size=12,
                )
            assert exc_info.value.status_code == 500
            assert exc_info.value.error == "upload_failed"

        # Test 3: Permission denied
        file = FileMetaData(
            user_id="owner_user",
            filename="perm_test.txt",
            filehash="perm_hash",
            key="perm/key",
            content_type="text/plain",
            size=100,
        )
        await file.save()

        with pytest.raises(PermissionDenied):  # PermissionDenied
            await file.soft_delete("other_user")

    @pytest.mark.asyncio
    async def test_file_streaming_with_range(
        self, file_manager: FileManager, upload_file: UploadFile
    ) -> None:
        """Test file streaming with range requests."""
        # Step 1: Upload file
        file_metadata = await file_manager.process_file(
            file=upload_file, user_id="stream_user", blocking=True
        )
        await file_metadata.save()

        # Step 2: Test streaming with range
        stream_chunks = [
            chunk
            async for chunk in file_manager.stream_file(file_metadata, start=0, end=9)
        ]

        # Verify partial content
        content = b"".join(stream_chunks)
        assert len(content) <= 10  # Should be 10 bytes or less
        assert content.startswith(b"Hello, Wor")

    @pytest.mark.asyncio
    async def test_cleanup_orphaned_files(self) -> None:
        """Test cleanup of orphaned files."""
        # Step 1: Create file without ObjectMetaData
        orphan_file = FileMetaData(
            user_id="cleanup_user",
            filename="orphan.txt",
            key="orphan/key",
            content_type="text/plain",
            size=100,
        )
        await orphan_file.save()

        # Step 2: Create file with ObjectMetaData
        valid_file = FileMetaData(
            user_id="cleanup_user",
            filename="valid.txt",
            key="valid/key",
            content_type="text/plain",
            size=100,
        )
        await valid_file.save()

        obj = ObjectMetaData(
            key="valid/key",
            size=100,
            object_hash="valid_hash",
            content_type="text/plain",
        )
        await obj.save()

        # Step 3: Run cleanup
        await FileMetaData.remove_no_key_files()

        # Step 4: Verify orphaned file is deleted
        retrieved_orphan = await FileMetaData.get_item(
            orphan_file.uid, user_id="cleanup_user"
        )
        assert retrieved_orphan is None

        # Step 5: Verify valid file still exists
        retrieved_valid = await FileMetaData.get_item(
            valid_file.uid, user_id="cleanup_user"
        )
        assert retrieved_valid is not None
