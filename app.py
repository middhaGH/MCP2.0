import logging
from logging.handlers import RotatingFileHandler
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, Response
from flask_sqlalchemy import SQLAlchemy
import os
import pandas as pd
from werkzeug.utils import secure_filename
import openpyxl
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import or_
import openai, sys  # Import OpenAI library
from dotenv import load_dotenv
from flask_migrate import Migrate
from openai import OpenAI

# Load environment variables from .env file
load_dotenv()

# Set your OpenAI API key from the .env file
openai.api_key = os.getenv("OPENAI_API_KEY")

# Configure logging with rotating file handler
handler = RotatingFileHandler('app.log', maxBytes=10000000, backupCount=5)
handler.setFormatter(logging.Formatter(
    '[%(asctime)s] %(levelname)s in %(module)s: %(message)s'
))
logging.basicConfig(
    level=logging.DEBUG,
    handlers=[handler]
)

# Add logger to Flask app
app = Flask("Career Crafter")
app.logger.addHandler(handler)

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///jobs.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = 'uploads'
app.secret_key = 'your_secret_key_here'

# Ensure the upload folder exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

db = SQLAlchemy(app)

# Initialize Flask-Migrate
migrate = Migrate(app, db)

class Job(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    company = db.Column(db.String(100), nullable=False)
    position = db.Column(db.String(200), nullable=False)
    resume_used = db.Column(db.String(200))
    date_applied = db.Column(db.String(20))
    status = db.Column(db.String(50))
    interview_details = db.Column(db.Text)
    comments = db.Column(db.Text)
    link = db.Column(db.String(300))
    job_description = db.Column(db.Text)  # New field for job description

    def __repr__(self):
        return f"<Job {self.company} - {self.position}>"

# Add logging to track application flow
logging.info("Starting Flask application")

@app.route('/')
def index():
    return redirect('/jobs')

@app.route('/jobs', methods=['GET', 'POST'])
def jobs():
    try:
        if request.method == 'POST':
            app.logger.info("Received POST request to add a new job", extra={
                'company': request.form['company'],
                'position': request.form['position']
            })
            new_job = Job(
                company=request.form['company'],
                position=request.form['position'],
                resume_used=request.form.get('resume_used'),
                date_applied=request.form.get('date_applied'),
                status=request.form.get('status'),
                interview_details=request.form.get('interview_details'),
                comments=request.form.get('comments'),
                link=request.form.get('link')
            )
            db.session.add(new_job)
            db.session.commit()
            app.logger.info("Successfully added new job", extra={
                'job_id': new_job.id,
                'company': new_job.company,
                'position': new_job.position
            })
            return redirect(url_for('jobs'))

        app.logger.debug("Fetching jobs from database")
        search_query = request.args.get('search', '').strip()
        if search_query:
            filter_cond = or_(
                Job.company.ilike(f"%{search_query}%"),
                Job.position.ilike(f"%{search_query}%"),
                Job.status.ilike(f"%{search_query}%")
            )
            jobs_list = Job.query.filter(filter_cond).all()
            app.logger.info(f"Retrieved {len(jobs_list)} jobs matching search '{search_query}'", extra={'search_query': search_query})
        else:
            jobs_list = Job.query.all()
            app.logger.info("Retrieved all jobs from database", extra={'job_count': len(jobs_list)})
        
        # Compute counts for Applied, Rejected, Interviewing
        applied_count = Job.query.filter_by(status='Applied').count()
        rejected_count = Job.query.filter_by(status='Rejected').count()
        interviewing_count = Job.query.filter_by(status='Interviewing').count()
        return render_template('jobs.html', jobs=jobs_list, search_query=search_query,
                               applied_count=applied_count,
                               rejected_count=rejected_count,
                               interviewing_count=interviewing_count)
    except SQLAlchemyError as e:
        app.logger.error("Database error in jobs route", exc_info=True, extra={
            'error': str(e)
        })
        flash(f"Database error: {e}")
        return render_template('jobs.html', jobs=[], search_query='',
                               applied_count=0, rejected_count=0, interviewing_count=0)

@app.route('/edit_job/<int:job_id>', methods=['GET', 'POST'])
def edit_job(job_id):
    job = Job.query.get_or_404(job_id)
    app.logger.info("Accessing job for edit", extra={
        'job_id': job_id,
        'company': job.company,
        'position': job.position
    })

    if request.method == 'POST':
        app.logger.info("Updating job details", extra={
            'job_id': job_id,
            'old_status': job.status,
            'new_status': request.form.get('status')
        })
        
        # Update the job details
        job.company = request.form['company']
        job.position = request.form['position']
        job.resume_used = request.form.get('resume_used')
        job.date_applied = request.form.get('date_applied')
        job.status = request.form.get('status')
        job.interview_details = request.form.get('interview_details')
        job.comments = request.form.get('comments')
        job.link = request.form.get('link')
        job.job_description = request.form.get('job_description')

        try:
            db.session.commit()
            app.logger.info("Successfully updated job", extra={
                'job_id': job_id,
                'company': job.company
            })
            
            if job.job_description:
                app.logger.debug("Generating interview plan")
                interview_plan = generate_interview_plan(job.job_description)
                flash(f"Interview Plan: {interview_plan}")

            return redirect(url_for('jobs'))
        except SQLAlchemyError as e:
            app.logger.error("Failed to update job", exc_info=True, extra={
                'job_id': job_id,
                'error': str(e)
            })
            flash(f"Error updating job: {e}")
            db.session.rollback()

    return render_template('jobs.html', jobs=Job.query.all(), edit_job=job)

# Function to generate an interview plan using OpenAI's GPT model
def generate_interview_plan(job_description):
    import os, sys
    from openai import OpenAI

    # Sanity check
    print("Python exe:", sys.executable)
    import openai as _oa
    print("OpenAI version:", _oa.__version__)
    print("OpenAI path:", _oa.__file__)

    # Instantiate the client
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": f"Create an interview plan for the following job description. Highlight key skills and requirements:\n{job_description}"},
            ],
            max_tokens=150
        )

        # Extract and return the generated text
        return resp.choices[0].message.content.strip()

    except Exception as e:
        # This will catch everything, including rate‑limit/quota errors
        print(f"Error ({type(e).__name__}): {e}")
        # Optionally, if it’s a JSON‑style API error you can introspect:
        try:
            err = e.error if hasattr(e, "error") else None
            print("Error details:", err)
        except:
            pass
        return "Error generating interview plan. Please try again later."

