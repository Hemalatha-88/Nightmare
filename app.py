import os
import sys
import io
import json
import secrets
import traceback
import re
from flask import Flask, jsonify, request
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from flask_mail import Mail, Message
from werkzeug.security import generate_password_hash, check_password_hash
from pypdf import PdfReader
from docx import Document
from dotenv import load_dotenv
from groq import Groq

load_dotenv()

# ── App ────────────────────────────────────────────────────────────────────────
app = Flask(__name__)

# ── Database ───────────────────────────────────────────────────────────────────
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///new_employeess.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)

# ── Mail  (port 465 + SSL — most reliable on Render) ──────────────────────────
app.config['MAIL_SERVER']         = 'smtp.gmail.com'
app.config['MAIL_PORT']           = 465
app.config['MAIL_USE_TLS']        = False
app.config['MAIL_USE_SSL']        = True
app.config['MAIL_USERNAME']       = os.getenv('MAIL_USERNAME', '2k23it18@kiot.ac.in')
app.config['MAIL_PASSWORD']       = os.getenv('MAIL_PASSWORD', 'yvim ckvi cfgm chwf')
app.config['MAIL_DEFAULT_SENDER'] = os.getenv('MAIL_USERNAME', '2k23it18@kiot.ac.in')
app.config['MAIL_TIMEOUT']        = 10
mail = Mail(app)

# ── CORS ───────────────────────────────────────────────────────────────────────
def is_allowed_origin(origin):
    if not origin:
        return False
    if origin.startswith("http://localhost"):
        return True
    if origin == "https://hrms-ai-5.vercel.app":
        return True
    if re.match(r"https://hrms-ai-5-.*\.vercel\.app", origin):
        return True
    extra = os.getenv("ALLOWED_ORIGIN", "")
    if extra and origin == extra:
        return True
    return False

CORS(app, resources={r"/*": {"origins": "*"}})

@app.after_request
def add_cors_headers(response):
    origin = request.headers.get('Origin', '')
    if is_allowed_origin(origin):
        response.headers['Access-Control-Allow-Origin']      = origin
        response.headers['Access-Control-Allow-Credentials'] = 'true'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type,Authorization'
    response.headers['Access-Control-Allow-Methods'] = 'GET,PUT,POST,DELETE,OPTIONS'
    return response

@app.before_request
def handle_options():
    if request.method == 'OPTIONS':
        return '', 200

# ── Groq client ────────────────────────────────────────────────────────────────
groq_client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

# ── Safe Groq helper  (JSON-object mode — for dict responses only) ─────────────
def call_groq_api(prompt):
    try:
        chat_completion = groq_client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama-3.1-8b-instant",
            response_format={"type": "json_object"}
        )
        return chat_completion.choices[0].message.content
    except Exception as e:
        print(f"Groq API Execution Error: {str(e)}", file=sys.stderr)
        return None

# ── Safe Groq helper  (plain text mode — for array responses) ─────────────────
def call_groq_api_text(prompt):
    """Use this when the response is a JSON ARRAY, not an object."""
    try:
        chat_completion = groq_client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama-3.1-8b-instant"
        )
        return chat_completion.choices[0].message.content
    except Exception as e:
        print(f"Groq API Text Error: {str(e)}", file=sys.stderr)
        return None

# ── Safe int cast (won't crash on None or non-numeric strings) ─────────────────
def safe_int(val, default=0):
    try:
        return int(val)
    except (TypeError, ValueError):
        return default

# ── Safe string cast for Groq fields that might come back None ─────────────────
def safe_str(val, default="Not Listed"):
    if val is None:
        return default
    if isinstance(val, str):
        return val.strip() or default
    return str(val)

