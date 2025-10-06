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
        return "No file uploaded"
    
    file = request.files['file']
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
    file.save(filepath)

    try:
        # PDF or Image detection
        if file.filename.lower().endswith(".pdf"):
            text = extract_text_from_pdf(filepath)
        else:
            text = pytesseract.image_to_string(Image.open(filepath))

        # Preprocess + Categorize
        clean_text = preprocess_text(text)
        category = categorize(clean_text)

        # Save to DB
        conn = sqlite3.connect(DB_NAME)
        c = conn.cursor()
        c.execute("INSERT INTO documents (filename, extracted_text, category) VALUES (?, ?, ?)",
                  (file.filename, text, category))
        conn.commit()
        conn.close()

    except Exception as e:
        return f"❌ Error processing file: {e}"

    return f"""
    <h2>Extracted Text:</h2>
    <pre>{text}</pre>
    <h2>Predicted Category:</h2>
    <p>{category}</p>
    <a href='{url_for('dashboard')}'>📂 Go to Dashboard</a>
    """

@app.route('/dashboard')
def dashboard():
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT id, filename, category FROM documents")
    docs = c.fetchall()
    conn.close()

    html = "<h1>📂 Document Dashboard</h1><ul>"
    for doc in docs:
        html += f"<li>{doc[1]} — <b>{doc[2]}</b> [<a href='/view/{doc[0]}'>View</a>]</li>"
    html += "</ul><a href='/'>⬅️ Upload More</a>"
    return html

@app.route('/view/<int:doc_id>')
def view_doc(doc_id):
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute("SELECT filename, extracted_text, category FROM documents WHERE id=?", (doc_id,))
    doc = c.fetchone()
    conn.close()

    if doc:
        return f"""
        <h2>File: {doc[0]}</h2>
        <h3>Category: {doc[2]}</h3>
        <pre>{doc[1]}</pre>
        <a href='{url_for('dashboard')}'>⬅️ Back to Dashboard</a>
        """
    else:
        return "❌ Document not found"

# ---------- Main ----------
if __name__ == "__main__":
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    init_db()
    # ✅ Use Render’s port if available; else default to 5000 for local runs
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