@app.route('/delete_job/<int:job_id>', methods=['POST'])
def delete_job(job_id):
    job = Job.query.get_or_404(job_id)
    app.logger.info("Deleting job", extra={
        'job_id': job_id,
        'company': job.company,
        'position': job.position
    })
    
    try:
        db.session.delete(job)
        db.session.commit()
        app.logger.info("Successfully deleted job", extra={
            'job_id': job_id
        })
    except SQLAlchemyError as e:
        app.logger.error("Failed to delete job", exc_info=True, extra={
            'job_id': job_id,
            'error': str(e)
        })
        db.session.rollback()
        flash(f"Error deleting job: {e}")
        
    return redirect(url_for('jobs'))

@app.route('/upload', methods=['POST'])
def upload():
    logging.info("Received file upload request")
    if 'file' not in request.files:
        logging.warning("No file part in the request")
        flash('No file part in the request')
        return redirect(url_for('jobs'))

    file = request.files['file']

    if file.filename == '':
        logging.warning("No file selected for upload")
        flash('No selected file')
        return redirect(url_for('jobs'))

    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        logging.info(f"File saved to {filepath}")

        try:
            if filename.endswith('.csv'):
                data = pd.read_csv(filepath)
            else:
                data = pd.read_excel(filepath)

            logging.info("Validating column headers")
            required_columns = {'company', 'position', 'resume used', 'date applied', 'status', 'interview details', 'comments', 'link'}
            file_columns = set(data.columns.str.strip().str.lower())

            if not required_columns.issubset(file_columns):
                missing_columns = required_columns - file_columns
                logging.warning(f"Missing required columns: {missing_columns}")
                flash(f"Missing required columns: {missing_columns}")
                return redirect(url_for('jobs'))

            logging.info("Normalizing column names and processing rows")
            data.columns = data.columns.str.strip().str.lower()

            # Handle column renaming and ignore unnecessary columns
            column_mapping = {
                'compay applied': 'company',
                'position applied': 'position',
                'resume used': 'resume used',
                'date applied': 'date applied',
                'status': 'status',
                'interview details': 'interview details',
                'comments': 'comments',
                'link': 'link'
            }
            data.rename(columns=column_mapping, inplace=True)

            # Drop unnecessary columns
            data = data[[col for col in column_mapping.values() if col in data.columns]]

            for _, row in data.iterrows():
                new_job = Job(
                    company=row.get('company', ''),
                    position=row.get('position', ''),
                    resume_used=row.get('resume used', ''),
                    date_applied=row.get('date applied', ''),
                    status=row.get('status', ''),
                    interview_details=row.get('interview details', ''),
                    comments=row.get('comments', ''),
                    link=row.get('link', '')
                )
                db.session.add(new_job)
                logging.info(f"Added job from file: {new_job}")

            db.session.commit()
            logging.info("File processed and data committed to the database")
            flash('File uploaded and data imported successfully!')
            return redirect(url_for('jobs'))
        except Exception as e:
            logging.error(f"Error processing file: {e}")
            flash(f"Error processing file: {e}")

    return redirect(url_for('jobs'))

