# SahaRa Backend

A comprehensive backend system built with FastAPI and PostgreSQL, providing robust APIs for user management, team collaboration, skill tracking, chat functionality, and file management.

## Features

- **User Authentication**: Support for multiple user roles (Professor, Student, Teaching Assistant)
- **Robust Database Integration**: PostgreSQL storage with SQLAlchemy ORM
- **File Upload System**: Secure file storage for assignments, submissions, and reference materials
- **Real-time Chat**: WebSocket-based chat functionality for instant communication
- **CSV Data Import**: Tools for importing user data via CSV files
- **Form Handling**: Dynamic form creation and management

## Project Structure

The project is organized into several components:
- Main application (`main.py`): Core API functionality
- User management: Authentication and authorization
- File handling: Upload and download capabilities

## Getting Started

### Prerequisites

- Python 3.8+
- PostgreSQL database
- Virtual environment (recommended)

### Installation

1. Clone the repository
2. Set up a virtual environment (optional but recommended)
3. Install dependencies:

```bash
pip install -r requirements.txt
```

### Configuration

The application uses PostgreSQL. Make sure your database is properly configured and update the `DATABASE_URL` in the code if necessary.

### Running the Server

Start the development server on port 8000:

```bash
fastapi dev main.py
```

For production deployment, use the `run` command instead:

```bash
fastapi run main.py
```

You can also use a production ASGI server like Uvicorn or Gunicorn for more robust deployment.

## API Documentation

When the server is running, you can access the API documentation at:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc
