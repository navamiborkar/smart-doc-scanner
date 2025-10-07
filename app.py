from flask import Flask, render_template, request, url_for
import pytesseract
from PIL import Image
import os
import re
import string
import sqlite3
import nltk
from PyPDF2 import PdfReader
from pdf2image import convert_from_path
from nltk.corpus import stopwords
from werkzeug.utils import secure_filename   # ✅ Added import

# ---------- Flask Config ----------
app = Flask(__name__)
UPLOAD_FOLDER = "uploads"
DB_NAME = "documents.db"
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

# ---------- NLTK Stopwords Setup ----------
# Try to load stopwords; download only if missing
try:
    stop_words = set(stopwords.words("english"))
except LookupError:
    nltk.download("stopwords")
    stop_words = set(stopwords.words("english"))

# ---------- Database Setup ----------
def init_db():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT,
            extracted_text TEXT,
            category TEXT
        )
    ''')
    conn.commit()
    conn.close()

# ---------- Text Preprocessing ----------
def preprocess_text(text):
    text = text.lower()
    text = re.sub(r'\d+', '', text)  # remove numbers
    text = text.translate(str.maketrans('', '', string.punctuation))  # remove punctuation
    tokens = text.split()
    tokens = [w for w in tokens if w not in stop_words]
    return " ".join(tokens)

# ---------- Rule-Based Categorizer ----------
def categorize(text):
    if any(word in text for word in ["invoice", "gst", "amount", "total"]):
        return "Bill"
    elif any(word in text for word in ["prn", "roll", "student", "id"]):
        return "ID Document"
    elif any(word in text for word in ["assignment", "lecture", "subject", "class"]):
        return "Notes"
    elif any(word in text for word in ["certificate", "award", "completion"]):
        return "Certificate"
    else:
        return "Uncategorized"

# ---------- PDF/Text Extraction ----------
def extract_text_from_pdf(filepath):
    """
    Try to extract text from a PDF:
    1. Direct text extraction with PyPDF2
    2. If empty, fallback to OCR with pdf2image + Tesseract
    """
    text = ""

    try:
        # Step 1: Try direct extraction (text-based PDFs)
        reader = PdfReader(filepath)
        for page in reader.pages:
            extracted = page.extract_text()
            if extracted:
                text += extracted + "\n"

        # Step 2: If no text found, fallback to OCR (scanned PDFs)
        if not text.strip():
            try:
                pages = convert_from_path(filepath)
                for page in pages:
                    text += pytesseract.image_to_string(page)
            except Exception:
                text += "\n⚠️ OCR not available in hosted version."

    except Exception as e:
        return f"❌ Error extracting PDF: {e}"

    return text.strip()

# ---------- Routes ----------
@app.route('/')
def index():
    return render_template("index.html")

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return "❌ No file uploaded"

    file = request.files['file']
    filename = secure_filename(file.filename)

    # ✅ Ensure a valid filename is provided
    if not filename:
        return "❌ No file selected or invalid filename"

    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)

    try:
        file.save(filepath)

        # PDF or Image detection
        if filename.lower().endswith(".pdf"):
            text = extract_text_from_pdf(filepath)
        else:
            text = pytesseract.image_to_string(Image.open(filepath))

        # Preprocess + Categorize
        clean_text = preprocess_text(text)
        category = categorize(clean_text)

        # Save to DB
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute(
            "INSERT INTO documents (filename, extracted_text, category) VALUES (?, ?, ?)",
            (filename, text, category)
        )
        conn.commit()
        conn.close()

    except Exception as e:
        return f"❌ Error processing file: {e}"

    return f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Extraction Result</title>

    <!-- Bootstrap -->
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">

    <style>
        body {{
            background-color: #f8f9fa;
            font-family: 'Segoe UI', sans-serif;
            padding: 30px;
        }}
        .result-card {{
            background: #fff;
            border-radius: 15px;
            box-shadow: 0 4px 20px rgba(0, 0, 0, 0.1);
            padding: 30px;
            max-width: 900px;
            margin: auto;
        }}
        pre {{
            background: #f1f3f5;
            border-radius: 10px;
            padding: 20px;
            max-height: 500px;
            overflow-y: auto;
            white-space: pre-wrap;
            word-wrap: break-word;
        }}
        h2 {{
            color: #007bff;
            font-weight: 600;
        }}
        h3 {{
            color: #343a40;
            margin-top: 20px;
        }}
        .btn {{
            border-radius: 10px;
            margin-top: 20px;
        }}
    </style>
</head>
<body>

    <div class="result-card">
        <h2>📄 Extracted Text</h2>
        <pre>{text}</pre>

        <h3>🧠 Predicted Category:</h3>
        <p><span class="badge bg-primary fs-6">{category}</span></p>

        <div class="mt-4">
            <a href='{url_for('dashboard')}' class="btn btn-outline-secondary">📂 Go to Dashboard</a>
            <a href='/' class="btn btn-primary">⬅️ Upload Another</a>
        </div>
    </div>

</body>
</html>
"""


@app.route('/dashboard')
def dashboard():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT id, filename, category FROM documents")
    docs = c.fetchall()
    conn.close()

    # Generate table rows dynamically
    rows_html = ""
    color_map = {
        "Bill": "primary",
        "ID Document": "warning",
        "Notes": "success",
        "Certificate": "info",
        "Uncategorized": "secondary"
    }

    for doc in docs:
        color = color_map.get(doc[2], "secondary")
        rows_html += f"""
        <tr>
            <td>{doc[0]}</td>
            <td>{doc[1]}</td>
            <td><span class='badge bg-{color}'>{doc[2]}</span></td>
            <td><a href='/view/{doc[0]}' class='btn btn-sm btn-outline-primary'>View</a></td>
        </tr>
        """

    return f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Document Dashboard</title>
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
        <style>
            body {{
                background-color: #f8f9fa;
                font-family: 'Segoe UI', sans-serif;
                padding: 40px;
            }}
            .dashboard-card {{
                background: #fff;
                border-radius: 15px;
                box-shadow: 0 4px 20px rgba(0, 0, 0, 0.1);
                padding: 30px;
                max-width: 1000px;
                margin: auto;
            }}
            table {{
                border-radius: 10px;
                overflow: hidden;
            }}
            th {{
                background-color: #007bff;
                color: white;
            }}
            .btn {{
                border-radius: 8px;
            }}
        </style>
    </head>
    <body>
        <div class="dashboard-card">
            <h2 class="text-center text-primary mb-4">📂 Document Dashboard</h2>

            <table class="table table-striped table-hover">
                <thead>
                    <tr>
                        <th>ID</th>
                        <th>File Name</th>
                        <th>Category</th>
                        <th>Action</th>
                    </tr>
                </thead>
                <tbody>
                    {rows_html if docs else "<tr><td colspan='4' class='text-center text-muted'>No documents uploaded yet.</td></tr>"}
                </tbody>
            </table>

            <div class="text-center mt-4">
                <a href="/" class="btn btn-primary">⬆️ Upload More</a>
            </div>
        </div>
    </body>
    </html>
    """


@app.route('/view/<int:doc_id>')
def view_doc(doc_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT filename, extracted_text, category FROM documents WHERE id=?", (doc_id,))
    doc = c.fetchone()
    conn.close()

    if not doc:
        return "<h3 class='text-danger text-center mt-5'>❌ Document not found</h3>"

    filename, extracted_text, category = doc

    color_map = {
        "Bill": "primary",
        "ID Document": "warning",
        "Notes": "success",
        "Certificate": "info",
        "Uncategorized": "secondary"
    }
    badge_color = color_map.get(category, "secondary")

    return f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>View Document - {filename}</title>

        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">

        <style>
            body {{
                background-color: #f8f9fa;
                font-family: 'Segoe UI', sans-serif;
                padding: 40px;
            }}
            .viewer-card {{
                background: #fff;
                border-radius: 15px;
                box-shadow: 0 4px 20px rgba(0, 0, 0, 0.1);
                padding: 30px;
                max-width: 1000px;
                margin: auto;
            }}
            pre {{
                background: #f1f3f5;
                border-radius: 10px;
                padding: 20px;
                max-height: 600px;
                overflow-y: auto;
                white-space: pre-wrap;
                word-wrap: break-word;
            }}
            .btn {{
                border-radius: 10px;
            }}
        </style>
    </head>
    <body>

        <div class="viewer-card">
            <h2 class="text-primary">📄 {filename}</h2>
            <p><span class="badge bg-{badge_color} fs-6">{category}</span></p>

            <h5 class="mt-4 mb-2 text-secondary">Extracted Text:</h5>
            <pre>{extracted_text}</pre>

            <div class="text-center mt-4">
                <a href='{url_for('dashboard')}' class="btn btn-outline-secondary">⬅️ Back to Dashboard</a>
                <a href='/' class="btn btn-primary">📤 Upload New Document</a>
            </div>
        </div>

    </body>
    </html>
    """


# ---------- Main ----------
if __name__ == "__main__":
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    init_db()
    # ✅ Use Render’s port if available; else default to 5000 for local runs
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