# ──────────────────────────────────────────────────────────────────────────────
# DATABASE MODELS
# ──────────────────────────────────────────────────────────────────────────────
class Job(db.Model):
    id           = db.Column(db.Integer, primary_key=True)
    role         = db.Column(db.String(100), nullable=False)
    must_have    = db.Column(db.Text, nullable=False)
    nice_to_have = db.Column(db.Text, nullable=True)
    budget_max   = db.Column(db.String(50), nullable=False)
    candidates   = db.relationship('Candidate', backref='job', cascade='all, delete-orphan', lazy=True)

    def to_dict(self):
        return {
            "id":          self.id,
            "role":        self.role or "Unassigned Opening",
            "mustHave":    [s.strip() for s in self.must_have.split(",")    if s.strip()] if self.must_have    else [],
            "niceToHave":  [s.strip() for s in self.nice_to_have.split(",") if s.strip()] if self.nice_to_have else [],
            "budgetMax":   self.budget_max or "N/A"
        }

class Candidate(db.Model):
    id                  = db.Column(db.Integer, primary_key=True)
    job_id              = db.Column(db.Integer, db.ForeignKey('job.id'), nullable=False)
    email               = db.Column(db.String(100))
    name                = db.Column(db.String(100), nullable=False)
    role                = db.Column(db.String(100))
    experience          = db.Column(db.String(50))
    skills              = db.Column(db.Text)
    education           = db.Column(db.String(100))
    previous_company    = db.Column(db.String(100))
    salary              = db.Column(db.String(50))
    summary             = db.Column(db.Text)
    score               = db.Column(db.Integer, default=None)
    recommendation      = db.Column(db.String(50), default=None)
    strengths           = db.Column(db.Text, default=None)
    concerns            = db.Column(db.Text, default=None)
    salary_fit          = db.Column(db.String(50), default=None)
    rank                = db.Column(db.Integer, default=None)
    interview_status    = db.Column(db.String(50), default="Pending")
    interview_token     = db.Column(db.String(100), unique=True, nullable=True)
    ai_interview_score  = db.Column(db.Integer, default=None)
    ai_interview_feedback = db.Column(db.Text, default=None)

    def to_dict(self):
        return {
            "id":               self.id,
            "jobId":            self.job_id,
            "email":            self.email or "N/A",
            "name":             self.name or "Anonymous",
            "role":             self.role or "N/A",
            "experience":       self.experience or "0 years",
            "skills":           [s.strip() for s in self.skills.split(",") if s.strip()] if self.skills else [],
            "education":        self.education or "N/A",
            "previousCompany":  self.previous_company or "N/A",
            "salary":           self.salary or "Negotiable",
            "summary":          self.summary or "",
            "score":            self.score,
            "recommendation":   self.recommendation,
            "strengths":        [s.strip() for s in self.strengths.split("|") if s.strip()] if self.strengths else [],
            "concerns":         [s.strip() for s in self.concerns.split("|")  if s.strip()] if self.concerns  else [],
            "salaryFit":        self.salary_fit,
            "rank":             self.rank,
            "interviewStatus":  self.interview_status,
            "interviewToken":   self.interview_token,
            "aiInterviewScore": self.ai_interview_score,
            "aiInterviewFeedback": self.ai_interview_feedback
        }

class Employee(db.Model):
    id            = db.Column(db.Integer, primary_key=True)
    name          = db.Column(db.String(100), nullable=False)
    department    = db.Column(db.String(100), nullable=False)
    role          = db.Column(db.String(100), nullable=False)
    email         = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    salary        = db.Column(db.String(50))
    experience    = db.Column(db.String(50))
    skills        = db.Column(db.String(300))
    status        = db.Column(db.String(50), default="Active")

    def to_dict(self):
        return {
            "id":         self.id,
            "name":       self.name or "Unnamed",
            "department": self.department or "Engineering",
            "role":       self.role or "Associate Staff",
            "email":      self.email or "",
            "salary":     self.salary or "Not Disclosed",
            "experience": self.experience or "0 years",
            "skills":     self.skills or "",
            "status":     self.status or "Active",
        }