@app.route('/validate_columns', methods=['GET'])
def validate_columns():
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], 'JobApplications.xlsx')

    if not os.path.exists(filepath):
        return "Excel file not found.", 404

    # Read column names from the Excel sheet
    workbook = openpyxl.load_workbook(filepath)
    sheet = workbook.active
    excel_columns = [cell.value.strip().lower() for cell in sheet[1] if cell.value]

    # Define expected column names from the database
    expected_columns = {'company', 'position', 'resume used', 'date applied', 'status', 'interview details', 'comments', 'link'}

    # Compare columns
    missing_columns = expected_columns - set(excel_columns)
    extra_columns = set(excel_columns) - expected_columns

    if missing_columns or extra_columns:
        return f"Missing columns: {missing_columns}, Extra columns: {extra_columns}", 400

    return "Column names are aligned.", 200

@app.route('/api/chat', methods=['POST'])
def api_chat():
    logging.info("[PrepMe] Received chat request")
    data = request.get_json() or {}
    user_msg = data.get('message', '').strip()
    
    logging.info(f"[PrepMe] User message: {user_msg}")
    
    if not user_msg:
        logging.warning("[PrepMe] Empty message received")
        return jsonify(response="Please type something!")

    try:
        # You can preload system/context messages here as needed
        messages = [
            {"role": "system", "content": "You are a helpful career coach."},
            {"role": "user", "content": user_msg}
        ]

        logging.info("[PrepMe] Calling OpenAI API")
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        
        chat = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            max_tokens=150
        )
        reply = chat.choices[0].message.content.strip()
        logging.info(f"[PrepMe] OpenAI response: {reply}")
        
        return jsonify(response=reply)
        
    except Exception as e:
        error_msg = f"Error: {str(e)}"
        logging.error(f"[PrepMe] Chat error: {error_msg}")
        return jsonify(response=error_msg)

@app.route('/prepme/<int:job_id>', methods=['GET'])
def prepme(job_id):
    job = Job.query.get_or_404(job_id)

    # Load the resume from the uploads directory
    resume_path = os.path.join(app.config['UPLOAD_FOLDER'], 'resume.docx')
    resume_content = ""
    if os.path.exists(resume_path):
        import docx
        doc = docx.Document(resume_path)
        resume_content = "\n".join([paragraph.text for paragraph in doc.paragraphs])

    # Initial context for the chatbot
    initial_context = f"Job Description:\n{job.job_description}\n\nResume:\n{resume_content}"

    # Generate initial LLM response
    try:
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        #logging.info(f"Initial context for OpenAI API: {initial_context}")
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a career coach."},
                {"role": "user", "content": f"Based on the following context, provide an initial response to help the user prepare for this job:\n{initial_context}"},
            ],
            max_tokens=150
        )
        initial_response = response.choices[0].message.content.strip()
    except Exception as e:
        logging.error(f"Error generating response from OpenAI API: {e}")
        initial_response = "Error generating response. Please try again later."

    return render_template('prepme.html', job=job, initial_context=initial_context, initial_response=initial_response)

# Endpoint to download jobs as CSV
@app.route('/download')
def download_jobs():
    search_query = request.args.get('search', '').strip()
    if search_query:
        filter_cond = or_(
            Job.company.ilike(f"%{search_query}%"),
            Job.position.ilike(f"%{search_query}%"),
            Job.status.ilike(f"%{search_query}%")
        )
        jobs_list = Job.query.filter(filter_cond).all()
    else:
        jobs_list = Job.query.all()
    # Prepare data for CSV
    data = [
        {'Company': job.company,
         'Position': job.position,
         'Resume Used': job.resume_used,
         'Date Applied': job.date_applied,
         'Status': job.status,
         'Interview Details': job.interview_details,
         'Comments': job.comments,
         'Link': job.link,
         'Job Description': job.job_description}
        for job in jobs_list
    ]
    df = pd.DataFrame(data)
    csv_data = df.to_csv(index=False)
    return Response(
        csv_data,
        mimetype='text/csv',
        headers={"Content-Disposition": "attachment;filename=jobs.csv"}
    )

# Helper function to check allowed file extensions
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in {'csv', 'xlsx'}

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)