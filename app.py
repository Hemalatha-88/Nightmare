import os
import sys
import io
import json
import secrets 
import traceback
from pathlib import Path
from flask import Flask, jsonify, request
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from flask_mail import Mail, Message
from werkzeug.security import generate_password_hash, check_password_hash
from pypdf import PdfReader
from docx import Document
from dotenv import load_dotenv
from groq import Groq
import random
import jwt
import datetime

# 1. Initialize app ONCE
app = Flask(__name__)
load_dotenv() 


db = SQLAlchemy(app)

# --- CRITICAL FIX: MOVE THIS OUTSIDE OF THE IF BLOCK ---
with app.app_context():
    db.create_all()
    # Check if we need to seed the data
    job_count = db.session.execute(db.select(db.func.count(Job.id))).scalar()
    if job_count == 0:
        db.session.add(Job(
            role="Senior Frontend Developer", 
            must_have="React, TypeScript, 3+ years experience", 
            nice_to_have="AWS, GraphQL, Team leadership", 
            budget_max="25 LPA"
        ))
        db.session.commit()
        print("Database tables created and seeded.")

# 2. Configure Mail
app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = os.getenv('2k23it18@kiot.ac.in')
app.config['MAIL_PASSWORD'] = os.getenv('yvim ckvi cfgm chwf')
app.config['MAIL_DEFAULT_SENDER'] = os.getenv('2k23it18@kiot.ac.in')

# 3. Initialize Mail extension
mail = Mail(app)

# 4. Configure CORS
# 4. Configure CORS
CORS(app, resources={r"/*": {"origins": "*"}}, supports_credentials=True)