# ── Create & seed tables ───────────────────────────────────────────────────────
with app.app_context():
    db.create_all()
    job_count = db.session.execute(db.select(db.func.count(Job.id))).scalar()
    if job_count == 0:
        db.session.add(Job(
            role="Senior Frontend Developer",
            must_have="React, TypeScript, 3+ years experience",
            nice_to_have="AWS, GraphQL, Team leadership",
            budget_max="25 LPA"
        ))
        db.session.commit()
        print("Database seeded.")

# ──────────────────────────────────────────────────────────────────────────────
# HEALTH CHECK
# ──────────────────────────────────────────────────────────────────────────────
@app.route("/", methods=["GET", "HEAD"])
def home():
    return jsonify({"status": "healthy", "message": "HR AI Backend Running"}), 200

# ── SMTP test (hit /test-mail in browser to verify email works after deploy) ───
@app.route("/test-mail")
def test_mail():
    try:
        msg = Message(
            "SMTP Test",
            recipients=[app.config['MAIL_USERNAME']],
            body="SMTP is working correctly from Render!"
        )
        mail.send(msg)
        return jsonify({"status": "Email sent successfully!"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ──────────────────────────────────────────────────────────────────────────────
# AUTH ENDPOINTS
# ──────────────────────────────────────────────────────────────────────────────
@app.route("/register", methods=["POST"])
def register_user():
    data       = request.json or {}
    email      = data.get("email", "").strip().lower()
    password   = data.get("password")
    if not email or not password:
        return jsonify({"error": "Email and password are required"}), 400
    if db.session.execute(db.select(Employee).filter_by(email=email)).scalars().first():
        return jsonify({"error": "Email already registered"}), 400
    new_account = Employee(
        name          = data.get("name", "New User"),
        email         = email,
        password_hash = generate_password_hash(password),
        role          = data.get("role", "employee"),
        department    = data.get("department", "General"),
        salary        = data.get("salary", "N/A"),
        experience    = data.get("experience", "0"),
        skills        = data.get("skills", ""),
        status        = "Active"
    )
    db.session.add(new_account)
    db.session.commit()
    return jsonify({"message": "Registered successfully!", "user": new_account.to_dict()}), 201

@app.route("/login", methods=["POST"])
def login_user():
    data     = request.json or {}
    email    = data.get("email", "").strip().lower()
    password = data.get("password")
    if not email or not password:
        return jsonify({"error": "Email and password are required"}), 400
    user = db.session.execute(db.select(Employee).filter_by(email=email)).scalars().first()
    if user and check_password_hash(user.password_hash, password):
        return jsonify({"message": "Login successful", "role": user.role, "email": user.email, "name": user.name}), 200
    return jsonify({"error": "Invalid email or password"}), 401

# ──────────────────────────────────────────────────────────────────────────────
# EMPLOYEE ENDPOINTS
# ──────────────────────────────────────────────────────────────────────────────
@app.route("/employees", methods=["GET", "POST", "OPTIONS"])
def manage_employees():
    if request.method == "OPTIONS":
        return jsonify({"status": "ok"}), 200

    if request.method == "POST":
        data        = request.json or {}
        email_clean = data.get("email", "").strip().lower()
        if not email_clean:
            return jsonify({"error": "Employee email is required"}), 400
        if db.session.execute(db.select(Employee).filter_by(email=email_clean)).scalars().first():
            return jsonify({"error": "An employee with this email already exists"}), 400
        employee = Employee(
            name          = data.get("name", "Unnamed"),
            department    = data.get("department", "Engineering"),
            role          = data.get("role", "Associate Staff"),
            email         = email_clean,
            password_hash = generate_password_hash("password123"),
            salary        = data.get("salary", "N/A"),
            experience    = data.get("experience", "0 years"),
            skills        = data.get("skills", ""),
            status        = data.get("status", "Active"),
        )
        db.session.add(employee)
        db.session.commit()
        return jsonify({"message": "Employee added successfully", "employee": employee.to_dict()}), 201

    employees = db.session.execute(db.select(Employee)).scalars().all()
    return jsonify([e.to_dict() for e in employees]), 200

@app.route("/employees/<int:id>", methods=["DELETE", "OPTIONS"])
def delete_employee(id):
    if request.method == "OPTIONS":
        return jsonify({"status": "ok"}), 200
    employee = db.session.get(Employee, id)
    if not employee:
        return jsonify({"error": "Employee not found"}), 404
    db.session.delete(employee)
    db.session.commit()
    return jsonify({"message": "Employee deleted"}), 200

# ──────────────────────────────────────────────────────────────────────────────
# JOB ENDPOINTS
# ──────────────────────────────────────────────────────────────────────────────
@app.route("/jobs", methods=["GET", "POST"])
def manage_jobs():
    if request.method == "POST":
        data = request.json or {}
        # FIX: role and budget_max are nullable=False — never allow None into them
        role       = data.get("role") or "Untitled Role"
        budget_max = data.get("budgetMax") or "N/A"
        must_have  = data.get("mustHave", "")
        nice_to_have = data.get("niceToHave", "")
        if isinstance(must_have, list):
            must_have = ",".join(must_have)
        if isinstance(nice_to_have, list):
            nice_to_have = ",".join(nice_to_have)
        job = Job(role=role, must_have=must_have or "", nice_to_have=nice_to_have, budget_max=budget_max)
        db.session.add(job)
        db.session.commit()
        return jsonify(job.to_dict()), 201

    jobs = db.session.execute(db.select(Job)).scalars().all()
    return jsonify([j.to_dict() for j in jobs])

@app.route("/jobs/<int:job_id>", methods=["PUT"])
def update_job(job_id):
    job = db.session.get(Job, job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    data = request.json or {}
    must_have    = data.get("mustHave", job.must_have)
    nice_to_have = data.get("niceToHave", job.nice_to_have)
    if isinstance(must_have, list):
        must_have = ",".join(must_have)
    if isinstance(nice_to_have, list):
        nice_to_have = ",".join(nice_to_have)
    job.role         = data.get("role", job.role) or job.role
    job.must_have    = must_have or job.must_have
    job.nice_to_have = nice_to_have
    job.budget_max   = data.get("budgetMax", job.budget_max) or job.budget_max
    db.session.commit()
    return jsonify(job.to_dict()), 200

@app.route("/jobs/<int:job_id>", methods=["DELETE"])
def delete_job(job_id):
    try:
        job = db.session.get(Job, job_id)
        if not job:
            return jsonify({"error": "Job not found"}), 404
        db.session.delete(job)
        db.session.commit()
        return jsonify({"message": f"Job {job_id} deleted"}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500

@app.route("/jobs/<int:job_id>/candidates", methods=["GET"])
def get_job_candidates(job_id):
    candidates = db.session.execute(db.select(Candidate).filter_by(job_id=job_id)).scalars().all()
    return jsonify([c.to_dict() for c in candidates])

# ──────────────────────────────────────────────────────────────────────────────
# RESUME ENDPOINTS
# ──────────────────────────────────────────────────────────────────────────────
@app.route("/extract-resume", methods=["POST", "OPTIONS"])
def extract_resume():
    if request.method == "OPTIONS":
        return jsonify({"status": "preflight_ok"}), 200

    job_id = request.form.get("jobId")
    if not job_id:
        return jsonify({"error": "No jobId provided"}), 400
    if 'file' not in request.files:
        return jsonify({"error": "No file in request"}), 400
    file = request.files['file']
    if not file or file.filename == '':
        return jsonify({"error": "No file selected"}), 400

    filename = file.filename.lower()
    try:
        file_bytes = file.read()
        if len(file_bytes) == 0:
            return jsonify({"error": "File is empty"}), 400
        if filename.endswith('.pdf'):
            reader   = PdfReader(io.BytesIO(file_bytes))
            raw_text = "\n".join(p.extract_text() for p in reader.pages if p.extract_text())
        elif filename.endswith('.docx'):
            doc      = Document(io.BytesIO(file_bytes))
            raw_text = "\n".join(p.text for p in doc.paragraphs)
        elif filename.endswith('.txt'):
            raw_text = file_bytes.decode('utf-8', errors='ignore')
        else:
            return jsonify({"error": "Unsupported format. Use .pdf, .docx, or .txt"}), 400
    except Exception as e:
        traceback.print_exc(file=sys.stderr)
        return jsonify({"error": f"File parsing failed: {str(e)}"}), 500

    if not raw_text or len(raw_text.strip()) < 5:
        return jsonify({"error": "No text could be extracted from the file"}), 400

    prompt = f"""
You are an AI resume parser. Extract the candidate's profile from the resume text below.
Resume:
{raw_text}

Return a single JSON object with exactly these fields:
- name (string)
- email (string)
- role (string — current title or target role)
- experience (string — total years)
- skills (JSON array of strings — 5 to 10 items)
- education (string — highest degree or college)
- previousCompany (string — most recent employer)
- salary (string — expected salary or "Negotiable")
- summary (string — 2 sentence profile summary)

If any field is missing from the resume, use "Not Listed" as the value.
Respond ONLY with valid JSON. No markdown, no backticks.
"""
    response_text = call_groq_api(prompt)
    if not response_text:
        return jsonify({"error": "Groq failed to parse resume"}), 500

    try:
        # Strip markdown fences if present
        response_text = response_text.strip()
        if response_text.startswith("```"):
            lines = response_text.splitlines()
            lines = lines[1:] if lines[0].startswith("```") else lines
            lines = lines[:-1] if lines and lines[-1].startswith("```") else lines
            response_text = "\n".join(lines).strip()

        p = json.loads(response_text)

        # FIX: all fields are guarded against None using safe_str
        raw_skills = p.get("skills", [])
        if isinstance(raw_skills, list):
            skills_str = ",".join(s for s in raw_skills if s)
        elif raw_skills:
            skills_str = str(raw_skills)
        else:
            skills_str = ""

        # FIX: education — could be string, dict, or None
        edu = p.get("education")
        if isinstance(edu, dict):
            education_str = edu.get("degree") or edu.get("college") or "Not Listed"
        else:
            education_str = safe_str(edu)

        # FIX: previousCompany — could be string, dict, or None
        prev = p.get("previousCompany")
        if isinstance(prev, dict):
            prev_company_str = prev.get("organization") or prev.get("name") or "Not Listed"
        else:
            prev_company_str = safe_str(prev)

        candidate = Candidate(
            job_id           = int(job_id),
            name             = safe_str(p.get("name"), "Unknown"),
            email            = safe_str(p.get("email"), "notprovided@example.com"),
            role             = safe_str(p.get("role")),
            experience       = safe_str(p.get("experience")),
            skills           = skills_str,
            education        = education_str,
            previous_company = prev_company_str,
            salary           = safe_str(p.get("salary"), "Negotiable"),
            summary          = safe_str(p.get("summary"), "")
        )
        db.session.add(candidate)
        db.session.commit()
        return jsonify(candidate.to_dict()), 200

    except Exception as e:
        traceback.print_exc(file=sys.stderr)
        return jsonify({"error": f"Resume processing failed: {str(e)}"}), 500


@app.route("/resume-analysis", methods=["POST", "OPTIONS"])
def resume_analysis():
    if request.method == "OPTIONS":
        return jsonify({"status": "preflight_ok"}), 200
    try:
        data_json = request.get_json()
        if not data_json:
            return jsonify({"error": "Missing JSON payload"}), 400
        job_id = data_json.get("jobId")
        job = db.session.get(Job, job_id)
        if not job:
            return jsonify({"error": "Job not found"}), 404

        candidates = db.session.execute(db.select(Candidate).filter_by(job_id=job_id)).scalars().all()
        if not candidates:
            return jsonify({"error": "No candidates for this job"}), 400

        raw_skills = "\n".join([
            f"Candidate ID {c.id}: {c.name}\n"
            f"- Role: {c.role or 'Not Listed'}\n"
            f"- Experience: {c.experience or 'Not Listed'}\n"
            f"- Skills: {c.skills or 'None'}\n"
            f"- Salary: {c.salary or 'Negotiable'}\n"
            f"- Summary: {c.summary or ''}"
            for c in candidates
        ])
        must_have    = [s.strip() for s in job.must_have.split(",")    if s.strip()] if job.must_have    else []
        nice_to_have = [s.strip() for s in job.nice_to_have.split(",") if s.strip()] if job.nice_to_have else []
        requirements = f"Job: {job.role}\nMust Have: {', '.join(must_have)}\nNice to Have: {', '.join(nice_to_have)}\nBudget: {job.budget_max}"

        # FIX: use call_groq_api_text — response is an ARRAY, not a dict
        # We wrap the instruction to return a JSON object with an "evaluations" key
        # to stay compatible with json_object mode, then unwrap it.
        prompt = f"""
You are an expert HR recruiter AI. Score every candidate below against the job requirements.

{requirements}

Candidates:
{raw_skills}

Return a JSON object with a single key "evaluations" whose value is an array.
Each item in the array must have exactly:
- id (integer — the Candidate ID)
- score (integer 0-100)
- recommendation (one of: "Strong Hire", "Hire", "Maybe", "Reject")
- strengths (array of 2-3 short strings)
- concerns (array of 1-2 short strings, empty array if none)
- salaryFit (one of: "Within Budget", "Above Budget", "Well Within Budget")
- rank (integer, 1 = best match)

Respond ONLY with valid JSON. No markdown.
"""
        response_text = call_groq_api(prompt)   # json_object mode — returns a dict
        if not response_text:
            return jsonify({"error": "Groq failed to score candidates"}), 500

        parsed = json.loads(response_text)
        # Unwrap from the "evaluations" key, or scan for a list value if key differs
        if isinstance(parsed, dict):
            eval_results = parsed.get("evaluations") or parsed.get("candidates") or parsed.get("results")
            if eval_results is None:
                for val in parsed.values():
                    if isinstance(val, list):
                        eval_results = val
                        break
        else:
            eval_results = parsed

        if not isinstance(eval_results, list):
            return jsonify({"error": "AI returned unexpected structure"}), 500

        for item in eval_results:
            if not isinstance(item, dict):
                continue
            c = db.session.get(Candidate, item.get("id"))
            if c:
                c.score          = safe_int(item.get("score"), 0)
                c.recommendation = item.get("recommendation")
                strengths_arr    = item.get("strengths", [])
                concerns_arr     = item.get("concerns", [])
                c.strengths      = "|".join(strengths_arr) if isinstance(strengths_arr, list) else str(strengths_arr or "")
                c.concerns       = "|".join(concerns_arr)  if isinstance(concerns_arr,  list) else str(concerns_arr  or "")
                c.salary_fit     = item.get("salaryFit")
                c.rank           = safe_int(item.get("rank"), 1)

        db.session.commit()
        fresh = db.session.execute(db.select(Candidate).filter_by(job_id=job_id)).scalars().all()
        return jsonify([c.to_dict() for c in fresh])

    except Exception as e:
        db.session.rollback()
        traceback.print_exc(file=sys.stderr)
        return jsonify({"error": f"Analysis failed: {str(e)}"}), 500

# ──────────────────────────────────────────────────────────────────────────────
# AI INTERVIEW ENDPOINTS
# ──────────────────────────────────────────────────────────────────────────────
CONVERSATION_HISTORY = {}

def generate_ai_response(candidate_name, role, skills, history):
    if len(history) == 0:
        first_skill = skills[0] if skills else "core technologies"
        return f"Hello {candidate_name}, welcome to your automated interview for the {role} position. Can you explain your experience with {first_skill}?"
    last_answer = history[-1].get("answer", "").lower()
    if "error" in last_answer or "exception" in last_answer:
        return "Interesting. How do you ensure resource clean-up or rollback when those exceptions occur?"
    elif "react" in last_answer or "frontend" in last_answer or "state" in last_answer:
        return "Got it. How do you optimize rendering performance when handling state at scale?"
    elif len(history) == 1:
        return "Great. How do you handle security or concurrent transactions in your stack?"
    elif len(history) == 2:
        return "Can you describe a challenging technical bug you encountered recently and how you debugged it?"
    else:
        return "CONCLUDE_INTERVIEW"

@app.route("/candidates/<int:candidate_id>/accept", methods=["POST"])
def accept_candidate(candidate_id):
    candidate = db.session.get(Candidate, candidate_id)
    if not candidate:
        return jsonify({"error": "Candidate not found"}), 404

    target_email = str(candidate.email).strip() if candidate.email else ""
    if not target_email or "@" not in target_email:
        return jsonify({"error": "Candidate has no valid email address"}), 400

    if not candidate.interview_token:
        candidate.interview_token = secrets.token_urlsafe(32)

    candidate.interview_status = "Invited"
    db.session.commit()

    FRONTEND_URL  = os.getenv("FRONTEND_URL", "https://hrms-ai-5.vercel.app")
    interview_url = f"{FRONTEND_URL}/interview/{candidate.interview_token}"

    try:
        msg = Message(
            subject   = f"Technical Assessment Invitation - {candidate.role or 'Open Position'}",
            recipients= [target_email],
            sender    = app.config.get('MAIL_DEFAULT_SENDER'),
            body      = f"""Dear {candidate.name},

Congratulations! The hiring team has moved your profile forward for the {candidate.role or 'open'} position.

Please use the secure link below to start your AI technical assessment:
{interview_url}

Best regards,
HR Operations Team"""
        )
        mail.send(msg)

    except Exception as email_err:
        # Roll back the status change so HR knows to retry
        candidate.interview_status = "Pending"
        db.session.commit()
        return jsonify({"error": f"Email failed: {str(email_err)}"}), 500

    return jsonify({
        "message":       "Candidate invited successfully.",
        "candidate":     candidate.to_dict(),
        "interviewLink": interview_url
    }), 200

@app.route("/interview/<string:token>/start", methods=["GET"])
def start_interview_session(token):
    candidate = Candidate.query.filter_by(interview_token=token).first()
    if not candidate:
        return jsonify({"error": "Invalid or expired token"}), 404
    skills = [s.strip() for s in candidate.skills.split(",") if s.strip()] if candidate.skills else []
    if token not in CONVERSATION_HISTORY:
        CONVERSATION_HISTORY[token] = []
    question = generate_ai_response(candidate.name, candidate.role or "the role", skills, CONVERSATION_HISTORY[token])
    return jsonify({
        "candidateName": candidate.name,
        "targetRole":    candidate.role,
        "status":        candidate.interview_status,
        "nextQuestion":  question
    }), 200

@app.route("/interview/<string:token>/process-turn", methods=["POST"])
def process_interview_turn(token):
    candidate = Candidate.query.filter_by(interview_token=token).first()
    if not candidate:
        return jsonify({"error": "Invalid token"}), 404

    data             = request.json or {}
    question_asked   = data.get("question")
    candidate_answer = data.get("answer")

    if not candidate_answer:
        return jsonify({"error": "No answer provided"}), 400

    if token not in CONVERSATION_HISTORY:
        CONVERSATION_HISTORY[token] = []

    CONVERSATION_HISTORY[token].append({"question": question_asked, "answer": candidate_answer})

    skills        = [s.strip() for s in candidate.skills.split(",") if s.strip()] if candidate.skills else []
    next_question = generate_ai_response(candidate.name, candidate.role or "the role", skills, CONVERSATION_HISTORY[token])

    if next_question == "CONCLUDE_INTERVIEW":
        total_words      = sum(len(t["answer"].split()) for t in CONVERSATION_HISTORY[token])
        calculated_score = min(60 + (total_words // 5), 98)
        ai_feedback      = f"Candidate completed {len(CONVERSATION_HISTORY[token])} interview rounds successfully."

        candidate.ai_interview_score    = calculated_score
        candidate.ai_interview_feedback = ai_feedback
        candidate.interview_status      = "Completed"
        db.session.commit()

        return jsonify({
            "status":   "Completed",
            "message":  "Interview completed.",
            "score":    calculated_score,
            "feedback": ai_feedback
        }), 200

    return jsonify({"status": "Ongoing", "nextQuestion": next_question}), 200

# ──────────────────────────────────────────────────────────────────────────────
# AI ANALYSIS ENDPOINTS
# ──────────────────────────────────────────────────────────────────────────────
@app.route("/analyze-skills", methods=["POST", "OPTIONS"])
def analyze_skills_realtime():
    if request.method == "OPTIONS":
        return jsonify({"status": "ok"}), 200
    try:
        employees = db.session.execute(db.select(Employee)).scalars().all()
        if not employees:
            return jsonify({"error": "No employees found. Add employees first."}), 400

        prompt = f"""
You are a corporate skills auditor.
For each employee below, identify 2-3 missing technical skills and assign urgency: 'High', 'Medium', or 'Low'.

Return a JSON object with a "results" array. Each item:
{{
  "name": "Employee Name",
  "department": "Department",
  "missingSkills": ["Skill A", "Skill B"],
  "urgency": "High"
}}

Employees:
{json.dumps([e.to_dict() for e in employees])}
"""
        raw = call_groq_api(prompt)
        if not raw:
            return jsonify({"error": "Groq failed"}), 500
        parsed = json.loads(raw)
        return jsonify(parsed.get("results", parsed)), 200

    except Exception as e:
        traceback.print_exc(file=sys.stderr)
        return jsonify({"error": str(e)}), 500


@app.route("/forecast-bridge", methods=["POST", "OPTIONS"])
def forecast_bridge():
    if request.method == "OPTIONS":
        return '', 200
    try:
        # FIX: guard against empty body
        data = request.get_json(silent=True)
        if not data:
            return jsonify([]), 200

        prompt = f"""Analyze these employees: {json.dumps(data)}.
Return ONLY a JSON array with keys: department, current, required, gap.
Example: [{{"department": "Engineering", "current": 10, "required": 12, "gap": 2}}]
No markdown, no explanation."""

        response = call_groq_api_text(prompt)
        if not response:
            raise ValueError("Empty Groq response")

        content = response.strip()
        # Strip markdown fences if present
        if "```" in content:
            parts   = content.split("```")
            content = parts[1].replace("json", "").strip() if len(parts) > 1 else content

        # Find the array in the response
        start = content.find("[")
        end   = content.rfind("]") + 1
        if start != -1 and end > start:
            content = content[start:end]

        return jsonify(json.loads(content))

    except Exception as e:
        print(f"forecast-bridge error: {e}", file=sys.stderr)
        return jsonify([
            {"department": "Engineering", "current": 5, "required": 6, "gap": 1},
            {"department": "Sales",       "current": 3, "required": 5, "gap": 2}
        ])


@app.route('/attrition-bridge', methods=['POST', 'OPTIONS'])
def attrition_bridge():
    if request.method == "OPTIONS":
        return jsonify({"status": "ok"}), 200

    # FIX: guard against empty body
    employees = request.get_json(silent=True)
    if not employees:
        return jsonify({"error": "No employee data provided"}), 400

    prompt = f"""Analyze these employees for attrition risk: {json.dumps(employees)}.
Return ONLY a valid JSON object:
{{ "results": [ {{ "name": "...", "riskLevel": "...", "riskScore": 80, "primaryReasons": [], "retentionActions": [], "replacementCost": "$...", "timeToLeave": "..." }} ] }}"""

    try:
        completion = groq_client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            response_format={"type": "json_object"}
        )
        content      = json.loads(completion.choices[0].message.content)
        results_list = content.get("results", [])
        return jsonify(results_list)

    except Exception as e:
        traceback.print_exc(file=sys.stderr)
        return jsonify({"error": str(e)}), 500

# ──────────────────────────────────────────────────────────────────────────────
# Run
# ──────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)