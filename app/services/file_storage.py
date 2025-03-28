import os
import uuid
from fastapi import UploadFile
from typing import Optional, Tuple

class FileStorage:
    def __init__(self):
        self.upload_dir = "uploads"
        self.allowed_extensions = {'.pdf', '.doc', '.docx', '.txt', '.png', '.jpg', '.jpeg'}
        
        # Create upload directory if it doesn't exist
        if not os.path.exists(self.upload_dir):
            os.makedirs(self.upload_dir)

    def _get_file_extension(self, filename: str) -> str:
        return os.path.splitext(filename)[1].lower()

    def is_allowed_file(self, filename: str) -> bool:
        return self._get_file_extension(filename) in self.allowed_extensions

    async def save_file(self, file: UploadFile, subfolder: Optional[str] = None) -> Tuple[bool, str]:
        """
        Save an uploaded file to the storage system
        
        Args:
            file: The uploaded file
            subfolder: Optional subfolder within uploads directory
            
        Returns:
            Tuple of (success, filename or error message)
        """
        try:
            if not self.is_allowed_file(file.filename):
                return False, "File type not allowed"

            # Generate unique filename
            unique_filename = f"{uuid.uuid4()}_{file.filename}"
            
            # Create full path
            save_path = self.upload_dir
            if subfolder:
                save_path = os.path.join(save_path, subfolder)
                os.makedirs(save_path, exist_ok=True)
                
            file_path = os.path.join(save_path, unique_filename)
            
            # Save file
            with open(file_path, "wb") as buffer:
                content = await file.read()
                buffer.write(content)
            
            return True, unique_filename
            
        except Exception as e:
            return False, str(e)

    def delete_file(self, filename: str, subfolder: Optional[str] = None) -> bool:
        """
        Delete a file from storage
        
        Args:
            filename: Name of file to delete
            subfolder: Optional subfolder within uploads directory
            
        Returns:
            True if deletion was successful, False otherwise
        """
        try:
            file_path = os.path.join(self.upload_dir, filename)
            if subfolder:
                file_path = os.path.join(self.upload_dir, subfolder, filename)
                
            if os.path.exists(file_path):
                os.remove(file_path)
                return True
            return False
            
        except Exception:
            return False

file_storage = FileStorage()