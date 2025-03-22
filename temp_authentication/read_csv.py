import csv
import io
from io import StringIO

# Define the expected header format
EXPECTED_HEADER = [
    "S.No.", "Batch", "Roll No", "Student Name", "Section", "Email", 
    "Year", "Programme", "Category", "Course Type", "Remark", "Action", "Credits", "Action"
]

class CSVFormatError(Exception):
    """Custom exception for CSV format errors"""
    pass

def extract_student_data(file_path):
    """
    
    Args:
        file_path (str): Path to the CSV file
    
   
    """
    student_data = []
    
    with open(file_path, 'r') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            email = row['Email']
            username = email.split('@')[0] if '@' in email else None
            
            student_data.append({
                'Name': row['Student Name'],
                'Email': email,
                'Username': username
            })
    
    return student_data

def extract_ta_data(file_path):
    """
    
    Args:
        file_path (str): Path to the CSV file
    
   
    """
    ta_data = []
    
    with open(file_path, 'r') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            email = row['Email']
            username = email.split('@')[0] if '@' in email else None
            
            ta_data.append({
                'Name': row['TA Name'],
                'Email': email,
                'Username': username
            })
    
    return ta_data

def extract_student_data_from_content(content):
    """
    Extract student data from CSV content with strict format validation.
    
    Args:
        content (str): CSV content as string
        
    Returns:
        list: List of dictionaries containing student data
        
    Raises:
        CSVFormatError: If the CSV format doesn't match the expected format
    """
    students = []
    reader = csv.reader(StringIO(content))
    
    # Validate header row
    try:
        header = next(reader)
        
        # Check if the header matches the expected format
        if len(header) != len(EXPECTED_HEADER):
            raise CSVFormatError(f"Invalid CSV format: Expected {len(EXPECTED_HEADER)} columns, found {len(header)}")
        
        # Check each column header
        for i, (expected, actual) in enumerate(zip(EXPECTED_HEADER, header)):
            if expected.strip() != actual.strip():
                raise CSVFormatError(f"Invalid CSV format: Column {i+1} should be '{expected}', found '{actual}'")
                
    except StopIteration:
        raise CSVFormatError("Empty CSV file")
    
    # Process data rows
    line_number = 2  # Header is line 1
    for row in reader:
        try:
            # Ensure row has enough columns
            if len(row) < len(EXPECTED_HEADER):
                raise CSVFormatError(f"Row {line_number} has insufficient columns: expected {len(EXPECTED_HEADER)}, found {len(row)}")
            
            # Extract name and email from their positions
            name = row[3].strip()  # Student Name is in column 4 (index 3)
            email = row[5].strip()  # Email is in column 6 (index 5)
            
            # Skip empty rows
            if not name or not email:
                line_number += 1
                continue
            
            # Validate email format (basic check)
            if '@' not in email:
                raise CSVFormatError(f"Row {line_number}: Invalid email format '{email}'")
            
            # Extract username from email (part before @)
            username = email.split('@')[0]
            
            students.append({
                'Name': name,
                'Email': email,
                'Username': username
            })
            
        except Exception as e:
            if isinstance(e, CSVFormatError):
                raise
            raise CSVFormatError(f"Error processing row {line_number}: {str(e)}")
        
        line_number += 1
    
    if not students:
        raise CSVFormatError("No valid student data found in the CSV file")
        
    return students

def extract_ta_data_from_content(content):
    """
    Extract TA data from CSV content with the same validation as student data.
    
    Args:
        content (str): CSV content as string
        
    Returns:
        list: List of dictionaries containing TA data
        
    Raises:
        CSVFormatError: If the CSV format doesn't match the expected format
    """
    # TAs are processed the same way as students
    return extract_student_data_from_content(content)
