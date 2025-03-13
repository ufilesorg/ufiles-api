from datetime import datetime, timedelta

from .models import FileMetaData


async def remove_deleted_files():
    files = await FileMetaData.find(
        FileMetaData.is_deleted == True,
        FileMetaData.updated_at < datetime.now() - timedelta(days=30),
        FileMetaData.is_directory == False,
    ).to_list()
    for file in files:
        await file.delete(file.user_id)


async def remove_deleted_directories():
    files = await FileMetaData.find(
        FileMetaData.is_deleted == True,
        FileMetaData.updated_at < datetime.now() - timedelta(days=30),
        FileMetaData.is_directory == True,
    ).to_list()
    print(len(files))
    for file in files:
        await file.delete(file.user_id)


async def remove_old_access_files():
    files = await FileMetaData.find(
        FileMetaData.is_deleted == False,
        FileMetaData.access_at < datetime.now() - timedelta(days=30),
        FileMetaData.is_directory == False,
    ).to_list()
    print(len(files))
    for file in files:
        await file.delete(file.user_id)