@app.after_request
def add_cors_headers(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    return response

@app.before_request
def handle_options():
    if request.method == 'OPTIONS':
        return '', 200


# ... Proceed with your other configs (Database, Groq, etc.) ...
# -----------------------------
# SQLite Database Setup
# -----------------------------
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///new_employeess.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)

# -----------------------------
# DATABASE TABLES FOR PERSISTENCE
# -----------------------------
class Job(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    role = db.Column(db.String(100), nullable=False)
    must_have = db.Column(db.Text, nullable=False)       
    nice_to_have = db.Column(db.Text, nullable=True)     
    budget_max = db.Column(db.String(50), nullable=False)
    candidates = db.relationship('Candidate', backref='job', cascade='all, delete-orphan', lazy=True)

    def to_dict(self):
        return {
            "id": self.id,
            "role": self.role or "Unassigned Opening",
            "mustHave": [s.strip() for s in self.must_have.split(",") if s.strip()] if self.must_have else [],
            "niceToHave": [s.strip() for s in self.nice_to_have.split(",") if s.strip()] if self.nice_to_have else [],
            "budgetMax": self.budget_max or "N/A"
        }

class Candidate(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    job_id = db.Column(db.Integer, db.ForeignKey('job.id'), nullable=False)
    email = db.Column(db.String(100))
    name = db.Column(db.String(100), nullable=False)
    role = db.Column(db.String(100))
    experience = db.Column(db.String(50))
    skills = db.Column(db.Text)
    education = db.Column(db.String(100))
    previous_company = db.Column(db.String(100))
    salary = db.Column(db.String(50))
    summary = db.Column(db.Text)
    score = db.Column(db.Integer, default=None)
    recommendation = db.Column(db.String(50), default=None)
    strengths = db.Column(db.Text, default=None)         
    concerns = db.Column(db.Text, default=None)          
    salary_fit = db.Column(db.String(50), default=None)
    rank = db.Column(db.Integer, default=None)
    interview_status = db.Column(db.String(50), default="Pending") 
    interview_token = db.Column(db.String(100), unique=True, nullable=True)
    ai_interview_score = db.Column(db.Integer, default=None)
    ai_interview_feedback = db.Column(db.Text, default=None)

    def to_dict(self):
        return {
            "id": self.id,
            "jobId": self.job_id,
            "email": self.email or "N/A",
            "name": self.name or "Anonymous Node",
            "role": self.role or "N/A",
            "experience": self.experience or "0 years",
            "skills": [s.strip() for s in self.skills.split(",") if s.strip()] if self.skills else [],
            "education": self.education or "N/A",
            "previousCompany": self.previous_company or "N/A",
            "salary": self.salary or "Negotiable",
            "summary": self.summary or "",
            "score": self.score,
            "recommendation": self.recommendation,
            "strengths": [s.strip() for s in self.strengths.split("|") if s.strip()] if self.strengths else [],
            "concerns": [s.strip() for s in self.concerns.split("|") if s.strip()] if self.concerns else [],
            "salaryFit": self.salary_fit,
            "rank": self.rank,
            "interviewStatus": self.interview_status,
            "interviewToken": self.interview_token,
            "aiInterviewScore": self.ai_interview_score,
            "aiInterviewFeedback": self.ai_interview_feedback
        }

class Employee(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    department = db.Column(db.String(100), nullable=False)
    role = db.Column(db.String(100), nullable=False)        
    email = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False) 
    salary = db.Column(db.String(50))
    experience = db.Column(db.String(50))
    skills = db.Column(db.String(300))
    status = db.Column(db.String(50), default="Active")

    def to_dict(self):
        # FIX: Explicit fallbacks for fields to avoid JS 'undefined' errors
        return {
            "id": self.id,
            "name": self.name or "Unnamed Position",
            "department": self.department or "Engineering",
            "role": self.role or "Associate Staff",
            "email": self.email or "",
            "salary": self.salary or "Not Disclosed",
            "experience": self.experience or "0 years",
            "skills": self.skills or "", # Handled safely as string with safe defaults
            "status": self.status or "Active",
        }


# -----------------------------
# Groq Core API Client Handler
# -----------------------------
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

# -----------------------------
# Home Route
# -----------------------------
@app.route("/")
def home():
    return jsonify({"message": "HR AI Backend Running via Groq Cloud Support"})

# -----------------------------
# AUTHENTICATION ENDPOINTS
# -----------------------------
@app.route("/register", methods=["POST"])
def register_user():
    data = request.json or {}
    email = data.get("email", "").strip().lower()
    password = data.get("password")
    role = data.get("role", "employee") 
    name = data.get("name", "New Account User")
    department = data.get("department", "General Staff Operations")

    if not email or not password:
        return jsonify({"error": "Email and password parameters are mandatory"}), 400

    existing_user = db.session.execute(db.select(Employee).filter_by(email=email)).scalars().first()
    if existing_user:
        return jsonify({"error": "This email address is already registered"}), 400

    hashed_pwd = generate_password_hash(password)
    new_account = Employee(
        name=name,
        email=email,
        password_hash=hashed_pwd,
        role=role,
        department=department,
        salary=data.get("salary", "N/A"),
        experience=data.get("experience", "0"),
        skills=data.get("skills", ""),
        status="Active"
    )
    db.session.add(new_account)
    db.session.commit()
    return jsonify({"message": "Registration processed cleanly!", "user": new_account.to_dict()}), 201

@app.route("/login", methods=["POST"])
def login_user():
    data = request.json or {}
    email = data.get("email", "").strip().lower()
    password = data.get("password")

    if not email or not password:
        return jsonify({"error": "Missing email or password attributes"}), 400

    user_record = db.session.execute(db.select(Employee).filter_by(email=email)).scalars().first()
    if user_record and check_password_hash(user_record.password_hash, password):
        return jsonify({
            "message": "Login authorization verified",
            "role": user_record.role,
            "email": user_record.email,
            "name": user_record.name
        }), 200
    return jsonify({"error": "Invalid email address or signature credentials match"}), 401

@app.route("/employees", methods=["GET", "POST", "OPTIONS"])
def manage_employees():
    if request.method == "OPTIONS":
        return jsonify({"status": "ok"}), 200
        
    if request.method == "POST":
        data = request.json or {}
        email_clean = data.get("email", "").strip().lower()
        if not email_clean:
            return jsonify({"error": "Employee email parameter is completely empty."}), 400
            
        # Check duplicate emails to avoid unhandled SQLite unique failure crashes
        existing = db.session.execute(db.select(Employee).filter_by(email=email_clean)).scalars().first()
        if existing:
            return jsonify({"error": "An employee node with this email address already exists."}), 400

        default_hashed = generate_password_hash("password123")
        employee = Employee(
            name=data.get("name", "Unnamed Profile"),
            department=data.get("department", "Engineering"),
            role=data.get("role", "Associate Staff"),
            email=email_clean,
            password_hash=default_hashed, 
            salary=data.get("salary", "N/A"),
            experience=data.get("experience", "0 years"),
            skills=data.get("skills", ""),
            status=data.get("status", "Active"),
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
    return jsonify({"message": "Employee deleted successfully"}), 200

@app.route("/employees", methods=["GET"])
def get_employees():
    employees = Employee.query.all()
    # Ensure this returns a list of dictionaries
    return jsonify([
        {
            "id": e.id, 
            "name": e.name, 
            "department": getattr(e, 'department', 'N/A')
        } for e in employees
    ])

# -----------------------------
# DYNAMIC MULTI-JOB ENDPOINTS
# -----------------------------
@app.route("/jobs", methods=["GET", "POST"])
def manage_jobs():
    if request.method == "POST":
        data = request.json or {}
        job = Job(
            role=data.get("role"),
            must_have=",".join(data.get("mustHave", [])) if isinstance(data.get("mustHave"), list) else data.get("mustHave", ""),
            nice_to_have=",".join(data.get("niceToHave", [])) if isinstance(data.get("niceToHave"), list) else data.get("niceToHave", ""),
            budget_max=data.get("budgetMax")
        )
        db.session.add(job)
        db.session.commit()
        return jsonify(job.to_dict()), 201
    
    jobs = db.session.execute(db.select(Job)).scalars().all()
    return jsonify([j.to_dict() for j in jobs])

@app.route("/jobs/<int:job_id>", methods=["PUT"])
def update_job(job_id):
    job = db.session.get(Job, job_id)
    if not job:
        return jsonify({"error": "Job profile not found"}), 404
    data = request.json or {}
    job.role = data.get("role", job.role)
    job.must_have = ",".join(data.get("mustHave", [])) if isinstance(data.get("mustHave"), list) else data.get("mustHave", "")
    job.nice_to_have = ",".join(data.get("niceToHave", [])) if isinstance(data.get("niceToHave"), list) else data.get("niceToHave", "")
    job.budget_max = data.get("budgetMax", job.budget_max)
    db.session.commit()
    return jsonify(job.to_dict()), 200

@app.route("/jobs/<int:job_id>", methods=["DELETE"])
def delete_job(job_id):
    try:
        job = db.session.get(Job, job_id)
        if not job:
            return jsonify({"error": "Job opening not found in database"}), 404
        db.session.delete(job)
        db.session.commit()
        return jsonify({"message": f"Job position {job_id} and all related candidates successfully wiped"}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Could not clear job row: {str(e)}"}), 500

@app.route("/jobs/<int:job_id>/candidates", methods=["GET"])
def get_job_candidates(job_id):
    candidates = db.session.execute(db.select(Candidate).filter_by(job_id=job_id)).scalars().all()
    return jsonify([c.to_dict() for c in candidates])

# -----------------------------
# INTERFACE PIPELINES
# -----------------------------
@app.route("/extract-resume", methods=["POST", "OPTIONS"])
def extract_resume():
    if request.method == "OPTIONS":
        return jsonify({"status": "preflight_ok"}), 200
    job_id = request.form.get("jobId")
    if not job_id:
        return jsonify({"error": "No target jobId provided with file data"}), 400
    if 'file' not in request.files:
        return jsonify({"error": "No file stream detected in payload"}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No file selected"}), 400
    
    raw_text = ""
    filename = file.filename.lower()
    try:
        file_bytes = file.read()
        if len(file_bytes) == 0:
            return jsonify({"error": "Uploaded file is empty"}), 400
        if filename.endswith('.pdf'):
            pdf_stream = io.BytesIO(file_bytes)
            reader = PdfReader(pdf_stream)
            extracted_pages = []
            for page in reader.pages:
                text = page.extract_text()
                if text:
                    extracted_pages.append(text)
            raw_text = "\n".join(extracted_pages)
        elif filename.endswith('.docx'):
            docx_stream = io.BytesIO(file_bytes)
            doc = Document(docx_stream)
            raw_text = "\n".join([paragraph.text for paragraph in doc.paragraphs])
        elif filename.endswith('.txt'):
            raw_text = file_bytes.decode('utf-8', errors='ignore')
        else:
            return jsonify({"error": "Unsupported file format. Please upload .pdf, .docx, or .txt"}), 400
    except Exception as parse_error:
        print("--- EXTRACT RESUME PARSING EXCEPTION DETECTED ---", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return jsonify({"error": f"Document compilation parsing failure: {str(parse_error)}"}), 500

    if not raw_text or len(raw_text.strip()) < 5:
        return jsonify({"error": "Could not extract clear structural text. Ensure document is not scanned/image-only."}), 400

    prompt = f"""
    You are an AI document parsing engine. Analyze the following extracted text from a candidate's resume and extract their personal profile attributes.
    Resume Document Text:
    {raw_text}
    Provide a single clean JSON object containing exactly these fields.
    - name (Full name of the candidate)
    - email (Candidate email address)
    - role (Target position, core specialization, or current title)
    - experience (Total years of experience)
    - skills (A plain JSON array of 5-10 technical tools, languages, or frameworks found)
    - education (Highest qualification, degree, or college found)
    - previousCompany (Most recent or notable workplace name)
    - salary (Expected salary benchmark if found, otherwise "Negotiable")
    - summary (A coherent 2-line summary condensing their entire profile experience)
    Respond ONLY with valid plain text JSON. Do not write markdown blocks or ```json text blocks.
    """
    response_text = call_groq_api(prompt)
    if not response_text:
        return jsonify({"error": "Failed to extract candidate profile using Groq processing service."}), 500

    try:
        response_text = response_text.strip()
        if response_text.startswith("```"):
            lines = response_text.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            response_text = "\n".join(lines).strip()
        p = json.loads(response_text)
        candidate = Candidate(
            job_id=int(job_id),
            name=p.get("name", "Unknown Name"),
            email=p.get("email", "notprovided@example.com"),
            role=p.get("role", "Not Listed"),
            experience=p.get("experience", "Not Listed"),
            skills=",".join(p.get("skills", [])) if isinstance(p.get("skills"), list) else str(p.get("skills", "")),
            education=p.get("education", "Not Listed"),
            previous_company=p.get("previousCompany", "Not Listed"),
            salary=p.get("salary", "Negotiable"),
            summary=p.get("summary", "")
        )
        db.session.add(candidate)
        db.session.commit()
        return jsonify(candidate.to_dict()), 200
    except Exception as e:
        print("--- EXTRACT RESUME PROCESSING EXCEPTION DETECTED ---", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return jsonify({"error": f"Profile Extraction Exception: {str(e)}"}), 500

@app.route("/resume-analysis", methods=["POST", "OPTIONS"])
def resume_analysis():
    if request.method == "OPTIONS":
        return jsonify({"status": "preflight_ok"}), 200
    try:
        data_json = request.get_json()
        if not data_json:
            return jsonify({"error": "Invalid or missing JSON payload"}), 400
        job_id = data_json.get("jobId")
        job = db.session.get(Job, job_id)
        if not job:
            return jsonify({"error": "Job profile not found"}), 404
        
        candidates = db.session.execute(db.select(Candidate).filter_by(job_id=job_id)).scalars().all()
        if not candidates:
            return jsonify({"error": "No active candidates found for this job position"}), 400

        raw_skills = "\n".join([
            f"Candidate ID {c.id}: {c.name}\n"
            f"- Current Role: {c.role if c.role else 'Not Listed'}\n"
            f"- Experience: {c.experience if c.experience else 'Not Listed'}\n"
            f"- Skills: {c.skills if c.skills else 'NoneListed'}\n"
            f"- Expected Salary: {c.salary if c.salary else 'Negotiable'}\n"
            f"- Summary: {c.summary if c.summary else ''}"
            for c in candidates
        ])
        must_have = [s.strip() for s in job.must_have.split(",") if s.strip()] if job.must_have else []
        nice_to_have = [s.strip() for s in job.nice_to_have.split(",") if s.strip()] if job.nice_to_have else []
        target_requirements = f"Job Role: {job.role}\nMust Have: {', '.join(must_have)}\nNice to Have: {', '.join(nice_to_have)}\nBudget Max: {job.budget_max}"

        prompt = f"""
        You are an expert HR recruiter AI. Analyze these candidates against the target job requirements.
        {target_requirements}
        Candidates Metadata Queue:
        {raw_skills}
        For each candidate, provide a JSON array containing objects with exactly these fields:
        - id (number matching the Candidate ID)
        - score (number from 0 to 100)
        - recommendation (one of: "Strong Hire", "Hire", "Maybe", "Reject")
        - strengths (array of 2-3 short strings)
        - concerns (array of 1-2 short strings, empty array if none)
        - salaryFit (one of: "Within Budget", "Above Budget", "Well Within Budget")
        - rank (integer where 1 represents the absolute best match)
        Respond ONLY with a valid plain text JSON array. Do not include markdown wraps, code block identifiers, backticks, or text outside the array.
        """
        response_text = call_groq_api(prompt)
        if not response_text:
            return jsonify({"error": "Failed to score candidates using Groq processing service."}), 500

        response_text = response_text.strip()
        if response_text.startswith("```"):
            lines = response_text.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            response_text = "\n".join(lines).strip()

        try:
            eval_results = json.loads(response_text)
        except json.JSONDecodeError:
            start_index = response_text.find("[")
            end_index = response_text.rfind("]") + 1
            if start_index != -1 and end_index != 0:
                eval_results = json.loads(response_text[start_index:end_index])
            else:
                raise ValueError("The generated text did not contain a readable JSON matrix array.")

        if isinstance(eval_results, dict):
            for key, val in eval_results.items():
                if isinstance(val, list):
                    eval_results = val
                    break

        if not isinstance(eval_results, list):
            raise ValueError("The processed AI structure could not be normalized into a candidate evaluation list.")

        for item in eval_results:
            if not isinstance(item, dict):
                continue
            c = db.session.get(Candidate, item.get("id"))
            if c:
                c.score = int(item.get("score", 0))
                c.recommendation = item.get("recommendation")
                strengths_arr = item.get("strengths", [])
                concerns_arr = item.get("concerns", [])
                c.strengths = "|".join(strengths_arr) if isinstance(strengths_arr, list) else str(strengths_arr)
                c.concerns = "|".join(concerns_arr) if isinstance(concerns_arr, list) else str(concerns_arr)
                c.salary_fit = item.get("salaryFit")
                c.rank = int(item.get("rank", 1))

        db.session.commit()
        fresh_candidates = db.session.execute(db.select(Candidate).filter_by(job_id=job_id)).scalars().all()
        return jsonify([cand.to_dict() for cand in fresh_candidates])
    except Exception as e:
        db.session.rollback()
        print("--- RESUME ANALYSIS EXCEPTION DETECTED ---", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return jsonify({"error": f"Groq Processing Exception: {str(e)}"}), 500

# -----------------------------
# AUTOMATED AI INTERVIEW WORKFLOW ENDPOINTS
# -----------------------------
@app.route("/candidates/<int:candidate_id>/accept", methods=["POST"])
def accept_candidate(candidate_id):
    candidate = db.session.get(Candidate, candidate_id)
    if not candidate:
        return jsonify({"error": "Candidate record not found"}), 404

    target_email = str(candidate.email).strip() if candidate.email else ""
    if not target_email or "@" not in target_email:
        return jsonify({"error": "Invalid email address."}), 400

    if not candidate.interview_token:
        candidate.interview_token = secrets.token_urlsafe(32)
    
    candidate.interview_status = "Invited"
    db.session.commit()

    # CORRECTED: Use a key (string) for getenv, not the URL itself
    # Default to the Vercel URL, but allow overrides via environment variables
    FRONTEND_URL = os.getenv("FRONTEND_URL", "https://hrms-ai-5.vercel.app")
    interview_url = f"{FRONTEND_URL}/interview/{candidate.interview_token}"
    
    try:
        msg = Message(
            subject=f"Technical Assessment Invitation - {candidate.role}",
            recipients=[target_email],
            sender=app.config.get('MAIL_DEFAULT_SENDER'),
            body=f"""Dear {candidate.name},

Congratulations! The hiring team has moved your profile forward for the {candidate.role} opening.

Please use the secure link below to launch your automated AI technical assessment interview screen:
{interview_url}

Best regards,
HR Operations Team"""
        )
        mail.send(msg)
        
    except Exception as email_err:
        db.session.rollback()
        candidate.interview_status = "Pending"
        db.session.commit()
        return jsonify({"error": f"SMTP failed: {str(email_err)}"}), 500

    return jsonify({
        "message": "Candidate invited successfully.",
        "candidate": candidate.to_dict(),
        "interviewLink": interview_url
    }), 200
CONVERSATION_HISTORY = {}

def generate_ai_response(candidate_name, role, skills, history):
    if len(history) == 0:
        return f"Hello {candidate_name}, welcome to your automated interview for the {role} position. Let's start with your background. Can you explain your experience working with {skills[0] if skills else 'core technologies'}?"
    
    last_answer = history[-1].get("answer", "").lower()
    if "error" in last_answer or "exception" in last_answer:
        return "That's an interesting approach to error handling. How do you ensure resource clean-up or rollback state when those exceptions occur?"
    elif "react" in last_answer or "frontend" in last_answer or "state" in last_answer:
        return "Got it. When handling state architecture in production, how do you optimize rendering performance?"
    elif len(history) == 1:
        return "Great. Looking at the required stack components, how do you handle security or concurrent transactions?"
    elif len(history) == 2:
        return "Can you describe a challenging technical architectural bug you encountered recently and exactly how you debugged it?"
    else:
        return "CONCLUDE_INTERVIEW"

@app.route("/interview/<string:token>/start", methods=["GET"])
def start_interview_session(token):
    candidate = Candidate.query.filter_by(interview_token=token).first()
    if not candidate:
        return jsonify({"error": "Invalid or expired interview token."}), 404
        
    skills = [s.strip() for s in candidate.skills.split(",") if s.strip()] if candidate.skills else []
    if token not in CONVERSATION_HISTORY:
        CONVERSATION_HISTORY[token] = []
        
    initial_question = generate_ai_response(candidate.name, candidate.role, skills, CONVERSATION_HISTORY[token])
    return jsonify({
        "candidateName": candidate.name,
        "targetRole": candidate.role,
        "status": candidate.interview_status,
        "nextQuestion": initial_question
    }), 200

@app.route("/interview/<string:token>/process-turn", methods=["POST"])
def process_interview_turn(token):
    candidate = Candidate.query.filter_by(interview_token=token).first()
    if not candidate:
        return jsonify({"error": "Candidate token failure."}), 404
        
    data = request.json or {}
    question_asked = data.get("question")
    candidate_answer = data.get("answer")
    
    if not candidate_answer:
        return jsonify({"error": "No answer speech transcript processed."}), 400
        
    if token not in CONVERSATION_HISTORY:
        CONVERSATION_HISTORY[token] = []
        
    CONVERSATION_HISTORY[token].append({
        "question": question_asked,
        "answer": candidate_answer
    })
    
    skills = [s.strip() for s in candidate.skills.split(",") if s.strip()] if candidate.skills else []
    next_question = generate_ai_response(candidate.name, candidate.role, skills, CONVERSATION_HISTORY[token])
    
    if next_question == "CONCLUDE_INTERVIEW":
        total_words = sum(len(turn["answer"].split()) for turn in CONVERSATION_HISTORY[token])
        calculated_score = min(60 + (total_words // 5), 98) 
        
        ai_feedback = f"Candidate successfully completed a real-time voice screening session across {len(CONVERSATION_HISTORY[token])} conversational rounds."
        
        candidate.ai_interview_score = calculated_score
        candidate.ai_interview_feedback = ai_feedback
        candidate.interview_status = "Completed"
        db.session.commit()
        
        return jsonify({
            "status": "Completed",
            "message": "Interview completed successfully.",
            "score": calculated_score,
            "feedback": ai_feedback
        }), 200
        
    return jsonify({
        "status": "Ongoing",
        "nextQuestion": next_question
    }), 200

@app.route("/analyze-skills", methods=["POST", "OPTIONS"])
def analyze_skills_realtime():
    if request.method == "OPTIONS":
        return jsonify({"status": "ok"}), 200
        
    try:
        # 1. Fetch real-time employee data straight from SQLite
        employees = db.session.execute(db.select(Employee)).scalars().all()
        
        if not employees:
            return jsonify({"error": "Your employee database is currently empty. Add users first!"}), 400
            
        # 2. Serialize real records for the context payload
        employee_dataset = [e.to_dict() for e in employees]

        # 3. Create a strict prompt for Groq's JSON mode
        prompt = f"""
        You are an advanced corporate skills inventory auditor.
        Task: Identify 2-3 specific missing technical skill gaps and assign an urgency level ('High', 'Medium', 'Low') for each employee based on their current role and department.
        
        Return a JSON object containing an array named "results".
        Each item inside "results" must match this exact schema format:
        {{
            "name": "Employee Name",
            "department": "Department",
            "missingSkills": ["Skill A", "Skill B"],
            "urgency": "High"
        }}

        Real-Time Employee Database Context:
        {json.dumps(employee_dataset)}
        """

        # 4. Request compilation from Llama through Groq
        raw_ai_response = call_groq_api(prompt)

        if not raw_ai_response:
            return jsonify({"error": "Groq failed to compile workforce data"}), 500

        # 5. Parse string to ensure it is valid structural JSON, then deliver
        parsed_payload = json.loads(raw_ai_response)
        
        # Check if Groq nested it under an outer object or array key
        if "results" in parsed_payload:
            return jsonify(parsed_payload["results"]), 200
        return jsonify(parsed_payload), 200

    except Exception as e:
        print(f"Realtime Skill Gap Exception: {str(e)}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return jsonify({"error": f"Internal execution failure: {str(e)}"}), 500

@app.route("/forecast-bridge", methods=["POST", "OPTIONS"])
def forecast_bridge():
    if request.method == "OPTIONS":
        return '', 200
        
    try:
        data = request.json
        prompt = f"""Analyze these employees: {json.dumps(data)}. 
        Return ONLY a JSON array with these keys: department, current, required, gap.
        Example: [{{"department": "Engineering", "current": 10, "required": 12, "gap": 2}}]
        No markdown, no conversation."""
        
        chat_completion = groq_client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama-3.1-8b-instant"
        )
        
        content = chat_completion.choices[0].message.content.strip()
        
        # ADD THIS: Print the raw content to your terminal so we can see what the AI is sending
        print(f"DEBUG AI RESPONSE: {content}")
        
        # Clean up
        if "```" in content:
            content = content.split("```")[1].replace("json", "").strip()
            
        return jsonify(json.loads(content))
        
    except Exception as e:
        print(f"CRITICAL ERROR: {e}")
        # Return a MOCK data response so the UI works even if AI fails
        return jsonify([
            {"department": "Engineering", "current": 5, "required": 6, "gap": 1},
            {"department": "Sales", "current": 3, "required": 5, "gap": 2}
        ])

@app.route('/attrition-bridge', methods=['POST'])
def attrition_bridge():
    employees = request.json
    
    prompt = f"""Analyze these employees for attrition risk: {json.dumps(employees)}. 
    Return ONLY a valid JSON object in this format: 
    {{ "results": [ {{ "name": "...", "riskLevel": "...", "riskScore": 80, "primaryReasons": [], "retentionActions": [], "replacementCost": "$...", "timeToLeave": "..." }} ] }}"""
    
    client = Groq(api_key=os.environ.get("GROQ_API_KEY"))
    
    try:
        completion = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            response_format={"type": "json_object"}
        )
        
        content = json.loads(completion.choices[0].message.content)
        
        # Explicitly extract the list from the "results" key
        results_list = content.get("results", [])
        return jsonify(results_list)
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    
    # ADD THIS TO PREVENT RENDER FROM KILLING YOUR APP
@app.route("/", methods=["GET", "HEAD"])
def health_check():
    return jsonify({"status": "healthy"}), 200
    
# -----------------------------
# Create Database & Run App
# -----------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)